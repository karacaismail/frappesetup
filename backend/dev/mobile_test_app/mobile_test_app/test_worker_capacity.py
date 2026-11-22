"""Check the capacity recommendation against every measured run."""

from unittest import TestCase

from . import measure_concurrent as benchmark


class WorkerCapacityTest(TestCase):
    def test_recommends_smallest_worker_count_whose_every_run_passes(self):
        trials = {
            12: [(True, 500), (True, 600)],
            4: [(True, 700), (True, 1100)],
            8: [(True, 850), (True, 950)],
        }
        self.assertEqual(benchmark.recommend_worker_count(trials, 1000), 8)

    def test_declines_when_all_worker_counts_fail(self):
        self.assertIsNone(benchmark.recommend_worker_count({4: [(False, 800)], 8: [(True, 1001)]}, 1000))
