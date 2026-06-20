from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.agent_loop import rollback_failed_task as rollback
from scripts.agent_loop._common import (
    BACKLOG_PATH,
    HUMAN_GATES_PATH,
    load_backlog,
    load_human_gates,
    load_state,
    select_eligible_task,
)


class AgentLoopTests(unittest.TestCase):
    def test_select_next_starts_with_spec_s0_task(self) -> None:
        selected = select_eligible_task(load_backlog(), load_human_gates(), load_state())
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.task["id"], "FINK-S0-01")

    def test_backlog_contains_required_model_research_tasks(self) -> None:
        ids = {task["id"] for task in load_backlog()["tasks"]}
        for idx in range(1, 11):
            self.assertIn(f"FINK-MR-{idx:02d}", ids)

    def test_state_keeps_icml_template_hashes(self) -> None:
        state = load_state()
        hashes = state["icml_template_hashes"]
        self.assertIn("paper/template/icml2026/icml2026.sty", hashes)
        self.assertRegex(hashes["paper/template/icml2026/icml2026.sty"], r"^[a-f0-9]{64}$")

    def test_required_loop_files_parse(self) -> None:
        self.assertTrue(BACKLOG_PATH.exists())
        self.assertTrue(HUMAN_GATES_PATH.exists())
        json.loads(Path("loop/STATE.json").read_text(encoding="utf-8"))

    def test_failed_task_rollback_is_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "allowed").mkdir()
            (repo / "outside").mkdir()
            (repo / "allowed" / "file.txt").write_text("base\n", encoding="utf-8")
            (repo / "outside" / "keep.txt").write_text("keep\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            (repo / "allowed" / "file.txt").write_text("changed\n", encoding="utf-8")
            (repo / "allowed" / "new.txt").write_text("remove me\n", encoding="utf-8")
            (repo / "outside" / "new.txt").write_text("preserve me\n", encoding="utf-8")

            old_root = rollback.REPO_ROOT
            old_git = rollback.git

            def temp_git(args: list[str], *, check: bool = True, capture: bool = True):
                return subprocess.run(
                    ["git", *args],
                    cwd=repo,
                    check=check,
                    text=True,
                    capture_output=capture,
                )

            try:
                rollback.REPO_ROOT = repo
                rollback.git = temp_git
                rollback.rollback_task(
                    {"allowed_paths": ["allowed/"]},
                    base,
                    repo / "runs" / "failed",
                    "BLOCKED",
                )
            finally:
                rollback.REPO_ROOT = old_root
                rollback.git = old_git

            self.assertEqual((repo / "allowed" / "file.txt").read_text(encoding="utf-8"), "base\n")
            self.assertFalse((repo / "allowed" / "new.txt").exists())
            self.assertTrue((repo / "outside" / "new.txt").exists())
            self.assertTrue((repo / "runs" / "failed" / "FAILED.patch").exists())


if __name__ == "__main__":
    unittest.main()
