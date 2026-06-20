# FInk Agent-Loop Bootstrap Repair Summary

- Engineer/auditor: Claude Opus 4.8 (effort max), lead bootstrap repair + safety audit.
- Date: 2026-06-21.
- Branch: `main` (only local branch). HEAD at repair: `b0f9644`.
- Loop base/state commit: `b3803bfa4df0e72a1b8623e271d8f202eba3dbd1`.
- Scope: agent-loop infrastructure only. No product feature implemented, no human
  gate approved, no commit, no push, no deploy, no DNS change, no ICML template
  edit, no branch created, no Hugging Face token read.

All changes are uncommitted in the working tree on `main`, for operator review.

## 1. Root causes

1. **Forbidden legal-verdict self-scan (the headline blocker).** `legal_verdict_scan`
   scans every tracked text file for verdict-style phrasings, but the patterns it
   searches for are *defined* in `validate_repo.py`. The third pattern is a plain
   string literal (a trained-end-to-end model-training claim), so the scanner
   matched its own policy definition and `run_gates.sh` failed with
   `forbidden legal/result assertion in: scripts/agent_loop/validate_repo.py`.
   Reproduced precisely: only that one pattern self-matches; the two structured
   `FInk ...`-anchored regexes never match their own definitions.

2. **No machine guard tying queues to the backlog.** The queues already resolved
   to real backlog ids (a prior session had reverted `queue.models.txt` from the
   phantom `MR-001..MR-014` back to `FINK-MR-01..FINK-MR-10`), but nothing
   *enforced* that. A future phantom id would silently make a lane unreachable
   (`select_next` drops unknown ids), exactly the original `queue.models.txt`
   failure.

3. **Ambiguous Claude model + unvalidated Claude result.** `run_claude.py` used the
   `--model opus` alias (not the pinned `claude-opus-4-8`) and, unlike
   `run_codex.py`, never schema-validated the review it persisted.

4. **`uv run pytest` could never pass.** Two independent reasons: `pytest` was not a
   declared dependency, and the repo root was not on `sys.path` under pytest, so
   `from scripts.agent_loop import ...` raised `ModuleNotFoundError`. Also, the loop
   genuinely requires PyYAML (it raises `LoopError` without it) yet declared
   `dependencies = []`.

5. **Content scanners skipped brand-new files.** `secret_scan` / `private_quote_scan`
   / `legal_verdict_scan` iterated tracked files only, so a file a task newly
   created was first scanned on the *next* task's gates — after `git_checkpoint`'s
   `git add -A` had already committed it (a real "never commit a secret" window).

6. **No sequential multi-queue runner**, and running one would have deadlocked on
   the single writer lock that `loop_once.sh` re-acquires per task.

## 2. Files changed

| File | Change |
|------|--------|
| `scripts/agent_loop/validate_repo.py` | Sentinel-block redaction of the policy-definition literals from the scanner's own source (kept from the prior in-tree fix), keyed strictly to this file's path; new `queue_consistency` gate; content scanners now cover untracked-non-ignored files; dropped two unused imports (F401). |
| `scripts/agent_loop/_common.py` | Added `untracked_files()` helper (untracked, `.gitignore`-respecting). |
| `scripts/agent_loop/run_claude.py` | Pinned model to `claude-opus-4-8` (removed the ambiguous `opus` alias); added `emit_review()` that schema-validates the review before persisting (mirrors `run_codex.py`). |
| `scripts/agent_loop/loop_once.sh` | Refactored the locked body into `run_task()`; honor `FINK_LOCK_HELD=1` so a parent runner that already holds the single writer lock does not deadlock. Behavior identical when run standalone. |
| `scripts/agent_loop/select_next.py` | Added read-only `--explain` mode that names queue tasks blocked solely by a closed human gate. |
| `scripts/agent_loop/run_all_queues.sh` | **New.** Sequential runner over the five queues in dependency order, under one writer lock. |
| `scripts/agent_loop/update_loop_docs.py` | Surfaced `run_all_queues.sh` in generated operator commands; fixed a placeholder-less f-string (F541). |
| `scripts/agent_loop/README.md` | Documented `run_all_queues.sh` exact usage, order, lock, STOP, gate-stop, logs, nohup, dry-run. |
| `LOOP.md` | Regenerated from the updated generator. |
| `pyproject.toml` | Declared the real PyYAML runtime dependency; added a dev group (`pytest`, `jsonschema`); set `pythonpath = ["."]` so `uv run pytest` resolves imports. |
| `uv.lock` | Lock churn from the two new dev tools + PyYAML. |
| `tests/test_gate_safety.py` | **New.** Regression tests (see below). |
| `loop/reviews/BOOTSTRAP_AUDIT.md`, `BOOTSTRAP_REQUIRED_ACTIONS.yaml`, `BOOTSTRAP_REPAIR_SUMMARY.md` | Audit outputs. |

No other files were touched. `paper/template/icml2026/**`, `loop/HUMAN_GATES.yaml`,
and `loop/MODEL_RESEARCH_HUMAN_GATES.yaml` are byte-unchanged.

## 3. Tests added (`tests/test_gate_safety.py`, 16 new test methods)

Legal-verdict scanner:
- a real prohibited product claim is flagged (phrases assembled at runtime so the
  literal never lands in a scanned file);
- realistic safe disclaimers pass;
- the scanner's own policy-definition text is not flagged, *and* the redaction is
  load-bearing (raw source matches, redacted view does not) and removes only the
  definition block (real code such as `def legal_verdict_scan` survives);
- the redaction markers are balanced (guards against silent over-redaction);
- the redaction is keyed to the scanner's path only (any other file's marker text
  is returned in full);
