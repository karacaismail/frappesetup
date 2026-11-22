"""Check the D-13 name digest against tracked paths and their contents."""

import hashlib
import os
import subprocess
import unicodedata
from collections import deque
from collections.abc import Iterable, Iterator
from pathlib import Path

NAME_DIGEST = bytes.fromhex("17618b2344e07d3418e161912308ad63a118158bf4e3f1307329b5543b5fd743")
WINDOW_LENGTH = 6
# Case-folded lookalikes, grouped by script and ordered by alphabet.
CONFUSABLES = str.maketrans(
    {
        # Greek
        "α": "a",
        "β": "b",
        "ι": "i",
        "κ": "k",
        "ν": "v",
        "ο": "o",
        "ρ": "p",
        "τ": "t",
        "υ": "y",
        "χ": "x",
        # Cyrillic
        "а": "a",
        "в": "b",
        "г": "r",
        "е": "e",
        "к": "k",
        "м": "m",
        "н": "h",
        "о": "o",
        "р": "p",
        "с": "c",
        "т": "t",
        "у": "y",
        "х": "x",
        "і": "i",
        "ј": "j",
        "ѕ": "s",
        "һ": "h",
        "ӏ": "l",
        # Armenian
        "ո": "n",
    }
)


def match_lines(lines: Iterable[str]) -> Iterator[int]:
    """Yield the source line of each matching window's first character."""
    window = deque(maxlen=WINDOW_LENGTH)
    positions = deque(maxlen=WINDOW_LENGTH)
    previous = 0
    for line, text in enumerate(lines, 1):
        for char in unicodedata.normalize("NFKD", text).casefold().translate(CONFUSABLES):
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
    local_variables = subprocess.run(
        ["git", "rev-parse", "--local-env-vars"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    environment = {key: value for key, value in os.environ.items() if key not in local_variables}
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        check=True,
        capture_output=True,
        env=environment,
    ).stdout


def commit_findings(root, commit_base):
    try:
        git_output(root, "rev-parse", "--verify", "HEAD")
    except subprocess.CalledProcessError:
        if commit_base is None:
            return
        raise
    revision = "HEAD"
    if commit_base is not None:
        base = git_output(root, "rev-parse", "--verify", "--end-of-options", f"{commit_base}^{{commit}}")
        revision = f"{base.decode('ascii').strip()}..HEAD"
    messages = git_output(
        root,
        "log",
        "-z",
        "--format=%H%x00%B",
        revision,
        "--max-count=1" if commit_base is None else "--full-history",
        "--",
    )
    fields = messages.decode("utf-8", errors="replace").split("\0")
    for commit, message in zip(fields[::2], fields[1::2]):
        for line in match_lines(message.splitlines()):
            yield f"git:{commit[:12]}", line, "Forbidden product name in a commit message."


def repository_root(backend):
    return Path(os.fsdecode(git_output(backend, "rev-parse", "--show-toplevel").removesuffix(b"\n")))


def stage_entries(root):
    seen = set()
    entries = git_output(root, "ls-files", "-z", "--stage")
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        metadata, relative_bytes = entry.split(b"\t", 1)
        relative = os.fsdecode(relative_bytes)
        if relative not in seen:
            seen.add(relative)
            yield relative, metadata.startswith(b"160000 ")


def find_path_code(backend, code):
    label = f"[redacted path {code}]"

    def lookup(root, prefix):
        for index, (relative, gitlink) in enumerate(stage_entries(root), 1):
            path = prefix / relative
            if redact_path(path.as_posix()) == label:
                return {"index": index, "repository": redact_path(prefix.as_posix())}
            if (
                gitlink
                and (root / relative / ".git").exists()
                and (root / relative).resolve() == root / relative
            ):
                match = lookup(root / relative, path)
                if match is not None:
                    return match
        return None

    return lookup(repository_root(backend), Path("."))


def tracked_findings(backend: Path, commit_base=None) -> Iterator[tuple[str, int, str]]:
    try:
        root = repository_root(backend)
        yield from commit_findings(root, commit_base)
    except (OSError, subprocess.CalledProcessError):
        yield ".", 1, "Could not inspect repository or commit range."
        return
    yield from tracked_files(root)


def tracked_files(root, prefix=Path(".")):
    try:
        entries = list(stage_entries(root))
    except (OSError, subprocess.CalledProcessError):
        yield redact_path(prefix.as_posix()), 1, "Could not list tracked repository files."
        return
    for relative, gitlink in entries:
        path = root / relative
        display_path = (prefix / relative).as_posix()
        label = redact_path(display_path)
        if label != display_path:
            yield label, 1, "Forbidden product name in a tracked path."
        try:
            if path.parent.resolve() != path.parent:
                yield label, 1, "Could not scan a tracked file through a symbolic link."
                continue
            if gitlink:
                if path.is_symlink() or not (path / ".git").exists():
                    yield label, 1, "Could not scan uninitialized submodule."
                else:
                    yield from tracked_files(path, prefix / relative)
            elif path.is_symlink():
                for line in match_lines([os.readlink(path)]):
                    yield label, line, "Forbidden product name in tracked content."
            elif path.is_file():
                with path.open(encoding="utf-8", errors="surrogateescape") as source:
                    for line in match_lines(source):
                        yield label, line, "Forbidden product name in tracked content."
        except (OSError, RuntimeError):
            yield label, 1, "Could not scan tracked file content."
