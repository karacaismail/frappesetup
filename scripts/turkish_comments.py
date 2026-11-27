#!/usr/bin/env python3
"""Count Turkish code comments in the repository.

A comment is Turkish when it contains a letter that only Turkish uses here:
c-cedilla, g-breve, dotless i, dotted capital I, o-umlaut, s-cedilla or u-umlaut.
Only comments count. String literals, screen text and translation catalogues do not.

Each language is read by its own small scanner:

- Python: ``tokenize`` comments and ``ast`` docstrings.
- JavaScript, TypeScript, TSX and Astro: a scanner that skips strings, template
  literals, regular expressions and JSX or HTML text.
- Java, Groovy (Jenkinsfile) and CSS: a C-style scanner.
- YAML, shell, TOML, env and similar files: ``#`` comments outside quotes.
- FreeMarker and HTML: ``<#-- -->``, ``<!-- -->`` and Jinja ``{# #}`` comments.

Usage:
  python3 scripts/turkish_comments.py            # count by folder
  python3 scripts/turkish_comments.py --depth 3  # finer folder breakdown
  python3 scripts/turkish_comments.py --list     # every Turkish comment
  python3 scripts/turkish_comments.py --markdown # list as a Markdown table
  python3 scripts/turkish_comments.py --check    # fail when above the baseline
  python3 scripts/turkish_comments.py --update-baseline
"""

from __future__ import annotations

import argparse
import ast
import bisect
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tests" / "turkish-comments-baseline.json"
SCOPE = ("backend", "packages", "scripts", "src", "tests")

TURKISH_LETTERS = re.compile("[çğıöşüÇĞİÖŞÜ]")


def is_turkish(text: str) -> bool:
    return bool(TURKISH_LETTERS.search(text))


@dataclass(frozen=True)
class Comment:
    line: int
    kind: str  # "comment" or "docstring"
    text: str


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    text: str

    @property
    def folder(self) -> str:
        return self.path.split("/", 1)[0]


@dataclass
class ScanResult:
    findings: List[Finding] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ScanError(Exception):
    pass


# ---------------------------------------------------------------- file types

DATA_EXTENSIONS = {
    ".md", ".json", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".svg", ".woff", ".woff2", ".ttf", ".otf", ".patch", ".diff", ".gitkeep",
    ".lock", ".frappe", ".eslintrc", ".pdf", ".zip",
}
DATA_NAMES = {"LICENSE", "NOTICE", ".frappe"}
# Translation catalogues hold screen text. Their own work item translates them.
CATALOGUE = re.compile(r"(^|/)(messages_tr\.properties|tr\.po|tr\.csv)$")
DATA_PATHS = re.compile(r"(^|/)(password-blacklists/|META-INF/services/)|(^|/)[^/]*license[^/]*\.txt$|(^|/)OFL\.txt$", re.I)

CODE_EXTENSIONS = {
    ".py": "python",
    ".ts": "js", ".mts": "js", ".cts": "js", ".js": "js", ".mjs": "js", ".cjs": "js",
    ".tsx": "jsx", ".jsx": "jsx",
    ".astro": "astro",
    ".css": "css",
    ".java": "clike", ".groovy": "clike", ".kt": "clike", ".gradle": "clike", ".jenkinsfile": "clike",
    ".html": "html", ".htm": "html", ".xml": "html",
    ".ftl": "ftl",
    ".yaml": "hash", ".yml": "hash", ".toml": "hash", ".sh": "hash", ".bash": "hash",
    ".env": "hash", ".conf": "hash", ".cfg": "hash", ".ini": "hash", ".in": "hash",
    ".txt": "hash", ".template": "hash", ".allowed": "hash", ".caddy": "hash",
    ".properties": "hash-line", ".dockerfile": "hash-line", ".gitignore": "hash-line",
    ".dockerignore": "hash-line", ".editorconfig": "hash-line", ".gitleaksignore": "hash-line",
}
CODE_NAMES = {
    "Dockerfile": "hash-line",
    "Caddyfile": "hash",
    "Jenkinsfile": "clike",
}


