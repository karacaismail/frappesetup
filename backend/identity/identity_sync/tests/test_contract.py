"""Sözleşme ile sunucunun aynı uçları taşıdığını denetler (SZ-3).

OpenAPI dosyası düz metin olarak okunur. Python'un kendi kitaplığında YAML okuyucu yoktur.
"""

from __future__ import annotations

import pathlib
import re
import threading
import unittest
import urllib.error
import urllib.request

from identity_sync.auth import reject_all
from identity_sync.server import make_server

from .fakes import Stack

CONTRACT = pathlib.Path(__file__).resolve().parents[3] / "contracts" / "identity_sync.openapi.yaml"
METHODS = ("get", "post", "put", "delete")


def contract_operations() -> dict[tuple[str, str], dict[str, str]]:
    operations: dict[tuple[str, str], dict[str, str]] = {}
    path, current = "", None
    for line in CONTRACT.read_text(encoding="utf-8").splitlines():
        if match := re.fullmatch(r"  (/\S*):", line):
            path = match.group(1)
        elif (match := re.fullmatch(r"    (\w+):", line)) and match.group(1) in METHODS and path:
            current = operations.setdefault((match.group(1).upper(), path), {})
        elif line.startswith("components:"):
            path, current = "", None
        elif current is not None and (match := re.fullmatch(r"      (summary|description|x-durum|x-yikici): ?(.*)", line)):
            current[match.group(1)] = match.group(2)
    return operations


class ContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = Stack()
        self.addCleanup(self.stack.close)
        self.httpd = make_server(self.stack.app, reject_all, host="127.0.0.1", port=0)
        thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def status(self, method: str, path: str) -> int:
        url = f"http://127.0.0.1:{self.httpd.server_address[1]}{path.replace('{tenant}', 'kiraci1')}"
        request = urllib.request.Request(url, data=b"{}" if method == "POST" else None, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as error:
            error.close()
            return error.code

    def test_contract_lists_operations(self) -> None:
        self.assertGreaterEqual(len(contract_operations()), 7)

    def test_every_operation_is_documented(self) -> None:
        # Her uç özet, açıklama ve yıkıcılık bilgisi taşır (`docs/sozlesmeler.md`, 10. bölüm).
        for key, fields in contract_operations().items():
            with self.subTest(operation=key):
                self.assertTrue(fields.get("summary"))
                self.assertIn("description", fields)
                self.assertIn(fields.get("x-durum"), ("uygulandi", "planlandi"))
                self.assertIn(fields.get("x-yikici"), ("true", "false"))

    def test_implemented_operations_exist_and_planned_ones_do_not(self) -> None:
        for (method, path), fields in contract_operations().items():
            with self.subTest(operation=(method, path)):
                status = self.status(method, path)
                if path == "/healthz":
                    self.assertEqual(status, 200)
                elif fields["x-durum"] == "uygulandi":
                    # Kimliksiz istek her korumalı uçta 401 alır.
                    self.assertEqual(status, 401)
                else:
                    self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
