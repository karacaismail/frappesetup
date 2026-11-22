import ast
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from press_tr import ansible_bridge

FORWARDED = (
	"v2_playbook_on_start",
	"v2_playbook_on_task_start",
	"v2_playbook_on_stats",
	"v2_runner_on_ok",
	"v2_runner_on_failed",
	"v2_runner_on_skipped",
	"v2_runner_on_unreachable",
)


def load_plugin():
	spec = importlib.util.spec_from_file_location("press_tr_bridge_under_test", ansible_bridge.PLUGIN_FILE)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


class AnsibleBridgeTest(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(ansible_bridge, "_hook_registered", False))

	def test_activate_points_ansible_at_the_bridge_before_ansible_loads(self):
		loader = ModuleType(ansible_bridge.LOADER_MODULE)
		loader.callback_loader = Mock()
		loader.init_plugin_loader = Mock()
		constants = ModuleType("ansible.constants")
		constants.DEFAULT_STDOUT_CALLBACK = "default"
		with (
			patch.dict(os.environ, {"ANSIBLE_CALLBACK_PLUGINS": "/opt/other"}, clear=False),
			patch.object(ansible_bridge.wrapt, "register_post_import_hook") as register,
		):
			for _attempt in range(2):
				ansible_bridge.activate(method="press.x", kwargs={}, transaction_type="job")
			self.assertEqual(os.environ["ANSIBLE_STDOUT_CALLBACK"], "press_tr_bridge")
			self.assertEqual(
				os.environ["ANSIBLE_CALLBACK_PLUGINS"].split(os.pathsep),
				[str(ansible_bridge.PLUGIN_DIR), "/opt/other"],
			)
			register.assert_called_once_with(
				ansible_bridge._prepare_loaded_ansible, ansible_bridge.LOADER_MODULE
			)
			# The hook runs when press.runner later imports Ansible inside a web request.
			with patch.dict(sys.modules, {"ansible.constants": constants}):
				register.call_args.args[0](loader)
		self.assertEqual(constants.DEFAULT_STDOUT_CALLBACK, "press_tr_bridge")
		loader.callback_loader.add_directory.assert_called_once_with(str(ansible_bridge.PLUGIN_DIR))
		loader.init_plugin_loader.assert_called_once_with()

	def test_activate_reconfigures_an_already_imported_ansible(self):
		constants = ModuleType("ansible.constants")
		constants.DEFAULT_STDOUT_CALLBACK = "default"
		loader = ModuleType(ansible_bridge.LOADER_MODULE)
		loader.callback_loader = Mock()
		loader.init_plugin_loader = Mock()
		with (
			patch.dict(sys.modules, {"ansible.constants": constants, ansible_bridge.LOADER_MODULE: loader}),
			patch.dict(os.environ, {}, clear=False),
		):
			ansible_bridge.activate()
			self.assertEqual(constants.DEFAULT_STDOUT_CALLBACK, "press_tr_bridge")
			loader.callback_loader.add_directory.assert_called_once_with(str(ansible_bridge.PLUGIN_DIR))
			loader.init_plugin_loader.assert_called_once_with()

	def test_plugin_file_is_a_stdout_callback_named_like_the_setting(self):
		self.assertTrue(ansible_bridge.PLUGIN_FILE.is_file())
		self.assertEqual(ansible_bridge.PLUGIN_FILE.stem, ansible_bridge.CALLBACK_NAME)
		self.assertEqual(ansible_bridge.PLUGIN_FILE.parent, ansible_bridge.PLUGIN_DIR)
		tree = ast.parse(ansible_bridge.PLUGIN_FILE.read_text(encoding="utf-8"))
		classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
		self.assertEqual([cls.name for cls in classes], ["CallbackModule"])
		attributes = {
			node.targets[0].id: node.value.value
			for node in classes[0].body
			if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
		}
		self.assertEqual(attributes["CALLBACK_TYPE"], "stdout")
		self.assertEqual(attributes["CALLBACK_NAME"], ansible_bridge.CALLBACK_NAME)
		methods = {node.name for node in classes[0].body if isinstance(node, ast.FunctionDef)}
		self.assertTrue(set(FORWARDED) <= methods, methods)

	def test_plugin_forwards_events_to_the_running_press_callback(self):
		try:
			plugin = load_plugin()
		except ImportError as error:
			self.skipTest(f"ansible is not installed here: {error}")
		press_callback = Mock()
		runner = ModuleType("press.runner")
		runner._get_current_ansible = lambda: SimpleNamespace(callback=press_callback)
		bridge = plugin.CallbackModule()
		with patch.dict(sys.modules, {"press.runner": runner}):
			for name in FORWARDED:
				getattr(bridge, name)("positional", keyword=name)
				getattr(press_callback, name).assert_called_once_with("positional", keyword=name)
		runner._get_current_ansible = lambda: None
		with patch.dict(sys.modules, {"press.runner": runner}):
			bridge.v2_playbook_on_stats(Mock())  # no running Press play: nothing to forward
		self.assertEqual(press_callback.v2_playbook_on_stats.call_count, 1)

	def test_bridge_covers_every_event_press_handles(self):
		try:
			from press.runner import AnsibleCallback
		except ImportError as error:
			self.skipTest(f"press is not importable here: {error}")
		press_events = {
			name
			for name in vars(AnsibleCallback)
			if name.startswith("v2_") and callable(getattr(AnsibleCallback, name))
		}
		self.assertEqual(press_events, set(FORWARDED))

	def test_hooks_activate_the_bridge_for_jobs_and_requests(self):
		from press_tr import hooks

		self.assertIn("press_tr.ansible_bridge.activate", hooks.before_job)
		self.assertIn("press_tr.ansible_bridge.activate", hooks.before_request)
