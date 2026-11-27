#!/usr/bin/env python3
"""press-ai entry point. Recommended call: `python3 -I packages/press-ai/server.py serve --config <path>`.

`-I` ignores environment variables and the user site-packages; the package directory is added explicitly here.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from press_ai.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
