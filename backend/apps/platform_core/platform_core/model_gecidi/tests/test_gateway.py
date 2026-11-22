import json
import threading
import unittest
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from model_gecidi.adapters import Endpoint, GatewayError, complete
from model_gecidi.routing import Candidate, candidates, on_failure

SECRET = "fixture-key"


class Handler(BaseHTTPRequestHandler):
	response = None
	status = 200

	def log_message(self, *args):
		pass

	def do_POST(self):
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
		self.send_response(self.status)
		self.send_header("Content-Type", "application/json")
		self.end_headers()
		self.wfile.write(json.dumps(self.response).encode())


class AdapterTests(unittest.TestCase):
	def setUp(self):
		server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
		thread = threading.Thread(target=server.serve_forever)
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
		with self.assertLogs("model_gecidi.adapters", level="WARNING"):
			with self.assertRaises(GatewayError) as failure:
				complete(endpoint, "fake", [], 20)
		self.assertEqual(failure.exception.code, "configuration")
		self.assertFalse(hasattr(self.server, "path"))

	def test_http_status_drives_failover(self):
		first = Candidate("first", "fake")
		for status, code in ((429, "rate_limit"), (503, "upstream")):
			with self.subTest(status=status):
				Handler.status = status
				with self.assertLogs("model_gecidi.adapters", level="WARNING"):
					with self.assertRaises(GatewayError) as failure:
						complete(Endpoint("first", "openai", self.url), "fake", [], 20, allow_test_http=True)
				self.assertEqual(failure.exception.code, code)
				self.assertTrue(on_failure(first, code, now=100, cooldown_seconds=30).try_next)

	def test_error_does_not_expose_secret(self):
		Handler.status = 401
		Handler.response = {"error": SECRET}
		endpoint = Endpoint("fixture", "openai", self.url, "api_key", SECRET)
		with self.assertLogs("model_gecidi.adapters", level="WARNING") as logs:
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
		for error in ("rate_limit", "upstream", "timeout"):
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

	def test_capped_account_requires_a_bounded_cost(self):
		budget = Decimal("1")
		unknown = Candidate("unknown", "fake", remaining_budget=budget)
		over = Candidate("over", "fake", cost=Decimal("2"), remaining_budget=budget)
		fits = Candidate("fits", "fake", cost=budget, remaining_budget=budget)
		self.assertEqual(candidates([unknown, over, fits], now=0), [fits])
