from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.agent_loop import run_claude, run_codex
from scripts.agent_loop import validate_repo as vr
from scripts.agent_loop._common import validate_against_schema


def _phrase(*tokens: str) -> str:
    """Join tokens at runtime.

    The forbidden verdict phrases below must never exist as a contiguous literal
    in this tracked file, or ``legal_verdict_scan`` would (correctly) flag this
    very test. Assembling them with a runtime join keeps the literal out of the
    source while still producing the exact phrase the scanner must catch.
    """
    return " ".join(tokens)


# Real prohibited product claims, assembled at runtime (never literal here).
PROHIBITED_CLAIMS = [
    _phrase("FInk", "determines", "the", "contract", "is", "fraud"),
    _phrase("FInk", "guarantees", "a", "financial", "loss"),
    _phrase("FInk", "score", "is", "a", "guaranteed", "loss"),
    _phrase("trained", "end-to-end", "DFL"),
]

# Safe disclaimers. These are deliberately literal: they are realistic FInk
# phrasings that MUST pass, and keeping them literal proves the scanner does not
# over-match. None of them matches any BAD_LEGAL_ASSERTIONS pattern.
SAFE_DISCLAIMERS = [
    "FInk does not determine fraud, illegality, or contract validity; "
    "it reports a Contractual Financial Review Priority Score only.",
    "FInk produces a review-priority score and never issues a legal verdict.",
    "This tool flags clauses for human review and does not decide unfairness.",
]


