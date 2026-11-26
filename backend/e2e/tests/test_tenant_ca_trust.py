"""A recreated tenant container trusts the stack's HTTPS relay without a manual step (AJA-936).

The tenant reaches Keycloak and identity-sync through the relay on https://identity-sync:9444.
session-tls.sh trusts the relay's certificate in the running container only. Compose recreates
the container from the image, so that trust is lost. The tenant services therefore build their
CA bundle at every start from the image's bundle and the relay certificate kept in the sites volume.
"""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
COMPOSE = BACKEND / "dev/compose.tenant.yaml"
SESSION_TLS = BACKEND / "e2e/preview/session-tls.sh"
TRUST_FILE = "sites/.e2e-trust/identity-sync.crt"
SYSTEM = "-----BEGIN CERTIFICATE-----\nSYSTEM\n-----END CERTIFICATE-----\n"
RELAY = "-----BEGIN CERTIFICATE-----\nRELAY\n-----END CERTIFICATE-----\n"


def anchor_block():
    text = COMPOSE.read_text()
    match = re.search(r"^x-tenant: &tenant\n((?:  .*\n|\n)+?)(?=^\S)", text, re.M)
    if not match:
        raise AssertionError("compose.tenant.yaml has no x-tenant anchor.")
    return match.group(1)


def anchor_entrypoint():
    match = re.search(r"^  entrypoint: (\[.*\])$", anchor_block(), re.M)
    if not match:
        raise AssertionError("The x-tenant anchor has no one-line entrypoint list.")
    return json.loads(match.group(1))


def run_entrypoint(workdir, environment):
    # Compose turns $$ into $ before the shell runs the entrypoint.
    entrypoint = [part.replace("$$", "$") for part in anchor_entrypoint()]
    # The image's own entrypoint links assets. Replace it with a probe that reports the bundle.
    probe = ["sh", "-c", 'printf "%s\\n" "$REQUESTS_CA_BUNDLE" "$SSL_CERT_FILE"; cat "$REQUESTS_CA_BUNDLE"']
    command = [*entrypoint[:-1], *probe]
    return subprocess.run(
        command, cwd=workdir, env=environment, capture_output=True, text=True, check=False
    )


class TenantCaTrustTest(unittest.TestCase):
    def test_tenant_services_point_python_and_openssl_at_the_built_bundle(self):
        block = anchor_block()
        values = {
            key: re.search(rf"^    {key}: (\S+)$", block, re.M) for key in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE")
        }
        self.assertTrue(all(values.values()), "Both CA settings must sit in the x-tenant environment.")
        bundle = Path(values["REQUESTS_CA_BUNDLE"].group(1))
        self.assertEqual(Path(values["SSL_CERT_FILE"].group(1)), bundle)
        # The bundle is rebuilt in the container, outside the shared sites volume.
        self.assertTrue(bundle.is_absolute())
        self.assertEqual(bundle.parent.name, "tmp")

    def test_entrypoint_keeps_the_image_entrypoint_last(self):
        entrypoint = anchor_entrypoint()
        self.assertEqual(entrypoint[:2], ["sh", "-c"])
        self.assertEqual(entrypoint[-1], "/usr/local/bin/entrypoint.sh")

    def test_start_adds_the_kept_relay_certificate_to_the_bundle(self):
        with tempfile.TemporaryDirectory() as workdir:
            root = Path(workdir)
            (root / "system.crt").write_text(SYSTEM)
            (root / TRUST_FILE).parent.mkdir(parents=True)
            (root / TRUST_FILE).write_text(RELAY)
            bundle = root / "bundle.crt"
            environment = {
                "PATH": os.environ["PATH"],
                "FS_SYSTEM_CA_BUNDLE": str(root / "system.crt"),
                "REQUESTS_CA_BUNDLE": str(bundle),
                "SSL_CERT_FILE": str(bundle),
            }
            result = run_entrypoint(workdir, environment)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.startswith(f"{bundle}\n{bundle}\n"))
            content = bundle.read_text()
            self.assertIn("SYSTEM", content)
            self.assertIn("RELAY", content)
            self.assertLess(content.index("SYSTEM"), content.index("RELAY"))

    def test_start_without_a_relay_certificate_keeps_the_image_bundle(self):
        with tempfile.TemporaryDirectory() as workdir:
            root = Path(workdir)
            (root / "system.crt").write_text(SYSTEM)
            bundle = root / "bundle.crt"
            environment = {
                "PATH": os.environ["PATH"],
                "FS_SYSTEM_CA_BUNDLE": str(root / "system.crt"),
                "REQUESTS_CA_BUNDLE": str(bundle),
                "SSL_CERT_FILE": str(bundle),
            }
            result = run_entrypoint(workdir, environment)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(bundle.read_text().strip(), SYSTEM.strip())

    def test_session_tls_keeps_the_certificate_in_the_sites_volume(self):
        """Without this copy a recreated container has nothing to trust."""
        script = SESSION_TLS.read_text()
        self.assertIn(TRUST_FILE, script)
        self.assertIn("update-ca-certificates", script)


if __name__ == "__main__":
    unittest.main()
