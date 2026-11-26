"""The Jenkins gates match backend/docs/handoff/ci-security.md, and the Jenkinsfiles hold no
scheduled trigger, no secret value and no server address.

Each gate is its own stage named "Gate: ...". The table "Jenkins kapıları" in ci-security.md is the
list of gates; this test keeps the two lists equal. Secrets come only from Jenkins credentials by
name; the handoff note backend/docs/handoff/jenkins-credentials.md lists those names.
"""

import re
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
BACKEND = DEPLOY.parent
JENKINS = DEPLOY / "jenkins"
CI_SECURITY = BACKEND / "docs" / "handoff" / "ci-security.md"
CREDENTIALS_NOTE = BACKEND / "docs" / "handoff" / "jenkins-credentials.md"
JENKINSFILES = sorted(path.name for path in JENKINS.glob("*.Jenkinsfile"))
ENVIRONMENTS = sorted(path.stem for path in (DEPLOY / "environments").glob("*.env"))

# Public code and tool hosts the line needs. No deployment server may appear in a Jenkinsfile:
# deploy scripts read server addresses from backend/deploy/environments/*.env.
ALLOWED_HOSTS = {"github.com", "ghcr.io", "osv-vulnerabilities.storage.googleapis.com"}
HOST = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+"
    r"(?:com|net|org|io|dev|app|tr|cloud|internal|local|localhost|lan|ts\.net)\b",
    re.IGNORECASE,
)
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SCHEDULED = re.compile(
    r"\b(cron|pollSCM|parameterizedCron|periodicFolderTrigger|upstream|timerTrigger)\s*\(",
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    # A literal value given to a secret-looking name: PASSWORD = 'x', token: "x", --password x.
    re.compile(
        r"(?i)\b(?![\w-]*(?:Variable|Id)\b)[\w-]*(?:password|passwd|secret|token|api[_-]?key)[\w-]*"
        r"\s*[:=]\s*['\"][^'\"$]+['\"]"
    ),
    re.compile(r"(?i)--(?:password|token)[= ]+(?!-)['\"]?[^\s'\"$]+"),
)


def code(text):
    """Drop line comments, so the rules about stages and steps test code only."""
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def block_after(text, start):
    """Return the text inside the braces that open at or after index start."""
    opening = text.index("{", start)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1:index]
    raise ValueError("unbalanced braces")


def gate_stages(text):
    """Return [(stage name, [sh commands], inside dir('web'))] for every "Gate: ..." stage."""
    text = code(text)
    gates = []
    for match in re.finditer(r"stage\('(Gate: [^']+)'\)", text):
        body = block_after(text, match.end())
        commands = re.findall(r"\bsh\s+'([^']*)'", body)
        gates.append((match.group(1), commands, "dir('web')" in body))
    return gates


def documented_gates(markdown):
    """Return {Jenkinsfile: [(stage, folder, command)]} from the table "Jenkins kapıları"."""
    section = markdown.split("\n## Jenkins kapıları\n", 1)
    if len(section) != 2:
        return {}
    section = section[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4 or not cells[0].startswith("`"):
            continue
        name, stage, folder, command = (cell.strip("`") for cell in cells)
        rows.setdefault(name, []).append((stage, folder, command))
    return rows


def scheduled_triggers(text):
    """Return the names of scheduled triggers in a Jenkinsfile. Only githubPush() may start a job."""
    found = SCHEDULED.findall(code(text))
    match = re.search(r"\btriggers\s*\{", code(text))
    if match:
        body = block_after(code(text), match.start())
        for call in re.findall(r"\b(\w+)\s*\(", body):
            if call != "githubPush":
                found.append(call)
    return sorted(set(found))


def open_secrets(text):
    """Return the lines that carry a literal secret value."""
    found = []
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in SECRET_PATTERNS):
            found.append(line.strip())
    return found


def server_addresses(text):
    """Return IP addresses and host names that are not public code or tool hosts."""
    found = set(IPV4.findall(text))
    for host in HOST.finditer(text):
        name = host.group(0).lower()
        if name not in ALLOWED_HOSTS:
            found.add(name)
    return sorted(found)


def credential_names(text):
    """Return the Jenkins credential ids a Jenkinsfile reads. ${...} is one per environment."""
    text = code(text)
    names = set(re.findall(r"credentialsId:\s*'([^']+)'", text))
    names |= set(re.findall(r"\bcredentials\('([^']+)'\)", text))
    for entry in re.findall(r"sshagent\(credentials: \[([^\]]*)\]", text):
        for literal in re.findall(r"['\"]([^'\"]+)['\"]", entry):
            if "${" in literal:
                prefix = literal.split("${", 1)[0]
                names |= {prefix + environment for environment in ENVIRONMENTS}
            else:
                names.add(literal)
    return names


