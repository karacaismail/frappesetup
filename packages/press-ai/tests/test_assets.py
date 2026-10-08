"""Kontrat, skill, agent ve doküman tutarlılığı: runtime ile birebir; uydurma kimlik veya araç yok.

Kılavuz sırası ve sitemap kimlikleri pressguide verisiyle denetlenir. Veri yolu yalnız `PRESSGUIDE_DATA` ortam
değişkeniyle verilir (pressguide deposunun src/data dizini); yoksa bu iki alt denetim atlanır ve `not_run` olarak
raporlanır (CI bu veriye bağlı değildir).
"""
import json
import os
import re
import unittest

import support
from press_ai import press_ops
from press_ai.cli import COVERAGE_END, COVERAGE_START, coverage_markdown
from press_ai.contract import AGENTS, MACHINE_PRECONDITIONS, SKILLS, TRACK_PROBES, Contract
from press_ai.tools import TOOLS, implemented_schemas

PACKAGE = support.PACKAGE
REPO = os.path.dirname(os.path.dirname(PACKAGE))
GUIDE_DATA = os.environ.get("PRESSGUIDE_DATA") or None
TOOL_NAMES = {name for name, *_ in TOOLS}
CLAUDE_TOOLS = {"Read", "Grep", "Glob", "Edit", "Write", "Bash", "WebFetch", "WebSearch", "NotebookEdit"}
WRITE_TOOLS = {"press_propose", "press_execute", "app_propose_change", "app_apply"}
_FILE_SUFFIX = re.compile(r"\.(py|json|md|txt|js|ts|toml|csv|po|ya?ml|html|css|lock)$")


def _frontmatter(path):
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, text


def _markdown_files(*dirs):
    for base in dirs:
        root = os.path.join(PACKAGE, base)
        for dirpath, _, files in os.walk(root):
            for name in files:
                if name.endswith(".md"):
                    yield os.path.join(dirpath, name)


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = Contract(os.path.join(PACKAGE, "contracts"))

    def test_contract_matches_runtime(self):
        guide_ids = sitemap_ids = None
        if GUIDE_DATA:
            with open(os.path.join(GUIDE_DATA, "guide.json"), "rb") as handle:
                guide_ids = [s["id"] for s in json.loads(handle.read())["steps"]]
            with open(os.path.join(GUIDE_DATA, "press-sitemap.json"), "rb") as handle:
                sitemap_ids = {n["id"] for n in json.loads(handle.read())["nodes"]}
        errors = self.contract.validate(implemented_schemas(), guide_ids, sitemap_ids,
                                        {k: m.preconditions for k, m in press_ops.MUTATIONS.items()})
        self.assertEqual(errors, [])
        if not GUIDE_DATA:
            self.skipTest("not_run: guide order and sitemap ids (set PRESSGUIDE_DATA)")

    def test_every_guide_step_is_mapped(self):
        self.assertEqual(len(self.contract.guide_steps()), 67)

    def test_live_verification_is_never_claimed(self):
        for op_id in self.contract.order:
            self.assertEqual(self.contract.operations[op_id]["verification"]["live"], "not_run", op_id)

    def test_human_only_work_is_not_executable(self):
        executable = set(implemented_schemas())
        for op_id in self.contract.order:
            op = self.contract.operations[op_id]
            if op["approval"] == "human_only" or set(op["authority"]) <= {"infrastructure_owner", "dns_owner",
                                                                          "account_holder"}:
                self.assertNotIn(op_id, executable, op_id)


class SkillAndAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contract = Contract(os.path.join(PACKAGE, "contracts"))
        cls.op_ids = set(contract.order)
        # Aynı noktalı biçimi kullanan ön koşul ve izleme kimlikleri de geçerli atıflardır.
        cls.known_ids = cls.op_ids | set(MACHINE_PRECONDITIONS) | set(TRACK_PROBES) | {
            p.get("id") for op in contract.operations.values() for p in op.get("preconditions") or []
            if isinstance(p, dict)}
        cls.prefixes = {op.split(".")[0] for op in cls.op_ids}

    def test_plugin_manifest_matches_package(self):
        from press_ai import SERVER_NAME, __version__
        with open(os.path.join(PACKAGE, ".claude-plugin", "plugin.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["name"], SERVER_NAME)
        self.assertEqual(manifest["version"], __version__)
        self.assertNotIn("mcpServers", manifest)  # MCP sunucusu kullanıcı yapılandırmasıyla ayrı kaydedilir

    def test_skills_exist_with_matching_frontmatter(self):
        for name in SKILLS:
            path = os.path.join(PACKAGE, "skills", name, "SKILL.md")
            self.assertTrue(os.path.exists(path), path)
            meta, _ = _frontmatter(path)
            self.assertEqual(meta.get("name"), name)
            self.assertTrue(10 < len(meta.get("description", "")) <= 1024, name)

    def test_agents_exist_with_separated_roles(self):
        tool_sets = {}
        for name in AGENTS:
            path = os.path.join(PACKAGE, "agents", name + ".md")
            self.assertTrue(os.path.exists(path), path)
            meta, _ = _frontmatter(path)
            self.assertEqual(meta.get("name"), name)
            self.assertTrue(meta.get("description"))
            tools = {t.strip() for t in meta.get("tools", "").split(",") if t.strip()}
            for tool in tools:
                if tool.startswith("mcp__"):
                    self.assertTrue(tool.startswith("mcp__press-ai__"), tool)
                    self.assertIn(tool[len("mcp__press-ai__"):], TOOL_NAMES, tool)
                else:
                    self.assertIn(tool, CLAUDE_TOOLS, tool)
                self.assertNotIn("approve", tool.lower())
            tool_sets[name] = {t.replace("mcp__press-ai__", "") for t in tools}
        self.assertFalse(tool_sets["press-diagnoser"] & (WRITE_TOOLS | {"Edit", "Write", "Bash"}))
        self.assertFalse(tool_sets["frappe-change-reviewer"] & (WRITE_TOOLS | {"Edit", "Write", "Bash"}))
        self.assertFalse(tool_sets["press-operator"] & {"Edit", "Write", "Bash", "app_apply", "app_propose_change"})
        self.assertIn("press_execute", tool_sets["press-operator"])
        # Geliştirici dosyaları yalnız app_propose_change → insan onayı → app_apply ile yazar; doğrudan yazma aracı yok.
        self.assertFalse(tool_sets["frappe-app-developer"] & {"press_execute", "press_propose", "Bash", "Edit", "Write",
                                                              "NotebookEdit"})
        self.assertTrue({"app_propose_change", "app_apply"} <= tool_sets["frappe-app-developer"])
        self.assertEqual(len({frozenset(s) for s in tool_sets.values()}), len(AGENTS), "agents must not be copies")

    def test_markdown_references_resolve(self):
        files = list(_markdown_files("skills", "agents", "references"))
        self.assertTrue(files)
        for path in files:
            _, text = _frontmatter(path)
            for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
                if re.match(r"[a-z]+://", target):
                    continue
                resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
                self.assertTrue(os.path.exists(resolved), "{} -> {}".format(path, target))
            for token in re.findall(r"`([a-z_]+\.[a-z_]+)`", text):
                if token.split(".")[0] in self.prefixes and not _FILE_SUFFIX.search(token):
                    self.assertIn(token, self.known_ids, "{} mentions unknown operation {}".format(path, token))
            for tool in re.findall(r"mcp__press-ai__([a-z_]+)", text):
                self.assertIn(tool, TOOL_NAMES, "{} mentions unknown tool {}".format(path, tool))


class DocsTests(unittest.TestCase):
    PAGES = ["ai-bakis", "ai-mcp", "ai-skills", "ai-agents", "ai-press-yetkinlik", "ai-gelistirme"]

    def read(self, page):
        with open(os.path.join(REPO, "src", "content", "docs", page + ".md"), encoding="utf-8") as handle:
            return handle.read()

    def test_coverage_block_is_generated_from_the_contract(self):
        text = self.read("ai-press-yetkinlik")
        match = re.search(re.escape(COVERAGE_START) + r".*?" + re.escape(COVERAGE_END), text, re.S)
        self.assertIsNotNone(match, "coverage markers missing in ai-press-yetkinlik.md")
        self.assertEqual(match.group(0), coverage_markdown(Contract(os.path.join(PACKAGE, "contracts"))))

    def test_pages_do_not_score_or_claim_live_verification(self):
        for page in self.PAGES:
            text = self.read(page)
            self.assertNotRegex(text, r"\|\s*Puan\s*\|", page)
            self.assertNotRegex(text.lower(), r"canlı press'te (doğrulandı|çalışıyor|test edildi)", page)


if __name__ == "__main__":
    unittest.main()
