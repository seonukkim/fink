from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = REPO_ROOT / "scripts" / "public_repo_preflight.sh"

REQUIRED_GITIGNORE = (
    ".fink/",
    "*.pdf",
    "*.zip",
    "uploads/",
    "contracts/",
    "models/",
    "indexes/",
    "data/private/",
    "data/raw/",
    "data/unsanitized/",
    ".env",
    "*.env",
)


class PublicRepoPreflightTests(unittest.TestCase):
    def test_clean_candidate_emits_preflight_ok(self) -> None:
        with self._repo() as root:
            self._write_gitignore(root)
            (root / "README.md").write_text("# Public fixture\n", encoding="utf-8")

            proc = self._run_preflight(root)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("gitignore_enforced:", proc.stdout)
        self.assertIn("preflight_ok:", proc.stdout)
        self.assertIn("secret_scan:", proc.stdout)
        self.assertIn("PREFLIGHT_OK", proc.stdout)

    def test_missing_required_ignore_rule_fails(self) -> None:
        with self._repo() as root:
            self._write_gitignore(root, omit={"uploads/"})
            (root / "README.md").write_text("# Public fixture\n", encoding="utf-8")

            proc = self._run_preflight(root)

        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("gitignore_enforced failed", proc.stderr)

    def test_prohibited_staged_file_fails_without_filename_leak(self) -> None:
        with self._repo() as root:
            self._write_gitignore(root)
            prohibited = root / "creator-private.pdf"
            prohibited.write_bytes(b"%PDF-private")
            self._git(root, "add", "-f", "creator-private.pdf")

            proc = self._run_preflight(root)

        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("prohibited commit-candidate", proc.stderr)
        self.assertNotIn("creator-private.pdf", proc.stdout + proc.stderr)
        self.assertNotIn("%PDF-private", proc.stdout + proc.stderr)

    def test_secret_scan_fails_without_secret_value_leak(self) -> None:
        secret = "sk-" + ("a" * 28)
        with self._repo() as root:
            self._write_gitignore(root)
            (root / "notes.md").write_text(f"api token: {secret}\n", encoding="utf-8")

            proc = self._run_preflight(root)

        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("secret_scan failed", proc.stderr)
        self.assertNotIn(secret, proc.stdout + proc.stderr)
        self.assertNotIn("notes.md", proc.stdout + proc.stderr)

    def test_env_candidate_fails_without_reading_secret_text(self) -> None:
        secret = "hf_" + ("A" * 24)
        with self._repo() as root:
            self._write_gitignore(root)
            env_file = root / ".env"
            env_file.write_text(f"HF_TOKEN={secret}\n", encoding="utf-8")
            self._git(root, "add", "-f", ".env")
            os.chmod(env_file, 0)

            proc = self._run_preflight(root)

        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("sensitive environment file", proc.stderr)
        self.assertNotIn(secret, proc.stdout + proc.stderr)
        self.assertNotIn("Permission denied", proc.stdout + proc.stderr)

    def test_success_logs_do_not_include_candidate_filenames_or_text(self) -> None:
        raw_filename = "actual_creator_contract_name.md"
        raw_text = "PRIVATE_CONTRACT_TEXT_SHOULD_NOT_APPEAR"
        with self._repo() as root:
            self._write_gitignore(root)
            (root / raw_filename).write_text(raw_text + "\n", encoding="utf-8")

            proc = self._run_preflight(root)

        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PREFLIGHT_OK", proc.stdout)
        self.assertNotIn(raw_filename, combined)
        self.assertNotIn(raw_text, combined)

    @staticmethod
    def _run_preflight(root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(PREFLIGHT)],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def _write_gitignore(root: Path, omit: set[str] | None = None) -> None:
        omitted = omit or set()
        lines = [line for line in REQUIRED_GITIGNORE if line not in omitted]
        (root / ".gitignore").write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )

    @classmethod
    @contextmanager
    def _repo(cls) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "checkout", "-b", "main"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            yield root


if __name__ == "__main__":
    unittest.main()
