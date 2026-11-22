import pytest


def assert_response(self, response):
    status = response.status_code
    body = response.get_data(as_text=True)
    # ruleid: test-raw-http-diagnostic
    self.assertEqual(status, 200, body)
    # ruleid: test-raw-http-diagnostic
    self.assertTrue(status == 200, msg=response.text)
    # ruleid: test-raw-http-diagnostic
    assert status == 200, response.content
    # ruleid: test-raw-http-diagnostic
    pytest.fail(response.text)
    # ok: test-raw-http-diagnostic
    self.assertEqual(status, 200, "Unexpected status")
    # ok: test-raw-http-diagnostic
    self.assertIn("expected", response.text)
    # ok: test-raw-http-diagnostic
    assert status == 200, status


def assert_replay(self, replay):
    # ruleid: test-raw-http-diagnostic
    self.assertEqual(replay.status_code, 200, replay.get_data(as_text=True))


def assert_error_diagnostics(self, response):
    # ruleid: test-raw-http-diagnostic
    self.assertEqual(response.status_code, 200, response.json)
    # ok: test-raw-http-diagnostic
    self.assertIn("expected", response.json)
    # ok: test-raw-http-diagnostic
    self.assertEqual(response.status_code, 200, response.json().get("exc_type"))
    # ruleid: test-raw-http-diagnostic
    self.assertEqual(response.status_code, 200, response.json().get("message"))
