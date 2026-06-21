from __future__ import annotations

import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "smoke" / "clean_clone_web.sh"


class CleanCloneWebSmokeScriptTests(unittest.TestCase):
    def test_script_exists_and_is_executable(self) -> None:
        self.assertTrue(SCRIPT.exists())
        self.assertTrue(os.access(SCRIPT, os.X_OK))

    def test_script_pins_clean_clone_runtime_guardrails(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        required_snippets = (
            "git clone --local --no-hardlinks --branch main --single-branch",
            "uv sync --extra web",
            "primary uv sync failed; trying cached offline wheelhouse",
            "uv sync --extra web --no-index --find-links",
            "env -u PYTHONPATH",
            "uv run --no-env-file --no-sync fink-web --host 127.0.0.1 --port",
            "LD_PRELOAD=",
            "FINK_NETWORK_GUARD_LOG=",
            "HF_HUB_OFFLINE=1",
            "TRANSFORMERS_OFFLINE=1",
            ".fink/clean_clone_web",
            "rm -rf \"$clone_dir\"",
            "kill -TERM \"$server_pid\"",
            "CLEAN_CLONE_WEB_SMOKE_OK",
        )
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, text)

        self.assertNotIn("git clone https://", text)
        self.assertNotIn("--host 0.0.0.0", text)
        self.assertNotIn("PYTHONPATH=", text)


if __name__ == "__main__":
    unittest.main()
