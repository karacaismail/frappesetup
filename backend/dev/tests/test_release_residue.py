"""Release gate: the public repository must not carry personal or real-looking data.

The repository is published. Every file in the Git snapshot is scanned for
home-folder paths, the full names of real people, personal e-mail addresses,
real-looking Turkish phone numbers, common secret formats, Telegram invite
links, public server addresses and real values in env files.

Content comes from Git objects, never from the working folder. The default
snapshot is HEAD. Set RELEASE_REV to another commit, or to ":" to scan the
staged content before a commit:

    RELEASE_REV=: python3 -B -m unittest backend/dev/tests/test_release_residue.py

Real names are never written in this file. Only SHA-256 digests of the
normalised two-word name are stored, the same way the naming gate stores the
forbidden product name (D-13).
"""

import hashlib
import ipaddress
import os
import re
import subprocess
import tempfile
import unicodedata
import unittest
from pathlib import Path

STAGED = ":"

REPO = Path(__file__).resolve().parents[3]

# SHA-256 of "<first> <last>" after normalise(): lower case, no diacritics.
NAME_DIGESTS = {
    "9ff91a1103d734d04908c5432c53ab346e9d02bd367f00cc16177584e2b6135e",
    "8c16cba08149fcf9930855858704966ea3429ca407ba99b0564942b1dfd777aa",
    "a382897924dc0b9d515af39e1ca4ff7bb890a055cff83c93fb146bc7f68ab6e9",
    "884b85aabd9a9428a4394e354f792b7320cb573329129aba8b912178e1688795",
}

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
    r"|(?<![\w-])sk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}"
    r"|-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
)


# Decisions of 26 November 2026: the shared channel is written as "proje Telegram
# grubu". The group link never enters the repository.
TELEGRAM_LINK = re.compile(r"(?i)(?<![\w.-])(?:t|telegram)\.(?:me|dog)/|tg://(?:join|resolve)")
# Server addresses stay on the servers. Only addresses that are routable on the
# public internet count. Loopback, private, Tailscale, link-local, multicast and
# the documentation ranges are allowed, and so are the well-known public
# resolvers that tests use as an example of a public address.
IPV4 = re.compile(r"(?<![\w.:/])((?:\d{1,3}\.){3}\d{1,3})(?![\w.]*\d)")
IPV6 = re.compile(r"(?<![\w:.])([23][0-9A-Fa-f]{3}(?::[0-9A-Fa-f]{0,4}){2,7})(?![\w:])")
PUBLIC_EXAMPLES = {"1.1.1.1", "8.8.8.8", "9.9.9.9", "2606:4700:4700::1111", "2001:4860:4860::8888"}
# A version string such as "WhatsApp/2.23.20.0" is not an address.
VERSION_PREFIX = re.compile(r"[A-Za-z]/$")
# Third-party data that is not ours: the common password list for Keycloak.
PUBLIC_IP_EXEMPT = {"backend/identity/keycloak/realm/password-blacklists/common-passwords.txt"}
ENV_FILE = re.compile(r"(?:^|/)(?:\.env(?:\.[^/]+)?|[^/]+\.env(?:\.[^/]+)?)$")
ENV_SECRET = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)[A-Za-z0-9_]*)"
    r"\s*=\s*(.*?)\s*$",
    re.IGNORECASE,
)
PLACEHOLDER = re.compile(r"(?i)^(?:|<[^>]*>?.*|\$\{?\w+\}?|/[\w./<>-]*)$|example|sahte|degistir|change|fake|dummy")


def public_address(text):
    """True when the text is an address that is routable on the public internet."""
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    if address.is_multicast or address.is_unspecified or not address.is_global:
        return False
    return str(address) not in PUBLIC_EXAMPLES and text not in PUBLIC_EXAMPLES


def network_prefix(rest, text):
    """True when the address starts a range such as 2000::/3 rather than naming one host."""
    match = re.match(r"/(\d{1,3})(?!\d)", rest)
    if not match:
        return False
    return int(match.group(1)) < (128 if ":" in text else 32)


def env_secret(name, line):
    """True when an env file gives a password, secret or token a real-looking value."""
    if not ENV_FILE.search(name):
        return False
    match = ENV_SECRET.match(line)
    if not match:
        return False
    value = match.group(2).strip().strip("\"'")
    return not PLACEHOLDER.search(value)


