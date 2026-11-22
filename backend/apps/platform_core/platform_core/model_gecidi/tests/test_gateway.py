import json
import threading
import unittest
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import monotonic, sleep
from unittest.mock import patch

import requests

from platform_core.model_gecidi.adapters import Endpoint, GatewayError, complete
from platform_core.model_gecidi.routing import Candidate, candidates, on_failure

SECRET = "fixture-key"


class Handler(BaseHTTPRequestHandler):
	response = None
	status = 200

	def log_message(self, *args):
		pass

	def do_POST(self):
		self.server.paths.append(self.path)
		self.server.path = self.path
		self.server.headers = self.headers
		raw = self.rfile.read(int(self.headers["Content-Length"]))
		if self.path == "/token":
			self.server.token_request = (self.headers["Authorization"], raw)
			self.send_response(200)
			self.end_headers()
			self.wfile.write(b'{"access_token":"fixture-token"}')
			return
		self.server.body = json.loads(raw)
		sleep(self.server.header_delay)
		self.send_response(self.status)
		self.send_header("Content-Type", "application/json")
		if self.server.location:
			self.send_header("Location", self.server.location)
		if self.server.content_encoding:
			self.send_header("Content-Encoding", self.server.content_encoding)
		self.end_headers()
		try:
			if self.server.chunks:
				for chunk in self.server.chunks:
					sleep(0.025)
					self.wfile.write(chunk)
					self.wfile.flush()
			else:
				self.wfile.write(json.dumps(self.response).encode())
		except (BrokenPipeError, ConnectionResetError):
			pass


