# FInk Agent-Loop Bootstrap Audit

- Auditor: Claude Opus 4.8 (Max), independent audit + scoped repair.
- Date: 2026-06-21.
- Branch at audit: `main` (only local branch is `main`).
- Base commit: `b3803bfa4df0e72a1b8623e271d8f202eba3dbd1`.
- Scope: agent-loop infrastructure only. No product features implemented, no
  human gates approved, no commit, no push, no deploy, no DNS change, no ICML
  template edit, no branch created.

## 0. Verdict summary

`REQUEST_CHANGES`. Three concrete bugs were found and **fixed in-tree** by this
audit (queue ID mismatch; two `.gitignore` defects). Three failure-path /
coverage defects in the orchestrator remain and are recorded as required Codex
actions (RA-1…RA-3) because they touch run-control flow and **must be
execution-tested** to land safely — and one naive form of the fix would be
destructive in `--dry-run`. In addition, the session permission mode blocked
execution of every script/interpreter command, so the machine gates could not be
re-run in this session; per `CLAUDE.md` ("Do not approve if machine gates fail")
I cannot positively certify the gates pass here. The combination yields
`REQUEST_CHANGES` rather than `APPROVE`.

The loop is structurally sound on the happy path and the dry-run path (assuming
gates pass): single-`main` policy, deterministic selection, dependency/human-gate
gating, flock + STOP, clean-tree + BASE_COMMIT capture, scoped rollback, Codex
GPT-5.5 xhigh / Claude Opus Max invocation, JSON-Schema validation, four-round
cap, allowed-path scope gate, financial-formula gate, privacy/legal scans,
ledgers, AI-use log, and complete run artifacts are all present.

## 1. Verification performed (and its limits)

Read-only checks that succeeded:
- `git branch --show-current` → `main`; `git branch --list` → only `main`.
- Full static read of `docs/FINK_MASTER_SPEC.md`, all `docs/specs/*`, `AGENTS.md`,
  `CLAUDE.md`, `LOOP.md`, all of `loop/`, all of `scripts/agent_loop/`,
  `scripts/model_research/`, `pyproject.toml`, `.gitignore`, `tests/`,
  `configs/models/candidates.yaml`, the paper ledgers, and the publish scripts.
- ICML template present with the 8 files recorded in `loop/STATE.json`.

Could **not** run (denied by this session's permission mode — held for approval
and not granted, including with sandbox override):
`bash scripts/agent_loop/doctor.sh --no-llm`, `bash scripts/agent_loop/run_gates.sh`,
`uv run pytest`, `bash scripts/agent_loop/loop_once.sh --dry-run`,
`bash scripts/agent_loop/loop_run.sh scripts/agent_loop/queue.s0.txt 1 --dry-run`,
and even `git check-ignore`. These were therefore audited **statically**. The
operator must run the six commands to confirm dynamic behavior; this audit does
not claim they were executed.

## 2. Fixes applied by this audit (in-tree, uncommitted)

| ID | File | Defect | Fix |
|----|------|--------|-----|
| F1 | `scripts/agent_loop/queue.models.txt` | Contained `MR-001`…`MR-014`, which match **no** backlog task. The backlog tasks are `FINK-MR-01`…`FINK-MR-10`. `select_next` filters `task_id not in queue_ids`, so this queue selected **zero** tasks → the model-research lane was unreachable. | Replaced with the 10 real IDs `FINK-MR-01`…`FINK-MR-10`. |
| F2 | `.gitignore` | A trailing unanchored `models/` appeared **after** `!configs/models/**`. By last-match precedence it re-ignored the `configs/models/` directory, so new `configs/models/**` files (which the model-card and FINK-MR tasks say belong in public Git) would be silently dropped by `git add -A`. | Moved the `!configs/...` negations to **after** the `/models/` and `models/` ignores so the negation wins for `configs/models/**` while `models/` still ignores weights everywhere else. |
| F3 | `.gitignore` | `secret_scan` deliberately skips files named/suffixed `.env`, yet `.env` was not gitignored — a committed `.env` would evade secret detection. | Added `.env` and `*.env` ignores. |

