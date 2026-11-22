"""Point the disposable Press test server at the local deletion fixture."""

import json
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

SETTINGS = {
	"identity_sync_url": "http://127.0.0.1:3205",
	"press_service_client_secret": "press-test-fixture",
}
SITE_CONFIG = Path("press.localhost/site_config.json")


def save_config(config: dict) -> None:
	with NamedTemporaryFile(mode="w", dir=SITE_CONFIG.parent, encoding="utf-8", delete=False) as temporary:
		json.dump(config, temporary)
		temporary.write("\n")
		os.chmod(temporary.name, SITE_CONFIG.stat().st_mode & 0o777)
	os.replace(temporary.name, SITE_CONFIG)


def main() -> None:
	action, backup_path = sys.argv[1:]
	backup = Path(backup_path)
	config = json.loads(SITE_CONFIG.read_text())
	if action == "restore":
		saved = backup.read_text()
		if not saved:
			backup.unlink()
			return
		previous = json.loads(saved)
		for key in SETTINGS:
			config.pop(key, None)
		config.update(previous)
		save_config(config)
		backup.unlink()
	else:
		backup.write_text(json.dumps({key: config[key] for key in SETTINGS if key in config}))
		config.update(SETTINGS)
		save_config(config)


if __name__ == "__main__":
	main()
