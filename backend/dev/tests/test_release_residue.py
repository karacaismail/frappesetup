"""Release gate: the public backend tree must not carry personal or real-looking data.

The repository is published. Every tracked file under backend/ is scanned for
home-folder paths, the full names of real people, personal e-mail addresses,
real-looking Turkish phone numbers and common secret formats.

Real names are never written in this file. Only SHA-256 digests of the
normalised two-word name are stored, the same way the naming gate stores the
forbidden product name (D-13).
"""

import hashlib
import re
import subprocess
import unicodedata
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

# SHA-256 of "<first> <last>" after normalise(): lower case, no diacritics.
NAME_DIGESTS = {
    "9ff91a1103d734d04908c5432c53ab346e9d02bd367f00cc16177584e2b6135e",
    "8c16cba08149fcf9930855858704966ea3429ca407ba99b0564942b1dfd777aa",
}

# Temporary: paradev/press-provision replaces the names in this file.
# Delete this entry once that branch is merged into backend.
NAME_EXEMPT = {"backend/dev/press/provisioning-readiness.md"}

HOME_PATH = re.compile(
    r"/Users/[A-Za-z]"
    r"|/home/(?!frappe\b)[a-z]"
    r"|[A-Za-z]:\\Users\\"
    r"|~/(?:Documents|Desktop|Developer|Downloads)\b"
)
EMAIL = re.compile(r"(?<![\w.@\\-])[\w.%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")
RESERVED_DOMAIN = re.compile(
    r"(?i)(?:^|\.)(?:example\.(?:com|net|org)|[a-z0-9-]+\.(?:test|example|invalid|localhost)"
    r"|test|example|invalid|localhost|users\.noreply\.github\.com)$"
)
PHONE = re.compile(
    r"(?<![\w+])(?:\+90|0090|0)[ .-]?\(?([1-9]\d{2})\)?[ .-]?(\d{3})[ .-]?(\d{2})[ .-]?(\d{2})(?![\w])"
)
SECRET = re.compile(
    r"AKIA[0-9A-Z]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{36}"
    r"|github_pat_[A-Za-z0-9_]{22,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|sk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}"
    r"|-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
)


def normalise(text):
    text = text.replace("İ", "i").replace("I", "ı").lower().replace("ı", "i")
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def tracked_files():
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "backend"],
            check=True,
            capture_output=True,
        ).stdout
        names = [name for name in out.decode().split("\0") if name]
    except (OSError, subprocess.CalledProcessError):
        names = [str(path.relative_to(REPO)) for path in BACKEND.rglob("*") if path.is_file()]
    for name in sorted(names):
        path = REPO / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue
        yield name, data.decode("utf-8", "replace")


def scan_text(name, text):
    """Return (kind, line) findings for one file. Values are not returned."""
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        if HOME_PATH.search(line):
            findings.append(("home-path", number))
        if name not in NAME_EXEMPT:
            words = re.findall(r"\w+", normalise(line))
            pairs = (f"{a} {b}" for a, b in zip(words, words[1:]))
            if any(hashlib.sha256(pair.encode()).hexdigest() in NAME_DIGESTS for pair in pairs):
                findings.append(("person-name", number))
        for match in EMAIL.finditer(line):
            if not RESERVED_DOMAIN.search(match.group(1)):
                findings.append(("email", number))
        for match in PHONE.finditer(line):
            area, a, b, c = match.groups()
            if not (a + b + c).startswith("00000"):
                findings.append(("phone", number))
        if SECRET.search(line):
            findings.append(("secret", number))
    return findings


class ScannerSelfTest(unittest.TestCase):
    """Synthetic samples prove each rule fires. They are assembled at run time."""

    def kinds(self, text):
        return {kind for kind, _ in scan_text("sample.md", text)}

    def test_rules_fire_on_synthetic_samples(self):
        self.assertEqual(self.kinds("/" + "Users/someone/x"), {"home-path"})
        self.assertEqual(self.kinds("~/" + "Documents/notes"), {"home-path"})
        self.assertEqual(self.kinds("kisi@" + "gercek-alan.com.tr"), {"email"})
        self.assertEqual(self.kinds("+90 " + "532 481 27 36"), {"phone"})
        self.assertEqual(self.kinds("AKIA" + "A" * 16), {"secret"})

    def test_reserved_and_fake_values_pass(self):
        clean = (
            "ad@example.com deneme@ornek.test x@provider.example.test",
            "+90 200 000 00 00 and +90 000 000 00 01",
            "/home/frappe/frappe-bench ~/.claude/skills/coding-standards",
            "@frappe.whitelist()",
            "import frappe\\n@frappe.whitelist()",
        )
        for line in clean:
            self.assertEqual(self.kinds(line), set(), line)


class ReleaseResidueTest(unittest.TestCase):
    def test_backend_has_no_release_residue(self):
        findings = [
            f"{name}:{number}: {kind}"
            for name, text in tracked_files()
            for kind, number in scan_text(name, text)
        ]
        self.assertEqual(findings, [], "\n".join(findings))


if __name__ == "__main__":
    unittest.main()
