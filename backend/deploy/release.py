#!/usr/bin/env python3
"""Release manifest and promotion rules of the Jenkins delivery line.

A release is built once. The manifest pins every image by digest and the web bundle by
SHA-256. Every environment runs the same manifest; nothing is rebuilt between environments.
Design: backend/docs/dagitim/ortamlar.md. Python 3.9+, standard library only.
"""

import argparse
import json
import re
import sys
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent
ORDER = ("alpha", "beta", "rc", "prod")
REQUIRED = {
    "backend": ("tenant", "keycloak", "identity-sync", "press"),
    "web": ("panel",),
}
ENV_KEYS = {
    "ATONOTA_ENV",
    "ATONOTA_PREVIOUS_ENV",
    "ATONOTA_SSH_HOST",
    "ATONOTA_BASE_HOST",
    "ATONOTA_ID_HOST",
    "ATONOTA_PRESS_HOST",
    "ATONOTA_TENANT_ZONE",
    "ATONOTA_TENANT_SITES",
    "ATONOTA_REQUIRE_ALL_COMPONENTS",
    "ATONOTA_REQUIRE_OFFSITE_BACKUP",
    "ATONOTA_AUTO_RESTORE_ON_FAILURE",
}
SECRET_KEY = re.compile(r"(?:^|_)(?:SECRET|PASSWORD|TOKEN|KEY)(?:_|$)")
COMMIT = re.compile(r"[0-9a-f]{40}")
IMAGE = re.compile(r"[a-z0-9.-]+(?::[0-9]+)?/[a-z0-9._/-]+@sha256:[0-9a-f]{64}")
SHA256 = re.compile(r"[0-9a-f]{64}")
WEB_FILE = re.compile(r"atonota-web-[0-9a-f]{12}\.tar\.gz")


class ReleaseError(ValueError):
    """A manifest, an environment file or a promotion breaks a delivery rule."""


def parse_env_file(path):
    settings = {}
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in ENV_KEYS:
            raise ReleaseError(f"{path}:{number}: unknown setting {key!r}")
        settings[key] = value
    return settings


def load_environments(folder=DEPLOY / "environments"):
    environments = {}
    for name in ORDER:
        settings = parse_env_file(Path(folder) / f"{name}.env")
        missing = ENV_KEYS - settings.keys()
        if missing or settings["ATONOTA_ENV"] != name:
            raise ReleaseError(f"{name}.env is incomplete: {sorted(missing)}")
        environments[name] = settings
    return environments


def release_id(kind, commit, build):
    return f"{kind}-{commit[:12]}-b{build}"


def new_manifest(kind, commit, build, components):
    if kind not in REQUIRED:
        raise ReleaseError(f"unknown release kind {kind!r}")
    if not COMMIT.fullmatch(commit or ""):
        raise ReleaseError("commit must be a full 40 character Git hash")
    if not isinstance(build, int) or build < 1:
        raise ReleaseError("build must be a positive Jenkins build number")
    return {
        "schema": 1,
        "kind": kind,
        "release_id": release_id(kind, commit, build),
        "commit": commit,
        "build": build,
        "components": components,
    }


def check_component(kind, name, component):
    if kind == "backend":
        if set(component) != {"image"} or not IMAGE.fullmatch(component["image"]):
            raise ReleaseError(f"{name}: image must be pinned by digest (name@sha256:...)")
    elif set(component) != {"file", "sha256"} or not (
        WEB_FILE.fullmatch(component["file"]) and SHA256.fullmatch(component["sha256"])
    ):
        raise ReleaseError(f"{name}: web bundle needs a file name and its SHA-256")


def check_manifest(manifest, environment):
    if environment not in ORDER:
        raise ReleaseError(f"unknown environment {environment!r}")
    if manifest.get("schema") != 1 or manifest.get("kind") not in REQUIRED:
        raise ReleaseError("unknown manifest schema or kind")
    kind = manifest["kind"]
    if not COMMIT.fullmatch(str(manifest.get("commit", ""))):
        raise ReleaseError("commit must be a full 40 character Git hash")
    if manifest.get("release_id") != release_id(kind, manifest["commit"], manifest.get("build")):
        raise ReleaseError("release_id does not match commit and build")
    components = manifest.get("components")
    if not isinstance(components, dict) or not components:
        raise ReleaseError("manifest has no component")
    unknown = set(components) - set(REQUIRED[kind])
    if unknown:
        raise ReleaseError(f"unknown components: {sorted(unknown)}")
    for name, component in components.items():
        check_component(kind, name, component)
    strict = load_environments()[environment]["ATONOTA_REQUIRE_ALL_COMPONENTS"] == "1"
    missing = [name for name in REQUIRED[kind] if name not in components]
    if strict and missing:
        raise ReleaseError(f"{environment} needs every component; missing: {', '.join(missing)}")


