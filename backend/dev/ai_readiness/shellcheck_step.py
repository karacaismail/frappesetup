"""Run the pinned ShellCheck container and return advisory diagnostics."""

import io
import json
import os
import re
import shutil
import subprocess
import tarfile

SHELLCHECK_IMAGE = (
    "koalaman/shellcheck-alpine:v0.11.0"
    "@sha256:9955be09ea7f0dbf7ae942ac1f2094355bb30d96fffba0ec09f5432207544002"
)
CONTEXTS = {"factory": ("--context", "colima-factory"), "default": ("--context", "colima"), "ci": ()}
SHELL_SUFFIXES = {".sh", ".bash", ".bats", ".dash", ".ksh"}
SHELL_HEADER = re.compile(
    rb"^(?:#![^\r\n]*[ /](?:bash|dash|ksh|ash|sh)(?:[ \t\r\n]|$)"
    rb"|#[ \t]*shellcheck[ \t]+shell=(?:bash|dash|ksh|sh|busybox)\b)"
)


def shell_script(path):
    if path.suffix.lower() in SHELL_SUFFIXES:
        return True
    with path.open("rb") as stream:
        return bool(SHELL_HEADER.match(stream.readline(4096)))


def shellcheck_snapshot(root, paths):
    files = {}
    for path in paths:
        if shell_script(path):
            files[f"backend/{path.relative_to(root).as_posix()}"] = path
    snapshot = io.BytesIO()
    if files:
        with tarfile.open(fileobj=snapshot, mode="w") as archive:
            for name, path in sorted(files.items()):
                archive.add(path, arcname=name, recursive=False)
    return files, snapshot.getvalue()


def shellcheck_records(result, files):
    if result.returncode not in {0, 1}:
        return None
    data = json.loads(result.stdout)
    comments = data.get("comments") if isinstance(data, dict) else None
    if not isinstance(comments, list) or bool(comments) != bool(result.returncode):
        return None
    records = []
    for comment in comments:
        filename, line, code, message = (comment[key] for key in ("file", "line", "code", "message"))
        if (
            filename not in files
            or type(line) is not int
            or line < 1
            or type(code) is not int
            or code < 1
            or not isinstance(message, str)
            or not message.strip()
        ):
            return None
        records.append((files[filename], line, f"shellcheck.SC{code}", message))
    return records


def run_shellcheck(root, paths):
    docker = shutil.which("docker")
    context = CONTEXTS.get(os.environ.get("FS_COLIMA_PROFILE", "factory"))
    if not docker or not os.path.isabs(docker) or context is None:
        return None
    try:
        files, snapshot = shellcheck_snapshot(root, paths)
        if not files:
            return None
        result = subprocess.run(
            [
                docker,
                *context,
                "run",
                "--rm",
                "-i",
                "--pull",
                "never",
                "--network",
                "none",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,nodev",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--workdir",
                "/tmp",
                "--entrypoint",
                "/bin/sh",
                SHELLCHECK_IMAGE,
                "-c",
                'tar -xf - && exec shellcheck --norc --format=json1 --source-path=SCRIPTDIR "$@"',
                "shellcheck",
                *sorted(files),
            ],
            input=snapshot,
            capture_output=True,
            check=False,
            timeout=90,
        )
        return shellcheck_records(result, files)
    except (KeyError, OSError, TypeError, ValueError, tarfile.TarError, subprocess.SubprocessError):
        return None
