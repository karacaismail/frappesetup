import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

APP = Path(__file__).resolve().parents[1] / "press_tr"


class TestSiteSetup(unittest.TestCase):
    def setUp(self):
        self.frappe = ModuleType("frappe")
        self.frappe.db = Mock()
        self.agent = ModuleType("press.agent")
        self.agent.Agent = Mock()
        upstream = ModuleType("press.press.doctype.site.site")
        upstream.Site = type("Site", (), {})
        spec = importlib.util.spec_from_file_location("site_setup", APP / "site_setup.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(
            sys.modules,
            {"frappe": self.frappe, self.agent.__name__: self.agent, upstream.__name__: upstream},
        ):
            spec.loader.exec_module(module)
        self.site = module.SetupSite()
        self.site.name = "tenant.example.test"

    def test_dispatches_after_site_is_active(self):
        self.frappe.db.get_value.side_effect = [("Active", 0, "test-server"), None]
        args = {"language": "tr", "country": "Türkiye", "currency": "TRY"}
        self.assertIs(
            self.site.complete_setup_wizard(args),
            self.agent.Agent.return_value.complete_setup_wizard.return_value,
        )
        self.agent.Agent.assert_called_once_with("test-server")
        self.agent.Agent.return_value.complete_setup_wizard.assert_called_once_with(self.site, args)

    def test_pending_and_completed_sites_do_not_dispatch(self):
        for status, completed in (("Pending", 0), ("Active", 1)):
            with self.subTest(status=status, completed=completed):
                self.frappe.db.get_value.return_value = (status, completed, "test-server")
                self.assertIsNone(self.site.complete_setup_wizard({}))
        self.agent.Agent.assert_not_called()

    def test_existing_job_prevents_duplicate_dispatch(self):
        self.frappe.db.get_value.side_effect = [("Active", 0, "test-server"), "existing-job"]
        self.assertIsNone(self.site.complete_setup_wizard({}))
        self.agent.Agent.assert_not_called()


BACKEND = Path(__file__).resolve().parents[3]
ACTIVATION_PATCH = BACKEND / "deploy/images/press-patches/0006-queue-setup-wizard.patch"
STATUS_WRITE = '\t\tfrappe.db.set_value("Site", job.site, "status", updated_status)'
PATCH_CALL = "\t\tqueue_setup_wizard(job.site, updated_status)"


def patch_function(text, name):
	"""Return the source of a function that the Press patch adds."""
	lines, inside = [], False
	for line in text.splitlines():
		if line.startswith(f"+def {name}("):
			inside = True
		elif inside and not line.startswith("+"):
			break
		if inside:
			lines.append(line[1:])
	return "\n".join(lines).rstrip() + "\n"


def load_patch_function(text, name, frappe):
	"""Write a patch function to a temporary module and import it."""
	with tempfile.TemporaryDirectory() as folder:
		path = Path(folder) / f"{name}_patch.py"
		path.write_text("import frappe\n\n" + patch_function(text, name), encoding="utf-8")
		spec = importlib.util.spec_from_file_location(f"{name}_patch", path)
		module = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"frappe": frappe}):
			spec.loader.exec_module(module)
	return getattr(module, name)


class FakePress:
	"""A Press database and Agent that record what the activation patch asks for."""

	def __init__(self, site_class, status="Active", completed=0):
		self.site_class = site_class
		self.site = {"status": status, "setup_wizard_complete": completed, "server": "f1.example.test"}
		self.site.update(name="tenant.example.test", bench="bench-1", team="team-1")
		self.team = {"user": "owner@example.test", "billing_name": "Deneme Yazılım"}
		self.user = {"full_name": "Ayşe Yılmaz", "email": "owner@example.test"}
		self.jobs = []
		self.queue = []
		self.agent_calls = []
		self.frappe = ModuleType("frappe")
		self.frappe.db = Mock()
		self.frappe.db.get_value.side_effect = self.get_value
		self.frappe.get_doc = Mock(side_effect=self.get_doc)
		self.frappe.enqueue_doc = Mock(side_effect=self.enqueue_doc)
		self.agent = Mock(side_effect=self.make_agent)

	def get_value(self, doctype, name, fields=None, for_update=False, as_dict=False):
		if doctype == "Site":
			values = [self.site[field] for field in fields]
			return values[0] if isinstance(fields, str) else tuple(values)
		if doctype == "Agent Job":
			return self.jobs[0] if self.jobs else None
		record = {"Team": self.team, "User": self.user}[doctype]
		return SimpleNamespace(**{field: record[field] for field in fields})

	def get_doc(self, doctype, name):
		site = self.site_class()
		for field, value in self.site.items():
			setattr(site, field, value)
		return site

	def enqueue_doc(self, doctype, name, method, enqueue_after_commit=False, **kwargs):
		self.queue.append((doctype, name, method, enqueue_after_commit, kwargs))

	def make_agent(self, server):
		agent = Mock()

		def complete_setup_wizard(site, args):
			self.agent_calls.append((server, site.name, args))
			self.jobs.append(f"job-{len(self.jobs) + 1}")
			return self.jobs[-1]

		agent.complete_setup_wizard.side_effect = complete_setup_wizard
		return agent

	def commit(self):
		"""Run queued jobs the way the worker does after the transaction commits."""
		queued, self.queue = self.queue, []
		for doctype, name, method, after_commit, kwargs in queued:
			if after_commit:
				getattr(self.get_doc(doctype, name), method)(**kwargs)


