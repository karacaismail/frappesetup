"""Write the Keycloak settings of the tenant site owned by e2e/stack. Settings arrive on stdin."""

import json
import secrets
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

DELETION_KEY = "kimlik_deletion_hmac_key"


def merge_settings(current, settings):
    """Apply the stack settings and keep a deletion key the site already has.

    The deletion record names are HMAC digests under this key (decision note 0013). A new key
    would hide every earlier deletion record, so the key is made once and then kept.
    """
    merged = dict(current)
    merged.update(settings)
    if not merged.get(DELETION_KEY):
        merged[DELETION_KEY] = secrets.token_urlsafe(32)
    return merged


def main():
    settings = json.load(sys.stdin)
    path = Path("sites/tenant1.localhost/site_config.json")
    config = merge_settings(json.loads(path.read_text()), settings)
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_text(json.dumps(config, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