def normalise(text):
    text = text.replace("İ", "i").replace("I", "ı").lower().replace("ı", "i")
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def tracked_files(root=REPO, rev=None):
    """Yield (path, text) for every text file stored in one Git snapshot.

    Content is read from Git objects, never from the working folder. rev is a
    commit or tree (default HEAD, or RELEASE_REV from the environment). Pass
    STAGED (":") to read the index, the content the next commit will carry.

    root must be the Git top level itself. An archive opened inside another
    repository would otherwise list that outer repository, or nothing at all.
    """
    root = Path(root).resolve()
    rev = rev or os.environ.get("RELEASE_REV") or "HEAD"

    def run(*args, data=None):
        return subprocess.run(
            ["git", "-C", str(root), *args], input=data, check=True, capture_output=True
        ).stdout

    try:
        top = Path(run("rev-parse", "--show-toplevel").decode().strip()).resolve()
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError(f"{root} is not a Git root") from error
    if top != root:
        raise RuntimeError(f"Git root is {top}, expected {root}")

    blobs = {}
    if rev == STAGED:
        for entry in run("ls-files", "-z", "--stage").decode().split("\0"):
            if entry:
                meta, name = entry.split("\t", 1)
                mode, oid, _stage = meta.split()
                blobs[name] = (mode, oid)
    else:
        try:
            tree = run("rev-parse", "--verify", "--quiet", f"{rev}^{{tree}}").decode().strip()
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"Git has no commit or tree {rev!r} under {root}") from error
        for entry in run("ls-tree", "-r", "-z", tree).decode().split("\0"):
            if entry:
                meta, name = entry.split("\t", 1)
                mode, kind, oid = meta.split()
                if kind == "blob":
                    blobs[name] = (mode, oid)
    if not blobs:
        raise RuntimeError(f"Git lists no files under {root} at {rev!r}")

    # Regular files only: symbolic links and submodules carry no file content.
    names = sorted(name for name, (mode, _) in blobs.items() if mode in {"100644", "100755"})
    request = "".join(f"{blobs[name][1]}\n" for name in names).encode()
    out = run("cat-file", "--batch", data=request)
    position = 0
    for name in names:
        header_end = out.index(b"\n", position)
        size = int(out[position:header_end].split()[2])
        data = out[header_end + 1 : header_end + 1 + size]
        position = header_end + 1 + size + 1
        if b"\0" in data[:8192]:
            continue
        yield name, data.decode("utf-8", "replace")


def scan_text(name, text):
    """Return (kind, line) findings for one file. Values are not returned."""
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        if HOME_PATH.search(line):
            findings.append(("home-path", number))
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
        if TELEGRAM_LINK.search(line):
            findings.append(("telegram-link", number))
        if name not in PUBLIC_IP_EXEMPT:
            for match in [*IPV4.finditer(line), *IPV6.finditer(line)]:
                if VERSION_PREFIX.search(line[: match.start()]):
                    continue
                if network_prefix(line[match.end() :], match.group(1)):
                    continue
                if public_address(match.group(1)):
                    findings.append(("public-ip", number))
                    break
        if env_secret(name, line):
            findings.append(("env-secret", number))
    return findings


