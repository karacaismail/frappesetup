"""Check the development inventory with fake Docker CLI and Engine output."""

import io
import json
import runpy
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

COMMAND = Path(__file__).resolve().parents[1] / "bin" / "dev-resources"
PROJECT = "com.docker.compose.project"
DF = "/v1.47/system/df?type=container&type=volume&type=image"
FINISHED = "2026-11-22T10:00:00.123456789Z"


class FakeEngine:
    def __init__(self, path, responses, requests):
        self.path = path
        self.responses = responses
        self.requests = requests

    def request(self, method, route):
        self.requests.append((self.path, method, route))
        self.data = self.responses[self.path][route]

    def getresponse(self):
        response = io.BytesIO(json.dumps(self.data).encode())
        response.status = 200
        return response

    def close(self):
        pass


class DevResourcesTests(unittest.TestCase):
    def setUp(self):
        self.main = runpy.run_path(str(COMMAND))["main"]

    def run_command(self, responses, docker="/tools/docker"):
        contexts = []
        requests = []

        def cli(arguments, **kwargs):
            self.assertEqual(
                arguments[:-1],
                [docker, "context", "inspect", "--format", '{{ (index .Endpoints "docker").Host }}'],
            )
            context = arguments[-1]
            contexts.append(context)
            if context not in responses:
                raise subprocess.CalledProcessError(1, arguments, stderr="Private error details")
            return subprocess.CompletedProcess(arguments, 0, stdout=f"unix:///{context}.sock\n")

        by_socket = {f"/{context}.sock": data for context, data in responses.items()}
        output = io.StringIO()
        with (
            patch("shutil.which", return_value=docker),
            patch("subprocess.run", side_effect=cli) as runner,
            patch.dict(
                self.main.__globals__,
                {"UnixConnection": lambda path: FakeEngine(path, by_socket, requests)},
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(self.main(), 0)
        self.assertEqual(runner.call_count, len(contexts))
        return output.getvalue(), contexts, requests

    def test_lists_only_fs_resources_and_marks_orphan_by_context(self):
        factory = {
            DF: {
                "Containers": [
                    {
                        "Id": "aa",
                        "Names": ["/fs-live-web"],
                        "State": "running",
                        "Labels": {PROJECT: "fs-live"},
                        "ImageID": "sha256:live",
                        "SizeRw": 200,
                        "Mounts": [{"Type": "volume", "Name": "fs-live_data"}],
                    },
                    {
                        "Id": "bb",
                        "Names": ["/fs-old-web"],
                        "State": "exited",
                        "Labels": {PROJECT: "fs-old"},
                        "ImageID": "sha256:old",
                        "SizeRw": 20,
                        "Mounts": [{"Type": "volume", "Name": "fs-old_data"}],
                    },
                    {"Id": "cc", "Names": ["/other-web"], "State": "running", "Labels": {PROJECT: "other"}},
                    {
                        "Id": "dd",
                        "Names": ["/fs-lookalike"],
                        "State": "running",
                        "Labels": {PROJECT: "other"},
                    },
                    {
                        "Id": "ee",
                        "Names": ["/custom-name"],
                        "State": "running",
                        "Labels": {PROJECT: "fs-custom"},
                    },
                ],
                "Volumes": [
                    {"Name": "fs-live_data", "Labels": {PROJECT: "fs-live"}, "UsageData": {"Size": 1000}},
                    {"Name": "fs-old_data", "Labels": {PROJECT: "fs-old"}, "UsageData": {"Size": 500}},
                    {"Name": "fs-custom_data", "Labels": {PROJECT: "fs-custom"}, "UsageData": {"Size": -1}},
                    {"Name": "other_data", "Labels": {PROJECT: "other"}, "UsageData": {"Size": 500}},
                ],
                "Images": [
                    {"Id": "sha256:live", "RepoTags": ["fs-live:latest", "unrelated:latest"], "Size": 600},
                    {"Id": "sha256:old", "RepoTags": ["fs-old:latest"], "Size": 120},
                    {"Id": "sha256:other", "RepoTags": ["fs-lookalike:latest"], "Labels": {PROJECT: "other"}},
                ],
            },
            "/v1.47/containers/bb/json": {
                "State": {"FinishedAt": FINISHED},
                "Config": {"Env": ["SECRET=hidden"]},
            },
        }
        default = {
            DF: {
                "Containers": [],
                "Volumes": [
                    {"Name": "fs-live_data", "Labels": {PROJECT: "fs-live"}, "UsageData": {"Size": 42}}
                ],
                "Images": [],
            },
        }
        output, contexts, requests = self.run_command({"colima-factory": factory, "colima": default})
        self.assertEqual(contexts, ["colima-factory", "colima"])
        self.assertTrue(all(method == "GET" for _, method, _ in requests))
        self.assertEqual({path for _, _, path in requests}, {DF, "/v1.47/containers/bb/json"})
        self.assertIn(
            "| colima-factory | Container | fs-live-web | 200 bytes | fs-live | In use |", output
        )
        self.assertIn(
            f"| colima-factory | Volume | fs-old_data | 500 bytes | fs-old | {FINISHED} | Orphaned |", output
        )
        self.assertIn(
            "| colima-factory | Volume | fs-custom_data | Unknown | fs-custom | Unknown |  |", output
        )
        self.assertIn("| colima | Volume | fs-live_data | 42 bytes | fs-live | Unknown | Orphaned |", output)
        self.assertIn(f"| colima-factory | Image | fs-old:latest | 120 bytes | fs-old | {FINISHED} |", output)
        for value in ("other-web", "other_data", "fs-lookalike", "unrelated:latest", "custom-name", "SECRET"):
            self.assertNotIn(value, output)

    def test_unavailable_context_does_not_hide_other_context(self):
        output, _, requests = self.run_command(
            {"colima": {DF: {"Containers": [], "Volumes": [], "Images": []}}}
        )
        self.assertIn("colima-factory: not_run", output)
        self.assertNotIn("colima: not_run", output)
        self.assertNotIn("Private error details", output)
        self.assertEqual(requests, [("/colima.sock", "GET", DF)])

    def test_missing_docker_reports_both_contexts_as_not_run(self):
        output, contexts, requests = self.run_command({}, docker=None)
        self.assertEqual(contexts, [])
        self.assertEqual(requests, [])
        self.assertIn("colima-factory: not_run", output)
        self.assertIn("colima: not_run", output)

    def test_missing_stop_time_does_not_discard_context(self):
        data = {
            DF: {
                "Containers": [{"Id": "aa", "Names": ["/fs-new"], "State": "created", "SizeRw": 0}],
                "Volumes": [],
                "Images": [],
            },
            "/v1.47/containers/aa/json": {"State": {"FinishedAt": None}},
        }
        output, _, _ = self.run_command({"colima-factory": data})
        self.assertIn("| colima-factory | Container | fs-new | 0 bytes | Unknown | Unknown |", output)
        self.assertNotIn("colima-factory: not_run", output)
