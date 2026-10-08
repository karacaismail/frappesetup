#!/usr/bin/env python3
"""press-ai giriş noktası. Önerilen çağrı: `python3 -I packages/press-ai/server.py serve --config <yol>`.

`-I` ortam değişkenlerini ve kullanıcı site-packages'ını yok sayar; paket dizini burada açıkça eklenir.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from press_ai.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
