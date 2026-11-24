"""Live end-to-end test of platform sign-in with a fake OIDC provider (G-159, G-160).

No real Google account is used. The fake provider is a separate, temporary realm in the same
local Keycloak. It plays the role of an external platform: the browser leaves the platform
realm, signs in at the fake provider and returns to /realms/platform/broker/<alias>/endpoint.

The fake platform is opened only through data: a record file in a temporary folder and the real
``bin/atonota-login apply`` command. All passwords and secrets are made at run time.

Run against a local development Keycloak (identity/keycloak/bin/kc-dev.sh up and tunnel):

  set -a; . ../keycloak/.env; set +a
  KC_PUBLIC_URL=http://identity.localhost:<port> ATONOTA_LOGIN_LIVE=1 \
    python3 -I -m unittest tests.test_live_platforms -v

The test removes its realm, users and fake platform at the end.
"""

from __future__ import annotations

import base64
import contextlib
import importlib.machinery
import importlib.util
import io
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar, DefaultCookiePolicy
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
COMMAND = PRODUCT / "bin" / "atonota-login"
LIVE = os.environ.get("ATONOTA_LOGIN_LIVE") == "1" and bool(os.environ.get("KC_PUBLIC_URL"))
REALM = "platform"
CLIENT = "account-console"
FAKE_ALIAS = "fake-oidc"
FAKE_ENV_ID = "ATONOTA_FAKE_OIDC_CLIENT_ID"
FAKE_ENV_CLIENT_KEY = "ATONOTA_FAKE_OIDC_CLIENT_" + "SECRET"
ENTERPRISE_ROLE = "enterprise-sso-required"


# Only http and https handlers: the tests reach the local Keycloak and nothing else.
HTTP = urllib.request.OpenerDirector()
for _handler in (urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), urllib.request.HTTPErrorProcessor(),
                 urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPRedirectHandler()):
    HTTP.add_handler(_handler)


def load_command():
    """Load bin/atonota-login as a module, so the test runs the real command in this process."""
    spec = importlib.util.spec_from_loader("atonota_login_command", importlib.machinery.SourceFileLoader(
        "atonota_login_command", str(COMMAND)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Browser:
    """A minimal browser: cookies, manual redirects, form posts. Stops at the client's address."""

    def __init__(self, stop_prefix: str):
        # Keycloak marks cookies Secure. Browsers treat *.localhost as secure over http too.
        jar = CookieJar(DefaultCookiePolicy(secure_protocols=("https", "wss", "http")))
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), _NoRedirect())
        self.stop_prefix = stop_prefix
        self.visited_hosts = []

    def _open(self, url, data=None):
        request = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
        if data is not None:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            response = self.opener.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read().decode("utf-8", "replace")

    def go(self, url, data=None):
        """Follow redirects. Returns (status, final url, body). Stops before the client address."""
        for _ in range(15):
            self.visited_hosts.append(urllib.parse.urlsplit(url).netloc)
            status, headers, body = self._open(url, data)
            location = headers.get("Location")
            if status in (301, 302, 303, 307) and location:
                url = urllib.parse.urljoin(url, location)
                data = None
                if url.startswith(self.stop_prefix):
                    return status, url, ""
                continue
            return status, url, body
        raise AssertionError("Too many redirects.")

    def submit(self, page_url, body, fields, form_index=0):
        actions = re.findall(r'<form[^>]*\saction="([^"]+)"', body)
        if not actions:
            raise AssertionError("The page has no form.")
        action = urllib.parse.urljoin(page_url, html.unescape(actions[form_index]))
        return self.go(action, urllib.parse.urlencode(fields).encode())