class AdapterTests(unittest.TestCase):
	def setUp(self):
		server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
		server.paths = []
		server.location = None
		server.content_encoding = None
		server.chunks = []
		server.header_delay = 0
		thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
		thread.start()
		self.addCleanup(server.server_close)
		self.addCleanup(thread.join)
		self.addCleanup(server.shutdown)
		self.server = server
		self.url = f"http://127.0.0.1:{server.server_port}"

	def test_four_protocols_return_same_text_and_usage(self):
		cases = {
			"openai": (
				"/v1/chat/completions",
				{
					"choices": [{"message": {"content": "hello"}}],
					"usage": {"prompt_tokens": 2, "completion_tokens": 3},
				},
			),
			"anthropic": (
				"/v1/messages",
				{
					"content": [{"type": "text", "text": "hello"}],
					"usage": {"input_tokens": 2, "output_tokens": 3},
				},
			),
			"gemini": (
				"/v1beta/models/fake:generateContent",
				{
					"candidates": [{"content": {"parts": [{"text": "hello"}]}}],
					"usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 3},
				},
			),
			"ollama": (
				"/api/chat",
				{"message": {"content": "hello"}, "prompt_eval_count": 2, "eval_count": 3},
			),
		}
		Handler.status = 200
		for adapter, (path, body) in cases.items():
			with self.subTest(adapter=adapter):
				Handler.response = body
				result = complete(
					Endpoint("fixture", adapter, self.url),
					"fake",
					[{"role": "user", "content": "test"}],
					20,
					allow_test_http=True,
				)
				self.assertEqual(self.server.path, path)
				self.assertEqual(
					result,
					{
						"api": "fixture",
						"model": "fake",
						"text": "hello",
						"tool_calls": [],
						"usage": {"input": 2, "output": 3},
					},
				)

	def test_four_protocols_return_same_function_arguments(self):
		function = {"name": "lookup", "arguments": {"term": "hello"}}
		cases = {
			"openai": {
				"choices": [
					{
						"message": {
							"tool_calls": [
								{
									"id": "call-0",
									"function": {"name": "lookup", "arguments": '{"term":"hello"}'},
								}
							]
						}
					}
				]
			},
			"anthropic": {
				"content": [
					{"type": "tool_use", "id": "call-0", "name": "lookup", "input": {"term": "hello"}}
				]
			},
			"gemini": {
				"candidates": [
					{"content": {"parts": [{"functionCall": {"name": "lookup", "args": {"term": "hello"}}}]}}
				]
			},
			"ollama": {"message": {"tool_calls": [{"function": function}]}},
		}
		request_fields = {
			"openai": ("tools", "response_format"),
			"anthropic": ("tools", "output_config"),
			"gemini": ("tools", "generationConfig"),
			"ollama": ("tools", "format"),
		}
		tool = {"name": "lookup", "parameters": {"type": "object"}}
		schema = {"type": "object", "properties": {"result": {"type": "string"}}}
		Handler.status = 200
		for adapter, body in cases.items():
			with self.subTest(adapter=adapter):
				Handler.response = body
				result = complete(
					Endpoint("fixture", adapter, self.url),
					"fake",
					[{"role": "user", "content": "test"}],
					20,
					tools=[tool],
					schema=schema,
					allow_test_http=True,
				)
				self.assertEqual(result["tool_calls"], [{"id": "call-0", **function}])
				tools_key, schema_key = request_fields[adapter]
				self.assertIn("lookup", json.dumps(self.server.body[tools_key]))
				self.assertIn("result", json.dumps(self.server.body[schema_key]))

	def test_lost_reservation_stops_http_dispatch(self):
		with self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"):
			with self.assertRaises(GatewayError) as failure:
				complete(
					Endpoint("fixture", "ollama", self.url),
					"fake",
					[],
					20,
					before_post=lambda: False,
				)
		self.assertEqual(failure.exception.code, "reservation_lost")
		self.assertFalse(hasattr(self.server, "path"))

	def test_provider_cannot_echo_a_credential_in_success(self):
		Handler.status = 200
		Handler.response = {"choices": [{"message": {"content": SECRET}}]}
		endpoint = Endpoint("fixture", "openai", self.url, "api_key", SECRET)
		with self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING") as logs:
			with self.assertRaises(GatewayError) as failure:
				complete(endpoint, "fake", [], 20, allow_test_http=True)
		self.assertEqual(failure.exception.code, "invalid_response")
		self.assertNotIn(SECRET, str(logs.output))

	def test_oauth_exchanges_credentials_for_a_bearer_token(self):
		Handler.status = 200
		Handler.response = {"choices": [{"message": {"content": "hello"}}]}
		endpoint = Endpoint(
			"fixture",
			"openai",
			self.url,
			"oauth_client_credentials",
			SECRET,
			self.url + "/token",
			"fixture-client",
		)
		result = complete(endpoint, "fake", [], 20, allow_test_http=True)
		auth, form = self.server.token_request
		self.assertTrue(auth.startswith("Basic "))
		self.assertEqual(form, b"grant_type=client_credentials")
		self.assertEqual(self.server.headers["Authorization"], "Bearer fixture-token")
		self.assertEqual(result["text"], "hello")

	def test_rejects_http_for_credentialed_upstream(self):
		endpoint = Endpoint("fixture", "openai", self.url, "api_key", SECRET)
		with self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"):
			with self.assertRaises(GatewayError) as failure:
				complete(endpoint, "fake", [], 20)
		self.assertEqual(failure.exception.code, "configuration")
		self.assertFalse(hasattr(self.server, "path"))

	def test_http_status_drives_failover(self):
		first = Candidate("first", "fake")
		for status, code in ((429, "rate_limit"), (503, "upstream")):
			with self.subTest(status=status):
				Handler.status = status
				with self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"):
					with self.assertRaises(GatewayError) as failure:
						complete(Endpoint("first", "openai", self.url), "fake", [], 20, allow_test_http=True)
				self.assertEqual(failure.exception.code, code)
				self.assertTrue(on_failure(first, code, now=100, cooldown_seconds=30).try_next)

	def test_connect_timeout_is_nonbillable_and_separate_from_read_timeout(self):
		with (
			patch.object(requests.Session, "post", side_effect=requests.ConnectTimeout) as post,
			self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"),
			self.assertRaises(GatewayError) as failure,
		):
			complete(
				Endpoint("first", "ollama", self.url), "fake", [], 4096, timeout=45, deadline=monotonic() + 60
			)
		self.assertEqual(post.call_args.kwargs["timeout"], (5, 45))
		self.assertEqual(failure.exception.code, "connect_failed")
		self.assertFalse(failure.exception.may_be_billed)

	def test_timeout_before_response_headers_is_ambiguous(self):
		Handler.status = 200
		self.server.header_delay = 0.075
		with (
			self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"),
			self.assertRaises(GatewayError) as failure,
		):
			complete(Endpoint("first", "ollama", self.url), "fake", [], 20, timeout=0.025)
		self.assertEqual(failure.exception.code, "timeout")
		self.assertTrue(failure.exception.may_be_billed)
		self.assertEqual(self.server.paths, ["/api/chat"])

	def test_redirects_are_not_followed_and_http_rejections_are_nonbillable(self):
		endpoint = Endpoint("first", "ollama", self.url)
		self.server.location = self.url + "/redirected"
		for status, expected in ((307, "rejected"), (400, "rejected"), (403, "forbidden"), (404, "rejected")):
			with (
				self.subTest(status=status),
				self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"),
				self.assertRaises(GatewayError) as failure,
			):
				Handler.status = status
				complete(endpoint, "fake", [], 20)
			self.assertEqual(failure.exception.code, expected)
			self.assertFalse(failure.exception.may_be_billed)
		self.assertEqual(self.server.paths, ["/api/chat"] * 4)

	def test_accepted_and_request_timeout_statuses_may_have_incurred_cost(self):
		endpoint = Endpoint("first", "ollama", self.url)
		for status, expected in ((202, "invalid_response"), (408, "timeout")):
			with (
				self.subTest(status=status),
				self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"),
				self.assertRaises(GatewayError) as failure,
			):
				Handler.status = status
				complete(endpoint, "fake", [], 20)
			self.assertEqual(failure.exception.code, expected)
			self.assertTrue(failure.exception.may_be_billed)

	def test_redirect_is_rejected_without_reading_its_body(self):
		Handler.status = 307
		self.server.location = self.url + "/redirected"
		self.server.chunks = [b" "] * 40
		started = monotonic()
		with (
			self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"),
			self.assertRaises(GatewayError) as failure,
		):
			complete(Endpoint("first", "ollama", self.url), "fake", [], 20, deadline=started + 0.4)
		self.assertEqual(failure.exception.code, "rejected")
		self.assertLess(monotonic() - started, 0.7)
		self.assertEqual(self.server.paths, ["/api/chat"])

	def test_body_requires_identity_encoding(self):
		Handler.status = 200
		self.server.content_encoding = "gzip"
		# Compressed reads can consume multiple network chunks before returning.
		# The provider must honor the requested identity encoding.
		with (
			self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"),
			self.assertRaises(GatewayError) as failure,
		):
			complete(Endpoint("first", "ollama", self.url), "fake", [], 20)
		self.assertEqual(self.server.headers["Accept-Encoding"], "identity")
		self.assertEqual(failure.exception.code, "invalid_response")

	def test_body_cannot_exceed_byte_or_elapsed_time_limits(self):
		endpoint = Endpoint("first", "ollama", self.url)
		Handler.status = 200
		Handler.response = {"message": {"content": "x" * (2 * 1024 * 1024)}}
		with (
			self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"),
			self.assertRaises(GatewayError) as failure,
		):
			complete(endpoint, "fake", [], 20)
		self.assertEqual(failure.exception.code, "invalid_response")
		self.assertTrue(failure.exception.may_be_billed)
		self.server.chunks = [b" "] * 40
		started = monotonic()
		with (
			self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"),
			self.assertRaises(GatewayError) as failure,
		):
			complete(endpoint, "fake", [], 20, deadline=started + 0.25)
		self.assertEqual(failure.exception.code, "timeout")
		self.assertLess(monotonic() - started, 0.75)

	def test_tool_calls_must_use_an_offered_name_and_unique_safe_identifier(self):
		Handler.status = 200
		endpoint = Endpoint("first", "openai", self.url)
		valid = {"id": "call-1", "function": {"name": "lookup", "arguments": "{}"}}
		bad_id = {**valid, "id": "invalid id"}
		bad_name = {**valid, "function": {**valid["function"], "name": "unlisted"}}
		for calls in ([bad_id], [bad_name], [valid, valid]):
			with (
				self.subTest(calls=calls),
				self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING"),
				self.assertRaises(GatewayError) as failure,
			):
				Handler.response = {"choices": [{"message": {"tool_calls": calls}}]}
				complete(
					endpoint,
					"fake",
					[],
					20,
					allow_test_http=True,
					tools=[{"name": "lookup", "parameters": {"type": "object"}}],
				)
			self.assertEqual(failure.exception.code, "invalid_response")

	def test_error_does_not_expose_secret(self):
		Handler.status = 401
		Handler.response = {"error": SECRET}
		endpoint = Endpoint("fixture", "openai", self.url, "api_key", SECRET)
		with self.assertLogs("platform_core.model_gecidi.adapters", level="WARNING") as logs:
			with self.assertRaises(GatewayError) as failure:
				complete(endpoint, "fake", [{"role": "user", "content": "test"}], 20, allow_test_http=True)
		self.assertEqual(self.server.headers["Authorization"], f"Bearer {SECRET}")
		self.assertEqual(failure.exception.code, "authentication")
		self.assertNotIn(SECRET, repr(endpoint) + repr(failure.exception) + str(logs.output))


