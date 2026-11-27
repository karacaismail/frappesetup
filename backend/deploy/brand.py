"""Read the public brand contract. Python 3.9+, standard library only."""

import re
from pathlib import Path

BRAND_FILE = Path(__file__).resolve().parents[1] / "brand.env"
KEYS = {"PRODUCT_NAME", "BRAND_DOMAIN"}
LABEL = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?")


def load_brand(path=BRAND_FILE):
    """Read exactly two unquoted UTF-8 values, without expanding shell expressions."""
    values = {}
    for number, raw in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or key not in KEYS or key in values or not value:
            raise ValueError(
                f"{path}:{number}: expected one nonempty value per brand key"
            )
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError(f"{path}:{number}: control characters are not allowed")
        values[key] = value
    if set(values) != KEYS:
        raise ValueError(f"{path}: PRODUCT_NAME and BRAND_DOMAIN are required")
    domain = values["BRAND_DOMAIN"]
    labels = domain.split(".")
    # Leave room for the longest generated host, demo.app.<environment>.<domain>.
    if (
        len(domain) > 238
        or len(labels) < 2
        or not all(LABEL.fullmatch(part) for part in labels)
    ):
        raise ValueError(
            f"{path}: BRAND_DOMAIN must be a root DNS name without a scheme or path"
        )
    return values