def health_record(manifest, environment):
    return {
        "environment": environment,
        "kind": manifest["kind"],
        "release_id": manifest["release_id"],
        "healthy": True,
    }


def check_promotion(manifest, target, source_record):
    """Allow only the release that is current and healthy in the previous environment."""
    if target not in ORDER or target == "alpha":
        raise ReleaseError("alpha is filled from main only; promotion targets are beta, rc, prod")
    source = load_environments()[target]["ATONOTA_PREVIOUS_ENV"]
    if source_record.get("environment") != source:
        raise ReleaseError(f"{target} takes releases only from {source}")
    if source_record.get("kind") != manifest["kind"]:
        raise ReleaseError("source record belongs to another release kind")
    if source_record.get("release_id") != manifest["release_id"]:
        raise ReleaseError(
            f"{source} runs release {source_record.get('release_id')!r}, not {manifest['release_id']!r}"
        )
    if source_record.get("healthy") is not True:
        raise ReleaseError(f"{source} health check has not passed for this release")
    check_manifest(manifest, target)


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseError(f"cannot read {path}: {error}") from error


def write_json(data, path):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="write a release manifest")
    new.add_argument("--kind", required=True, choices=sorted(REQUIRED))
    new.add_argument("--commit", required=True)
    new.add_argument("--build", required=True, type=int)
    new.add_argument("--image", action="append", default=[], help="name=registry/repo@sha256:...")
    new.add_argument("--web-file")
    new.add_argument("--web-sha256")
    new.add_argument("--out", required=True)
    check = commands.add_parser("check", help="validate a manifest for one environment")
    check.add_argument("manifest")
    check.add_argument("--env", required=True)
    record = commands.add_parser("record", help="write the health record after a passed check")
    record.add_argument("manifest")
    record.add_argument("--env", required=True)
    record.add_argument("--out", required=True)
    promote = commands.add_parser("promote-check", help="refuse a promotion that breaks the order")
    promote.add_argument("manifest")
    promote.add_argument("--target", required=True)
    promote.add_argument("--source-record", required=True)
    field = commands.add_parser("field", help="print one top level field")
    field.add_argument("manifest")
    field.add_argument("name")
    env_check = commands.add_parser("env-check", help="validate every environment file")
    env_check.add_argument("env", choices=ORDER)
    images = commands.add_parser("images", help="print name=image lines")
    images.add_argument("manifest")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "new":
            components = {}
            for item in arguments.image:
                name, _, reference = item.partition("=")
                components[name] = {"image": reference}
            if arguments.web_file:
                components["panel"] = {"file": arguments.web_file, "sha256": arguments.web_sha256 or ""}
            manifest = new_manifest(arguments.kind, arguments.commit, arguments.build, components)
            check_manifest(manifest, "alpha")
            write_json(manifest, arguments.out)
        elif arguments.command == "check":
            check_manifest(read_json(arguments.manifest), arguments.env)
        elif arguments.command == "record":
            manifest = read_json(arguments.manifest)
            check_manifest(manifest, arguments.env)
            write_json(health_record(manifest, arguments.env), arguments.out)
        elif arguments.command == "promote-check":
            check_promotion(
                read_json(arguments.manifest), arguments.target, read_json(arguments.source_record)
            )
        elif arguments.command == "field":
            print(read_json(arguments.manifest)[arguments.name])
        elif arguments.command == "env-check":
            load_environments()
        elif arguments.command == "images":
            for name, component in sorted(read_json(arguments.manifest)["components"].items()):
                if "image" in component:
                    print(f"{name}={component['image']}")
    except (ReleaseError, KeyError) as error:
        print(f"release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