F1 is a data-file fix not read by any gate. F2/F3 do not affect gate execution
(gates use `git ls-files`, not `.gitignore` parsing) and introduce no surprise
files (no untracked `configs/models/**` or `.env` files currently exist). F2 was
verified by gitignore semantics (last-matching pattern + parent re-inclusion),
not by `git check-ignore` (denied).

## 3. Required actions (Codex; re-audit after)

See `loop/reviews/BOOTSTRAP_REQUIRED_ACTIONS.yaml` for the machine-readable list.

- **RA-1 (major) — gate failure leaves a dirty tree.** `loop_once.sh` runs
  `bash run_gates.sh > log` under `set -e`. If a gate fails after Codex or after
  Claude, the script aborts at that line **before** any rollback: no
  `FAILED.patch`/`FAILED.status`, allowed paths not restored, `main` left dirty —
  violating the charter ("a failed task … leaves main clean"). The next run then
  fails its clean-tree gate and the loop is stuck until a human cleans up.
  Required: capture the gate exit status without aborting and roll back within
  `allowed_paths` on failure. **Critical constraint:** this must **not** trigger
  rollback in `--dry-run` — `FINK-S0-01`'s `allowed_paths` includes `scripts/`,
  and a dry-run rollback would `git restore` + delete the **untracked**
  `scripts/agent_loop/*` files. Gate the rollback on `dry_run != 1`.

- **RA-2 (major) — blocked tasks are never recorded, so they retry forever.** On
  `BLOCKED` and on `EXHAUSTED_REQUEST_CHANGES`, `loop_once.sh` calls
  `rollback_failed_task.py` but never calls `apply_verdict.py`, so the task stays
  `READY` in the backlog and `active_task` stays null. The next `loop_once`
  re-selects the same task with the same inputs → unbounded BLOCK→rollback→retry.
  `apply_verdict.py` already has the `BLOCKED` branch; it is simply never invoked
  from the orchestrator. Required: persist `BLOCKED` (and surface
  `EXHAUSTED_REQUEST_CHANGES`) so the task is excluded from re-selection.

- **RA-3 (moderate) — privacy/secret/legal scans miss brand-new files.**
  `secret_scan`, `legal_verdict_scan`, and `private_quote_scan` iterate
  `tracked_files()` (`git ls-files`). Files Codex newly creates are **untracked**
  at gate time and are first scanned only on the *next* task's gates — after
  `git_checkpoint`'s `git add -A` has already committed them. A secret, legal
  verdict, or long private quotation in a new file is committed before it is ever
  scanned. Required: extend the scan set to untracked-non-ignored files
  (`git ls-files --others --exclude-standard`), preserving the `.env` skip and the
  `.fink/`/binary exclusions. (Strengthening only — does not weaken any gate.)

- **RA-4 (minor) — duplicate gate source of truth.**
  `loop/MODEL_RESEARCH_HUMAN_GATES.yaml` duplicates the four `MODEL_*` gates that
  already live in `loop/HUMAN_GATES.yaml` (the file the loop actually loads), with
  a different schema. Two sources can drift. Consolidate into `HUMAN_GATES.yaml`
  or mark the other explicitly as informational.

- **RA-5 (minor) — unused state fields / lock semantics.** `active_task` is never
  set during a run and `path_locks` is always `{}`, so the path-lock conflict
  branch in `select_eligible_task` is currently dead code; single-run mutual
  exclusion relies solely on the `.fink/agent-loop.lock` flock. Either set/clear
  `active_task` around a run or document that flock is the sole concurrency guard.

## 4. Audit matrix (25 required dimensions)

Legend: PASS = correct; PASS* = correct by static reading only (not executed);
CONCERN = defect recorded above.

