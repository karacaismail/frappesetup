"""The product name and the brand domain come from one setting file (AJA-1053).

backend/brand.env holds the two values. No other tracked file may write them out,
except the paths in backend/brand-exclusions.txt. The test reads the values from
brand.env, so this file never writes them itself.

Technical names stay as they are and do not match: the package name uses an
underscore and the command name uses a hyphen, so neither equals the product name.

Design: AJA-1059 plan, section 3.
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
BRAND_ENV = BACKEND / "brand.env"
EXCLUSIONS = BACKEND / "brand-exclusions.txt"
KEYS = ("PRODUCT_NAME", "BRAND_DOMAIN")


def read_brand(path):
    """Read KEY=value lines. Values are not quoted and may hold spaces."""
    values = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"{path}:{number}: KEY=value bekleniyor")
        values[key.strip()] = value.strip()
    if set(values) != set(KEYS):
        raise ValueError(f"{path}: anahtarlar {sorted(values)}, beklenen {sorted(KEYS)}")
    for key in KEYS:
        if not values[key]:
            raise ValueError(f"{path}: {key} boş")
    return values


def read_exclusions(path):
    """Return (path, reason) pairs. Every line must carry a reason."""
    entries = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entry, sep, reason = line.partition("#")
        entry, reason = entry.strip(), reason.strip()
        if not sep or not reason:
            raise ValueError(f"{path}:{number}: neden yazılmamış: {line}")
        entries.append((entry, reason))
    return entries


def is_excluded(rel, entries):
    for entry, _ in entries:
        if entry.endswith("/"):
            if rel.startswith(entry):
                return True
        elif rel == entry:
            return True
    return False


def patterns(values):
    return [re.compile(re.escape(values[key]), re.IGNORECASE) for key in KEYS]


def find_hits(root, files, values, entries):
    """Return 'path:line: text' for every line outside the exclusions that holds a value."""
    regexes = patterns(values)
    hits = []
    for rel in files:
        if is_excluded(rel, entries):
            continue
        path = root / rel
        # A symlink points at a tracked file; the target is scanned on its own.
        if path.is_symlink() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if any(r.search(line) for r in regexes):
                hits.append(f"{rel}:{number}: {line.strip()[:160]}")
    return hits


def missing_exclusions(root, files, entries):
    """Return the exclusion entries that match no tracked file."""
    missing = []
    for entry, _ in entries:
        if entry.endswith("/"):
            found = any(rel.startswith(entry) for rel in files)
        else:
            found = entry in files
        if not found:
            missing.append(entry)
    return missing


def tracked_files():
    top = subprocess.run(
        ["git", "-C", str(BACKEND), "rev-parse", "--show-toplevel"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    out = subprocess.run(
        ["git", "-C", top, "ls-files", "-z"],
        check=True, capture_output=True, text=True,
    ).stdout
    return Path(top), [f for f in out.split("\0") if f]


class BrandScannerTests(unittest.TestCase):
    """The scanner itself, on a small fake tree with fake values."""

    VALUES = {"PRODUCT_NAME": "Ornek Giris", "BRAND_DOMAIN": "ornek.test"}

    def scan(self, files, entries=()):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            return find_hits(root, sorted(files), self.VALUES, list(entries))

    def test_product_name_outside_setting_fails(self):
        hits = self.scan({"app/view.py": "x = 1\ntitle = 'ornek giris'\n"})
        self.assertEqual(hits, ["app/view.py:2: title = 'ornek giris'"])

    def test_domain_outside_setting_fails(self):
        hits = self.scan({"deploy/a.env": "HOST=beta.Ornek.Test\n"})
        self.assertEqual(hits, ["deploy/a.env:1: HOST=beta.Ornek.Test"])

    def test_technical_names_pass(self):
        hits = self.scan({"app/x.py": "import ornek_giris\nrun('ornek-giris')\nornektest\n"})
        self.assertEqual(hits, [])

    def test_excluded_file_and_folder_pass(self):
        files = {"brand.env": "PRODUCT_NAME=Ornek Giris\n", "docs/old/a.md": "Ornek Giris\n"}
        entries = [("brand.env", "kaynak"), ("docs/old/", "tarih")]
        self.assertEqual(self.scan(files, entries), [])

    def test_folder_entry_needs_trailing_slash(self):
        files = {"docs/older.md": "Ornek Giris\n"}
        self.assertEqual(len(self.scan(files, [("docs/old/", "tarih")])), 1)

    def test_symlink_is_not_counted_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.env").write_text("X=Ornek Giris\n", encoding="utf-8")
            (root / "b.env").symlink_to("a.env")
            hits = find_hits(root, ["a.env", "b.env"], self.VALUES, [])
        self.assertEqual(hits, ["a.env:1: X=Ornek Giris"])

    def test_stale_exclusion_is_reported(self):
        entries = [("a.md", "x"), ("gone.md", "y"), ("dir/", "z"), ("nodir/", "w")]
        self.assertEqual(
            missing_exclusions(Path("."), ["a.md", "dir/b.md"], entries),
            ["gone.md", "nodir/"],
        )

    def test_exclusion_without_reason_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.txt"
            path.write_text("a.md\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_exclusions(path)

    def test_brand_file_rejects_extra_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brand.env"
            path.write_text("PRODUCT_NAME=A B\nBRAND_DOMAIN=a.test\nEXTRA=1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_brand(path)


class RepositoryBrandTests(unittest.TestCase):
    """The real repository: the two values live only in the setting file."""

    @classmethod
    def setUpClass(cls):
        cls.values = read_brand(BRAND_ENV)
        cls.entries = read_exclusions(EXCLUSIONS)
        cls.root, cls.files = tracked_files()

    def test_setting_file_is_excluded(self):
        rel = BRAND_ENV.relative_to(self.root).as_posix()
        self.assertTrue(is_excluded(rel, self.entries), f"{rel} listede yok")

    def test_every_exclusion_still_exists(self):
        missing = missing_exclusions(self.root, self.files, self.entries)
        self.assertEqual(missing, [], "Listedeki bu yollar artık yok: " + ", ".join(missing))

    def test_no_hardcoded_brand(self):
        hits = find_hits(self.root, self.files, self.values, self.entries)
        if hits:
            self.fail(
                f"Ürün adı ya da alan adı ayar dışında {len(hits)} satırda yazılı. "
                "Değeri backend/brand.env dosyasından okuyun ya da yolu "
                "backend/brand-exclusions.txt listesine nedeniyle ekleyin.\n"
                + "\n".join(hits)
            )


if __name__ == "__main__":
    unittest.main()
