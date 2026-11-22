"""Generate the shell projection fixture from the canonical OpenAPI components."""

import argparse
import json
from pathlib import Path

from contract_json import parse_json

SCRIPT = Path(__file__).resolve()
CONTRACT = SCRIPT.parents[5] / "contracts" / "platform_core-shell.openapi.yaml"
SNAPSHOT = SCRIPT.parents[2] / "tests" / "shell_contract_components.json"
PROJECTION_COMPONENTS = (
	"Field",
	"SidebarData",
	"SidebarItem",
	"FieldCondition",
	"SelectChoice",
	"Sensitivity",
	"DocType",
	"Meta",
	"Error",
)


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--check", action="store_true", help="Fail if the snapshot needs regeneration.")
	args = parser.parse_args()
	schemas = parse_json(CONTRACT.read_bytes())["components"]["schemas"]
	snapshot = {name: schemas[name] for name in PROJECTION_COMPONENTS}
	output = (json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
	if args.check:
		if not SNAPSHOT.is_file() or SNAPSHOT.read_bytes() != output:
			raise SystemExit(f"Regenerate {SNAPSHOT.name} using {SCRIPT.name}.")
	else:
		SNAPSHOT.write_bytes(output)


if __name__ == "__main__":
	main()
