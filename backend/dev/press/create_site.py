"""Create the disposable Press site without putting credentials in process arguments."""

import os
from contextlib import contextmanager
from tempfile import NamedTemporaryFile

import frappe
from frappe import database
from frappe.installer import _new_site
from frappe.utils import CallbackManager


@contextmanager
def protect_database_import_credentials():
    # Frappe 16.50 passes its generated database password to the MariaDB CLI.
    # Keep that password in a private option file for this development bootstrap.
    original = database.get_command
    with NamedTemporaryFile(mode="w", encoding="utf-8", prefix="press-db-", dir="/dev/shm") as options:

        def get_command(*args, password=None, **kwargs):
            executable, arguments, binary_name = original(*args, password=None, **kwargs)
            if password:
                escaped = (
                    password.replace("\\", "\\\\")
                    .replace('"', '\\"')
                    .replace("\n", "\\n")
                    .replace("\r", "\\r")
                )
                options.seek(0)
                options.truncate()
                options.write(f'[client]\npassword="{escaped}"\n')
                options.flush()
                arguments.insert(0, f"--defaults-extra-file={options.name}")
            return executable, arguments, binary_name

        database.get_command = get_command
        try:
            yield
        finally:
            database.get_command = original


def main() -> None:
    site = "press.localhost"
    database_password = os.environ["PRESS_DB_PASSWORD"]
    administrator_password = os.environ["PRESS_ADMIN_PASSWORD"]
    if not database_password or not administrator_password:
        raise SystemExit("Both Press development passwords are required.")

    frappe.init(site, new_site=True)
    rollback = CallbackManager()
    try:
        with protect_database_import_credentials():
            _new_site(
                db_name=None,
                site=site,
                db_type="mariadb",
                db_root_password=database_password,
                admin_password=administrator_password,
                install_apps=["press"],
                mariadb_user_host_login_scope="%",
                rollback_callback=rollback,
            )
    except Exception:
        rollback.run()
        raise
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
