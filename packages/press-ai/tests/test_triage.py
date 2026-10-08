"""Build teşhisi: kılavuz olaylarından türetilmiş sınıflar (pressguide@2b83441 adım kimlikleri)."""
import unittest

import support  # noqa: F401
from press_ai import triage
from press_ai.redaction import Redactor


def build(status, *steps):
    return {"name": "bld-x", "status": status, "build_steps": [
        {"idx": i + 1, "stage": st, "step": sp, "status": s, "output": out} for i, (st, sp, s, out) in enumerate(steps)]}


class TriageTests(unittest.TestCase):
    def classify(self, *args):
        return triage.classify(build(*args), Redactor())

    def test_pending_and_preparing_are_not_failures(self):  # preparing, live-build-start
        for status in ("Preparing", "Pending", "Running", "Scheduled"):
            self.assertEqual(self.classify(status, ("Clone", "frappe", "Pending", ""))["state"], "in_progress")

    def test_required_app_not_found(self):  # live-error, identity-error
        out = self.classify("Failure", ("Clone", "frappe", "Success", ""),
                            ("Pre-build", "Validate", "Failure", "Required app not found: erpnext"),
                            ("Upload", "Docker Image", "Pending", ""))
        self.assertEqual(out["classification"], "required_app_not_found")
        self.assertEqual(out["first_failure"]["position"], 2)
        self.assertEqual(out["pending_after_first_failure"], 1)

    def test_npm_range_is_press_code_not_app(self):  # live-npm-range-validation
        out = self.classify("Failure", ("Pre-build", "Validate", "Failure",
                                        "ValueError: Invalid simple block '^20.19.0 || >=22.12.0'"))
        self.assertEqual(out["classification"], "npm_range_parse")
        self.assertEqual(out["owner"], "app_developer")

    def test_upload_context_http_500(self):  # live-upload-row, live-agent-http500
        out = self.classify("Failure", ("Upload", "Build Context", "Failure",
                                        "POST /agent/builder/upload returned 500 Internal Server Error"))
        self.assertEqual(out["classification"], "upload_context_http_error")
        self.assertEqual(out["owner"], "infrastructure_owner")

    def test_missing_registry_repository(self):  # live-ecr-push-failure
        out = self.classify("Failure", ("Upload", "Docker Image", "Failure",
                                        "name unknown: The repository with name 'bench-0027' does not exist"))
        self.assertEqual(out["classification"], "docker_image_push_failed")

    def test_disk_full_wins_over_generic_upload(self):  # live-redis-enospc
        out = self.classify("Failure", ("Upload", "Build Context", "Failure", "OSError: [Errno 28] No space left on device"))
        self.assertEqual(out["classification"], "disk_full")

    def test_clone_and_runtime(self):  # branch, live-runtime
        self.assertEqual(self.classify("Failure", ("Clone Repositories", "education", "Failure",
                                                   "fatal: Remote branch version-17 not found"))["classification"],
                         "clone_failed")
        self.assertEqual(self.classify("Failure", ("Install Apps", "crm", "Failure",
                                                   "ERROR: Package 'crm' requires a different Python"))["classification"],
                         "runtime_incompatible")

    def test_success_needs_every_step(self):  # live-build-success
        ok = self.classify("Success", ("Clone", "frappe", "Success", ""), ("Upload", "Docker Image", "Success", ""))
        self.assertEqual(ok["state"], "succeeded")
        partial = self.classify("Success", ("Clone", "frappe", "Success", ""), ("Upload", "Docker Image", "Failure", ""))
        self.assertEqual(partial["state"], "unknown")

    def test_unclassified_is_not_guessed(self):
        out = self.classify("Failure", ("Install Apps", "lms", "Failure", "something new happened"))
        self.assertEqual(out["classification"], "unclassified")
        self.assertEqual(out["confidence"], "none")

    def test_output_is_redacted(self):
        out = self.classify("Failure", ("Upload", "Docker Image", "Failure",
                                        "denied: registry_password=hunter2-very-secret"))
        self.assertNotIn("hunter2-very-secret", out["first_failure"]["output_tail"])


if __name__ == "__main__":
    unittest.main()
