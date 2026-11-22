"""Merge review findings E1 and O7: the production image carries its own safe defaults.

E1: the magic link extension's REST resource and its cross-device authenticator are off by the image's
default configuration (conf/keycloak.conf), not only by the development compose file.
O7: plain HTTP for signed events is off in the production image. Only the development image carries
the fixed host list (contract section 11).

The live part runs against a container started from the "prod" target by `bin/kc-dev.sh prod-check`.
"""

from __future__ import annotations

import os
import re
import unittest

from yardimci import KLASOR, istek

DOCKERFILE = (KLASOR / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (KLASOR.parents[1] / "dev" / "compose.keycloak.yaml").read_text(encoding="utf-8")
CONF = KLASOR / "conf" / "keycloak.conf"
HOSTS = KLASOR / "conf" / "webhook-plain-http-hosts.txt"
MAGIC_LINK_OFF = (
    "spi-realm-restapi-extension--magiclink-login--enabled=false",
    "spi-authenticator--magiclink-continuation--enabled=false",
)
MAGIC_LINK_REST_PATH = "magiclink-login"
MAGIC_LINK_CONTINUATION = "magiclink-continuation"


def _stage(name: str) -> str:
    match = re.search(rf"FROM [^\n]+ AS {name}\n(.*?)(?=\nFROM |\Z)", DOCKERFILE, re.S)
    if match is None:
        raise AssertionError(f"stage {name} is missing")
    return match.group(1)


class ProductionImageFileTest(unittest.TestCase):
    def test_production_configuration_turns_the_magic_link_side_doors_off(self):
        lines = {line.strip() for line in CONF.read_text(encoding="utf-8").splitlines()}
        for line in MAGIC_LINK_OFF:
            self.assertIn(line, lines)
        self.assertIn("COPY --chown=1000:0 conf/keycloak.conf /opt/keycloak/conf/keycloak.conf", _stage("prod"))

    def test_compose_does_not_carry_the_only_copy_of_the_setting(self):
        self.assertNotIn("MAGICLINK_LOGIN__ENABLED", COMPOSE)
        self.assertNotIn("MAGICLINK_CONTINUATION__ENABLED", COMPOSE)

    def test_plain_http_list_is_only_in_the_development_image(self):
        self.assertNotIn("webhook-plain-http-hosts.txt", _stage("prod"))
        self.assertIn("COPY --chown=1000:0 conf/webhook-plain-http-hosts.txt "
                      "/opt/keycloak/conf/webhook-plain-http-hosts.txt", _stage("dev"))
        hosts = [line.strip() for line in HOSTS.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#")]
        self.assertEqual(hosts, ["event-sink.localhost"])


PROD_URL = os.environ.get("PROD_KC_URL", "")


@unittest.skipUnless(PROD_URL, "PROD_KC_URL yok. Testi bin/kc-dev.sh prod-check ile çalıştırın.")
class ProductionImageLiveTest(unittest.TestCase):
    def _admin_token(self) -> str:
        response = istek("POST", f"{PROD_URL}/realms/master/protocol/openid-connect/token", form={
            "grant_type": "password", "client_id": "admin-cli",
            "username": os.environ["KC_BOOTSTRAP_ADMIN_USERNAME"],
            "password": os.environ["KC_BOOTSTRAP_ADMIN_PASSWORD"]})
        self.assertEqual(response.durum, 200, response.govde[:200])
        return response.json()["access_token"]

    def test_rest_resource_answers_404(self):
        sample = "00000000-0000-4000-8000-000000000000"
        response = istek("GET", f"{PROD_URL}/realms/platform/{MAGIC_LINK_REST_PATH}?id={sample}&magicKey={sample}")
        self.assertEqual(response.durum, 404)

    def test_cross_device_authenticator_is_not_loaded(self):
        providers = istek("GET", f"{PROD_URL}/admin/serverinfo", belirtec=self._admin_token()).json()["providers"]
        self.assertIn("magiclink", providers["authenticator"]["providers"])
        self.assertNotIn(MAGIC_LINK_CONTINUATION, providers["authenticator"]["providers"])

    def test_webhook_listener_is_loaded(self):
        providers = istek("GET", f"{PROD_URL}/admin/serverinfo", belirtec=self._admin_token()).json()["providers"]
        self.assertIn("webhook", providers["eventsListener"]["providers"])

    def test_production_image_refused_a_plain_http_event_address(self):
        # bin/kc-dev.sh prod-check first starts the prod image with a plain HTTP address and records
        # whether Keycloak refused to start.
        self.assertEqual(os.environ.get("PROD_HTTP_REFUSED"), "yes",
                         "the prod image must not start with a plain HTTP event address")


if __name__ == "__main__":
    unittest.main()
