"""Check Press files around an integration command on a disposable bench."""

import hashlib
import json
import os
import sys
from pathlib import Path

GENERATED_DIRECTORIES = {".git", "__pycache__", "node_modules"}


def raise_walk_error(error: OSError) -> None:
	raise error


def snapshot(core: Path) -> dict[str, list[int | str]]:
	if not core.is_dir():
		raise ValueError(f"Press core is not a directory: {core}")
	files = {}
	for directory, subdirectories, filenames in os.walk(core, onerror=raise_walk_error):
		paths = [Path(directory) / name for name in filenames]
		for name in subdirectories[:]:
			path = Path(directory) / name
			if name in GENERATED_DIRECTORIES:
				subdirectories.remove(name)
			elif path.is_symlink():
				subdirectories.remove(name)
				paths.append(path)

		for path in paths:
			info = path.lstat()
			if path.is_symlink():
				content = os.readlink(path)
			elif path.is_file():
				with path.open("rb") as stream:
					content = hashlib.file_digest(stream, "sha256").hexdigest()
			else:
				raise ValueError(f"Unexpected entry in Press core: {path}")
			files[path.relative_to(core).as_posix()] = [info.st_mode, info.st_mtime_ns, content]
	return files


def compare(before: dict, after: dict) -> int:
	changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
	for path in changed:
		print(f"Press core changed: {path}", file=sys.stderr)
	return int(bool(changed))


if __name__ == "__main__":
	current = snapshot(Path(sys.argv[1]).resolve(strict=True))
	if len(sys.argv) == 2:
		json.dump(current, sys.stdout)
	else:
		with Path(sys.argv[2]).open() as stream:
			before = json.load(stream)
		raise SystemExit(compare(before, current))
