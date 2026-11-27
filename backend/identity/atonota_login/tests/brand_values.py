"""Brand values for the tests, read from backend/brand.env (AJA-1059 plan, section 1).

The tests never write the product name or the domain. A new brand then needs no test change.
"""

from pathlib import Path

BRAND_ENV = Path(__file__).resolve().parents[3] / "brand.env"
KEYS = ("PRODUCT_NAME", "BRAND_DOMAIN")


def read_brand(path=BRAND_ENV):
    """Read the KEY=value lines. Values are not quoted and may hold spaces."""
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    if set(values) != set(KEYS) or not all(values.values()):
        raise ValueError(f"{path}: expected exactly {', '.join(KEYS)} with values")
    return values


VALUES = read_brand()
PRODUCT_NAME = VALUES["PRODUCT_NAME"]
BRAND_DOMAIN = VALUES["BRAND_DOMAIN"]
LOGIN_HOST = f"api.login.{BRAND_DOMAIN}"
