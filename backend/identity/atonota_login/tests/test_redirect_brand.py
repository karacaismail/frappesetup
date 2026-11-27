"""Offline CLI regressions for the shared brand and deployment environment contract."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PRODUCT = Path(__file__).resolve().parents[1]
BACKEND = PRODUCT.parents[1]


class BrandRedirectTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.backend = self.root / "backend"
        product = self.backend / "identity" / "atonota_login"
        for folder in ("bin", "atonota_login", "platforms"):
            shutil.copytree(PRODUCT / folder, product / folder,
                            ignore=shutil.ignore_patterns("__pycache__"))
        deploy = self.backend / "deploy"
        shutil.copytree(BACKEND / "deploy" / "environments", deploy / "environments")
        for name in ("release.py", "brand.py"):
            shutil.copy2(BACKEND / "deploy" / name, deploy / name)
        self.brand = self.backend / "brand.env"
        self.brand.write_text("PRODUCT_NAME=Example Login\nBRAND_DOMAIN=example.test\n", encoding="utf-8")
        self.command = product / "bin" / "atonota-login"
        self.aliases = {json.loads(path.read_text())["alias"] for path in (product / "platforms").glob("*.json")}

    def run_command(self, *arguments):
        return subprocess.run(
            [sys.executable, "-I", str(self.command), "redirects", *arguments, "--json"],
            cwd=self.root, capture_output=True, text=True, check=False,
        )

    def test_environment_redirects_follow_the_shared_brand(self):
        # The contract uses the environment label before the root domain; prod has no label.
        for name in ("alpha", "beta", "rc", "prod", "all"):
            with self.subTest(environment=name):
                result = self.run_command("--env", name)
                self.assertEqual(result.returncode, 0, result.stderr)
                names = ("alpha", "beta", "rc", "prod") if name == "all" else (name,)
                expected = {}
                for environment in names:
                    base = "example.test" if environment == "prod" else f"{environment}.example.test"
                    for alias in self.aliases:
                        expected[f"{environment} {alias}"] = (
                            f"https://api.login.{base}/realms/platform/broker/{alias}/endpoint"
                        )
                self.assertEqual(json.loads(result.stdout), expected)

    def test_invalid_brand_is_refused_without_a_traceback(self):
        for content in ("PRODUCT_NAME=Example Login\n", "PRODUCT_NAME=Example Login\nBRAND_DOMAIN=https://example.test\n"):
            with self.subTest(content=content):
                self.brand.write_text(content, encoding="utf-8")
                result = self.run_command("--env", "alpha")
                self.assertEqual(result.returncode, 1)
                self.assertIn("BRAND_DOMAIN", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_invalid_environment_label_is_refused_without_a_traceback(self):
        path = self.backend / "deploy" / "environments" / "alpha.env"
        path.write_text(path.read_text().replace("ATONOTA_HOST_LABEL=alpha", "ATONOTA_HOST_LABEL=other"))
        result = self.run_command("--env", "alpha")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ATONOTA_HOST_LABEL", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_missing_brand_is_refused_but_local_redirects_still_work(self):
        self.brand.unlink()
        result = self.run_command("--env", "alpha")
        self.assertEqual(result.returncode, 1)
        self.assertIn("brand.env", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")
        result = self.run_command("--public-url", "http://identity.localhost:5280")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            alias: f"http://identity.localhost:5280/realms/platform/broker/{alias}/endpoint"
            for alias in self.aliases
        })
