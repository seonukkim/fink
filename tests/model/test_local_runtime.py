from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fink.model import runtime


class LocalRuntimeManifestTests(unittest.TestCase):
    def test_manifest_pins_required_profiles_and_open_public_components(self) -> None:
        manifest = runtime.load_runtime_manifest()

        self.assertEqual(set(runtime.REQUIRED_PROFILE_IDS), set(manifest.profiles))
        self.assertEqual(manifest.max_download_size_gb, 20)
        for component in manifest.components.values():
            with self.subTest(component=component.id):
                self.assertRegex(component.exact_revision, r"^[0-9a-f]{40}$")
                self.assertIn(component.license, runtime.OPEN_LICENSE_FLOOR)
                self.assertTrue(component.public_ungated)
                self.assertFalse(component.gated)
                self.assertFalse(component.private)
                self.assertTrue(component.prefer_safetensors)
                self.assertFalse(component.allow_pickle)

    def test_default_fink_home_uses_user_share_dir(self) -> None:
        env = {"HOME": "/home/example", "XDG_DATA_HOME": "/tmp/xdg-data"}
        self.assertEqual(
            runtime.resolve_fink_home(env=env),
            Path("/tmp/xdg-data/fink"),
        )
        self.assertEqual(
            runtime.resolve_fink_home(env={"HOME": "/home/example"}),
            Path("/home/example/.local/share/fink"),
        )
        self.assertEqual(
            runtime.resolve_fink_home(env={"FINK_HOME": "/tmp/custom", "HOME": "/home/example"}),
            Path("/tmp/custom"),
        )
        with self.assertRaises(runtime.LocalModelRuntimeError):
            runtime.resolve_fink_home(fink_home=runtime.REPO_ROOT / "models")

    def test_mock_install_is_idempotent_and_weight_free(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fink-runtime-test-") as tmp:
            home = Path(tmp) / "fink-home"
            first = runtime.run_install(
                profile_id="standard",
                fink_home=home,
                mock_download=True,
            )
            second = runtime.run_install(
                profile_id="standard",
                fink_home=home,
                mock_download=True,
            )

            self.assertEqual(first["status"], "mock_installed")
            self.assertEqual(second["status"], "mock_installed")
            self.assertEqual(first["installed_count"], second["installed_count"])
            self.assertEqual(second["missing_count"], 0)
            self.assertFalse(second["tracked_weight_files"])
            weight_files = [
                path
                for path in home.rglob("*")
                if path.is_file() and path.name.lower().endswith(runtime.WEIGHT_SUFFIXES)
            ]
            self.assertEqual(weight_files, [])

    def test_runtime_analyze_enforces_offline_flags_and_deterministic_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fink-runtime-test-") as tmp:
            home = Path(tmp) / "fink-home"
            local_runtime = runtime.LocalModelRuntime(profile_id="standard", fink_home=home)
            old_value = os.environ.get("HF_HUB_OFFLINE")
            with mock.patch.dict(os.environ, {"FINK_MODEL_DOWNLOAD_ALLOWED": "true"}):
                first = local_runtime.analyze(
                    "Synthetic clause: payment within 30 days and 40% revenue share.",
                    question="What should be reviewed?",
                )
                second = local_runtime.analyze(
                    "Synthetic clause: payment within 30 days and 40% revenue share.",
                    question="What should be reviewed?",
                )

        self.assertEqual(first, second)
        self.assertEqual(os.environ.get("HF_HUB_OFFLINE"), old_value)
        self.assertEqual(first["runtime_offline_flags"], runtime.OFFLINE_ENV_FLAGS)
        self.assertEqual(first["outbound_connection_attempts"], 0)
        self.assertFalse(first["download_allowed_at_runtime"])
        self.assertTrue(first["deterministic_fallback_used"])
        self.assertEqual(first["adapter_modes"]["embedding"], "deterministic_fallback")
        self.assertIn(
            "Contractual Financial Review Priority",
            first["optional_explanation_qa"]["answer"],
        )

    def test_doctor_output_never_contains_token_value(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fink-runtime-test-") as tmp:
            token_value = "TOKEN_VALUE_SHOULD_NOT_APPEAR"
            with mock.patch.dict(os.environ, {"HF_TOKEN": token_value}):
                output = runtime.run_doctor(profile_id="core", fink_home=Path(tmp))
            text = json.dumps(output, sort_keys=True)
            self.assertNotIn(token_value, text)
            self.assertEqual(output["status"], "doctor_ok")
            self.assertTrue(output["no_tracked_weights"])

    def test_manifest_rejects_unapproved_pickle_component(self) -> None:
        manifest_text = runtime.MANIFEST_PATH.read_text(encoding="utf-8")
        modified = re.sub(r"allow_pickle: false", "allow_pickle: true", manifest_text, count=1)
        with tempfile.TemporaryDirectory(prefix="fink-runtime-test-") as tmp:
            path = Path(tmp) / "runtime_profiles.yaml"
            path.write_text(modified, encoding="utf-8")
            with self.assertRaises(runtime.LocalModelRuntimeError):
                runtime.load_runtime_manifest(path)


if __name__ == "__main__":
    unittest.main()
