"""The panel and Press session cookies of G-13 (AJA-523).

G-13 asks for a host-bound "sid" cookie with Secure, HttpOnly and SameSite=Lax, and no Domain.
Frappe sets HttpOnly and SameSite=Lax itself and never writes a Domain. It sets Secure only when
the request scheme is https (frappe/auth.py CookieManager.set_cookie).
The chain is browser -> Caddy (https) -> nginx in the frontend container -> gunicorn (http).
nginx forwards X-Forwarded-Proto: https. gunicorn honours that header only from the addresses in
forwarded_allow_ips; the default is 127.0.0.1 and ::1. nginx runs in another container, so
without the option the scheme stays http and "sid" leaves without Secure.
Trusting every sender is safe only while no one but nginx reaches gunicorn: the web services
publish no port, and nginx writes the header itself.
"""

import re
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
STACK = DEPLOY / "compose" / "stack.yaml"
SETTINGS = DEPLOY / "settings"
WEB_SERVICES = ("tenant-web", "press-web")
FRONTENDS = {"tenant-frontend": "tenant-web:8000", "press-frontend": "press-web:8000"}


def service(text: str, name: str) -> str:
    """Returns the lines of one top level compose service."""
    found = re.search(rf"^  {name}:\n(.*?)(?=^  \S|^\S|\Z)", text, re.M | re.S)
    if not found:
        raise AssertionError(f"service {name} missing")
    return found.group(1)


def command(block: str) -> list[str]:
    found = re.search(r"(?m)^    command:\n((?:      - .*\n)+)", block)
    if not found:
        raise AssertionError("gunicorn command missing")
    return [line.strip()[2:] for line in found.group(1).splitlines()]


class PanelSessionCookieTest(unittest.TestCase):
    def setUp(self):
        self.stack = STACK.read_text(encoding="utf-8")

    def test_gunicorn_trusts_the_forwarded_scheme_so_sid_is_secure(self):
        for name in WEB_SERVICES:
            with self.subTest(service=name):
                args = command(service(self.stack, name))
                self.assertEqual(args[0], "env/bin/gunicorn")
                self.assertIn("--forwarded-allow-ips=*", args)
                self.assertEqual(args[-1], "frappe.app:application")

    def test_only_nginx_reaches_gunicorn(self):
        for name in WEB_SERVICES:
            with self.subTest(service=name):
                block = service(self.stack, name)
                self.assertNotRegex(block, r"(?m)^    (ports|network_mode):")
                self.assertIn("--bind=0.0.0.0:8000", command(block))
        for name, backend in FRONTENDS.items():
            with self.subTest(service=name):
                self.assertIn(f"BACKEND: {backend}", service(self.stack, name))

    def test_realtime_comes_from_the_same_origin(self):
        # socket.io sits behind the nginx of the same host (location /socket.io in the image's
        # template), so realtime uses the same origin and the same sid cookie. No socket port is
        # published, and the edge has no separate realtime host.
        for name, socket in (("tenant-frontend", "tenant-socket"), ("press-frontend", "press-socket")):
            with self.subTest(service=name):
                self.assertIn(f"SOCKETIO: {socket}:9000", service(self.stack, name))
                self.assertNotRegex(service(self.stack, socket), r"(?m)^    (ports|network_mode):")
        template = (DEPLOY / "compose" / "site.caddy.template").read_text(encoding="utf-8")
        self.assertNotRegex(template, r"(?i)socket|:9000")
        tenant = re.search(r"(?ms)^__TENANT_SITES__ \{\n(.*?)^\}", template).group(1)
        self.assertRegex(tenant, r"(?m)^\treverse_proxy __ENV__-tenant:8080$")

    def test_no_shared_cookie_domain_and_no_cross_origin_access(self):
        # Panel and Press API share one origin, so Press needs no allow_cors (G-13, G-45).
        # A Domain cookie would carry one host's session to every other name.
        for path in sorted(SETTINGS.glob("*.env.example")):
            keys = {line.split("=", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
                    if line and not line.startswith("#")}
            with self.subTest(file=path.name):
                self.assertFalse(keys & {"allow_cors", "cookie_domain", "session_cookie_domain"})


if __name__ == "__main__":
    unittest.main()