def classify(path: str, head: str = "") -> str:
    """Return the scanner name for a repository path, "data" or "unknown"."""
    name = path.rsplit("/", 1)[-1]
    if CATALOGUE.search(path) or DATA_PATHS.search(path) or name in DATA_NAMES:
        return "data"
    if name.endswith(".example"):
        return classify(path[: -len(".example")], head)
    if name in CODE_NAMES:
        return CODE_NAMES[name]
    if name.startswith("Dockerfile."):
        return "hash-line"
    if name.startswith(".env"):
        return "hash"
    ext = os.path.splitext(name)[1].lower()
    if not ext and name.startswith("."):
        ext = name.lower()  # for example .gitignore
    if ext in DATA_EXTENSIONS:
        return "data"
    if ext in CODE_EXTENSIONS:
        return CODE_EXTENSIONS[ext]
    if not ext:
        first = head.split("\n", 1)[0]
        if first.startswith("#!"):
            return "python" if "python" in first else "hash"
        if not head.strip():
            return "data"
    return "unknown"


# ------------------------------------------------------------------ scanners


class LineIndex:
    def __init__(self, text: str):
        self.starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def line(self, pos: int) -> int:
        return bisect.bisect_right(self.starts, pos)


def python_comments(source: str) -> List[Comment]:
    out: List[Comment] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                if tok.start[0] == 1 and tok.string.startswith("#!"):
                    continue
                out.append(Comment(tok.start[0], "comment", tok.string))
        tree = ast.parse(source)
    except (tokenize.TokenError, SyntaxError) as exc:
        raise ScanError(str(exc)) from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                out.append(Comment(first.lineno, "docstring", first.value.value))
    return sorted(out, key=lambda c: c.line)


REGEX_KEYWORDS = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw",
    "case", "do", "else", "yield", "await",
}
HTML_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr", "!doctype",
}
WORD = re.compile(r"[\w$]+")
TAG_NAME = re.compile(r"[\w.:\-!]+")


