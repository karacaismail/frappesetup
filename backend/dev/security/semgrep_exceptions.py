"""Apply reviewed findings only when their entire application scope still matches."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).with_name("semgrep-exceptions.json")
RULES = Path("backend/dev/security/fixtures/rules.yaml")
REVIEWABLE = {"frappe-missing-permission", "frappe-ignore-permissions"}
PRESS_LOGOUT = "backend/apps/press_tr/press_tr/api/__init__.py"
GUEST_LIMIT = "frappe-guest-without-limit"


def source_digest(root, scope):
    root = root.resolve()
    directory = root / scope
    if not directory.is_dir() or directory.is_symlink() or not directory.resolve().is_relative_to(root):
        return None
    try:
        rule_content = (root / RULES).read_bytes()
    except FileNotFoundError:
        return None
    digest = hashlib.sha256(hashlib.sha256(rule_content).digest())
    git = shutil.which("git")
    if not git or not Path(git).is_absolute():
        return None
    # Match the source list used by the Gitleaks step in security-audit.
    listing = subprocess.run(
        [git, "--literal-pathspecs", "ls-files", "-z", "--cached", "--others",
         "--deduplicate", "--exclude-standard", "--", scope],
        cwd=root, capture_output=True, check=False,
    )
    if listing.returncode:
        return None
    paths = (root / name for name in listing.stdout.decode("utf-8").split("\0") if name)
    for path in sorted(paths):
        if path.is_symlink() or path.resolve() != path:
            return None
        if path.is_file():
            name = path.relative_to(root).as_posix()
            digest.update(name.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def review_scopes(config):
    review = json.loads(config.read_text())
    return [review, *review.get("additionalReviews", [])]


def approved_keys(root, config, before=None):
    allowed = set()
    for review in review_scopes(config):
        scope = review["scope"]
        current = source_digest(root, scope)
        if current is None or current != review["sha256"]:
            continue
        if before is not None and current != before.get(scope):
            continue
        allowed.update(
            (entry["rule"], entry["path"], entry["line"])
            for entry in review["findings"]
            if (entry["rule"] in REVIEWABLE or (entry["rule"], entry["path"]) == (GUEST_LIMIT, PRESS_LOGOUT))
            and entry["reason"].strip()
            and Path(entry["path"]).is_relative_to(Path(scope))
        )
    return allowed


def reviewed_findings(root, config, findings, before):
    if before is None:
        return findings
    allowed = approved_keys(root, config, before)
    remaining = []
    for finding in findings:
        rule = finding["check_id"].rsplit(".", 1)[-1]
        key = (rule, finding["path"], finding["start"]["line"])
        if key in allowed:
            print(f"Semgrep reviewed: {key[1]}:{key[2]} [{rule}]")
            allowed.remove(key)
        else:
            remaining.append(finding)
    return remaining


def main():
    root = Path.cwd()
    if sys.argv[1:] == ["--snapshot"]:
        print(json.dumps({review["scope"]: source_digest(root, review["scope"])
                          for review in review_scopes(CONFIG)}))
        return 0
    if len(sys.argv) != 4:
        raise ValueError("Expected report path, scan status and pre-scan signature.")
    report = json.loads(Path(sys.argv[1]).read_text())
    status = int(sys.argv[2])
    errors = report["errors"]
    findings = report["results"]
    if not isinstance(errors, list) or not isinstance(findings, list):
        raise TypeError("Expected Semgrep errors and results to be lists.")
    if status not in (0, 1) or errors or bool(findings) != (status == 1):
        print(
            f"Semgrep did not complete cleanly: exit={status}, "
            f"errors={len(errors)}, findings={len(findings)}.",
            file=sys.stderr,
        )
        return 1
    before = json.loads(sys.argv[3])
    if not isinstance(before, dict):
        raise TypeError("Expected Semgrep snapshots by scope.")
    remaining = reviewed_findings(root, CONFIG, findings, before)
    for finding in remaining:
        print(f"{finding['path']}:{finding['start']['line']} [{finding['check_id']}]")
    return int(bool(remaining))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Invalid Semgrep review input: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
