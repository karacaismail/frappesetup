"""Run two synchronized HTTP request groups on the isolated mobile fixture site."""

import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.error import HTTPError, URLError
from urllib.request import Request
from uuid import uuid4

from platform_core.mobil.tests.loopback_http import open_loopback

from .load_accounts import LOAD_ACCOUNTS


def call(port, token, operation, payload):
	request = Request(
		f"http://127.0.0.1:{port}/api/method/platform_core.api.mobile.v1_{operation}",
		data=json.dumps(payload).encode(),
		headers={
			"Authorization": token,
			"Content-Type": "application/json",
			"X-Mobile-App-Version": "1.0.0",
			"X-Mobile-Contract-Version": "1",
		},
		method="POST",
	)
	try:
		with open_loopback(request, timeout=15) as response:
			return response.status, json.load(response)
	except HTTPError as error:
		with error:
			if 300 <= error.code < 400:
				result = {"code": "redirect_rejected"}
			else:
				try:
					result = json.load(error)
				except ValueError:
					result = {"code": "invalid_error_response"}
		return error.code, result
	except (TimeoutError, URLError) as error:
		return None, {"code": type(error).__name__}


def write(port, token, installation_id, record_id):
	return call(
		port,
		token,
		"push",
		{
			"installation_id": installation_id,
			"operations": [
				{
					"operation_id": str(uuid4()),
					"command": "fixture.create",
					"record_id": record_id,
					"fields": {"title": "Load test record"},
				},
			],
		},
	)


def run_group(name, requests, send):
	barrier = Barrier(len(requests), timeout=5)

	def synchronized(request):
		barrier.wait()
		return send(*request)

	with ThreadPoolExecutor(max_workers=len(requests)) as pool:
		results = list(pool.map(synchronized, requests))
	counts = Counter(status for status, _ in results)
	print(
		json.dumps({"workload": name, "requests": len(requests), "503": counts[503], "statuses": counts}),
		flush=True,
	)
	return results


def main(port):
	installations = []
	for token in LOAD_ACCOUNTS:
		installation_id, seed_id = str(uuid4()), str(uuid4())
		status, result = call(port, token, "register", {"installation_id": installation_id})
		if status != 200:
			raise SystemExit(f"Load setup registration failed: {status} {result.get('code')}")
		status, result = write(port, token, installation_id, seed_id)
		if status != 200:
			raise SystemExit(f"Load setup write failed: {status} {result.get('code')}")
		installations.append((token, installation_id, seed_id))

	writes = run_group(
		"concurrent_writes",
		[(token, installation_id, str(uuid4())) for token, installation_id, _ in installations],
		lambda token, installation_id, record_id: write(port, token, installation_id, record_id),
	)
	pulls = run_group(
		"concurrent_initial_pulls",
		[(token, installation_id) for token, installation_id, _ in installations],
		lambda token, installation_id: call(port, token, "pull", {"installation_id": installation_id}),
	)
	for (_, _, seed_id), (status, result) in zip(installations, pulls, strict=True):
		if status == 200 and seed_id not in {change["record_id"] for change in result["message"]["changes"]}:
			raise SystemExit("An initial pull omitted a seeded record")
	return int(any(status != 200 for status, _ in (*writes, *pulls)))


if __name__ == "__main__":
	if len(sys.argv) != 2 or not sys.argv[1].isdigit() or not 1 <= int(sys.argv[1]) <= 65535:
		raise SystemExit("Usage: python -m mobile_test_app.load_test <loopback-port>")
	raise SystemExit(main(int(sys.argv[1])))