class Admin:
    def __init__(self, base):
        self.base = base
        self.sign_in()

    def sign_in(self):
        base = self.base
        form = urllib.parse.urlencode({
            "grant_type": "password", "client_id": "admin-cli",
            "username": os.environ["KC_BOOTSTRAP_ADMIN_USERNAME"],
            "password": os.environ["KC_BOOTSTRAP_ADMIN_PASSWORD"],
        }).encode()
        with HTTP.open(f"{base}/realms/master/protocol/openid-connect/token", form, timeout=30) as response:
            self.token = json.load(response)["access_token"]

    def call(self, method, path, payload=None, expect=(200, 201, 204)):
        request = urllib.request.Request(
            f"{self.base}/admin/realms{path}", method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        status, body = self._send(request)
        if status == 401:
            # The master realm admin token lives one minute. Sign in again once.
            self.sign_in()
            request.headers["Authorization"] = f"Bearer {self.token}"
            status, body = self._send(request)
        if expect and status not in expect:
            raise AssertionError(f"{method} {path}: HTTP {status}")
        return status, (json.loads(body) if body else None)

    @staticmethod
    def _send(request):
        try:
            with HTTP.open(request, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            body = error.read()
            error.close()
            return error.code, body

    def user(self, realm, username):
        _, found = self.call("GET", f"/{realm}/users?exact=true&username={urllib.parse.quote(username)}")
        return found[0] if found else None

    def links(self, user_id):
        _, found = self.call("GET", f"/{REALM}/users/{user_id}/federated-identity")
        return {item["identityProvider"]: item for item in found}


def page_message(body):
    """The page title and Keycloak's feedback text, for failure messages."""
    text = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", body, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:300]


def pkce_auth_url(base):
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    query = urllib.parse.urlencode({
        "client_id": CLIENT, "redirect_uri": f"{base}/realms/{REALM}/account/", "response_type": "code",
        "scope": "openid", "state": secrets.token_urlsafe(8), "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"{base}/realms/{REALM}/protocol/openid-connect/auth?{query}"


@unittest.skipUnless(LIVE, "Set ATONOTA_LOGIN_LIVE=1 and KC_PUBLIC_URL for the live test.")
class LivePlatformTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = os.environ["KC_PUBLIC_URL"].rstrip("/")
        cls.admin = Admin(cls.base)
        cls.upstream = "fake-upstream-" + secrets.token_hex(4)
        cls.client_secret = secrets.token_urlsafe(32)
        cls.folder = Path(tempfile.mkdtemp())
        cls.users = {}
        cls.addClassCleanup(cls.cleanup)
        redirect = f"{cls.base}/realms/{REALM}/broker/{FAKE_ALIAS}/endpoint"
        cls.admin.call("POST", "", {
            "realm": cls.upstream, "enabled": True, "sslRequired": "none",
            "clients": [{
                "clientId": "atonota-login", "enabled": True, "publicClient": False,
                "secret": cls.client_secret, "redirectUris": [redirect], "standardFlowEnabled": True,
                "directAccessGrantsEnabled": False, "fullScopeAllowed": False,
            }],
        })
        # Platform realm: one account with a password, one that must use corporate sign-in.
        cls.shared_email = f"twin-{secrets.token_hex(4)}@example.test"
        cls.enterprise_email = f"corp-{secrets.token_hex(4)}@example.test"
        cls.newcomer_email = f"new-{secrets.token_hex(4)}@example.test"
        cls.twin_password = secrets.token_urlsafe(18)
        cls.make_user(REALM, cls.shared_email, cls.twin_password, verified=True)
        cls.make_user(REALM, cls.enterprise_email, secrets.token_urlsafe(18), verified=True)
        role = cls.admin.call("GET", f"/{REALM}/roles/{ENTERPRISE_ROLE}")[1]
        enterprise_id = cls.admin.user(REALM, cls.enterprise_email)["id"]
        cls.admin.call("POST", f"/{REALM}/users/{enterprise_id}/role-mappings/realm", [role])
        # Fake platform accounts, each with the same e-mail as above or a new one.
        for email in (cls.shared_email, cls.enterprise_email, cls.newcomer_email):
            cls.users[(cls.upstream, email)] = secrets.token_urlsafe(18)
            cls.make_user(cls.upstream, email, cls.users[(cls.upstream, email)], verified=True)
        # Review finding 1 (pre-hijack): a platform account that claims a future victim's address
        # without verifying it, and one with no e-mail at all.
        cls.victim_email = f"victim-{secrets.token_hex(4)}@example.test"
        cls.users[(cls.upstream, cls.victim_email)] = secrets.token_urlsafe(18)
        cls.make_user(cls.upstream, cls.victim_email, cls.users[(cls.upstream, cls.victim_email)], verified=False)
        cls.no_mail_name = f"nomail-{secrets.token_hex(4)}"
        cls.users[(cls.upstream, cls.no_mail_name)] = secrets.token_urlsafe(18)
        cls.make_user(cls.upstream, cls.no_mail_name, cls.users[(cls.upstream, cls.no_mail_name)], verified=False, email=None)
        upstream_enterprise = cls.admin.user(cls.upstream, cls.enterprise_email)["id"]
        # The fake platform comes as data only: the product records plus one new file.
        for record in (PRODUCT / "platforms").glob("*.json"):
            shutil.copy(record, cls.folder / record.name)
        issuer = f"{cls.base}/realms/{cls.upstream}"
        (cls.folder / f"{FAKE_ALIAS}.json").write_text(json.dumps({
            "alias": FAKE_ALIAS, "providerId": "oidc", "displayName": "Fake OIDC",
            "authorizationHost": urllib.parse.urlsplit(cls.base).hostname,
            "secrets": {"clientId": FAKE_ENV_ID, "clientSecret": FAKE_ENV_CLIENT_KEY},
            "config": {
                "issuer": issuer,
                "authorizationUrl": f"{issuer}/protocol/openid-connect/auth",
                "tokenUrl": f"{issuer}/protocol/openid-connect/token",
                "userInfoUrl": f"{issuer}/protocol/openid-connect/userinfo",
                "jwksUrl": f"{issuer}/protocol/openid-connect/certs",
                "useJwksUrl": "true", "validateSignature": "true",
                "clientAuthMethod": "client_secret_post", "defaultScope": "openid email profile",
                "pkceEnabled": "true", "pkceMethod": "S256", "syncMode": "IMPORT",
                "filteredByClaim": "true", "claimFilterName": "email_verified", "claimFilterValue": "true",
            },
        }), encoding="utf-8")
        cls.apply(open_fake=True)
        # The enterprise user is already linked, so the post-login rule runs for this account.
        cls.admin.call("POST", f"/{REALM}/users/{enterprise_id}/federated-identity/{FAKE_ALIAS}", {
            "identityProvider": FAKE_ALIAS, "userId": upstream_enterprise, "userName": cls.enterprise_email,
        })

    @classmethod
    def make_user(cls, realm, username, password, verified, email=""):
        user = {
            "username": username, "firstName": "Test", "lastName": "Person",
            "enabled": True, "emailVerified": verified,
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        }
        if email is not None:
            user["email"] = email or username
        cls.admin.call("POST", f"/{realm}/users", user)

    @classmethod
    def apply(cls, open_fake):
        saved = {name: os.environ.get(name) for name in (FAKE_ENV_ID, FAKE_ENV_CLIENT_KEY)}
        os.environ[FAKE_ENV_ID] = "atonota-login" if open_fake else ""
        os.environ[FAKE_ENV_CLIENT_KEY] = cls.client_secret if open_fake else ""
        output, errors = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                code = load_command().main(
                    ["--platforms-dir", str(cls.folder), "--allow-local-http", "apply", "--from-env"])
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        if code != 0:
            raise AssertionError(errors.getvalue())
        if cls.client_secret in output.getvalue() + errors.getvalue():
            raise AssertionError("The apply command printed a secret.")
        return output.getvalue()

    @classmethod
    def cleanup(cls):
        cls.admin.call("DELETE", f"/{cls.upstream}", expect=None)
        cls.admin.call("DELETE", f"/{REALM}/identity-provider/instances/{FAKE_ALIAS}", expect=None)
        for email in (cls.shared_email, cls.enterprise_email, cls.newcomer_email, cls.victim_email, cls.no_mail_name):
            found = cls.admin.user(REALM, email)
            if found:
                cls.admin.call("DELETE", f"/{REALM}/users/{found['id']}", expect=None)
        shutil.rmtree(cls.folder, ignore_errors=True)

    def start(self):
        browser = Browser(f"{self.base}/realms/{REALM}/account/")
        status, url, body = browser.go(pkce_auth_url(self.base))
        self.assertEqual(status, 200)
        return browser, url, body

    def sign_in_at_fake_platform(self, email):
        browser, url, body = self.start()
        links = re.findall(r'href="([^"]*/broker/' + FAKE_ALIAS + r'/login[^"]*)"', body)
        self.assertEqual(len(links), 1, "The fake platform button is missing.")
        status, url, body = browser.go(urllib.parse.urljoin(url, html.unescape(links[0])))
        self.assertIn(f"/realms/{self.upstream}/", url, f"HTTP {status}: {page_message(body)}")
        password = self.users[(self.upstream, email)]
        return browser, *browser.submit(url, body, {"username": email, "password": password})

    def test_login_page_shows_only_open_platforms(self):
        _, _, body = self.start()
        aliases = set(re.findall(r"/broker/([a-z0-9-]+)/login", body))
        self.assertEqual(aliases, {FAKE_ALIAS})

    def test_new_account_is_linked_by_the_platform_user_number(self):
        browser, status, url, body = self.sign_in_at_fake_platform(self.newcomer_email)
        user = self.admin.user(REALM, self.newcomer_email)
        self.assertIsNotNone(user, f"HTTP {status}")
        self.assertFalse(user["emailVerified"], "A platform e-mail is not trusted.")
        upstream_id = self.admin.user(self.upstream, self.newcomer_email)["id"]
        self.assertEqual(self.admin.links(user["id"])[FAKE_ALIAS]["userId"], upstream_id)

    def test_same_e_mail_is_not_linked_without_signing_in_again(self):
        twin = self.admin.user(REALM, self.shared_email)
        browser, status, url, body = self.sign_in_at_fake_platform(self.shared_email)
        self.assertEqual(status, 200)
        self.assertIn("linkAccount", body, "Keycloak must ask before linking.")
        self.assertNotIn(FAKE_ALIAS, self.admin.links(twin["id"]))
        status, url, body = browser.submit(url, body, {"submitAction": "linkAccount"})
        self.assertEqual(status, 200)
        self.assertIn('name="password"', body, "Linking must ask for the existing password.")
        self.assertNotIn("Verify existing account by Email".lower(), body.lower())
        self.assertNotIn(FAKE_ALIAS, self.admin.links(twin["id"]))
        status, url, body = browser.submit(url, body, {"username": self.shared_email, "password": secrets.token_urlsafe(12)})
        self.assertNotIn(FAKE_ALIAS, self.admin.links(twin["id"]), "A wrong password linked the account.")
        status, url, body = browser.submit(url, body, {"username": self.shared_email, "password": self.twin_password})
        self.assertIn("code=", url, f"HTTP {status}: {page_message(body)}")
        self.assertIn(FAKE_ALIAS, self.admin.links(twin["id"]))
        self.assertEqual(twin["id"], self.admin.user(REALM, self.shared_email)["id"], "Accounts were merged.")

    def test_enterprise_user_cannot_use_social_sign_in(self):
        browser, status, url, body = self.sign_in_at_fake_platform(self.enterprise_email)
        self.assertNotIn("code=", url)
        self.assertTrue(
            "kurumsal girişi" in body or "corporate sign-in" in body,
            f"HTTP {status}: {page_message(body)}",
        )

    def test_unverified_e_mail_cannot_claim_an_address(self):
        # Pre-hijack: the platform says the e-mail is not verified. No account is made, nothing is linked.
        browser, status, url, body = self.sign_in_at_fake_platform(self.victim_email)
        self.assertFalse(url.startswith(browser.stop_prefix), f"HTTP {status}: {page_message(body)}")
        self.assertIsNone(self.admin.user(REALM, self.victim_email), "An account was made for an unverified e-mail.")

    def test_platform_without_e_mail_cannot_make_an_account(self):
        browser, status, url, body = self.sign_in_at_fake_platform(self.no_mail_name)
        self.assertFalse(url.startswith(browser.stop_prefix), f"HTTP {status}: {page_message(body)}")
        if f"/realms/{REALM}/" in url:
            # The fake platform may ask for an e-mail on its own page. Our realm never does.
            self.assertNotIn('name="email"', body, "The user must not type an e-mail address.")
        self.assertIsNone(self.admin.user(REALM, self.no_mail_name))

    def test_unknown_platform_return_address_is_refused(self):
        browser = Browser(f"{self.base}/realms/{REALM}/account/")
        for alias in ("no-such-platform", "facebook"):
            status, url, _ = browser.go(f"{self.base}/realms/{REALM}/broker/{alias}/endpoint?code=x&state=y")
            self.assertGreaterEqual(status, 400, alias)
            status, url, _ = browser.go(f"{self.base}/realms/{REALM}/broker/{alias}/login?client_id={CLIENT}&tab_id=x&session_code=y")
            self.assertNotIn("facebook.com", url, alias)

    def test_zz_closed_platform_disappears_from_the_login_page(self):
        try:
            self.apply(open_fake=False)
            _, _, body = self.start()
            self.assertNotIn(f"/broker/{FAKE_ALIAS}/login", body)
            _, state = self.admin.call("GET", f"/{REALM}/identity-provider/instances/{FAKE_ALIAS}")
            self.assertFalse(state["enabled"])
            self.assertTrue(state["hideOnLogin"])
        finally:
            self.apply(open_fake=True)


if __name__ == "__main__":
    unittest.main()
