"""Times that leave the layer: ISO 8601 with the site's UTC offset.

Frappe stores naive datetimes in the site's time zone (System Settings). A reader in another
zone cannot interpret such a value, so every time in a result carries its offset.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from frappe.utils import get_datetime, get_system_timezone, now_datetime


def iso(value) -> str | None:
	"""Return a stored site-local time as ISO 8601 text with a UTC offset."""
	if not value:
		return None
	moment: datetime = get_datetime(value)
	return moment.replace(tzinfo=ZoneInfo(get_system_timezone())).isoformat()


def now_iso() -> str:
	return iso(now_datetime())
