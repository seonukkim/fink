from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from fink.model import runtime


REPO_ROOT = runtime.REPO_ROOT


class LocalRuntimeScriptTests(unittest.TestCase):
    def test_requested_scripts_pass_help(self) -> None:
        for script in ("install_local.sh", "model_doctor.sh", "run_demo.sh"):
            with self.subTest(script=script):
                proc = subprocess.run(
                    ["bash", f"scripts/{script}", "--help"],
                    cwd=REPO_ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("usage:", proc.stdout.lower())

    def test_install_local_self_test_is_idempotent_and_json(self) -> None:
        proc = subprocess.run(
            ["bash", "scripts/install_local.sh", "--self-test", "--json"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "local_runtime_self_test_ok")
        self.assertEqual(payload["missing_count"], 0)
        self.assertEqual(payload["outbound_connection_attempts"], 0)
        self.assertTrue(payload["deterministic_fallback_stable"])
        self.assertEqual(payload["weight_files_written"], 0)

    def test_model_doctor_and_demo_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fink-runtime-script-") as tmp:
            doctor = subprocess.run(
                [
                    "bash",
                    "scripts/model_doctor.sh",
                    "--profile",
                    "core",
                    "--fink-home",
                    tmp,
                    "--json",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            demo = subprocess.run(
                ["bash", "scripts/run_demo.sh", "--profile", "core", "--fink-home", tmp, "--json"],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
        doctor_payload = json.loads(doctor.stdout)
        demo_payload = json.loads(demo.stdout)
        self.assertEqual(doctor_payload["status"], "doctor_ok")
        self.assertFalse(doctor_payload["runtime_download_allowed_on_analyze"])
        self.assertEqual(demo_payload["status"], "analyze_completed_offline")
        self.assertEqual(demo_payload["outbound_connection_attempts"], 0)
        self.assertFalse(demo_payload["download_allowed_at_runtime"])

    def test_hf_auth_wrapper_allows_missing_token_for_public_operations(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fink-hf-auth-") as tmp:
            env = dict(os.environ)
            env["HF_HOME"] = tmp
            env.pop("HF_TOKEN", None)
            proc = subprocess.run(
                [
                    "bash",
                    "scripts/model_research/run_with_hf_auth.sh",
                    "python3",
                    "-c",
                    (
                        "import os; "
                        "print(os.environ.get('FINK_HF_AUTH_TOKEN_PRESENT')); "
                        "print('HF_TOKEN' in os.environ)"
                    ),
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
        self.assertEqual(proc.stdout.splitlines(), ["false", "False"])

    def test_hf_auth_wrapper_require_token_fails_without_printing_token(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fink-hf-auth-") as tmp:
            env = dict(os.environ)
            env["HF_HOME"] = tmp
            env.pop("HF_TOKEN", None)
            proc = subprocess.run(
                [
                    "bash",
                    "scripts/model_research/run_with_hf_auth.sh",
                    "--require-token",
                    "python3",
                    "-c",
                    "print('unreachable')",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing Hugging Face token", proc.stderr)
        self.assertNotIn("HF_TOKEN=", proc.stderr)


if __name__ == "__main__":
    unittest.main()
