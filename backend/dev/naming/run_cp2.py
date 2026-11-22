#!/usr/bin/env python3
"""Run the CP2 branch transition against copies of the repository's worktrees."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path

NAMING = Path(__file__).resolve().parent
PROTECTED_BRANCHES = {"backend", "main"}


def command(directory, arguments, env):
    return subprocess.run(
        arguments, cwd=directory, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
    )


def git(directory, env, *arguments):
    result = command(directory, ["git", *arguments], env)
    if result.returncode:
        raise ValueError(os.fsdecode(result.stdout).strip())
    return os.fsdecode(result.stdout)


def worktrees(repo, env):
    listing = git(repo, env, "worktree", "list", "--porcelain", "-z")
    for record in listing.split("\0\0"):
        if record:
            yield dict(field.partition(" ")[::2] for field in record.strip("\0").split("\0"))


def check_author_guard(repo, env):
    guard = Path.home() / ".config/git/author-guard/hooks"
    query = command(repo, ["git", "config", "--path", "--get", "core.hooksPath"], env)
    configured = os.fsdecode(query.stdout).strip()
    if (
        query.returncode
        or (repo / configured).resolve() != guard.resolve()
        or not os.access(guard / "commit-msg", os.X_OK)
    ):
        raise ValueError("The personal Git author guard must be active in the copied repository.")


def transition(repo, entry, backend_ref, copy, test_command, apply, env):
    branch = entry.get("branch", "").removeprefix("refs/heads/") or None
    ref = entry.get("HEAD")
    row = {
        "worktree": entry["worktree"],
        "branch": branch,
        "head": ref,
        "status": "skipped",
        "commit": None,
        "changed_files": 0,
    }
    if not ref or "bare" in entry or "prunable" in entry:
        row["output"] = "No active checkout to copy."
        return row
    dry_run = not apply or branch is None or branch in PROTECTED_BRANCHES
    row["mode"] = "dry-run" if dry_run else "apply"
    try:
        git(repo, env, "clone", "--quiet", "--no-checkout", "--no-hardlinks", "--", str(repo), str(copy))
        git(copy, env, "remote", "remove", "origin")
        checkout = branch if branch and branch not in PROTECTED_BRANCHES else "cp2-preview"
        git(copy, env, "switch", "--quiet", "-C", checkout, ref)
        if not (copy / "backend").is_dir():
            row["output"] = "No backend directory in the checked-out commit."
            return row
        git(copy, env, "update-ref", "refs/heads/backend", backend_ref)
        if not dry_run:
            check_author_guard(copy, env)
        naming_command = [str(NAMING / "apply-to-branch")]
        if dry_run:
            naming_command.append("--no-commit")
        result = command(copy, [*naming_command, "--", *test_command], env)
        row["output"] = os.fsdecode(result.stdout)
        row["returncode"] = result.returncode
        new_head = git(copy, env, "rev-parse", "HEAD").strip()
        if dry_run and new_head != ref:
            raise ValueError("The dry run changed HEAD inside the copy.")
        if not result.returncode and new_head != ref:
            row["commit"] = new_head
        file_changes = git(copy, env, "diff", "--find-renames", "--name-only", "-z", ref, "--", "backend/")
        row["changed_files"] = sum(bool(filename) for filename in file_changes.split("\0"))
        row["status"] = "failed" if result.returncode else "passed"
        if row["commit"]:
            row["copy"] = str(copy)
    except (OSError, ValueError) as error:
        row["status"] = "failed"
        row["output"] = str(error)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--apply", action="store_true", help="Keep local commits in copies. Pane orchestrator only."
    )
    parser.add_argument("test_command", nargs=argparse.REMAINDER, metavar="[-- TEST_COMMAND ...]")
    args = parser.parse_args()
    if args.apply and not os.environ.get("PANE_ORCHESTRATION_SESSION_ID"):
        parser.error("--apply requires the active Pane orchestrator.")
    test_command = args.test_command
    if test_command and test_command[0] != "--":
        parser.error("Put the optional test command after --.")
    test_command = test_command[1:] or [
        sys.executable,
        "-B",
        "-m",
        "unittest",
        "discover",
        "-s",
        "backend/dev/tests",
    ]
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key != "PANE_ORCHESTRATION_SESSION_ID"
    }
    env["PYTHON"] = sys.executable
    repo = args.repo.resolve()
    try:
        backend_ref = git(repo, env, "rev-parse", "--verify", "refs/heads/backend").strip()
        entries = list(worktrees(repo, env))
        scratch = os.environ.get("PANE_SCRATCH_DIR")
        if args.apply:
            workspace = nullcontext(tempfile.mkdtemp(prefix="cp2-", dir=scratch))
        else:
            workspace = tempfile.TemporaryDirectory(prefix="cp2-", dir=scratch)
        with workspace as directory:
            rows = [
                transition(
                    repo, entry, backend_ref, Path(directory) / str(number), test_command, args.apply, env
                )
                for number, entry in enumerate(entries, 1)
            ]
            report = {"mode": "apply" if args.apply else "dry-run", "backend": backend_ref, "worktrees": rows}
            if args.apply:
                report["copies"] = directory
            print(json.dumps(report, ensure_ascii=True, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(2, f"CP2 could not start: {error}\n")
    return int(any(row["status"] == "failed" for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