class TestSiteActivationPatch(unittest.TestCase):
	def setUp(self):
		self.patch_text = ACTIVATION_PATCH.read_text(encoding="utf-8")

	def load(self, status="Active", completed=0):
		press = FakePress(None, status, completed)
		agent_module = ModuleType("press.agent")
		agent_module.Agent = press.agent
		upstream = ModuleType("press.press.doctype.site.site")
		upstream.Site = type("Site", (), {})
		spec = importlib.util.spec_from_file_location("site_setup_activation", APP / "site_setup.py")
		module = importlib.util.module_from_spec(spec)
		with patch.dict(
			sys.modules,
			{"frappe": press.frappe, agent_module.__name__: agent_module, upstream.__name__: upstream},
		):
			spec.loader.exec_module(module)
		press.site_class = module.SetupSite
		return press, load_patch_function(self.patch_text, "queue_setup_wizard", press.frappe)

	def test_active_site_sends_setup_wizard_to_the_agent_once(self):
		press, queue_setup_wizard = self.load()
		queue_setup_wizard("tenant.example.test", "Active")
		self.assertEqual(press.agent_calls, [], "The Agent call must wait for the commit")
		self.assertTrue(all(item[3] for item in press.queue), "Jobs must run after the commit")
		press.commit()
		self.assertEqual(len(press.agent_calls), 1)
		self.assertEqual(press.agent_calls[0][:2], ("f1.example.test", "tenant.example.test"))
		press.frappe.get_doc.assert_any_call("Site", "tenant.example.test")

	def test_other_statuses_never_call_the_agent(self):
		for status in ("Pending", "Installing", "Broken"):
			with self.subTest(status=status):
				press, queue_setup_wizard = self.load(status=status)
				queue_setup_wizard("tenant.example.test", status)
				press.commit()
				self.assertEqual(press.queue, [])
				self.assertEqual(press.agent_calls, [])

	def test_second_active_write_does_not_call_the_agent_again(self):
		press, queue_setup_wizard = self.load()
		queue_setup_wizard("tenant.example.test", "Active")
		press.commit()
		queue_setup_wizard("tenant.example.test", "Active")
		press.commit()
		self.assertEqual(len(press.agent_calls), 1)

	def test_completed_setup_wizard_stops_the_patch(self):
		press, queue_setup_wizard = self.load(completed=1)
		queue_setup_wizard("tenant.example.test", "Active")
		press.commit()
		self.assertEqual(press.queue, [])
		self.assertEqual(press.agent_calls, [])

	def test_setup_wizard_arguments_match_g42(self):
		press, queue_setup_wizard = self.load()
		queue_setup_wizard("tenant.example.test", "Active")
		press.commit()
		args = press.agent_calls[0][2]
		self.assertEqual(
			{key: args[key] for key in ("language", "country", "timezone", "currency")},
			{"language": "tr", "country": "Türkiye", "timezone": "Europe/Istanbul", "currency": "TRY"},
		)
		self.assertEqual(args["chart_of_accounts"], "Turkey - Chart of Accounts")
		self.assertEqual(args["enable_telemetry"], 0)
		self.assertRegex(args["fy_start_date"], r"^\d{4}-01-01$")
		self.assertEqual(args["fy_end_date"], args["fy_start_date"][:4] + "-12-31")
		self.assertEqual((args["company_name"], args["company_abbr"]), ("Deneme Yazılım", "DY"))
		self.assertEqual((args["full_name"], args["email"]), ("Ayşe Yılmaz", "owner@example.test"))

	def test_patch_runs_right_after_press_writes_the_new_status(self):
		lines = self.patch_text.splitlines()
		call = lines.index("+" + PATCH_CALL)
		self.assertIn(" " + STATUS_WRITE, lines[call - 3 : call])
		self.assertIn("process_new_site_job_update", "\n".join(lines[:call]).rsplit("@@", 1)[-1])
		self.assertEqual(self.patch_text.count("diff --git"), 1)