- `legal_verdict_scan()` passes on the real tree.

Queue/backlog consistency: real queues pass; unknown id, cross-queue duplicate,
and in-queue dependency-order violations each fail.

Untracked-file coverage (RA-3): untracked files enter the scan set; a secret in an
untracked file is flagged (secret assembled at runtime).

Model pins + schema validation: Codex `gpt-5.5`/`xhigh`; Claude `claude-opus-4-8`/
`max` (and the bare `opus` alias is absent); the dry-run review schema-validates;
a malformed review is rejected when `jsonschema` is present.

## 4. Commands actually run (this session) and actual results

| Command | Result |
|---------|--------|
| `git branch --show-current` / `--list` | `main`; only `main`. |
| `git status --short` | 11 modified + 2 untracked (this repair); nothing staged/committed. |
| `bash scripts/agent_loop/doctor.sh --no-llm` | `DOCTOR_OK branch=main` (rc 0). |
| `bash scripts/agent_loop/run_gates.sh` | `GATES_OK`, 19 `[PASS]` (rc 0). |
| `uv run pytest` | `21 passed, 7 subtests passed` (rc 0). |
| `python3 -m unittest discover -s tests` (gate fallback) | `Ran 21 tests ... OK` (rc 0). |
| `bash scripts/agent_loop/loop_once.sh --dry-run` | `DRY_RUN_OK task=FINK-S0-01` (rc 0). |
| `loop_run.sh queue.s0.txt 1 --dry-run` | `DRY_RUN_OK task=FINK-S0-01` (rc 0). |
| `loop_run.sh queue.models.txt 1 --dry-run` | `DRY_RUN_OK task=FINK-MR-01` (rc 0). |
| `bash scripts/agent_loop/run_all_queues.sh --dry-run` | all 5 queues `QUEUE_DONE`, `FULL_LOOP_DONE` (rc 0). |
| `run_all_queues.sh --max-tasks-per-queue 20 --dry-run` | `FULL_LOOP_DONE` (rc 0). |

Negative/safety checks that ran: queue gate fails on phantom/duplicate/dep-order;
the writer lock refuses a second loop command; `--max-tasks-per-queue abc` and an
unknown flag exit 2; `loop/STOP` halts the runner cleanly; `--explain` names
`MODEL_LICENSES_APPROVED` for `FINK-MR-04` once its dependency is `DONE`.

The real `codex` and `claude` CLIs are present in this environment, so **no
non-dry-run loop command was run** (it would invoke the real agents on the real
repo and implement product features / commit, both prohibited here). Every loop
command above used `--dry-run`, which short-circuits before the CLIs are called.

## 5. Remaining human gates (unchanged; none approved)

OPEN: `HR-01`, `HR-02`, `HR-03`, `HR-04`, `HR-05`, `HR-06`, `HR-08`,
`MODEL_LICENSES_APPROVED`, `MODEL_DOWNLOAD_APPROVED`, `MODEL_PROFILE_APPROVED`.
APPROVED (pre-existing, human-set): `HR-07`, `MODEL_METADATA_NETWORK_APPROVED`.
This audit approved nothing.

## 6. Documented follow-ups (non-blocking; not done this session — see RA list)

`RA-1` (graceful scoped rollback on a real-run gate/sub-tool failure) and `RA-2`
(persist `BLOCKED`/exhausted status so a failed task is not re-selected) touch the
real-run failure/commit control flow. They are **fail-stop, not unsafe**: the loop
never commits on failing gates (`set -e` aborts before the APPROVE→commit branch is
reached) and never pushes; the worst case is a dirty tree needing manual cleanup
and a manual re-run repeating a blocked task. They are deferred deliberately
because they can only be *executed*-tested by driving a real Codex/Claude failure
round, which this session must not do. `RA-4` (informational duplicate model-gate
file), `RA-6` (`ruff`/`mypy`/`pytest` binaries absent; offline fallbacks are the
supported path — the specific F401/F541 items ruff would flag were fixed), and
`RA-7` (`git_checkpoint` pre-stage check) are minor/nit.

## 7. Is the real loop safe to start?

**Yes, safe to start — recommended supervised first.** Single-`main`, clean-tree +
`BASE_COMMIT`, deterministic selection, dependency/human-gate gating, flock + STOP,
bounded 4 rounds, pinned Codex/Claude models, schema-validated results, scoped
rollback for Claude verdicts, enforced privacy/secret/legal/license gates
(strengthened to untracked files), queue/backlog consistency, ICML preservation,
and a never-push policy are all present and verified. Begin with a small
`--max-tasks-per-queue` (or `loop_once.sh`) and watch the first real failure; the
loop fails safe. Implement `RA-1`/`RA-2` before fully unattended, long multi-task
runs so a real-run failure rolls back and persists status without manual cleanup.

## 8. Exact commands to execute next

```bash
# 1. Re-confirm the green state (all should pass)
bash scripts/agent_loop/doctor.sh --no-llm
bash scripts/agent_loop/run_gates.sh
uv run pytest
bash scripts/agent_loop/run_all_queues.sh --dry-run

# 2. Review and commit this bootstrap repair (operator decision; loop never commits this)
git add -A && git status
git commit -m "fix(loop): repair legal-verdict self-scan; add queue-consistency gate, run_all_queues, model pin + schema validation"

# 3. First REAL run, supervised, one foundation task
bash scripts/agent_loop/loop_once.sh

# 4. When ready, drive the foundation queue (resumes from loop state)
bash scripts/agent_loop/run_all_queues.sh --max-tasks-per-queue 8

# 5. To stop after the current task at any time
touch loop/STOP
```