1. Deterministic task selection — PASS*. `select_eligible_task` sorts by
   (priority P0<P1<…, scope S<M<L, lexical id); `FINK-S0-01` selected first.
2. Dependency + human-gate enforcement — PASS*. Deps must be `DONE`; every
   `human_gate` must be `approved:true` or `RESOLVED`. MR download/license/profile
   gates are OPEN, so `FINK-MR-04/05/10` cannot be selected.
3. Lock + STOP behavior — PASS*. `flock -n 9` writer lock; `loop/STOP` checked in
   `loop_once.sh` and each `loop_run.sh` iteration; `loop/STOP.example` documents it.
4. Main-branch enforcement — PASS*. `loop_once.sh` + `branch_gate` require branch
   `main` and reject any non-`main` local branch.
5. Clean-tree + BASE_COMMIT — PASS*. Clean tree required at task start (real runs);
   `BASE_COMMIT` recorded to the run dir; dry-run downgrades to a notice.
6. No branch creation/switching — PASS. No `git branch`/`switch`/`checkout -b`/
   `worktree` anywhere in `scripts/`.
7. Local direct commit on success — PASS*. `git_checkpoint.sh` commits on `main`
   only, refuses prohibited tracked files, never pushes.
8. Safe allowed-path rollback on failure — CONCERN (RA-1, RA-2). Scoped rollback is
   correct for Claude verdicts and unit-tested, but the gate-failure path bypasses
   it and blocked tasks are not persisted.
9. Codex GPT-5.5 xhigh — PASS*. `codex exec --model gpt-5.5 --reasoning-effort xhigh --json`.
10. Claude Opus 4.8 Max — PASS*. `claude -p --model opus --effort max --permission-mode acceptEdits --output-format json`.
11. JSON-Schema validation — PASS*. `task`/`state`/`codex_result`/`claude_review`
    schemas present; validated in gates and at emit time; graceful no-op if
    `jsonschema` is absent.
12. Max four repair rounds — PASS*. `for round in 1 2 3 4` (round 1 builder + 3
    repair); exhaustion triggers rollback. (Bounded at four cycles.)
13. Allowed-path enforcement — PASS*. `allowed_path_scope` gate diffs changed files
    vs `FINK_ALLOWED_PATHS` on real runs; `rollback` refuses unsafe paths.
14. All machine gates — PASS* (static) / NOT-EXECUTED. Gate set is complete and
    each was read; financial vectors recomputed by hand and match. Not run here.
15. Local-only runtime constraints — PASS*. No network in the loop; offline
    fallbacks for ruff/mypy/pytest; CLIs are local.
16. Private corpus exclusion — PASS (+F2/F3). `.fink/`, contracts, uploads, models,
    indexes, data/private|raw|unsanitized, PDFs, ZIPs ignored; `FORBIDDEN_TRACKED`
    + `git_checkpoint` block them; `.env` now ignored too.
17. Legal-language safeguards — PASS* (coverage caveat RA-3). `BAD_LEGAL_ASSERTIONS`
    + `legal_verdict_scan`; master spec / `docs/specs` excused for definitional text.
18. Financial-formula gate coverage — PASS. FIM-1 (=1,400,000), FIM-2 (PV≈237,760),
    FIM-3 ([17,9,4]), FIM-8 (low/base/high) recomputed and correct.
19. Paper-note + ledger sync — PASS*. `CLAIM_/RESULT_/FIGURE_` ledger headers match
    the `paper_ledgers` gate; no fabricated results; populated by future S7 tasks.
20. AI-use logging — PASS*. `docs/ai-use-log.md` carries the bootstrap entry and
    `HR-08` status (both required by the `ai_use_log` gate).
21. Complete run artifacts — PASS*. Per-round `task.json`, `selected_context.txt`,
    prompts, `codex_events.jsonl`, `codex_result.json`, both gate logs,
    `claude_review.json`, `diff.patch`, `summary.md`, plus `BASE_COMMIT.txt`/
    `selection.json`.
