"""Compare live worker, scheduler and queue settings with worker_sizing.json (G-50)."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

DEV = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("config_layers", DEV / "config_layers.py")
config_layers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config_layers)


def threads_problem(worker_class, threads):
    """Gunicorn uses `threads` only in the gthread worker.

    A sync worker with more than one thread silently becomes gthread, and other
    worker types ignore the setting. Both cases mean the pair was not chosen together.
    """
    if not isinstance(threads, int) or threads <= 1 or worker_class == "gthread":
        return None
    if worker_class == "sync":
        return "sync worker switches to gthread when threads > 1; choose gthread explicitly"
    return f"threads has no effect on {worker_class} workers"


def compare(expected, found, label, path=""):
    """Return messages for expected keys that are missing or different."""
    problems = []
    for key, want in expected.items():
        name = f"{path}{key}"
        if key not in found:
            problems.append(f"{label}: {name} missing")
        elif isinstance(want, dict):
            if isinstance(found[key], dict):
                problems += compare(want, found[key], label, f"{name}.")
            else:
                problems.append(f"{label}: {name} expected an object")
        elif found[key] != want or isinstance(found[key], str):
            problems.append(f"{label}: {name} expected {want}, found {json.dumps(found[key])}")
    return problems


def check_sizing(sizing):
    problems = []
    group = sizing["release_group"]
    for kind in ("gunicorn", "background"):
        low, high = f"min_{kind}_workers", f"max_{kind}_workers"
        if group[low] > group[high]:
            problems.append(f"sizing: {low} is above {high}")
    problem = threads_problem(sizing["gunicorn_worker_class"], group["gunicorn_threads_per_worker"])
    if problem:
        problems.append(f"sizing: {problem}")
    for key in sizing["common_site_config"]:
        if key not in config_layers.BENCH_KEYS:
            problems.append(f"sizing: {key} is not a G-38 bench-layer key")
    return problems


def load_object(path, label, problems):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        problems.append(f"{label}: cannot read a JSON object")
        return None
    if not isinstance(value, dict):
        problems.append(f"{label}: expected a JSON object")
        return None
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizing", type=Path, default=DEV / "worker_sizing.json")
    parser.add_argument("--common-site-config", type=Path, help="sites/common_site_config.json")
    parser.add_argument("--release-group", type=Path, help="Release Group fields as a JSON object")
    parser.add_argument("--bench", type=Path, help="Bench fields as a JSON object")
    parser.add_argument("--system-settings", type=Path,
                        help='JSON object: {"<site>": {"enable_scheduler": <value>}}')
    parser.add_argument("--gunicorn-worker-class", help="worker class the bench actually runs")
    args = parser.parse_args()
    if not any((args.common_site_config, args.release_group, args.bench,
                args.system_settings, args.gunicorn_worker_class)):
        parser.error("give at least one input to compare")

    problems = []
    sizing = load_object(args.sizing, "sizing", problems)
    if sizing is None:
        print("\n".join(problems), file=sys.stderr)
        return 1
    problems += check_sizing(sizing)

    if args.common_site_config:
        common = load_object(args.common_site_config, "common_site_config", problems)
        if common is not None:
            problems += compare(sizing["common_site_config"], common, "common_site_config")
            if not config_layers.check_file(args.common_site_config, "common_site_config", shared=True):
                problems.append("common_site_config: G-38 layer check failed")

    group = None
    if args.release_group:
        group = load_object(args.release_group, "release_group", problems)
        if group is not None:
            problems += compare(sizing["release_group"], group, "release_group")

    if args.gunicorn_worker_class:
        threads = (group or sizing["release_group"]).get("gunicorn_threads_per_worker")
        problem = threads_problem(args.gunicorn_worker_class, threads)
        if problem:
            problems.append(f"gunicorn: {problem}")

    if args.bench:
        bench = load_object(args.bench, "bench", problems)
        if bench is not None:
            problems += compare(sizing["bench"], bench, "bench")

    if args.system_settings:
        sites = load_object(args.system_settings, "system_settings", problems)
        if sites is not None and not sites:
            problems.append("system_settings: no sites to check")
        for site, settings in sorted((sites or {}).items()):
            if isinstance(settings, dict):
                problems += compare(sizing["system_settings"], settings, site)
            else:
                problems.append(f"{site}: expected a JSON object")

    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
