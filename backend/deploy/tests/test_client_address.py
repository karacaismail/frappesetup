"""Keycloak sees the real client address (G-162 source limit, AJA-413 and AJA-440).

The magic link fork limits mails per source. The source is the client IP address Keycloak reads
from X-Forwarded-For (KC_PROXY_HEADERS=xforwarded). That is safe only while:
- only Caddy reaches Keycloak: the keycloak service has no published port;
- Caddy writes X-Forwarded-For itself: without trusted_proxies Caddy drops the header the client
  sent and writes the address it saw. No site may set the header by hand either.
Design: backend/docs/decisions/0003-keycloak-extensions.md, section "G-162 ek iş".
"""

import re
import unittest
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[1] / "compose"


def _service(text: str, name: str) -> str:
    """Returns the lines of one top level compose service."""
    found = re.search(rf"^  {name}:\n(.*?)(?=^  \S|^\S|\Z)", text, re.M | re.S)
    if not found:
        raise AssertionError(f"service {name} missing")
    return found.group(1)


class ClientAddressTest(unittest.TestCase):
    def test_keycloak_sees_the_real_client_address(self):
        keycloak = _service((COMPOSE / "stack.yaml").read_text(encoding="utf-8"), "keycloak")
        self.assertIn("KC_PROXY_HEADERS: xforwarded", keycloak)
        self.assertNotRegex(keycloak, r"(?m)^    ports:", "only Caddy may reach Keycloak")
        for name in ("Caddyfile", "site.caddy.template", "edge.yaml"):
            with self.subTest(file=name):
                text = (COMPOSE / name).read_text(encoding="utf-8")
                self.assertNotIn("trusted_proxies", text, "Caddy must not trust a client X-Forwarded-For")
                self.assertNotRegex(text, r"(?i)header_up\s+[+-]?X-Forwarded-For")


if __name__ == "__main__":
    unittest.main()
