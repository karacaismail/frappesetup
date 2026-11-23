"""Tests for the Press production image and its place in the release (blocker E-2).

Design: backend/docs/dagitim/ortamlar.md and backend/docs/dagitim/press-imaji.md.
These tests read files and run bin/build-release with a fake docker; they need only bash.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
BACKEND = DEPLOY.parent
IMAGES = DEPLOY / "images"
PATCHES = IMAGES / "press-patches"
sys.path.insert(0, str(DEPLOY))

import release  # noqa: E402

PRESS_COMMIT = "7a4384d5eec9f0f0dce4124e9dd48b106e51222f"
COMMIT = "0123456789abcdef0123456789abcdef01234567"

FAKE_DOCKER = r"""#!/usr/bin/env bash
{ printf 'docker'; printf '\t%s' "$@"; printf '\n'; } >>"$FAKE_LOG"
if [[ "$1" == image && "$2" == inspect ]]; then
    reference="${@: -1}"
    printf '%s@sha256:%064d\n' "${reference%:*}" 7
fi
exit 0
"""


def dockerfile():
    return (IMAGES / "press.Dockerfile").read_text()


def instructions():
    """The Dockerfile without its comment lines."""
    return "\n".join(line for line in dockerfile().splitlines() if not line.lstrip().startswith("#"))


def base_image(text):
    return re.findall(r"^FROM (\S+)", text, re.M)


def requirement_names(text):
    names = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line and re.match(r"[A-Za-z0-9]", line):
            names.add(re.split(r"[<>=~!; \[]", line, maxsplit=1)[0].lower().replace("_", "-"))
    return names


def service_networks(text):
    """Networks of every service in stack.yaml; a service without its own list takes the anchor's.

    The file uses two forms: "networks: [a, b]" and a block of "<name>: {...}" lines below it.
    """
    def networks(block, indent):
        inline = re.search(rf"^{indent}networks: \[(.*?)\]$", block, re.M)
        if inline:
            return {name.strip() for name in inline.group(1).split(",") if name.strip()}
        nested = re.search(rf"^{indent}networks:\n((?:{indent}  \S.*\n)+)", block, re.M)
        if nested:
            return set(re.findall(rf"^{indent}  ([a-z0-9-]+):", nested.group(1), re.M))
        return None

    anchors = {}
    for match in re.finditer(r"^x-(\w+): &\1\n((?:  .*\n)+)", text, re.M):
        anchors[match.group(1)] = networks(match.group(2), "  ")
    services = text.split("\nservices:\n", 1)[1].split("\nvolumes:\n", 1)[0] + "\n"
    result = {}
    for match in re.finditer(r"^  ([a-z0-9-]+):\n((?:(?:    .*)?\n)*)", services, re.M):
        name, block = match.groups()
        own = networks(block, "    ")
        merged = re.search(r"^    <<: \*(\w+)$", block, re.M)
        result[name] = own if own is not None else anchors[merged.group(1)] if merged else set()
    return result

class PressDockerfile(unittest.TestCase):
    def test_base_is_the_pinned_tenant_base(self):
        tenant = base_image((IMAGES / "tenant.Dockerfile").read_text())
        self.assertEqual(set(base_image(dockerfile())), set(tenant))
        for reference in base_image(dockerfile()):
            self.assertRegex(reference, r"@sha256:[0-9a-f]{64}$")

    def test_press_source_is_the_pinned_commit(self):
        text = dockerfile()
        self.assertIn("ARG PRESS_TAG=v0.154.1", text)
        self.assertIn(f"ARG PRESS_COMMIT={PRESS_COMMIT}", text)
        self.assertIn('test "$(git -C apps/press rev-parse HEAD)" = "$PRESS_COMMIT"', text)

    def test_every_patch_is_checked_before_it_is_applied(self):
        text = dockerfile()
        self.assertRegex(text, r'git -C apps/press apply --check "\$patch" && git -C apps/press apply "\$patch" \|\| exit 1')

    def test_development_patch_never_enters_the_image(self):
        # O-18: patch-py314.sh and the development marker stay in the development image.
        text = instructions()
        for forbidden in ("patch-py314", "development-image", "dev/press", "UV_OVERRIDE"):
            self.assertNotIn(forbidden, text)
        ignore = (IMAGES / "press.Dockerfile.dockerignore").read_text()
        self.assertNotIn("!dev", ignore)

    def test_no_secret_and_no_site_enters_the_image(self):
        ignore = (IMAGES / "press.Dockerfile.dockerignore").read_text().splitlines()
        self.assertEqual(ignore[0], "**")
        self.assertIn("**/.env*", ignore)
        text = instructions()
        for forbidden in ("site_config.json", "new-site", "PASSWORD", "TOKEN", "SECRET"):
            self.assertNotIn(forbidden, text)

    def test_packages_come_from_the_hashed_lock_and_pass_the_check(self):
        text = dockerfile()
        self.assertIn('--no-deps --require-hashes -r "$lock"', text)
        self.assertIn("uv pip check", text)
        self.assertIn("press-pip-check.allowed", text)
        self.assertRegex(text, r"\| diff -u - /tmp/press-deps/pip-check.txt")

    def test_press_tr_and_assets_are_built_in(self):
        text = dockerfile()
        self.assertIn("COPY --chown=1000:0 apps/press_tr /home/frappe/frappe-bench/apps/press_tr", text)
        self.assertIn("bundle('production', apps='press,press_tr')", text)
        self.assertIn("compile_translations(app) for app in ('press', 'press_tr')", text)
        # The build skips the after_build hook runner only while no app declares such a hook.
        self.assertIn("! grep -lE '^[[:space:]]*after_(app_)?build[[:space:]]*(\\+?=|:)' apps/*/*/hooks.py", text)
        self.assertIn("('desk.bundle.js', 'erpnext.bundle.js', 'press.bundle.js')", text)
        self.assertIn("ARG UV_NO_CACHE=1", text)
        self.assertIn("printf '\\npress\\npress_tr\\n' >> sites/apps.txt", text)

    def test_build_tools_leave_the_image(self):
        final = dockerfile().split(" AS press\n", 1)[1]
        self.assertNotIn("apt-get", final)
        self.assertNotIn("go.dev", final)
        self.assertIn("rm -rf apps/press/node_modules apps/press/dashboard/node_modules", final)


    def test_arm64_source_build_runs_only_for_a_local_trial(self):
        # Review 1, finding 2: on arm64 the dockerfile sdist fetches Go code without a pinned
        # version. That build is allowed only with PRESS_LOCAL_ARM64_TRIAL=1; build-release never
        # sets it, so a release image never carries the unpinned Go code.
        stage = dockerfile().split(" AS dockerfile-wheel\n", 1)[1].split("\nFROM ", 1)[0]
        self.assertIn("ARG PRESS_LOCAL_ARM64_TRIAL=0", stage)
        gate = stage.index('[ "$PRESS_LOCAL_ARM64_TRIAL" = 1 ] || {')
        self.assertLess(gate, stage.index("apt-get update"))
        self.assertLess(gate, stage.index("curl "))
        self.assertNotIn("PRESS_LOCAL_ARM64_TRIAL", (DEPLOY / "bin" / "build-release").read_text())

class PatchSeries(unittest.TestCase):
    def patches(self):
        return sorted(PATCHES.glob("*.patch"))

    def test_patches_are_numbered_in_order(self):
        names = [path.name for path in self.patches()]
        self.assertGreaterEqual(len(names), 1)
        self.assertEqual([name[:4] for name in names], [f"{number:04d}" for number in range(1, len(names) + 1)])

    def test_each_patch_states_purpose_upstream_link_and_removal(self):
        for path in self.patches():
            header = path.read_text().split("diff --git", 1)[0]
            with self.subTest(patch=path.name):
                self.assertIn("Purpose:", header)
                self.assertIn("Upstream:", header)
                self.assertIn("press-python314-upstream.md", header)
                self.assertIn("Remove when", header)
                self.assertIn("O-52", header)

    def test_patches_never_touch_frappe_or_tests(self):
        for path in self.patches():
            for target in re.findall(r"^\+\+\+ b/(\S+)", path.read_text(), re.M):
                with self.subTest(patch=path.name, target=target):
                    self.assertFalse(target.startswith(("frappe/", "apps/")), target)
                    self.assertNotRegex(target, r"(^|/)test_[^/]*\.py$")

    def test_license_note_keeps_agpl(self):
        note = (PATCHES / "README.md").read_text()
        self.assertIn("AGPL-3.0", note)

    def test_record_links_the_new_decision_to_o18(self):
        record = (BACKEND / "PROJECT-RECORD.md").read_text()
        decision = re.search(r"^- \*\*O-52\..*?(?=^- \*\*O-|^## )", record, re.M | re.S)
        self.assertIsNotNone(decision)
        for term in ("O-18", "M-4", "press-patches"):
            self.assertIn(term, decision.group(0))
        self.assertIn("O-18", record)


class PressLock(unittest.TestCase):
    def test_lock_pins_every_requirement_with_hashes(self):
        lock = (IMAGES / "press-requirements.lock.txt").read_text()
        pins = {}
        for match in re.finditer(r"^([A-Za-z0-9_.-]+)==(\S+)", lock, re.M):
            pins[match.group(1).lower().replace("_", "-")] = match.group(2)
        wanted = requirement_names((IMAGES / "press-requirements.in").read_text())
        self.assertEqual(wanted - set(pins), set())
        for entry in re.split(r"\n(?=[A-Za-z0-9])", lock):
            if re.match(r"[A-Za-z0-9]", entry):
                with self.subTest(entry=entry.split(" ", 1)[0]):
                    self.assertIn("--hash=sha256:", entry)

    def test_lock_covers_press_tr_requirements(self):
        metadata = (BACKEND / "apps/press_tr/pyproject.toml").read_text()
        block = re.search(r"(?ms)^dependencies = \[(.*?)\]", metadata).group(1)
        needed = requirement_names(block.replace('"', "").replace(",", "\n")) - {"oidc-verify"}
        self.assertEqual(needed - requirement_names((IMAGES / "press-requirements.in").read_text()), set())

    def test_telegram_client_is_not_installed(self):
        # Patch 0004: python-telegram-bot 13 cannot be imported on Python 3.12 and later.
        lock = (IMAGES / "press-requirements.lock.txt").read_text()
        self.assertNotIn("python-telegram-bot", lock)

    def test_allowed_check_lines_are_explained(self):
        allowed = (IMAGES / "press-pip-check.allowed").read_text().splitlines()
        lines = [line for line in allowed if line and not line.startswith("#")]
        self.assertTrue(lines)
        for line in lines:
            self.assertRegex(line, r"^The package `frappe-mcp` requires ")


class ReleaseCarriesPress(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        fake_bin = self.folder / "bin"
        fake_bin.mkdir()
        (fake_bin / "docker").write_text(FAKE_DOCKER)
        (fake_bin / "docker").chmod(0o755)
        self.log = self.folder / "calls.log"
        self.environment = {
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_LOG": str(self.log),
            "GIT_COMMIT": COMMIT,
            "BUILD_NUMBER": "42",
        }

    def build_release(self):
        out = self.folder / "out" / "release.json"
        result = subprocess.run(
            [str(DEPLOY / "bin" / "build-release"), str(out)],
            env=self.environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(out.read_text())

    def test_release_json_holds_the_press_image_by_digest(self):
        manifest = self.build_release()
        self.assertIn("press", manifest["components"])
        self.assertRegex(
            manifest["components"]["press"]["image"],
            r"^ghcr\.io/karacaismail/atonota-press@sha256:[0-9a-f]{64}$",
        )
        self.assertEqual(set(manifest["components"]), set(release.REQUIRED["backend"]))

    def test_apply_and_health_decide_on_press_the_same_way(self):
        # Press runs only with its image in the release and ATONOTA_PRESS_ENABLED=1 (review B1, M2).
        apply = (DEPLOY / "remote" / "apply").read_text()
        health = (DEPLOY / "bin" / "health").read_text()
        rule = 'press_on "$ATONOTA_PRESS_ENABLED"'
        self.assertIn(rule, apply)
        self.assertIn(rule, health)
        self.assertNotIn("grep -q '^ATONOTA_IMAGE_PRESS='", apply)

    def test_press_is_built_from_the_backend_folder(self):
        self.build_release()
        builds = [line.split("\t") for line in self.log.read_text().splitlines() if line.startswith("docker\tbuild")]
        press = [call for call in builds if str(IMAGES / "press.Dockerfile") in call]
        self.assertEqual(len(press), 1)
        self.assertEqual(press[0][-1], str(BACKEND))


    def test_every_release_image_is_built_for_amd64(self):
        # Review 1, finding 2 and E-15: the release images are built for linux/amd64 on any build
        # agent, so an arm64 agent cannot produce a different Press image from the same commit.
        self.build_release()
        builds = [line.split("\t") for line in self.log.read_text().splitlines() if line.startswith("docker\tbuild")]
        self.assertEqual(len(builds), len(release.REQUIRED["backend"]))
        for call in builds:
            with self.subTest(dockerfile=call[call.index("--file") + 1]):
                self.assertEqual(call[call.index("--platform") + 1], "linux/amd64")

class StackServesPress(unittest.TestCase):
    def stack(self):
        return (DEPLOY / "compose" / "stack.yaml").read_text()

    def test_press_services_use_the_release_image(self):
        text = self.stack()
        for service in ("press-web", "press-worker", "press-frontend"):
            block = re.search(rf"^  {service}:\n(.*?)(?=^  \S|^\S)", text, re.M | re.S)
            self.assertIsNotNone(block, service)
            self.assertRegex(text, r"x-press: &press\n  image: \$\{ATONOTA_IMAGE_PRESS")
            self.assertIn("<<: *press", block.group(1))
            self.assertIn("profiles: [press]", block.group(1))

    def test_only_the_press_frontend_joins_the_edge(self):
        text = self.stack()
        self.assertEqual(text.count('aliases: ["${ATONOTA_ENV:?}-press"]'), 1)
        frontend = re.search(r"^  press-frontend:\n(.*?)(?=^  \S|^\S)", text, re.M | re.S).group(1)
        self.assertIn('aliases: ["${ATONOTA_ENV:?}-press"]', frontend)
        self.assertNotIn("ports:", text)

    def test_press_has_its_own_queue(self):
        # Both benches live in /home/frappe/frappe-bench, so a shared Redis queue would let the
        # tenant worker take Press jobs.
        text = self.stack()
        self.assertIn("  press-redis-queue:", text)
        self.assertIn("  press-redis-cache:", text)

    def test_press_has_its_own_network(self):
        # Review 1, finding 1: a tenant container must not reach the Press Redis queue or
        # press-web:8000 past the front proxy. Press services join only press-internal; the
        # database joins both networks; press-frontend joins the edge as well.
        text = self.stack()
        networks = service_networks(text)
        self.assertRegex(text, r"(?m)^networks:\n(?:  .*\n)*  press-internal: \{\}")
        press = {name for name in networks if name.startswith("press-")}
        self.assertEqual(press, {"press-redis-cache", "press-redis-queue", "press-web", "press-worker",
                                 "press-socket", "press-frontend"})
        for name in press:
            with self.subTest(service=name):
                self.assertNotIn("internal", networks[name])
                self.assertIn("press-internal", networks[name])
        self.assertEqual(networks["press-frontend"], {"press-internal", "edge"})
        self.assertEqual(networks["press-web"], {"press-internal", "press-identity"})
        self.assertEqual(networks["tenant-db"], {"internal", "press-internal"})
        for name in set(networks) - press - {"tenant-db"}:
            with self.subTest(service=name):
                self.assertNotIn("press-internal", networks[name])
                self.assertTrue(networks[name])

    def test_press_reaches_identity_sync_only_on_a_closed_network(self):
        # Review 2, finding 1: Press left the network "internal", so the only way left to reach
        # identity-sync was a public address. The deletion and session revocation endpoints must
        # not reach the edge. press-web and identity-sync share a network without a gateway.
        text = self.stack()
        networks = service_networks(text)
        top = text.split("\nnetworks:\n")[-1]
        self.assertRegex(top, r"(?m)^  press-identity: \{internal: true\}$")
        members = {name for name, nets in networks.items() if "press-identity" in nets}
        self.assertEqual(members, {"press-web", "identity-sync"})
        self.assertEqual(networks["identity-sync"], {"internal", "press-identity"})
        self.assertNotIn("press-internal", networks["identity-sync"])
        edge = {name for name, nets in networks.items() if "edge" in nets}
        self.assertEqual(edge, {"tenant-frontend", "keycloak", "press-frontend"})
        for name in ("site.caddy.template", "Caddyfile", "edge.yaml"):
            with self.subTest(edge_file=name):
                edge_text = (DEPLOY / "compose" / name).read_text()
                self.assertNotIn("identity-sync", edge_text)
                self.assertNotIn("6115", edge_text)
                self.assertNotIn("/v1/", edge_text)
        self.assertNotIn("identity-sync by their public HTTPS addresses", text)
        settings = (DEPLOY / "settings" / "press-site.production.env.example").read_text()
        self.assertRegex(settings, r"(?m)^identity_sync_url=http://identity-sync:6115$")

    def test_edge_sends_the_press_host_to_the_press_frontend(self):
        template = (DEPLOY / "compose" / "site.caddy.template").read_text()
        block = re.search(r"__PRESS_HOST__ \{\n(.*?)\n\}", template, re.S).group(1)
        self.assertIn("reverse_proxy __ENV__-press:8080", block)


if __name__ == "__main__":
    unittest.main()
