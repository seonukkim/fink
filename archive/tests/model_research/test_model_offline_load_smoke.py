from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.model_research import model_offline_load_smoke as smoke


class ModelOfflineLoadSmokeTests(unittest.TestCase):
    def _model_path_items(
        self,
        root: Path,
        model_ids: tuple[str, ...] = smoke.DEFAULT_PROFILE_MODEL_IDS,
    ) -> list[str]:
        items: list[str] = []
        for model_id in model_ids:
            model_dir = root / model_id
            model_dir.mkdir(parents=True)
            (model_dir / "config.json").write_text(
                json.dumps({"model_type": "bert", "fixture_id": model_id}),
                encoding="utf-8",
            )
            items.append(f"{model_id}={model_dir.as_posix()}")
        return items

    def test_self_test_runs_default_profile_offline(self) -> None:
        result = smoke.run_self_test()
        self.assertEqual(result["status"], "offline_load_smoke_passed")
        self.assertEqual(result["machine_gate"], "model_offline_load_smoke")
        self.assertEqual(result["profile_id"], smoke.DEFAULT_PROFILE_ID)
        self.assertEqual(result["selected_count"], 3)
        self.assertEqual(result["outbound_connection_attempts"], 0)
        self.assertTrue(result["human_gate_approved"])
        self.assertEqual(result["network_blocker_self_test"], "blocked_socket_create_connection")
        self.assertEqual(result["repo_local_path_self_test"], "rejected")
        self.assertEqual(
            [record["id"] for record in result["models"]],
            list(smoke.DEFAULT_PROFILE_MODEL_IDS),
        )
        self.assertTrue(
            all(record["private_path_recorded"] is False for record in result["models"])
        )

    def test_run_smoke_sets_runtime_offline_flags_without_persisting_them(self) -> None:
        old_value = os.environ.get("FINK_RUNTIME_OFFLINE")
        with tempfile.TemporaryDirectory(prefix="fink-smoke-test-") as tmp:
            result = smoke.run_smoke(
                shortlist_path=smoke.SHORTLIST_PATH,
                human_gates_path=smoke.HUMAN_GATES_PATH,
                model_ids=[],
                model_path_items=self._model_path_items(Path(tmp)),
                storage_mode="private-root",
                private_model_root=None,
                load_mode="metadata",
            )
        self.assertEqual(result["runtime_offline_flags"], smoke.OFFLINE_ENV_FLAGS)
        self.assertEqual(os.environ.get("FINK_RUNTIME_OFFLINE"), old_value)
        self.assertFalse(result["remote_runtime_api_allowed"])

    def test_network_blocker_rejects_outbound_connections(self) -> None:
        with smoke.NetworkBlocker() as blocker:
            with self.assertRaises(smoke.OfflineNetworkAttemptError):
                socket.create_connection(("example.com", 443), timeout=0.001)
            with self.assertRaises(smoke.OfflineNetworkAttemptError):
                socket.socket.connect(object(), ("example.com", 443))
        self.assertGreaterEqual(len(blocker.attempts), 2)

    def test_profile_gate_must_be_live_loop_approved_gate(self) -> None:
        with self.assertRaises(smoke.OfflineLoadSmokeError):
            smoke.validate_profile_gate(
                {
                    "gates": {
                        "MODEL_PROFILE_APPROVED": {
                            "status": "OPEN",
                            "approved": False,
                            "policy": "open_license_floor",
                        }
                    }
                },
                Path("isolated.yaml"),
            )

        gate = smoke.validate_profile_gate(
            {
                "gates": {
                    "MODEL_PROFILE_APPROVED": {
                        "status": "RESOLVED",
                        "approved": True,
                        "policy": "open_license_floor",
                    }
                }
            },
            Path("isolated.yaml"),
        )
        self.assertTrue(gate["approved"])

    def test_model_path_inside_repo_is_rejected(self) -> None:
        with self.assertRaises(smoke.OfflineLoadSmokeError):
            smoke.require_outside_repo(smoke.REPO_ROOT / "models" / "bad", "model path")

    def test_unknown_or_unselected_path_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fink-smoke-test-") as tmp:
            root = Path(tmp)
            model_paths = self._model_path_items(root)
            model_paths.append(f"bge_m3={(root / 'bge_m3').as_posix()}")
            with self.assertRaises(smoke.OfflineLoadSmokeError):
                smoke.run_smoke(
                    shortlist_path=smoke.SHORTLIST_PATH,
                    human_gates_path=smoke.HUMAN_GATES_PATH,
                    model_ids=[],
                    model_path_items=model_paths,
                    storage_mode="private-root",
                    private_model_root=None,
                    load_mode="metadata",
                )

    def test_tracked_weight_files_fail_the_smoke(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fink-smoke-test-") as tmp:
            with mock.patch.object(
                smoke,
                "tracked_weight_files",
                return_value=["models/x.safetensors"],
            ):
                with self.assertRaises(smoke.OfflineLoadSmokeError):
                    smoke.run_smoke(
                        shortlist_path=smoke.SHORTLIST_PATH,
                        human_gates_path=smoke.HUMAN_GATES_PATH,
                        model_ids=[],
                        model_path_items=self._model_path_items(Path(tmp)),
                        storage_mode="private-root",
                        private_model_root=None,
                        load_mode="metadata",
                    )

    def test_cli_self_test_json(self) -> None:
        proc = subprocess.run(
            [
                "python3",
                "scripts/model_research/model_offline_load_smoke.py",
                "--self-test",
                "--json",
            ],
            cwd=smoke.REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "offline_load_smoke_passed")
        self.assertEqual(payload["outbound_connection_attempts"], 0)


if __name__ == "__main__":
    unittest.main()