class ScannerSelfTest(unittest.TestCase):
    """Synthetic samples prove each rule fires. They are assembled at run time."""

    def kinds(self, text):
        return {kind for kind, _ in scan_text("sample.md", text)}

    def test_rules_fire_on_synthetic_samples(self):
        self.assertEqual(self.kinds("/" + "Users/someone/x"), {"home-path"})
        self.assertEqual(self.kinds("~/" + "Documents/notes"), {"home-path"})
        self.assertEqual(self.kinds("kisi@" + "gercek-alan.com.tr"), {"email"})
        # A plainly artificial mobile number: 5 followed by the digits 1 to 9 in order.
        mobile = "5" + "".join(str(digit) for digit in range(1, 10))
        sample = "+90 {} {} {} {}".format(mobile[:3], mobile[3:6], mobile[6:8], mobile[8:])
        self.assertEqual(self.kinds(sample), {"phone"})
        self.assertEqual(self.kinds("AKIA" + "A" * 16), {"secret"})
        self.assertEqual(self.kinds("key=sk-" + "a" * 40), {"secret"})

    def test_new_rules_fire_on_synthetic_samples(self):
        """Samples for the 26 November 2026 rules. Values are assembled at run time."""
        self.assertEqual(self.kinds("Grup: https://" + "t" + ".me/" + "ornekgrup"), {"telegram-link"})
        self.assertEqual(self.kinds("tg:" + "//join?invite=abc"), {"telegram-link"})
        self.assertEqual(self.kinds("Sunucu " + ".".join(["5", "9", "40", "11"])), {"public-ip"})
        self.assertEqual(self.kinds("ssh root@" + ".".join(["88", "99", "12", "3"])), {"public-ip"})
        self.assertEqual(self.kinds("allow " + ".".join(["88", "99", "12", "3"]) + "/32"), {"public-ip"})
        self.assertEqual(self.kinds("AAAA " + ":".join(["2a01", "4f8", "c0c", "1"]) + "::1"), {"public-ip"})
        self.assertEqual(
            {kind for kind, _ in scan_text("deploy/prod.env", "DB_PASSWORD=" + "Gercek" + "Deger42")},
            {"env-secret"},
        )
        self.assertEqual(
            {kind for kind, _ in scan_text("dev/.env.example", "API_TOKEN=" + "Gercek" + "Deger42")},
            {"env-secret"},
        )

    def test_new_rules_pass_on_reserved_and_placeholder_values(self):
        clean = (
            "127.0.0.1 10.1.2.3 172.18.0.250 192.168.1.99 100.64.0.0/10 169.254.169.254",
            "192.0.2.1 198.51.100.9 203.0.113.7 198.18.0.1 224.0.0.1 0.0.0.0",
            "public resolver 1.1.1.1 and 2606:4700:4700::1111",
            'curl -A "WhatsApp/2.23.20.0 A"',
            "fd7a:115c:a1e0::/48 ::ffff:10.0.0.1 fe80::1 2001:db8::1 values[1::2]",
            "proje Telegram grubu",
            'ip_network("2000::/3") and 5.9.0.0/16',
        )
        for line in clean:
            self.assertEqual(self.kinds(line), set(), line)
        placeholders = (
            ("deploy/keycloak.production.env.example", "KC_DB_PASSWORD=<Keycloak veritabanı parolası>"),
            ("dev/.env.example", "MARIADB_ROOT_PASSWORD=example-only-change-before-use"),
            ("identity/.env.example", "KC_DB_PASSWORD=degistir-veritabani-parolasi"),
            ("identity/.env.example", "IDENTITY_SYNC_CLIENT_SECRET=sahte-istemci-sirri"),
            ("deploy/prod.env", "ATONOTA_SECRET_FILE=/etc/atonota/prod/keycloak.env"),
            ("deploy/prod.env", "IDENTITY_SYNC_WEBHOOK_SECRET="),
            ("docs/note.md", "DB_PASSWORD=" + "Gercek" + "Deger42"),
        )
        for name, line in placeholders:
            self.assertEqual({kind for kind, _ in scan_text(name, line)}, set(), line)

    def test_own_source_has_no_mobile_number_literal(self):
        """Samples are built at run time, so the release gate never sees a real-looking number."""
        mobile = re.compile(r"(?<!\d)5\d{2}[ .-]?\d{3}[ .-]?\d{2}[ .-]?\d{2}(?!\d)")
        lines = Path(__file__).read_text(encoding="utf-8").splitlines()
        hits = [number for number, line in enumerate(lines, 1) if mobile.search(line)]
        self.assertEqual(hits, [])

    def test_reserved_and_fake_values_pass(self):
        clean = (
            "ad@example.com deneme@ornek.test x@provider.example.test",
            "+90 200 000 00 00 and +90 000 000 00 01",
            "/home/frappe/frappe-bench ~/.claude/skills/coding-standards",
            "@frappe.whitelist()",
            "import frappe\\n@frappe.whitelist()",
            "desk-schema-press-settings-field-log_server-and-more",
        )
        for line in clean:
            self.assertEqual(self.kinds(line), set(), line)


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class FileListTest(unittest.TestCase):
    """The file list must come from this repository's own Git root and must not be empty."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        git(self.root, "init", "-q")

    def snapshot(self):
        """Record the working files as a Git tree. No commit, so no author is needed."""
        git(self.root, "add", "-A")
        return subprocess.run(
            ["git", "-C", str(self.root), "write-tree"], check=True, capture_output=True, text=True
        ).stdout.strip()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_scan_reaches_files_outside_backend(self):
        self.write("src/page.md", "Path: /" + "Users/someone/notes\n")
        files = dict(tracked_files(self.root, self.snapshot()))
        self.assertIn("src/page.md", files)
        self.assertEqual(scan_text("src/page.md", files["src/page.md"]), [("home-path", 1)])

    def test_commit_content_is_read_not_the_working_copy(self):
        self.write("page.md", "Path: /" + "Users/someone/notes\n")
        tree = self.snapshot()
        self.write("page.md", "clean\n")
        git(self.root, "add", "page.md")
        self.write("new.md", "Path: /" + "Users/someone/untracked\n")
        files = dict(tracked_files(self.root, tree))
        self.assertEqual(sorted(files), ["page.md"])
        self.assertEqual(scan_text("page.md", files["page.md"]), [("home-path", 1)])

    def test_staged_content_is_read_not_the_working_copy(self):
        self.write("page.md", "Path: /" + "Users/someone/notes\n")
        git(self.root, "add", "page.md")
        self.write("page.md", "clean\n")
        files = dict(tracked_files(self.root, STAGED))
        self.assertEqual(scan_text("page.md", files["page.md"]), [("home-path", 1)])

    def test_missing_commit_fails(self):
        with self.assertRaisesRegex(RuntimeError, "no commit"):
            list(tracked_files(self.root, "HEAD"))

    def test_empty_file_list_fails(self):
        with self.assertRaisesRegex(RuntimeError, "no files"):
            list(tracked_files(self.root, STAGED))

    def test_folder_inside_another_repository_fails(self):
        inner = self.root / "archive"
        inner.mkdir()
        (inner / "README.md").write_text("plain\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Git root"):
            list(tracked_files(inner))


class ReleaseResidueTest(unittest.TestCase):
    def test_repository_has_no_release_residue(self):
        findings = [
            f"{name}:{number}: {kind}"
            for name, text in tracked_files(REPO)
            for kind, number in scan_text(name, text)
        ]
        self.assertEqual(findings, [], "\n".join(findings))


if __name__ == "__main__":
    unittest.main()
