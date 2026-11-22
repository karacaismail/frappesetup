"""Run Press's unchanged press/runner.py against a local target with Frappe replaced in memory.

Usage: python -I ansible_runner_harness.py --press-source <press checkout> --press-tr <press_tr app>
           --scenario success|failure|async --bridge off|before-import|after-import

The last stdout line is a JSON report of the Ansible Play and Ansible Task documents Press wrote.
"""

import argparse
import datetime
import importlib.util
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path
from types import ModuleType, SimpleNamespace

ROLE_TASKS = {
	"success": """\
- name: Echo the extra variable
  ansible.builtin.command: echo "{{ harness_message }}"
  changed_when: false
- name: Skip on condition
  ansible.builtin.debug:
    msg: never shown
  when: false
- name: Touch a file
  ansible.builtin.file:
    path: "{{ harness_file }}"
    state: touch
""",
	"failure": """\
- name: Echo the extra variable
  ansible.builtin.command: echo "{{ harness_message }}"
  changed_when: false
- name: Fail on purpose
  ansible.builtin.command: /bin/sh -c 'exit 1'
""",
	"async": """\
- name: Sleep in the background
  ansible.builtin.command: sleep 1
  async: 60
  poll: 1
""",
}


class FakeDocument:
	def __init__(self, data):
		self.__dict__.update(data)

	def get(self, key, default=None):
		return getattr(self, key, default)

	def update(self, values):
		self.__dict__.update(values)
		return self

	def insert(self):
		store = _store[self.doctype]
		self.name = f"{self.doctype.replace(' ', '-').lower()}-{len(store) + 1:04d}"
		store[self.name] = self
		return self

	def save(self):
		return self

	def as_dict(self):
		return dict(self.__dict__)


_store = {"Ansible Play": {}, "Ansible Task": {}}
_realtime_events = []


def install_fake_frappe(playbook_dir):
	frappe = ModuleType("frappe")

	class _dict(dict):
		# Like frappe._dict: a missing key reads as None instead of raising.
		def __getattr__(self, key):
			return self.get(key)

		def __setattr__(self, key, value):
			self[key] = value

	def get_doc(*args):
		if isinstance(args[0], dict):
			return FakeDocument(args[0])
		doctype, name = args
		return _store[doctype][name]

	def get_value(doctype, filters, fieldname):
		for doc in _store[doctype].values():
			if all(doc.get(key) == value for key, value in filters.items()):
				return doc.get(fieldname)
		return None

	frappe._dict = _dict
	frappe.get_doc = get_doc
	frappe.get_value = get_value
	frappe.db = SimpleNamespace(
		get_value=lambda doctype, name, fields: [_store[doctype][name].get(f) for f in fields],
		is_interface_error=lambda error: False,
		commit=lambda: None,
		connect=lambda: None,
	)
	frappe.session = _dict(user="Administrator")
	frappe.publish_realtime = lambda *args, **kwargs: _realtime_events.append((args, kwargs))
	frappe.get_app_path = lambda app, *parts: str(Path(playbook_dir).joinpath(*parts[1:]))
	frappe.enqueue_doc = lambda *args, **kwargs: None
	frappe.get_traceback = lambda **kwargs: traceback.format_exc()
	utils = ModuleType("frappe.utils")
	utils.cstr = lambda value: "" if value is None else str(value)
	utils.now_datetime = datetime.datetime.now
	model = ModuleType("frappe.model")
	document = ModuleType("frappe.model.document")
	document.Document = FakeDocument
	model.document = document
	frappe.utils = utils
	frappe.model = model
	sys.modules.update(
		{"frappe": frappe, "frappe.utils": utils, "frappe.model": model, "frappe.model.document": document}
	)


def install_fake_press_package():
	names = ("press", "press.press", "press.press.doctype", "press.press.doctype.ansible_play")
	for name in names:
		module = ModuleType(name)
		module.__path__ = []
		sys.modules[name] = module
	ansible_play = ModuleType("press.press.doctype.ansible_play.ansible_play")
	ansible_play.AnsiblePlay = FakeDocument
	sys.modules[ansible_play.__name__] = ansible_play


def load_press_runner(press_source):
	spec = importlib.util.spec_from_file_location("press.runner", Path(press_source) / "press" / "runner.py")
	module = importlib.util.module_from_spec(spec)
	sys.modules["press.runner"] = module
	spec.loader.exec_module(module)
	return module


def write_playbook(root, scenario):
	playbooks = Path(root) / "playbooks"
	tasks = playbooks / "roles" / "harness" / "tasks"
	tasks.mkdir(parents=True)
	(tasks / "main.yml").write_text(ROLE_TASKS[scenario])
	(playbooks / "harness.yml").write_text(
		"---\n- name: Harness play\n  hosts: all\n  gather_facts: false\n  roles:\n    - role: harness\n"
	)
	return playbooks


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--press-source", required=True)
	parser.add_argument("--press-tr", required=True)
	parser.add_argument("--scenario", choices=sorted(ROLE_TASKS), required=True)
	parser.add_argument("--bridge", choices=("off", "before-import", "after-import"), required=True)
	options = parser.parse_args()

	os.environ.setdefault("ANSIBLE_LOCALHOST_WARNING", "0")
	os.environ.setdefault("ANSIBLE_DEPRECATION_WARNINGS", "0")
	sys.path.insert(0, options.press_tr)
	if options.bridge == "before-import":
		from press_tr import ansible_bridge

		ansible_bridge.activate()

	with tempfile.TemporaryDirectory() as root:
		playbooks = write_playbook(root, options.scenario)
		install_fake_frappe(playbooks)
		install_fake_press_package()
		runner = load_press_runner(options.press_source)
		if options.bridge == "after-import":
			from press_tr import ansible_bridge

			ansible_bridge.activate(method="press.press.doctype.server.server.Server._setup_server")

		server = SimpleNamespace(doctype="Server", name="harness-server", ip="localhost", private_ip=None)
		server.get = lambda key, default=None: getattr(server, key, default)
		report = {"scenario": options.scenario, "bridge": options.bridge, "exception": None}
		try:
			ansible = runner.Ansible(
				server=server,
				playbook="harness.yml",
				variables={
					"ansible_connection": "local",
					"ansible_python_interpreter": sys.executable,
					"harness_message": "hello from press",
					"harness_file": str(Path(root) / "touched"),
				},
			)
			ansible.run()
		except Exception:
			report["exception"] = traceback.format_exc()

		play = next(iter(_store["Ansible Play"].values()), None)
		report["play"] = {
			key: (value.isoformat() if hasattr(value, "isoformat") else value)
			for key, value in (play.as_dict() if play else {}).items()
			if key in {"status", "ok", "failures", "skipped", "changed", "unreachable", "start", "end", "play"}
		}
		report["play"].setdefault("status", "Pending")
		report["tasks"] = [
			{
				key: task.get(key)
				for key in ("task", "role", "status", "output", "error", "exception", "result", "job_id")
			}
			for task in _store["Ansible Task"].values()
		]
		report["realtime_events"] = len(_realtime_events)
		report["realtime_progress"] = [kwargs["message"]["progress"] if "message" in kwargs else args[1]["progress"] for args, kwargs in _realtime_events]
		sys.stdout.flush()
		print(json.dumps(report))


if __name__ == "__main__":
	main()