class GateList(unittest.TestCase):
    def test_every_documented_gate_is_its_own_stage(self):
        documented = documented_gates(CI_SECURITY.read_text())
        self.assertTrue(documented, "ci-security.md has no table under '## Jenkins kapıları'")
        self.assertLessEqual(set(documented), set(JENKINSFILES))
        for name in JENKINSFILES:
            text = (JENKINS / name).read_text()
            stages = gate_stages(text)
            expected = [(stage, [command], folder == "web") for stage, folder, command in documented.get(name, [])]
            self.assertEqual(stages, expected, name)

    def test_no_stage_holds_several_gates(self):
        for name in JENKINSFILES:
            text = code((JENKINS / name).read_text())
            self.assertFalse("stage('Gates')" in text, name)

    def test_osv_setup_runs_right_before_the_first_gate(self):
        text = code((JENKINS / "backend.Jenkinsfile").read_text())
        stages = re.findall(r"stage\('([^']+)'\)", text)
        first_gate = next(index for index, stage in enumerate(stages) if stage.startswith("Gate: "))
        self.assertEqual(stages[first_gate - 1], "Security tools")


class Triggers(unittest.TestCase):
    def test_no_jenkinsfile_has_a_scheduled_trigger(self):
        for name in JENKINSFILES:
            self.assertEqual(scheduled_triggers((JENKINS / name).read_text()), [], name)

    def test_the_check_finds_scheduled_triggers(self):
        self.assertEqual(scheduled_triggers("triggers {\n  cron('H 2 * * *')\n}"), ["cron"])
        self.assertEqual(scheduled_triggers("triggers { pollSCM('H/5 * * * *') }"), ["pollSCM"])
        self.assertEqual(
            scheduled_triggers("triggers { githubPush()\n parameterizedCron('H 3 * * * %X=1') }"),
            ["parameterizedCron"],
        )
        self.assertEqual(scheduled_triggers("properties([pipelineTriggers([cron('@daily')])])"), ["cron"])
        self.assertEqual(scheduled_triggers("triggers {\n  githubPush()\n}"), [])


class Secrets(unittest.TestCase):
    def test_no_jenkinsfile_holds_a_secret_value(self):
        for name in JENKINSFILES:
            self.assertEqual(open_secrets((JENKINS / name).read_text()), [], name)

    def test_the_check_finds_secret_values(self):
        samples = (
            "environment { REGISTRY_TOKEN = 'abc123def' }",
            'def password = "hunter22"',
            "sh 'docker login ghcr.io --password s3cretvalue'",
            "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
            "env.GH = 'ghp_" + "a" * 36 + "'",
        )
        for sample in samples:
            self.assertEqual(len(open_secrets(sample)), 1, sample)
        self.assertEqual(open_secrets('sh \'printf %s "$REGISTRY_TOKEN" | docker login --password-stdin\''), [])

    def test_no_jenkinsfile_names_a_server(self):
        for name in JENKINSFILES:
            self.assertEqual(server_addresses((JENKINS / name).read_text()), [], name)

    def test_the_check_finds_server_addresses(self):
        self.assertEqual(server_addresses("sh 'ssh deploy@203.0.113.7 true'"), ["203.0.113.7"])
        self.assertEqual(server_addresses("url 'https://jenkins.example.com/x'"), ["jenkins.example.com"])
        self.assertEqual(server_addresses("host 'alpha.tailnet-1.ts.net'"), ["alpha.tailnet-1.ts.net"])
        self.assertEqual(server_addresses("git url: 'https://github.com/x/y.git'"), [])
        self.assertEqual(server_addresses("python3 -I backend/deploy/release.py field release/release.json"), [])

    def test_secrets_come_from_named_credentials_listed_in_the_handoff_note(self):
        used = set()
        for name in JENKINSFILES:
            used |= credential_names((JENKINS / name).read_text())
        self.assertTrue(used)
        note = CREDENTIALS_NOTE.read_text()
        listed = set(re.findall(r"^\| `([a-z0-9-]+)` \|", note, flags=re.MULTILINE))
        self.assertEqual(listed, used)


if __name__ == "__main__":
    unittest.main()
