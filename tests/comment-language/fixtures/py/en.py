import re

# Reads the configured path.
PATTERN = re.compile(r"#ş[ğü]+")
URL = "https://example.test/// çalışma"
MESSAGE = f"Değer: {URL!r} # değil yorum"


def read(path):
    """Read the file and return its lines."""
    return open(path).read()  # trailing English note