class JsScanner:
    """Comment scanner for JavaScript, TypeScript, TSX and Astro templates."""

    def __init__(self, source: str, jsx: bool = False, html: bool = False):
        self.s = source
        self.n = len(source)
        self.i = 0
        self.jsx = jsx
        self.html = html  # markup follows HTML rules (void tags, <!-- -->, raw script/style)
        self.prev: Optional[str] = None  # last significant token: "value", a punctuator or "kw"
        self.lines = LineIndex(source)
        self.out: List[Comment] = []

    def add(self, start: int, end: int) -> None:
        self.out.append(Comment(self.lines.line(start), "comment", self.s[start:end]))

    def startswith(self, text: str) -> bool:
        return self.s.startswith(text, self.i)

    # -- code

    def expression_position(self) -> bool:
        return self.prev is None or self.prev == "kw" or (self.prev not in ("value", ")", "]", "}"))

    def line_comment(self) -> None:
        end = self.s.find("\n", self.i)
        end = self.n if end < 0 else end
        self.add(self.i, end)
        self.i = end

    def block_comment(self, close: str = "*/", open_len: int = 2) -> None:
        end = self.s.find(close, self.i + open_len)
        end = self.n if end < 0 else end + len(close)
        self.add(self.i, end)
        self.i = end

    def string(self, quote: str) -> None:
        self.i += 1
        while self.i < self.n:
            ch = self.s[self.i]
            if ch == "\\":
                self.i += 2
                continue
            self.i += 1
            if ch == quote or ch == "\n":
                return

    def template(self) -> None:
        self.i += 1
        while self.i < self.n:
            ch = self.s[self.i]
            if ch == "\\":
                self.i += 2
            elif ch == "`":
                self.i += 1
                return
            elif self.startswith("${"):
                self.i += 2
                self.code(until_brace=True)
            else:
                self.i += 1

    def regex(self) -> None:
        self.i += 1
        in_class = False
        while self.i < self.n:
            ch = self.s[self.i]
            if ch == "\\":
                self.i += 2
                continue
            if ch == "\n":
                return
            self.i += 1
            if ch == "[":
                in_class = True
            elif ch == "]":
                in_class = False
            elif ch == "/" and not in_class:
                break
        while self.i < self.n and self.s[self.i].isalpha():
            self.i += 1

    def code(self, until_brace: bool = False) -> None:
        depth = 0
        while self.i < self.n:
            ch = self.s[self.i]
            if ch.isspace():
                self.i += 1
            elif self.startswith("//"):
                self.line_comment()
            elif self.startswith("/*"):
                self.block_comment()
            elif self.i == 0 and self.startswith("#!"):
                self.i = self.n if self.s.find("\n") < 0 else self.s.find("\n")
            elif ch in "'\"":
                self.string(ch)
                self.prev = "value"
            elif ch == "`":
                self.template()
                self.prev = "value"
            elif ch == "/" and self.expression_position():
                self.regex()
                self.prev = "value"
            elif ch == "<" and self.jsx and self.expression_position() and self.i + 1 < self.n and (
                self.s[self.i + 1].isalpha() or self.s[self.i + 1] == ">"
            ):
                self.element()
                self.prev = "value"
            elif ch == "{":
                depth += 1
                self.i += 1
                self.prev = "{"
            elif ch == "}":
                self.i += 1
                if depth == 0 and until_brace:
                    return
                depth -= 1
                self.prev = "}"
            else:
                m = WORD.match(self.s, self.i)
                if m:
                    self.prev = "kw" if m.group() in REGEX_KEYWORDS else "value"
                    self.i = m.end()
                else:
                    self.prev = ch
                    self.i += 1

    # -- markup (JSX and Astro/HTML templates)

    def element(self) -> None:
        """Scan one element that starts at "<"; children are scanned for JSX and HTML."""
        self.i += 1
        if self.startswith(">"):  # JSX fragment
            self.i += 1
            self.children()
            return
        m = TAG_NAME.match(self.s, self.i)
        name = m.group().lower() if m else ""
        self.i = m.end() if m else self.i
        while self.i < self.n:
            ch = self.s[self.i]
            if self.startswith("/>"):
                self.i += 2
                return
            if ch == ">":
                self.i += 1
                break
            if ch == "{":
                self.i += 1
                self.code(until_brace=True)
            elif ch in "'\"":
                end = self.s.find(ch, self.i + 1)
                self.i = self.n if end < 0 else end + 1
            elif self.startswith("//") and not self.html:
                self.line_comment()
            elif self.startswith("/*") and not self.html:
                self.block_comment()
            else:
                self.i += 1
        else:
            return
        if self.html and name in ("script", "style"):
            self.raw_block(name)
        elif self.html and name in HTML_VOID:
            return
        else:
            self.children()

    def raw_block(self, name: str) -> None:
        close = re.compile(r"</%s\s*>" % name, re.I).search(self.s, self.i)
        end = close.start() if close else self.n
        body = self.s[self.i:end]
        offset = self.lines.line(self.i) - 1
        inner = css_comments(body) if name == "style" else JsScanner(body).run()
        self.out.extend(Comment(c.line + offset, c.kind, c.text) for c in inner)
        self.i = close.end() if close else self.n

    def children(self, top: bool = False) -> None:
        while self.i < self.n:
            if self.startswith("<!--"):
                self.block_comment("-->", 4)
            elif self.startswith("</"):
                end = self.s.find(">", self.i)
                self.i = self.n if end < 0 else end + 1
                if not top:
                    return
            elif self.startswith("<") and self.i + 1 < self.n and (self.s[self.i + 1].isalpha() or self.s[self.i + 1] in ">!"):
                self.element()
            elif self.startswith("{"):
                self.i += 1
                self.prev = None
                self.code(until_brace=True)
            else:
                self.i += 1

    def run(self) -> List[Comment]:
        self.code()
        return self.out

    def run_template(self) -> List[Comment]:
        self.children(top=True)
        return self.out


def js_comments(source: str) -> List[Comment]:
    return JsScanner(source).run()


def jsx_comments(source: str) -> List[Comment]:
    return JsScanner(source, jsx=True).run()