class RoutingTests(unittest.TestCase):
	def test_retry_disable_cooldown_and_budget(self):
		first = Candidate("first", "fake", priority=1)
		second = Candidate("second", "fake", priority=2)
		exhausted = Candidate("exhausted", "fake", priority=0, remaining_budget=0)
		for error in ("rate_limit", "upstream", "timeout", "connect_failed"):
			with self.subTest(error=error):
				decision = on_failure(first, error, now=100, cooldown_seconds=30)
				self.assertTrue(decision.try_next)
				self.assertEqual(candidates([decision.candidate, second, exhausted], now=129), [second])
				self.assertEqual(
					candidates([decision.candidate, second, exhausted], now=130), [decision.candidate, second]
				)
		decision = on_failure(first, "authentication", now=100, cooldown_seconds=30)
		self.assertTrue(decision.try_next)
		self.assertEqual(candidates([decision.candidate, second], now=500), [second])
		decision = on_failure(first, "forbidden", now=100, cooldown_seconds=30)
		self.assertTrue(decision.try_next)
		self.assertIs(decision.candidate, first)

	def test_capped_account_requires_a_bounded_cost(self):
		budget = Decimal("1")
		unknown = Candidate("unknown", "fake", remaining_budget=budget)
		over = Candidate("over", "fake", cost=Decimal("2"), remaining_budget=budget)
		fits = Candidate("fits", "fake", cost=budget, remaining_budget=budget)
		self.assertEqual(candidates([unknown, over, fits], now=0), [fits])
