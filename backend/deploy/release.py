#!/usr/bin/env python3
"""Release manifest and promotion rules of the Jenkins delivery line.

A release is built once. The manifest pins every image by digest and the web bundle by
SHA-256. Every environment runs the same manifest; nothing is rebuilt between environments.
Design: backend/docs/dagitim/ortamlar.md. Python 3.9+, standard library only.
"""

import argparse
import hashlib
import json
import re
import shutil
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
    "ATONOTA_SSH_USER",
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
# Remote scripts put the release id into paths and commands, so it holds only these characters.
RELEASE_ID = re.compile(r"(?:backend|web)-[0-9a-f]{12}-b[1-9][0-9]*")


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


def check_build(build):
    # bool is a subclass of int in Python; a JSON true must not pass as build 1.
    if type(build) is not int or build < 1:
        raise ReleaseError("build must be a positive Jenkins build number")


def new_manifest(kind, commit, build, components):
    if kind not in REQUIRED:
        raise ReleaseError(f"unknown release kind {kind!r}")
    if not COMMIT.fullmatch(commit or ""):
        raise ReleaseError("commit must be a full 40 character Git hash")
    check_build(build)
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
    check_build(manifest.get("build"))
    if manifest.get("release_id") != release_id(kind, manifest["commit"], manifest["build"]):
        raise ReleaseError("release_id does not match commit and build")
    if not RELEASE_ID.fullmatch(manifest["release_id"]):
        raise ReleaseError("release_id has an unexpected form")
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


def check_same_release(archived, server):
    """The copy on a server must equal the copy Jenkins archived when it built the release."""
    if archived != server:
        raise ReleaseError("the server copy of the release differs from the Jenkins archive")


# Files a release carries beside its manifest (review 2, finding Ö8). Promotion sends exactly
# these copies, so rc and prod run the compose files and scripts of the release commit, not the
# newest main. Paths are relative to backend/deploy.
DEPLOY_PATTERNS = (
    "compose/stack.yaml",
    "compose/edge.yaml",
    "compose/Caddyfile",
    "compose/site.caddy.template",
    "environments/*.env",
    "remote/*",
    "settings/*.production.env.example",
)
# Production setting lists (blocker E-4). remote/apply checks the server against them.
SETTING_LISTS = (
    "tenant", "tenant-db", "tenant-site", "keycloak", "keycloak-db", "identity-sync", "press",
    "press-site", "offsite", "edge",
)
NEEDED = (
    "compose/stack.yaml",
    "compose/edge.yaml",
    "compose/Caddyfile",
    "compose/site.caddy.template",
    "remote/apply",
    "remote/common.sh",
    "remote/backup",
    "remote/restore",
    "remote/status",
    "remote/rollback",
    "remote/settings.py",
    "remote/site-probe.py",
) + tuple(f"environments/{name}.env" for name in ORDER) + tuple(
    f"settings/{name}.production.env.example" for name in SETTING_LISTS
)


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pack_deploy(source, release_folder, commit):
    """Copy the deploy files of one checkout into <release folder>/deploy with a checksum list."""
    if not COMMIT.fullmatch(commit):
        raise ReleaseError(f"bad commit: {commit}")
    source = Path(source)
    out = Path(release_folder) / "deploy"
    if out.exists():
        raise ReleaseError(f"{out} already exists")
    files = {}
    for pattern in DEPLOY_PATTERNS:
        for path in sorted(source.glob(pattern)):
            if path.is_file():
                name = path.relative_to(source).as_posix()
                (out / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, out / name)
                files[name] = sha256_of(path)
    missing = [name for name in NEEDED if name not in files]
    if missing:
        raise ReleaseError(f"deploy files missing in {source}: {', '.join(missing)}")
    write_json({"commit": commit, "files": files}, out / "files.json")


def check_deploy(release_folder):
    """Refuse deploy files that differ from the list written at build time."""
    folder = Path(release_folder) / "deploy"
    listing_path = folder / "files.json"
    if not listing_path.is_file():
        raise ReleaseError(f"the release has no deploy files ({listing_path}); build it again")
    listing = read_json(listing_path)
    files = listing.get("files", {})
    missing = [name for name in NEEDED if name not in files]
    if missing:
        raise ReleaseError(f"deploy files are not listed: {', '.join(missing)}")
    for name, digest in files.items():
        path = folder / name
        if ".." in Path(name).parts or not path.is_file():
            raise ReleaseError(f"deploy file is missing: {name}")
        if sha256_of(path) != digest:
            raise ReleaseError(f"deploy file differs from the build: {name}")
    present = {
        path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()
    } - {"files.json"}
    extra = sorted(present - set(files))
    if extra:
        raise ReleaseError(f"extra deploy files: {', '.join(extra)}")
    manifest = read_json(Path(release_folder) / "release.json")
    # A backend release and its deploy files come from one commit. A web release comes from the
    # atonota-web repository; its deploy files come from this repository at build time.
    if manifest.get("kind") == "backend" and listing.get("commit") != manifest.get("commit"):
        raise ReleaseError(
            f"deploy files are from commit {listing.get('commit')}, the release from {manifest.get('commit')}"
        )


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
    same = commands.add_parser("same-release", help="refuse a server copy that differs from the archive")
    same.add_argument("archived")
    same.add_argument("server")
    field = commands.add_parser("field", help="print one top level field")
    field.add_argument("manifest")
    field.add_argument("name")
    env_check = commands.add_parser("env-check", help="validate every environment file")
    env_check.add_argument("env", choices=ORDER)
    images = commands.add_parser("images", help="print name=image lines")
    images.add_argument("manifest")
    pack = commands.add_parser("pack-deploy", help="copy the deploy files into a release folder")
    pack.add_argument("--from", dest="source", default=str(DEPLOY))
    pack.add_argument("--commit", required=True)
    pack.add_argument("release_folder")
    check_files = commands.add_parser("check-deploy", help="refuse changed or missing deploy files")
    check_files.add_argument("release_folder")
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
        elif arguments.command == "same-release":
            check_same_release(read_json(arguments.archived), read_json(arguments.server))
        elif arguments.command == "field":
            print(read_json(arguments.manifest)[arguments.name])
        elif arguments.command == "env-check":
            load_environments()
        elif arguments.command == "pack-deploy":
            pack_deploy(arguments.source, arguments.release_folder, arguments.commit)
        elif arguments.command == "check-deploy":
            check_deploy(arguments.release_folder)
        elif arguments.command == "images":
            for name, component in sorted(read_json(arguments.manifest)["components"].items()):
                if "image" in component:
                    print(f"{name}={component['image']}")
    except (ReleaseError, KeyError, OSError) as error:
        print(f"release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