def astro_comments(source: str) -> List[Comment]:
    out: List[Comment] = []
    start = 0
    m = re.match(r"\s*---[ \t]*\n", source)
    if m:
        close = re.compile(r"^---[ \t]*$", re.M).search(source, m.end())
        end = close.start() if close else len(source)
        out.extend(JsScanner(source[:end]).run())
        start = close.end() if close else len(source)
    scanner = JsScanner(source, jsx=True, html=True)
    scanner.i = start
    out.extend(scanner.run_template())
    return sorted(out, key=lambda c: c.line)


def html_comments(source: str) -> List[Comment]:
    out = [
        Comment(LineIndex(source).line(m.start()), "comment", m.group())
        for m in re.finditer(r"\{#.*?#\}", source, re.S)
    ]
    out.extend(JsScanner(source, jsx=True, html=True).run_template())
    return sorted(out, key=lambda c: c.line)


def ftl_comments(source: str) -> List[Comment]:
    index = LineIndex(source)
    return [
        Comment(index.line(m.start()), "comment", m.group())
        for m in re.finditer(r"<#--.*?-->|<!--.*?-->", source, re.S)
    ]


def clike_comments(source: str, line_comments: bool = True) -> List[Comment]:
    """Comments of Java, Groovy and CSS. CSS has no line comments."""
    index = LineIndex(source)
    out: List[Comment] = []
    i, n = 0, len(source)
    while i < n:
        if line_comments and source.startswith("//", i):
            end = source.find("\n", i)
            end = n if end < 0 else end
            out.append(Comment(index.line(i), "comment", source[i:end]))
            i = end
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append(Comment(index.line(i), "comment", source[i:end]))
            i = end
        elif source.startswith('"""', i) or source.startswith("'''", i):
            end = source.find(source[i : i + 3], i + 3)
            i = n if end < 0 else end + 3
        elif source[i] in "'\"":
            quote = source[i]
            i += 1
            while i < n and source[i] not in (quote, "\n"):
                i += 2 if source[i] == "\\" else 1
            i += 1
        else:
            i += 1
    return out


def css_comments(source: str) -> List[Comment]:
    return clike_comments(source, line_comments=False)


def hash_comments(source: str, line_start_only: bool = False) -> List[Comment]:
    out: List[Comment] = []
    for lineno, line in enumerate(source.splitlines(), 1):
        if lineno == 1 and line.startswith("#!"):
            continue
        stripped = line.lstrip()
        if stripped.startswith("#") or (line_start_only and stripped.startswith("!")):
            out.append(Comment(lineno, "comment", stripped))
            continue
        if line_start_only:
            continue
        quote = None
        j = 0
        while j < len(line):
            ch = line[j]
            if quote:
                if ch == "\\" and quote == '"':
                    j += 1
                elif ch == quote:
                    quote = None
            elif ch in "'\"" and (j == 0 or line[j - 1] in " \t:=[{,("):
                quote = ch
            elif ch == "#" and j > 0 and line[j - 1] in " \t":
                out.append(Comment(lineno, "comment", line[j:]))
                break
            j += 1
    return out


SCANNERS: Dict[str, Callable[[str], List[Comment]]] = {
    "python": python_comments,
    "js": js_comments,
    "jsx": jsx_comments,
    "astro": astro_comments,
    "css": css_comments,
    "clike": clike_comments,
    "html": html_comments,
    "ftl": ftl_comments,
    "hash": hash_comments,
    "hash-line": lambda source: hash_comments(source, line_start_only=True),
}


def comments_in(path: str, source: str) -> List[Comment]:
    kind = classify(path, source[:200])
    scanner = SCANNERS.get(kind)
    return scanner(source) if scanner else []


# ------------------------------------------------------------------ repository


