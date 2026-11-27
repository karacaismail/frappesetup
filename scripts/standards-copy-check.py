#!/usr/bin/env python3
"""Kapı 4b: compare the shared agent rule folder with docs/standartlar (AJA-1344).

docs/standartlar/ is the single source of truth. docs/standartlar/kopyalar.json
maps each rule file to its copy in the shared folder and lists the files that are
not rules. The gate never passes silently.

Exit codes:
  0  every mapped copy equals its source and every file is listed
  1  a finding: a copy differs, a copy or source is missing, or a file is unlisted
  2  the gate could not finish: bad arguments, missing folder or broken map

Usage:
  python3 -I scripts/standards-copy-check.py --copies ~/.claude/skills/coding-standards/references

Standard library only. Python 3.9 or newer.
"""
import argparse
import difflib
import json
from pathlib import Path, PurePosixPath
import sys

STANDARDS = "docs/standartlar"
MAP_NAME = "kopyalar.json"


class GateError(Exception):
    """The gate cannot finish; exit code 2."""


def _relative_name(value, field):
    if not isinstance(value, str) or not value:
        raise GateError(f"{field} boş olmayan bir dizgi olmalı: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise GateError(f"{field} klasör dışına çıkamaz: {value!r}")
    return path


def load_map(root):
    map_path = root / STANDARDS / MAP_NAME
    try:
        data = json.loads(map_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GateError(f"eşleme dosyası yok: {map_path}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"eşleme dosyası okunamadı: {map_path}: {exc}")
    if not isinstance(data, dict) or data.get("version") != 1:
        raise GateError("eşleme dosyasında version 1 olmalı")
    copies, not_rules = data.get("copies"), data.get("notRules")
    if not isinstance(copies, list) or not copies:
        raise GateError("eşleme dosyasında copies boş olmayan bir liste olmalı")
    if not isinstance(not_rules, list) or MAP_NAME not in not_rules:
        raise GateError(f"eşleme dosyasında notRules listesi {MAP_NAME} adını içermeli")
    pairs, names = [], set()
    for entry in copies:
        if not isinstance(entry, dict) or set(entry) != {"source", "copy"}:
            raise GateError(f"copies kaydı yalnız source ve copy taşır: {entry!r}")
        source = _relative_name(entry["source"], "source")
        copy = _relative_name(entry["copy"], "copy")
        if str(source.parent) != STANDARDS:
            raise GateError(f"source {STANDARDS}/ klasöründe olmalı: {entry['source']}")
        if source.name in names:
            raise GateError(f"source iki kez eşlendi: {entry['source']}")
        names.add(source.name)
        pairs.append((source, copy))
    for name in not_rules:
        path = _relative_name(name, "notRules")
        if len(path.parts) != 1:
            raise GateError(f"notRules yalnız dosya adı taşır: {name!r}")
        if name in names:
            raise GateError(f"dosya hem kural hem kural değil: {name}")
        names.add(name)
    return pairs, names


def check(root, copies_dir):
    if not copies_dir.is_dir():
        raise GateError(f"--copies klasörü yok: {copies_dir}")
    std_dir = root / STANDARDS
    if not std_dir.is_dir():
        raise GateError(f"kaynak klasör yok: {std_dir}")
    pairs, listed = load_map(root)
    findings = []
    for source, copy in pairs:
        src_path, copy_path = root / source, copies_dir / copy
        if not src_path.is_file():
            findings.append(f"{source.name}: kaynak dosya yok ({src_path})")
            continue
        if not copy_path.is_file():
            findings.append(f"{source.name}: kopya yok ({copy_path})")
            continue
        try:
            src_bytes, copy_bytes = src_path.read_bytes(), copy_path.read_bytes()
        except OSError as exc:
            raise GateError(f"dosya okunamadı: {exc}")
        if src_bytes != copy_bytes:
            diff = difflib.unified_diff(
                src_bytes.decode("utf-8", "replace").splitlines(),
                copy_bytes.decode("utf-8", "replace").splitlines(),
                fromfile=str(source), tofile=str(copy_path), lineterm="", n=1,
            )
            findings.append(f"{source.name}: kopya kaynaktan farklı\n" + "\n".join(list(diff)[:40]))
    for path in sorted(std_dir.iterdir()):
        if path.is_file() and path.name not in listed:
            findings.append(f"{path.name}: {STANDARDS}/{MAP_NAME} dosyasında eşlenmemiş")
    return findings, len(pairs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--copies", required=True, type=Path, help="ortak kural klasörü")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="frappesetup deposunun kökü (varsayılan: betiğin deposu)")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code not in (0, None):
            print("KAPI ÇALIŞMADI: komut satırı hatalı", file=sys.stderr)
            return 2
        raise
    try:
        findings, count = check(args.root.expanduser(), args.copies.expanduser())
    except GateError as exc:
        print(f"KAPI ÇALIŞMADI: {exc}", file=sys.stderr)
        return 2
    if findings:
        for finding in findings:
            print(f"BULGU: {finding}")
        print(f"Kapı 4b: {len(findings)} bulgu. Ortak klasör değiştirilmedi.")
        return 1
    print(f"Kapı 4b: {count} kopya kaynakla aynı. Eşlenmemiş dosya yok.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
