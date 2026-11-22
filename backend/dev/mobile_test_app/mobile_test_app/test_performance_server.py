"""Verify synchronized benchmark requests reach the server concurrently."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from platform_core.mobil.tests.loopback_http import open_loopback

from . import measure_performance


class PerformanceServerTest(unittest.TestCase):
    def test_server_can_enter_two_request_handlers_at_the_same_time(self):
        handlers = Barrier(2, timeout=1)

        def application(_environ, start_response):
            try:
                handlers.wait()
            except BrokenBarrierError:
                status = "503 Service Unavailable"
            else:
                status = "200 OK"
            start_response(status, [("Content-Length", "0")])
            return [b""]

        def request(url):
            try:
                with open_loopback(Request(url), timeout=5) as response:
                    return response.status
            except HTTPError as error:
                with error:
                    return error.code

        with (
            patch.object(measure_performance, "timed_application", application),
            measure_performance.benchmark_server([]) as url,
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            self.assertEqual(list(pool.map(request, [url, url])), [200, 200])

    def test_gunicorn_reports_the_worker_that_handled_requests(self):
        def application(_environ, start_response):
            start_response("200 OK", [("Content-Length", "0")])
            return [b""]

        with (
            patch.object(measure_performance, "application", application),
            measure_performance.benchmark_server([], workers=4) as url,
            open_loopback(Request(url), timeout=5) as response,
        ):
            self.assertGreater(int(response.headers["X-Mobile-Test-Worker"]), 0)
