"""Test yardımcıları: geçici yapılandırma, kimlik dosyası, sahte Press, sabit saat ve insan onayı benzetimi.

İnsan onayı testlerde `ProposalStore.write_approval` ile benzetilir: `server.py approve` aynı çağrıyı
TTY'de özet ve onay ifadesi doğrulandıktan sonra yapar. TTY zorunluluğu ayrı bir CLI testinde sınanır.
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest

PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PACKAGE not in sys.path:
    sys.path.insert(0, PACKAGE)

from press_ai.config import Config  # noqa: E402
from press_ai.tools import Context, Toolbox  # noqa: E402

from fake_press import KEY, SECRET, FakePress, FakePressServer  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class Clock:
    def __init__(self, start=None):
        self.now = start or dt.datetime(2026, 10, 8, 12, 0, 0, tzinfo=dt.timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now = self.now + dt.timedelta(**delta)


class TempHome:
    """Repo dışında geçici dizin: state, kimlik dosyası ve workspace burada."""

    def __init__(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="press-ai-test-"))
        os.chmod(self.root, 0o700)

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def credentials(self, mode=0o600, key=KEY, secret=SECRET):
        path = self.path("press-credentials.json")
        with open(path, "w") as handle:
            json.dump({"api_key": key, "api_secret": secret}, handle)
        os.chmod(path, mode)
        return path

    def workspace(self, copy_fixture=True):
        target = self.path("bench-apps")
        if not os.path.exists(target):
            if copy_fixture:
                shutil.copytree(os.path.join(FIXTURES, "apps"), target, symlinks=False)
            else:
                os.makedirs(target)
        return target

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def make_config(home, url=None, principal="team", team="team-alpha", mutations=(), workspace=None,
                allow_writes=False, approver_uid=None, timeout=5):
    data = {"approval": {"state_dir": home.path("state")}}
    if approver_uid is not None:
        data["approval"]["approver_uid"] = approver_uid
    if url:
        data["press"] = {"base_url": url, "principal": principal, "credentials": {"source": "file",
                                                                                  "path": home.credentials()},
                         "timeout_seconds": timeout, "enabled_mutations": list(mutations),
                         "allow_insecure_loopback": True}
        if team:
            data["press"]["team"] = team
    if workspace:
        data["workspace"] = {"root": workspace, "allow_writes": allow_writes}
    path = home.path("config.json")
    with open(path, "w") as handle:
        json.dump(data, handle)
    return path, Config.load(path)


def approve(ctx, proposal_id):
    """İnsan onayının benzetimi (CLI'nin TTY doğrulamasından sonraki adım)."""
    record = ctx.store.load(proposal_id)
    return ctx.store.write_approval(proposal_id, record)


class PressCase(unittest.TestCase):
    """Sahte Press + yapılandırılmış Toolbox. Alt sınıflar PRINCIPAL ve MUTATIONS belirler."""

    PRINCIPAL = "team"
    TEAM = "team-alpha"
    MUTATIONS = ()
    WORKSPACE = False

    def setUp(self):
        self.home = TempHome()
        self.fake = FakePress(principal=self.PRINCIPAL, team=self.TEAM)
        self.server = FakePressServer(self.fake).__enter__()
        self.clock = Clock()
        workspace = self.home.workspace() if self.WORKSPACE else None
        self.config_path, self.config = make_config(self.home, self.server.url, self.PRINCIPAL, self.TEAM,
                                                    self.MUTATIONS, workspace, allow_writes=self.WORKSPACE)
        self.ctx = Context(self.config, clock=self.clock)
        self.tools = Toolbox(self.ctx)

    def tearDown(self):
        self.server.__exit__(None, None, None)
        self.home.cleanup()

    def call(self, name, **arguments):
        return self.tools.call(name, arguments)

    def methods(self):
        return [r[0] for r in self.fake.requests]

    def state_text(self):
        """State dizinindeki tüm dosyaların birleşik metni (secret sızıntısı testleri için)."""
        chunks = []
        for base, _, files in os.walk(self.home.path("state")):
            for name in files:
                with open(os.path.join(base, name), "rb") as handle:
                    chunks.append(handle.read().decode("utf-8", "replace"))
        return "\n".join(chunks)