def tracked_files(root: Path) -> List[str]:
    """Git-tracked files in scope; falls back to a directory walk outside Git."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", *SCOPE],
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8")
        return sorted(p for p in out.split("\0") if p)
    except (OSError, subprocess.CalledProcessError):
        files = []
        for folder in SCOPE:
            for base, dirs, names in os.walk(root / folder):
                dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__")]
                files.extend(str(Path(base, n).relative_to(root)).replace(os.sep, "/") for n in names)
        return sorted(files)


def scan(root: Path, paths: Iterable[str]) -> ScanResult:
    result = ScanResult()
    for path in paths:
        full = root / path
        if not full.is_file():
            continue
        try:
            source = full.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            if classify(path) not in ("data", "unknown"):
                result.errors.append(f"{path}: not UTF-8")
            continue
        if not is_turkish(source):
            continue
        try:
            comments = comments_in(path, source)
        except ScanError as exc:
            result.errors.append(f"{path}: {exc}")
            continue
        for c in comments:
            if is_turkish(c.text):
                result.findings.append(Finding(path, c.line, c.kind, c.text))
    return result


def folder_of(path: str, depth: int) -> str:
    parts = path.split("/")
    return "/".join(parts[: min(depth, len(parts) - 1)] or parts[:1])


def count_by_folder(result: ScanResult, depth: int = 1) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for f in result.findings:
        key = folder_of(f.path, depth)
        counts[key] = counts.get(key, 0) + 1
    return counts


def compare(counts: Dict[str, int], baseline: dict) -> List[str]:
    """Return one problem line per folder whose count is above the baseline."""
    allowed = baseline.get("folders", {})
    problems = []
    for folder in sorted(set(counts) | set(allowed)):
        now, limit = counts.get(folder, 0), allowed.get(folder, 0)
        if now > limit:
            problems.append(
                f"{folder}/: {now} Turkish comments, baseline {limit}. "
                "Write new comments in British English (en-GB)."
            )
    return problems


def short(text: str, limit: int = 100) -> str:
    one = " ".join(text.split())
    return one if len(one) <= limit else one[: limit - 1] + "…"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--depth", type=int, default=1, help="folder depth of the breakdown")
    parser.add_argument("--list", action="store_true", help="print every Turkish comment")
    parser.add_argument("--markdown", action="store_true", help="print the list as a Markdown table")
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    parser.add_argument("--check", action="store_true", help="fail when a folder is above the baseline")
    parser.add_argument("--update-baseline", action="store_true", help="write today's counts as the baseline")
    args = parser.parse_args(argv)

    files = tracked_files(ROOT)
    result = scan(ROOT, files)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)

    if args.json:
        print(json.dumps([f.__dict__ for f in result.findings], ensure_ascii=False, indent=1))
        return 1 if result.errors else 0
    if args.markdown:
        print("| Folder | File | Line | Kind | Comment |")
        print("| --- | --- | --- | --- | --- |")
        for f in result.findings:
            text = short(f.text).replace("|", "\\|")
            print(f"| `{f.folder}` | `{f.path}` | {f.line} | {f.kind} | {text} |")
        return 1 if result.errors else 0
    if args.list:
        for f in result.findings:
            print(f"{f.path}:{f.line}: [{f.kind}] {short(f.text)}")

    top = count_by_folder(result)
    detail = count_by_folder(result, args.depth)
    print("Turkish code comments by folder:")
    for folder in SCOPE:
        print(f"  {folder + '/':<10} {top.get(folder, 0):>6}")
        if args.depth > 1:
            for key in sorted(k for k in detail if k.split("/", 1)[0] == folder and k != folder):
                print(f"    {key + '/':<60} {detail[key]:>6}")
    print(f"  {'total':<10} {len(result.findings):>6}")

    if args.update_baseline:
        data = {
            "note": "Upper limit of Turkish code comments per folder. Lower it as comments are translated; the target is 0. Update with: python3 scripts/turkish_comments.py --update-baseline",
            "total": len(result.findings),
            "folders": {folder: top.get(folder, 0) for folder in SCOPE},
        }
        BASELINE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Baseline written: {BASELINE.relative_to(ROOT)}")

    if args.check:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        problems = compare(top, baseline)
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        lower = [f for f in SCOPE if top.get(f, 0) < baseline["folders"].get(f, 0)]
        if lower and not problems:
            print("Some folders are below the baseline. Lower it with --update-baseline: " + ", ".join(lower))
        return 1 if problems or result.errors else 0
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