class LegalVerdictScannerTests(unittest.TestCase):
    def test_real_prohibited_claims_are_flagged(self) -> None:
        for claim in PROHIBITED_CLAIMS:
            with self.subTest(claim=claim):
                self.assertTrue(
                    any(pattern.search(claim) for pattern in vr.BAD_LEGAL_ASSERTIONS),
                    f"no pattern matched a real prohibited claim: {claim!r}",
                )

    def test_safe_disclaimers_pass(self) -> None:
        for disclaimer in SAFE_DISCLAIMERS:
            with self.subTest(disclaimer=disclaimer):
                self.assertFalse(
                    any(pattern.search(disclaimer) for pattern in vr.BAD_LEGAL_ASSERTIONS),
                    f"a safe disclaimer was wrongly flagged: {disclaimer!r}",
                )

    def test_scanner_own_definitions_not_flagged(self) -> None:
        # The raw source genuinely contains a forbidden literal (the policy
        # definition), so the redaction must be load-bearing: scanning the raw
        # text matches, scanning the redacted view does not.
        raw = vr.SELF_PATH.read_text(encoding="utf-8")
        redacted = vr.scannable_text(vr.SELF_PATH)
        self.assertTrue(
            any(pattern.search(raw) for pattern in vr.BAD_LEGAL_ASSERTIONS),
            "expected the raw scanner source to contain its own policy literal",
        )
        self.assertFalse(
            any(pattern.search(redacted) for pattern in vr.BAD_LEGAL_ASSERTIONS),
            "redaction failed: scanner still flags its own policy definitions",
        )
        # The redaction must remove only the definition block, not real code.
        self.assertIn("def legal_verdict_scan", redacted)
        self.assertIn("def queue_consistency", redacted)

    def test_redaction_markers_are_balanced(self) -> None:
        # An unbalanced/missing marker would silently redact the rest of the file
        # from scanning. Exactly one START and one END line must exist.
        lines = vr.SELF_PATH.read_text(encoding="utf-8").splitlines()
        starts = [ln for ln in lines if ln.strip() == "# FINK-POLICY-DEFINITIONS-START"]
        ends = [ln for ln in lines if ln.strip() == "# FINK-POLICY-DEFINITIONS-END"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(len(ends), 1)

    def test_redaction_only_applies_to_the_scanner_itself(self) -> None:
        # The exclusion is keyed strictly to the scanner's own path. Any other
        # file with the same marker text is returned (and scanned) in full.
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "other.py"
            other.write_text(
                "# FINK-POLICY-DEFINITIONS-START\nkeep this line\n# FINK-POLICY-DEFINITIONS-END\n",
                encoding="utf-8",
            )
            self.assertIn("keep this line", vr.scannable_text(other))

    def test_legal_verdict_gate_passes_on_repo(self) -> None:
        # End-to-end: the real gate over the real tree must pass. This is the
        # exact check that originally failed on the scanner's own source.
        self.assertEqual(vr.legal_verdict_scan(), "no forbidden verdict assertions")


class QueueConsistencyTests(unittest.TestCase):
    def test_real_queues_are_consistent(self) -> None:
        self.assertIn("queue.models.txt=10", vr.queue_consistency())

    def _run_isolated(self, backlog: str, queues: dict[str, str]) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue_dir = root / "scripts" / "agent_loop"
            queue_dir.mkdir(parents=True)
            (root / "loop").mkdir()
            (root / "loop" / "BACKLOG.yaml").write_text(backlog, encoding="utf-8")
            for name, content in queues.items():
                (queue_dir / name).write_text(content, encoding="utf-8")
            saved_root, saved_backlog = vr.REPO_ROOT, vr.BACKLOG_PATH
            vr.REPO_ROOT = root
            vr.BACKLOG_PATH = root / "loop" / "BACKLOG.yaml"
            try:
                return vr.queue_consistency()
            finally:
                vr.REPO_ROOT, vr.BACKLOG_PATH = saved_root, saved_backlog

    BACKLOG = (
        "tasks:\n"
        "- id: FINK-S0-01\n  depends_on: []\n"
        "- id: FINK-S0-02\n  depends_on: ['FINK-S0-01']\n"
    )

    def test_unknown_task_id_fails(self) -> None:
        with self.assertRaises(vr.GateFailure):
            self._run_isolated(self.BACKLOG, {"queue.s0.txt": "FINK-S0-01\nMR-001\n"})

    def test_duplicate_across_queues_fails(self) -> None:
        with self.assertRaises(vr.GateFailure):
            self._run_isolated(
                self.BACKLOG,
                {"queue.s0.txt": "FINK-S0-01\n", "queue.s1.txt": "FINK-S0-01\n"},
            )

    def test_dependency_order_within_queue_fails(self) -> None:
        with self.assertRaises(vr.GateFailure):
            self._run_isolated(self.BACKLOG, {"queue.s0.txt": "FINK-S0-02\nFINK-S0-01\n"})


class UntrackedScanCoverageTests(unittest.TestCase):
    """text_files_for_scan must cover untracked-non-ignored files (RA-3)."""

    def test_untracked_files_enter_scan_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tracked.py").write_text("ok\n", encoding="utf-8")
            (root / "fresh.py").write_text("ok\n", encoding="utf-8")
            saved = (vr.REPO_ROOT, vr.tracked_files, vr.untracked_files)
            vr.REPO_ROOT = root
            vr.tracked_files = lambda: ["tracked.py"]
            vr.untracked_files = lambda: ["fresh.py"]
            try:
                scanned = {p.name for p in vr.text_files_for_scan()}
            finally:
                vr.REPO_ROOT, vr.tracked_files, vr.untracked_files = saved
            self.assertIn("fresh.py", scanned)
            self.assertIn("tracked.py", scanned)

    def test_secret_in_untracked_file_is_flagged(self) -> None:
        # Assemble the secret at runtime so the literal never exists in this
        # tracked test file (otherwise secret_scan would flag this very file).
        secret = "sk-" + ("a" * 28)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "leak.py").write_text("token = '" + secret + "'\n", encoding="utf-8")
            saved = (vr.REPO_ROOT, vr.tracked_files, vr.untracked_files)
            vr.REPO_ROOT = root
            vr.tracked_files = lambda: []
            vr.untracked_files = lambda: ["leak.py"]
            try:
                with self.assertRaises(vr.GateFailure):
                    vr.secret_scan()
            finally:
                vr.REPO_ROOT, vr.tracked_files, vr.untracked_files = saved