22. No push/deploy/DNS mutation — PASS. The loop never pushes. The only `git push`
    is in `scripts/create_public_repo.sh`, a human-only tool gated by
    `FINK_PUBLIC_CONFIRM=YES` + `gh auth`, not invoked by the loop.
23. Dry-run correctness — PASS* (assuming gates pass). `--dry-run` skips task-start
    gates, allows a dirty tree, stubs Codex/Claude, exits after round 1 with
    `DRY_RUN_OK`; `loop_run.sh … --dry-run` runs one iteration then exits. Not
    executed here.
24. LOOP.md observability — PASS*. `update_loop_docs.py --loop-md` regenerates
    state, human-gate table, next-task, and operator commands.
25. ToonTransfer-workflow compatibility — PASS. ToonTransfer appears only as a
    process analogy in `prompts/`; no ToonTransfer files or `.env` are copied.

## 5. Hugging Face auth + open-license policy addendum

- Token read path — PASS. The token **value** is read only by
  `scripts/model_research/run_with_hf_auth.sh` (`export HF_TOKEN="$(… < token)"`).
  `hf_auth_preflight.sh` only checks existence and `chmod 600` and explicitly does
  **not** read the value; `create_private_model_env.sh` writes an env file under
  `PRIVATE_ROOT` (outside the repo) and copies no token.
- Token never printed/committed — PASS*. No script echoes the token; secret
  patterns and `git_checkpoint` would block obvious leaks (subject to RA-3 for new
  files).
- ToonTransfer files / `.env` not copied — PASS. No copy of either; `.env` reads
  are forbidden and now also gitignored.
- Model weights excluded from Git — PASS (+F2). `/models/`, `models/`, HF cache,
  and `PRIVATE_ROOT/models` are out of Git; `configs/models/**` (IDs/licenses/
  revisions/configs only) stays tracked after F2.
- Open-license-only eligibility — PASS. `configs/models/candidates.yaml`
  `public_open` allowlist (apache-2.0, mit, bsd-2/3, isc, cc0-1.0, cc-by-4.0).
- Unknown/missing/gated/custom/noncommercial/research-only rejected by default —
  PASS. Listed under `reject_by_default`; mirrored in `docs/model-card.md`.
- Download requires metadata/license/revision/disk dry-run — PASS*. Encoded as
  `FINK-MR-02` (metadata/license/gated/revision) and `FINK-MR-03` (size dry run,
  no weights), both behind `MODEL_METADATA_NETWORK_APPROVED`.
- Runtime evaluation offline — PASS*. `FINK-MR-06` offline load smoke;
  `create_private_model_env.sh` sets `FINK_RUNTIME_OFFLINE=true`,
  `FINK_MODEL_DOWNLOAD_ALLOWED=false`, telemetry off.
- KO + EN benchmarked — PASS*. `FINK-MR-08` KO/EN retrieval consistency.
- OCR benchmark covers money/%/dates/durations/article numbers — PASS*.
  `FINK-MR-07` enumerates exactly these.
- Local LLM cannot create legal evidence or set production risk scores — PASS*.
  `FINK-MR-09` boundary test; `docs/model-card.md` states the prohibition.
- Download blocked behind human gates — PASS*. `FINK-MR-04` →
  `MODEL_LICENSES_APPROVED` (OPEN), `FINK-MR-05` → `MODEL_DOWNLOAD_APPROVED`
  (OPEN), `FINK-MR-10` → `MODEL_PROFILE_APPROVED` (OPEN); selection blocks all
  three. With F1, these tasks are now reachable through the models queue once a
  human approves the relevant gate.

## 6. Boundaries respected by this audit

No product feature implemented; no gate weakened (only F2/F3 hardening +
RA-3 strengthening proposed); no human gate approved; no commit; no push; no
deploy; no DNS change; the ICML template under `paper/template/icml2026/` was not
touched; no test result fabricated; no branch created (only `main` exists).

BOOTSTRAP_VERDICT: REQUEST_CHANGES
