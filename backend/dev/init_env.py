"""Create local development credentials without printing or overwriting them."""

import os
import secrets
import stat
from pathlib import Path


def main() -> None:
    path = Path(os.environ.get("DEV_ENV_FILE", Path(__file__).with_name(".env")))
    if path.is_symlink():
        raise SystemExit("Refusing a symlink for the development environment file.")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise SystemExit("The development environment file must be private (chmod 600).") from None
        print("Existing development environment file retained.")
        return
    with os.fdopen(fd, "w") as stream:
        for key in ("MARIADB_ROOT_PASSWORD", "ADMIN_PASSWORD"):
            stream.write(f"{key}={secrets.token_urlsafe(32)}\n")
    print("Created private development environment file.")


if __name__ == "__main__":
    main()