class ModelLicenseFloorTests(unittest.TestCase):
    """Open-source-only model policy enforced as a machine gate (HD-12)."""

    def test_real_repo_passes(self) -> None:
        self.assertIn("open-license floor ok", vr.model_license_floor())

    def test_tracked_weight_fails(self) -> None:
        saved = vr.tracked_files
        vr.tracked_files = lambda: ["models/model.safetensors"]
        try:
            with self.assertRaises(vr.GateFailure):
                vr.model_license_floor()
        finally:
            vr.tracked_files = saved

    def _isolated(self, candidates_yaml: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs" / "models").mkdir(parents=True)
            (root / "configs" / "models" / "candidates.yaml").write_text(
                candidates_yaml, encoding="utf-8"
            )
            saved_root, saved_tracked = vr.REPO_ROOT, vr.tracked_files
            vr.REPO_ROOT = root
            vr.tracked_files = lambda: []
            try:
                return vr.model_license_floor()
            finally:
                vr.REPO_ROOT, vr.tracked_files = saved_root, saved_tracked

    def test_widened_allowlist_fails(self) -> None:
        with self.assertRaises(vr.GateFailure):
            self._isolated(
                "license_policy:\n  public_open_allowlist: [apache-2.0, research-only]\n"
                "candidates: {}\n"
            )

    def test_non_open_declared_license_fails(self) -> None:
        with self.assertRaises(vr.GateFailure):
            self._isolated(
                "license_policy:\n  public_open_allowlist: [apache-2.0]\n"
                "candidates:\n  ocr:\n    - id: x\n      license: cc-by-nc-4.0\n"
            )

    def test_open_declared_license_passes(self) -> None:
        out = self._isolated(
            "license_policy:\n  public_open_allowlist: [apache-2.0, mit]\n"
            "candidates:\n  ocr:\n    - id: x\n      license: apache-2.0\n"
        )
        self.assertIn("open-license floor ok", out)


class ClaudeEnvelopeParsingTests(unittest.TestCase):
    """run_claude must read the review out of the CLI's JSON envelope."""

    def test_extracts_review_from_fenced_result(self) -> None:
        review = {"verdict": "APPROVE", "summary": "ok"}
        envelope = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Here is my review:\n```json\n" + json.dumps(review) + "\n```",
        }
        out = run_claude.parse_review_payload(json.dumps(envelope))
        self.assertEqual(out["verdict"], "APPROVE")

    def test_extracts_review_from_raw_result(self) -> None:
        envelope = {"is_error": False, "result": json.dumps({"verdict": "REQUEST_CHANGES"})}
        out = run_claude.parse_review_payload(json.dumps(envelope))
        self.assertEqual(out["verdict"], "REQUEST_CHANGES")

    def test_cli_error_envelope_becomes_blocked(self) -> None:
        envelope = {"is_error": True, "subtype": "error_max_turns", "result": ""}
        out = run_claude.parse_review_payload(json.dumps(envelope))
        self.assertEqual(out["verdict"], "BLOCKED")

    def test_bare_review_passthrough(self) -> None:
        out = run_claude.parse_review_payload(json.dumps({"verdict": "BLOCKED", "summary": "x"}))
        self.assertEqual(out["verdict"], "BLOCKED")

    def test_unparseable_result_becomes_blocked(self) -> None:
        envelope = {"is_error": False, "result": "I could not produce a verdict."}
        out = run_claude.parse_review_payload(json.dumps(envelope))
        self.assertEqual(out["verdict"], "BLOCKED")

    def test_non_json_stdout_becomes_blocked(self) -> None:
        self.assertEqual(run_claude.parse_review_payload("not json").get("verdict"), "BLOCKED")


class AgentModelPinTests(unittest.TestCase):
    def test_codex_model_is_pinned(self) -> None:
        source = Path(run_codex.__file__).read_text(encoding="utf-8")
        self.assertIn('"gpt-5.5"', source)
        self.assertIn('"xhigh"', source)

    def test_claude_model_is_pinned_exactly(self) -> None:
        source = Path(run_claude.__file__).read_text(encoding="utf-8")
        # Must be the exact id, not the ambiguous "opus" alias.
        self.assertIn('"claude-opus-4-8"', source)
        self.assertIn('"max"', source)

    def test_claude_review_is_schema_validated(self) -> None:
        self.assertTrue(run_claude.CLAUDE_REVIEW_SCHEMA.exists())
        valid = run_claude.empty_review("APPROVE", "ok")
        self.assertIsNone(validate_against_schema(valid, run_claude.CLAUDE_REVIEW_SCHEMA))

    def test_invalid_claude_review_is_rejected_when_jsonschema_present(self) -> None:
        try:
            import jsonschema  # noqa: F401
        except Exception:  # pragma: no cover - offline fallback
            self.skipTest("jsonschema not installed; validation is a no-op here")
        bad = {"verdict": "MAYBE", "summary": "missing required arrays"}
        self.assertIsNotNone(validate_against_schema(bad, run_claude.CLAUDE_REVIEW_SCHEMA))


if __name__ == "__main__":
    unittest.main()
