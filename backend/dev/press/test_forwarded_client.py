import unittest
from pathlib import Path


class ForwardedClientTest(unittest.TestCase):
    def test_proxy_overwrites_forwarded_client_address(self):
        config = Path(__file__).with_name("forwarded-client.conf")
        directives = [
            line.strip()
            for line in config.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        self.assertEqual(directives, ["proxy_set_header X-Forwarded-For $remote_addr;"])
