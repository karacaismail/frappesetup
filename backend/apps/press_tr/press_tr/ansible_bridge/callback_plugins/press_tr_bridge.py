# Loaded by Ansible's callback plugin loader, not imported as part of press_tr.
from __future__ import annotations

from ansible.plugins.callback import CallbackBase

DOCUMENTATION = """
    name: press_tr_bridge
    type: stdout
    short_description: Forward playbook events to the Press Ansible callback
    description:
        - Press (press/runner.py) records Ansible Play and Ansible Task documents from its own
          callback object. ansible-core 2.19 stopped accepting that object directly, so this plugin
          receives the events and forwards them to the callback of the play running in this thread.
    version_added: "0.0.1"
"""


class CallbackModule(CallbackBase):
	CALLBACK_VERSION = 2.0
	CALLBACK_TYPE = "stdout"
	CALLBACK_NAME = "press_tr_bridge"

	def _forward(self, event: str, *args, **kwargs) -> None:
		from press.runner import _get_current_ansible

		running = _get_current_ansible()
		if running is not None:
			getattr(running.callback, event)(*args, **kwargs)

	def v2_playbook_on_start(self, *args, **kwargs):
		self._forward("v2_playbook_on_start", *args, **kwargs)

	def v2_playbook_on_task_start(self, *args, **kwargs):
		self._forward("v2_playbook_on_task_start", *args, **kwargs)

	def v2_playbook_on_stats(self, *args, **kwargs):
		self._forward("v2_playbook_on_stats", *args, **kwargs)

	def v2_runner_on_ok(self, *args, **kwargs):
		self._forward("v2_runner_on_ok", *args, **kwargs)

	def v2_runner_on_failed(self, *args, **kwargs):
		self._forward("v2_runner_on_failed", *args, **kwargs)

	def v2_runner_on_skipped(self, *args, **kwargs):
		self._forward("v2_runner_on_skipped", *args, **kwargs)

	def v2_runner_on_unreachable(self, *args, **kwargs):
		self._forward("v2_runner_on_unreachable", *args, **kwargs)
