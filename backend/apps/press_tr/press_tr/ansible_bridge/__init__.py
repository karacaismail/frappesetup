"""Let Press's unchanged Ansible runner work on ansible-core 2.19 and later.

Press (press/runner.py) was written for ansible-base 2.10 and relies on two behaviours that
ansible-core dropped in 2.19:

1. Importing ``ansible.plugins.loader`` no longer installs the collection finder. API users must
   call ``init_plugin_loader()``; otherwise not even ``ansible.builtin.command`` resolves.
2. ``TaskQueueManager._stdout_callback`` no longer exists. The stdout callback is loaded by name,
   so the ``AnsibleCallback`` object Press assigns never receives an event and every Ansible Play
   stays "Pending".

``activate`` fixes both from outside Press: it points Ansible at the ``press_tr_bridge`` stdout
callback plugin (which forwards each event to the Press callback of the play running in the
current thread) and initialises the plugin loader as soon as ``ansible.plugins.loader`` is
imported. Press code is not modified; only Ansible's configuration is.

``activate`` is wired to Frappe's ``before_job`` and ``before_request`` hooks. Frappe imports the
job method, and with it ``press.runner`` and Ansible, before it runs ``before_job`` hooks, so the
post-import hook fires immediately in that case and later in a web request.

For ``bench`` commands that run plays directly, export ``ANSIBLE_STDOUT_CALLBACK=press_tr_bridge``
and ``ANSIBLE_CALLBACK_PLUGINS=<this package>/callback_plugins``; the loader still needs
``init_plugin_loader()``, which those commands must call themselves.
"""

import os
import sys
import warnings
from pathlib import Path

import wrapt

CALLBACK_NAME = "press_tr_bridge"
PLUGIN_DIR = Path(__file__).resolve().parent / "callback_plugins"
PLUGIN_FILE = PLUGIN_DIR / f"{CALLBACK_NAME}.py"
LOADER_MODULE = "ansible.plugins.loader"

_hook_registered = False


def activate(**_hook_arguments) -> None:
	"""Configure Ansible for Press, whether Ansible is imported before or after this call."""
	global _hook_registered

	plugin_dir = str(PLUGIN_DIR)
	os.environ["ANSIBLE_STDOUT_CALLBACK"] = CALLBACK_NAME
	configured = [path for path in os.environ.get("ANSIBLE_CALLBACK_PLUGINS", "").split(os.pathsep) if path]
	if plugin_dir not in configured:
		os.environ["ANSIBLE_CALLBACK_PLUGINS"] = os.pathsep.join([plugin_dir, *configured])

	if not _hook_registered:
		_hook_registered = True
		wrapt.register_post_import_hook(_prepare_loaded_ansible, LOADER_MODULE)


def _prepare_loaded_ansible(loader) -> None:
	"""Runs once per process, right after ansible.plugins.loader is imported."""
	sys.modules["ansible.constants"].DEFAULT_STDOUT_CALLBACK = CALLBACK_NAME
	loader.callback_loader.add_directory(str(PLUGIN_DIR))
	with warnings.catch_warnings():
		# Only a CLI entry point would have configured the finder already; then this is a no-op.
		warnings.filterwarnings("ignore", message="AnsibleCollectionFinder has already been configured")
		loader.init_plugin_loader()
