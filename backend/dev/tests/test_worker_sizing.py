"""G-50 worker, scheduler and queue sizing audit."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEV = Path(__file__).resolve().parents[1]
AUDIT = DEV / "worker_sizing.py"
SIZING = DEV / "worker_sizing.json"

# Expected values come from the G-50 text in src/data/requirements.json.
RELEASE_GROUP = {
    "min_gunicorn_workers": 2,
    "max_gunicorn_workers": 8,
    "min_background_workers": 2,
    "max_background_workers": 6,
    "gunicorn_threads_per_worker": 2,
    "use_rq_workerpool": 1,
    "merge_default_and_short_rq_queues": 1,
}
COMMON = {
    "scheduler_tick_interval": 60,
    "workers": {"long": {"timeout": 3000}, "reports": {}},
}


class SizingFileTest(unittest.TestCase):
    def test_file_holds_g50_starting_values(self):
        sizing = json.loads(SIZING.read_text(encoding="utf-8"))
        self.assertEqual(sizing["release_group"], RELEASE_GROUP)
        self.assertEqual(sizing["bench"], {"auto_scale_workers": 1})
        self.assertEqual(sizing["common_site_config"], COMMON)
        self.assertEqual(sizing["system_settings"], {"enable_scheduler": 1})
        self.assertEqual(sizing["gunicorn_worker_class"], "gthread")

    def test_shared_settings_follow_the_g38_bench_layer(self):
        sys.path.insert(0, str(DEV))
        try:
            import config_layers
        finally:
            sys.path.remove(str(DEV))
        sizing = json.loads(SIZING.read_text(encoding="utf-8"))
        for key in sizing["common_site_config"]:
            self.assertIn(key, config_layers.BENCH_KEYS)


class AuditCase(unittest.TestCase):
    def run_audit(self, *, common=None, release_group=None, bench=None, sites=None,
                  worker_class=None, sizing=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = [sys.executable, "-B", str(AUDIT)]
            if sizing is not None:
                (root / "sizing.json").write_text(json.dumps(sizing))
                args += ["--sizing", str(root / "sizing.json")]
            for flag, value in (
                ("--common-site-config", common),
                ("--release-group", release_group),
                ("--bench", bench),
                ("--system-settings", sites),
            ):
                if value is not None:
                    path = root / (flag.strip("-") + ".json")
                    path.write_text(json.dumps(value))
                    args += [flag, str(path)]
            if worker_class is not None:
                args += ["--gunicorn-worker-class", worker_class]
            return subprocess.run(args, capture_output=True, text=True, check=False)


class AuditTest(AuditCase):
    def test_accepts_matching_values(self):
        result = self.run_audit(
            common={**copy.deepcopy(COMMON), "mail_port": 2525},
            release_group={**RELEASE_GROUP, "name": "g1", "merge_all_rq_queues": 0},
            bench={"auto_scale_workers": 1},
            sites={"a.localhost": {"enable_scheduler": 1}},
            worker_class="gthread",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_extra_queue_is_allowed(self):
        common = copy.deepcopy(COMMON)
        common["workers"]["ai"] = {"timeout": 600}
        result = self.run_audit(common=common)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrong_release_group_value_fails(self):
        result = self.run_audit(release_group={**RELEASE_GROUP, "max_gunicorn_workers": 12})
        self.assertEqual(result.returncode, 1)
        self.assertIn("release_group: max_gunicorn_workers expected 8, found 12", result.stderr)

    def test_missing_release_group_value_fails(self):
        values = dict(RELEASE_GROUP)
        del values["use_rq_workerpool"]
        result = self.run_audit(release_group=values)
        self.assertEqual(result.returncode, 1)
        self.assertIn("release_group: use_rq_workerpool missing", result.stderr)

    def test_wrong_common_values_fail(self):
        common = {"scheduler_tick_interval": 240, "workers": {"long": {"timeout": 1500}}}
        result = self.run_audit(common=common)
        self.assertEqual(result.returncode, 1)
        self.assertIn("common_site_config: scheduler_tick_interval expected 60, found 240", result.stderr)
        self.assertIn("common_site_config: workers.long.timeout expected 3000, found 1500", result.stderr)
        self.assertIn("common_site_config: workers.reports missing", result.stderr)

    def test_common_file_must_follow_g38_layers_without_echoing_values(self):
        result = self.run_audit(common={**COMMON, "encryption_key": "fixture-secret"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("encryption_key belongs in site_config.json", result.stderr)
        self.assertNotIn("fixture-secret", result.stderr)

    def test_bench_auto_scale_off_fails(self):
        result = self.run_audit(bench={"auto_scale_workers": 0})
        self.assertEqual(result.returncode, 1)
        self.assertIn("bench: auto_scale_workers expected 1, found 0", result.stderr)

    def test_every_new_site_needs_enable_scheduler(self):
        result = self.run_audit(sites={
            "a.localhost": {"enable_scheduler": 1},
            "b.localhost": {"enable_scheduler": 0},
            "c.localhost": {},
        })
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("a.localhost", result.stderr)
        self.assertIn("b.localhost: enable_scheduler expected 1, found 0", result.stderr)
        self.assertIn("c.localhost: enable_scheduler missing", result.stderr)

    def test_site_list_must_not_be_empty(self):
        result = self.run_audit(sites={})
        self.assertEqual(result.returncode, 1)
        self.assertIn("no sites", result.stderr)

    def test_needs_at_least_one_input(self):
        result = self.run_audit()
        self.assertEqual(result.returncode, 2)

    def test_unreadable_input_fails(self):
        result = self.run_audit(release_group=["not", "an", "object"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected a JSON object", result.stderr)


class ThreadsTest(AuditCase):
    """`threads` only matters for the gthread worker (gunicorn settings)."""

    def test_threads_accepted_with_gthread(self):
        result = self.run_audit(release_group=RELEASE_GROUP, worker_class="gthread")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_threads_with_sync_worker_fails(self):
        result = self.run_audit(release_group=RELEASE_GROUP, worker_class="sync")
        self.assertEqual(result.returncode, 1)
        self.assertIn("sync worker switches to gthread", result.stderr)

    def test_threads_with_other_worker_has_no_effect(self):
        result = self.run_audit(release_group=RELEASE_GROUP, worker_class="gevent")
        self.assertEqual(result.returncode, 1)
        self.assertIn("threads has no effect on gevent workers", result.stderr)

    def test_single_thread_is_fine_with_any_worker(self):
        values = {**RELEASE_GROUP, "gunicorn_threads_per_worker": 1}
        sizing = json.loads(SIZING.read_text(encoding="utf-8"))
        sizing["release_group"]["gunicorn_threads_per_worker"] = 1
        sizing["gunicorn_worker_class"] = "sync"
        result = self.run_audit(release_group=values, worker_class="sync", sizing=sizing)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sizing_file_itself_must_pair_threads_with_gthread(self):
        sizing = json.loads(SIZING.read_text(encoding="utf-8"))
        sizing["gunicorn_worker_class"] = "sync"
        result = self.run_audit(release_group=RELEASE_GROUP, sizing=sizing)
        self.assertEqual(result.returncode, 1)
        self.assertIn("sizing: sync worker switches to gthread", result.stderr)

    def test_sizing_file_min_above_max_fails(self):
        sizing = json.loads(SIZING.read_text(encoding="utf-8"))
        sizing["release_group"]["min_background_workers"] = 7
        result = self.run_audit(release_group=sizing["release_group"], sizing=sizing)
        self.assertEqual(result.returncode, 1)
        self.assertIn("sizing: min_background_workers is above max_background_workers", result.stderr)


if __name__ == "__main__":
    unittest.main()
