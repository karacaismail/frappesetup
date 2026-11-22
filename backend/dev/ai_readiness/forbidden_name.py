"""Check the D-13 name digest against tracked paths and their contents."""

import hashlib
import os
import subprocess
from collections import deque
from collections.abc import Iterable, Iterator
from pathlib import Path

NAME_DIGEST = bytes.fromhex("17618b2344e07d3418e161912308ad63a118158bf4e3f1307329b5543b5fd743")
WINDOW_LENGTH = 6


def match_lines(lines: Iterable[str]) -> Iterator[int]:
    """Yield the source line of each matching window's first character."""
    window = deque(maxlen=WINDOW_LENGTH)
    positions = deque(maxlen=WINDOW_LENGTH)
    previous = 0
    for line, text in enumerate(lines, 1):
        for char in text.lower():
            if not char.isalnum():
                continue
            window.append(char)
            positions.append(line)
            if len(window) == WINDOW_LENGTH and positions[0] != previous:
                if hashlib.sha256("".join(window).encode("utf-8")).digest() == NAME_DIGEST:
                    previous = positions[0]
                    yield previous


def redact_path(path: str) -> str:
    if next(match_lines([path]), None) is None:
        return path
    fingerprint = hashlib.sha256(os.fsencode(path)).hexdigest()[:12]
    return f"[redacted path {fingerprint}]"


def git_output(directory: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        check=True,
        capture_output=True,
    ).stdout


def tracked_findings(backend: Path) -> Iterator[tuple[str, int, str]]:
    try:
        root = Path(os.fsdecode(git_output(backend, "rev-parse", "--show-toplevel").removesuffix(b"\n")))
        paths = git_output(root, "ls-files", "-z", "--cached", "--deduplicate").split(b"\0")
    except (OSError, subprocess.CalledProcessError):
        yield ".", 1, "Could not list tracked repository files."
        return

    for entry in paths:
        if not entry:
            continue
        relative = os.fsdecode(entry)
        path = root / relative
        label = redact_path(relative)
        if label != relative:
            yield label, 1, "Forbidden product name in a tracked path."
        try:
            if path.parent.resolve() != path.parent:
                yield label, 1, "Could not scan a tracked file through a symbolic link."
                continue
            if path.is_symlink():
                lines = match_lines([os.readlink(path)])
                for line in lines:
                    yield label, line, "Forbidden product name in tracked content."
            elif path.is_file():
                with path.open(encoding="utf-8", errors="surrogateescape") as source:
                    for line in match_lines(source):
                        yield label, line, "Forbidden product name in tracked content."
        except (OSError, RuntimeError):
            yield label, 1, "Could not scan tracked file content."
