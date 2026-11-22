"""Run Press's unchanged Ansible class (press/runner.py) against the pinned Ansible.

The harness replaces Frappe with an in-memory document store, so the test exercises the loader,
the playbook parsing that creates Ansible Task rows, and the callback that stores task results.
"""

import json
import subprocess
import unittest

import ansible_test_env as env

HARNESS = env.PRESS_DEV / "ansible_runner_harness.py"
PRESS_TR = env.REPO / "backend/apps/press_tr"


def run_harness(scenario, bridge):
    completed_process = subprocess.run(
        [
            env.PYTHON,
            "-I",
            str(HARNESS),
            "--press-source",
            env.PRESS_SOURCE,
            "--press-tr",
            str(PRESS_TR),
            "--scenario",
            scenario,
            "--bridge",
            bridge,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if completed_process.returncode != 0:
        raise AssertionError(completed_process.stdout + completed_process.stderr)
    return json.loads(completed_process.stdout.splitlines()[-1])


@env.requires_ansible_environment
class PressRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env.assert_interpreter_matches_pins(cls())

    def test_press_alone_cannot_even_parse_a_playbook(self):
        # Importing ansible.plugins.loader no longer installs the collection finder (ansible-core
        # 2.19+); Press never calls init_plugin_loader(). The bridge does. When this test fails,
        # Press or Ansible changed and the bridge should be reviewed.
        report = run_harness("success", bridge="off")
        self.assertIn("couldn't resolve module/action 'ansible.builtin.command'", report["exception"])
        self.assertEqual(report["tasks"], [])

    def test_bridge_delivers_task_results_to_press(self):
        report = run_harness("success", bridge="before-import")
        self.assertIsNone(report["exception"])
        play = report["play"]
        self.assertEqual(play["status"], "Success")
        self.assertEqual((play["ok"], play["failures"], play["skipped"], play["unreachable"]), (2, 0, 1, 0))
        self.assertTrue(play["start"] and play["end"])
        statuses = {task["task"]: task["status"] for task in report["tasks"]}
        self.assertEqual(
            statuses,
            {"Echo the extra variable": "Success", "Skip on condition": "Skipped", "Touch a file": "Success"},
        )
        echo = next(task for task in report["tasks"] if task["task"] == "Echo the extra variable")
        self.assertEqual(echo["output"], "hello from press")
        self.assertIn("rc", json.loads(echo["result"]))
        self.assertEqual(report["realtime_events"], 2 * len(report["tasks"]))

    def test_bridge_also_works_when_ansible_was_imported_first(self):
        # Frappe resolves the job method (importing press.runner and ansible) before before_job hooks.
        report = run_harness("success", bridge="after-import")
        self.assertEqual(report["play"]["status"], "Success")

    def test_bridge_records_a_failed_task_and_play(self):
        report = run_harness("failure", bridge="before-import")
        self.assertEqual(report["play"]["status"], "Failure")
        self.assertEqual(report["play"]["failures"], 1)
        failed = next(task for task in report["tasks"] if task["task"] == "Fail on purpose")
        self.assertEqual(failed["status"], "Failure")
        self.assertEqual(failed["exception"], "The command exited with a non-zero return code.")
        self.assertEqual(json.loads(failed["result"])["rc"], 1)

    @unittest.expectedFailure
    def test_async_tasks_still_break_on_press_side(self):
        # Press's TaskExecutor._poll_async_result patch keeps the ansible-core <= 2.20 signature.
        # None of server.yml / self_hosted.yml uses async; other Press playbooks do. Fix belongs upstream.
        report = run_harness("async", bridge="before-import")
        self.assertIsNone(report["exception"])
        self.assertEqual(report["play"]["status"], "Success")
