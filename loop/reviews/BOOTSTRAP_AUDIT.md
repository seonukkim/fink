# FInk Agent-Loop Bootstrap Audit

- Auditor: Claude Opus 4.8 (Max), independent audit + scoped repair.
- Date: 2026-06-21.
- Branch at audit: `main` (only local branch is `main`).
- Base commit (loop BASE/state): `b3803bfa4df0e72a1b8623e271d8f202eba3dbd1`.
- HEAD at audit: `d49720f` (bootstrap infrastructure commit).
- Scope: agent-loop infrastructure only. No product features implemented, no
  human gate approved, no commit, no push, no deploy, no DNS change, no ICML
  template edit, no branch created.

## 0. Verdict summary

`REQUEST_CHANGES`.

One working-tree defect was found and **fixed in-tree** by this audit
(`queue.models.txt` had been corrupted to IDs that match no backlog task; see
section 2). The fix also returned the worktree to a clean state identical to
`HEAD`. Beyond that, three real run-control / coverage defects remain in the
committed orchestrator (RA-1, RA-2, RA-3) plus three minor items (RA-4, RA-5,
RA-6) and one nit (RA-7). RA-1 is the decisive one: on a gate failure (or a
non-zero exit from the Codex/Claude sub-tools) the orchestrator aborts under
`set -e` **before** any rollback, leaving `main` dirty with no `FAILED.patch` —
which violates the charter guarantee that "a failed task ... leaves main clean"
and is exactly required audit dimension #8 ("safe allowed-path rollback on
failure"). These touch failure/commit control flow, are **not** exercised by any
of the six dry-run/no-LLM verification commands, and must be **execution-tested**;
one naive form of the RA-1 fix is destructive in `--dry-run`. They are therefore
recorded as required actions rather than hot-patched blind.

In addition, this session's permission mode held every script/interpreter command
for approval and did not grant it, so the six verification commands could not be
executed here (section 1). Per `CLAUDE.md` ("Do not approve if machine gates
fail") I will not positively certify the gates from this session. The most recent
recorded gate run and the recorded dry-run round artifacts both show `GATES_OK`
on the same gate-relevant code, and the worktree is now clean, so a re-run is
**expected** to reproduce `GATES_OK` — but this audit does not claim to have run
it. The combination yields `REQUEST_CHANGES`, not `APPROVE`.

The loop is structurally sound on the happy path and the dry-run path: single-
`main` policy, deterministic selection, dependency/human-gate gating, flock +
STOP, clean-tree + BASE_COMMIT capture, scoped rollback for Claude verdicts,
Codex GPT-5.5 xhigh / Claude Opus 4.8 Max invocation, JSON-Schema validation,
four-round cap, allowed-path scope gate, financial-formula gate, privacy/legal
scans, ledgers, AI-use log, and complete run artifacts are all present.

## 1. Verification performed (and its limits)

Read-only checks that succeeded this session:

- `git branch --show-current` -> `main`; `git branch --list` -> only `main`.
- `git status --short` -> empty (clean worktree) after the section-2 fix.
- Full static read of `docs/FINK_MASTER_SPEC.md`, all `docs/specs/*`, `AGENTS.md`,
  `CLAUDE.md`, `LOOP.md`, all of `loop/`, all of `scripts/agent_loop/`,
  `scripts/model_research/`, `pyproject.toml`, `.gitignore`, `tests/`,
  `configs/models/candidates.yaml`, the paper ledgers, and the publish scripts.
- The recorded gate run `.fink/runs/bootstrap/gates-before-claude.log` ->
  `GATES_OK` (17 FInk gates PASS) with `ruff`/`mypy`/`pytest` reported
  unavailable so the style/parse/unittest fallbacks ran; `python3` has PyYAML +
  jsonschema (YAML parse + schema validation ran for real).
  `.fink/runs/bootstrap/doctor-before-claude.log` -> `DOCTOR_OK`.
- A recorded dry-run round (`.fink/runs/20260620T211309Z-.../round-01/`) shows
  `gates_after_claude.log` = `GATES_OK` and `claude_review.json` = `APPROVE`
  (dry-run stub), i.e. the dry-run pipeline completes end-to-end.

Could **not** run this session (each held for approval and not granted, including
with the sandbox override): `bash scripts/agent_loop/doctor.sh --no-llm`,
`bash scripts/agent_loop/run_gates.sh`, `uv run pytest`,
`bash scripts/agent_loop/loop_once.sh --dry-run`,
`bash scripts/agent_loop/loop_run.sh scripts/agent_loop/queue.s0.txt 1 --dry-run`.
These were audited **statically** and against the recorded logs above. The
operator must run all six to confirm dynamic behavior; this audit does not claim
to have executed them.

## 2. Fix applied by this audit (in-tree, uncommitted)

| ID | File | Defect | Fix |
|----|------|--------|-----|
| F1 | `scripts/agent_loop/queue.models.txt` | The worktree copy had been changed to `MR-001`..`MR-014`, which match **no** backlog task. The backlog defines `FINK-MR-01`..`FINK-MR-10`, and `select_next` drops any id not present in the backlog, so this queue would select **zero** model-research tasks (the lane was unreachable). | Reverted to `FINK-MR-01`..`FINK-MR-10` (plus the explanatory header), matching `loop/BACKLOG.yaml` and `HEAD`. This restored a clean worktree (`git status --short` empty). |

F1 is a queue data file; it is not read by any gate and contains only task IDs
(no secret/legal/private content). Correctness was verified by reading the IDs
against `loop/BACKLOG.yaml` (which defines exactly `FINK-MR-01`..`FINK-MR-10`)
and by confirming the worktree became clean.

No executable gate code or orchestrator code was edited by this audit: with no
ability to run or even syntax-check Python/Bash this session, blind edits to the
gate engine (`validate_repo.py`) or run-control flow (`loop_once.sh`) would risk
regressing a currently-working happy path with no way to detect it. Those fixes
are specified as required actions below.

## 3. Required actions (for execution-tested implementation; re-audit after)

See `loop/reviews/BOOTSTRAP_REQUIRED_ACTIONS.yaml` for the machine-readable list.

- **RA-1 (major) — failure path leaves a dirty tree with no scoped rollback.**
  In `loop_once.sh`, `bash run_gates.sh > log` runs under `set -euo pipefail`.
  A gate failure after Codex or after Claude aborts the script at that line
  **before** any rollback: no `FAILED.patch`/`FAILED.status`, allowed paths not
  restored, `main` left dirty, and the next run then fails its clean-tree gate.
  The same abort-before-rollback happens when `run_codex.py` or `run_claude.py`
  exit non-zero (e.g. `run_claude.py` deliberately writes a `BLOCKED` review and
  then exits non-zero, clearly intending the orchestrator to act on `BLOCKED`,
  but `set -e` prevents it). Required: capture these exit statuses without
  aborting; on failure in a REAL run, preserve artifacts and roll back within
  `allowed_paths`; and make `APPROVE` -> commit conditional on the final gates
  having passed (never commit on failing gates). **Constraint:** must **not**
  roll back in `--dry-run` (`FINK-S0-01`'s `allowed_paths` include `scripts/`, so
  a dry-run rollback would `git restore` + delete untracked `scripts/agent_loop/*`
  files); gate the rollback on `dry_run != 1`.

- **RA-2 (major) — blocked / exhausted tasks are never persisted.**
  On `BLOCKED` and on `EXHAUSTED_REQUEST_CHANGES`, `loop_once.sh` calls
  `rollback_failed_task.py` but never `apply_verdict.py`, so the task stays
  `READY` and `active_task` stays null; a subsequent `loop_once` re-selects the
  same task with the same inputs. The `apply_verdict.py` `BLOCKED` branch already
  exists but is never invoked, and the exhausted case has no `BLOCKED` review at
  all. Required: persist the terminal status so the task is excluded from
  re-selection. **Reconciliation the fix must address:** writing `BLOCKED` into
  the tracked `loop/BACKLOG.yaml`/`loop/STATE.json` dirties the worktree, which
  then trips the clean-tree gate on the next run. Resolve by either (a) committing
  the bookkeeping as a dedicated `agent-loop: block <task>` checkpoint after the
  allowed-path rollback (mirroring the `APPROVE` path, so the failed *work* is not
  committed but the status is durable and `main` stays clean), or (b) recording
  the block in a git-ignored store under `.fink/` that `select_next` consults.

- **RA-3 (moderate) — privacy/secret/legal scans skip brand-new files.**
  `secret_scan`, `legal_verdict_scan`, and `private_quote_scan` iterate
  `tracked_files()` only. A file Codex newly creates is untracked at gate time and
  is first scanned on the *next* task's gates — after `git_checkpoint`'s
  `git add -A` has already committed it. Required: extend the scan set to
  untracked-non-ignored files (`git ls-files --others --exclude-standard`),
  keeping the `.env` skip and the `.fink/`/binary exclusions. Strengthening only;
  it weakens no gate (with the current clean tree there are no untracked files, so
  this changes no current result).

- **RA-4 (minor) — duplicate model-gate source of truth.**
  `loop/MODEL_RESEARCH_HUMAN_GATES.yaml` duplicates the four `MODEL_*` gates that
  already live in `loop/HUMAN_GATES.yaml` (the file the loop actually loads), with
  a different schema; the two can drift. Consolidate into `HUMAN_GATES.yaml` or
  mark the other file explicitly as informational-only.

- **RA-5 (minor) — unused `active_task` / `path_locks`.**
  `active_task` is never set during a run and `path_locks` is always `{}`, so the
  path-lock conflict branch in `select_eligible_task` is dead code; mutual
  exclusion relies solely on the `.fink/agent-loop.lock` flock. Note that setting
  `active_task` *before* the gates is unsafe today: `loop/STATE.json` is not in any
  task's `allowed_paths`, so writing it pre-gate would fail the `allowed_path_scope`
  gate. Either document that the flock is the sole concurrency guard, or set/clear
  `active_task` only after the scope gate (paired with the RA-2 bookkeeping).

- **RA-6 (minor) — the `ruff` lint path has never been exercised.**
  Every recorded gate run reports `ruff`/`mypy`/`pytest` unavailable and uses the
  fallbacks, so `ruff check .` / `ruff format --check` have never actually run. If
  `ruff` is installed, `ruff check .` would fail: `E402` is pervasive (every
  entrypoint does `sys.path.insert(...)` before its imports), `F401` fires on the
  unused `git` and `HUMAN_GATES_PATH` imports in `validate_repo.py`, and `F541`
  fires on the placeholder-less f-string at `update_loop_docs.py:271`. Either add
  the dev tools and clean these (with `# noqa: E402` on the bootstrap imports or a
  per-file ignore), or document that the offline fallbacks are the supported path.

- **RA-7 (nit) — `git_checkpoint.sh` forbidden-file check runs pre-stage.**
  The `git ls-files | grep` forbidden-path check runs **before** `git add -A`, so
  it inspects only already-tracked files, not the about-to-be-staged set. It is
  not exploitable today because every forbidden path is git-ignored (so `add -A`
  cannot stage it), but the check would be stronger run after staging against
  `git diff --cached --name-only`.

## 4. Audit matrix (25 required dimensions)

Legend: PASS = correct by static reading; PASS+log = also confirmed by a recorded
gate/dry-run artifact; CONCERN = defect recorded above. None executed this session.

1. Deterministic task selection — PASS. `select_eligible_task` sorts by
   (priority P0<P1<..., scope S<M<L, lexical id); `FINK-S0-01` is selected first
   (also asserted by `tests/test_agent_loop.py`).
2. Dependency + human-gate enforcement — PASS. Deps must be `DONE`; every
   `human_gate` must be `approved:true` or `RESOLVED`. `FINK-MR-04/05/10` are gated
   by OPEN `MODEL_LICENSES/DOWNLOAD/PROFILE_APPROVED` and cannot be selected.
3. Lock + STOP behavior — PASS. `flock -n 9` writer lock; `loop/STOP` checked in
   `loop_once.sh` and each `loop_run.sh` iteration; `loop/STOP.example` documents it.
4. Main-branch enforcement — PASS+log. `loop_once.sh` + `branch_gate` require
   branch `main` and reject any non-`main` local branch (`[PASS] branch is main`).
5. Clean-tree + BASE_COMMIT — PASS. Clean tree required at task start (real runs);
   `BASE_COMMIT` recorded to the run dir; dry-run downgrades to a notice.
6. No branch creation/switching — PASS. No `git branch`/`switch`/`checkout -b`/
   `worktree` anywhere in `scripts/`.
7. Local direct commit on success — PASS. `git_checkpoint.sh` commits on `main`
   only, refuses prohibited tracked files, never pushes (RA-7 is a pre-stage nit).
8. Safe allowed-path rollback on failure — CONCERN (RA-1, RA-2). Scoped rollback
   is correct and unit-tested for Claude verdicts, but the gate-failure /
   sub-tool-failure path bypasses it and terminal status is not persisted.
9. Codex GPT-5.5 xhigh — PASS. `codex exec --model gpt-5.5 --reasoning-effort xhigh --json`.
10. Claude Opus 4.8 Max — PASS. `claude -p --model opus --effort max --permission-mode acceptEdits --output-format json`.
11. JSON-Schema validation — PASS+log. `task`/`state`/`codex_result`/`claude_review`
    schemas present; validated in gates and at emit time; graceful no-op when
    `jsonschema` is absent (`[PASS] schema validation - schemas valid`).
12. Max four repair rounds — PASS. `for round in 1 2 3 4` (round 1 builder + 3
    repair); exhaustion triggers rollback (and must persist BLOCKED per RA-2).
13. Allowed-path enforcement — PASS. `allowed_path_scope` diffs changed files vs
    `FINK_ALLOWED_PATHS` on real runs; `rollback` refuses unsafe/absolute/`..` paths.
14. All machine gates — PASS+log / NOT-EXECUTED here. The 17-gate set is complete
    and each was read; `GATES_OK` in the recorded runs. Not run this session.
15. Local-only runtime constraints — PASS. No network in the loop; offline
    fallbacks for ruff/mypy/pytest; the CLIs are local.
16. Private corpus exclusion — PASS+log. `.fink/`, contracts, uploads, models,
    indexes, data/private|raw|unsanitized, PDFs, ZIPs, `.env`/`*.env` are ignored;
    `FORBIDDEN_TRACKED` + `git_checkpoint` block tracked offenders
    (`[PASS] ... tracking scan`).
17. Legal-language safeguards — PASS (coverage caveat RA-3). `legal_verdict_scan`
    blocks verdict-style assertions (claims that the tool decides/proves fraud,
    illegality, validity, voidness, unfairness, or guaranteed loss; "score is X
    probability" phrasings; a trained-end-to-end model claim). Master spec and
    `docs/specs/` are excused for definitional text.
18. Financial-formula gate coverage — PASS+log. `financial_formula_tests` covers
    FIM-1 (1,400,000), FIM-2 (PV), FIM-3, and FIM-8 low/base/high
    (`[PASS] financial-formula tests`).
19. Paper-note + ledger sync — PASS+log. `CLAIM_/RESULT_/FIGURE_` ledger headers
    match the `paper_ledgers` gate; no measured results claimed; populated by S7.
20. AI-use logging — PASS+log. `docs/ai-use-log.md` carries the bootstrap entry and
    the `HR-08` status (both required by `ai_use_log`).
21. Complete run artifacts — PASS. Per-round `task.json`, `selected_context.txt`,
    prompts, `codex_events.jsonl`, `codex_result.json`, both gate logs,
    `claude_review.json`, `diff.patch`, `summary.md`, plus `BASE_COMMIT.txt` and
    `selection.json` (confirmed present in `.fink/runs/`).
22. No push/deploy/DNS mutation — PASS. The loop never pushes. The only `git push`
    lives in `scripts/create_public_repo.sh`, a human-only tool gated by
    `FINK_PUBLIC_CONFIRM=YES` + `gh auth`, not invoked by the loop.
23. Dry-run correctness — PASS+log. `--dry-run` skips task-start gates, tolerates a
    dirty tree, stubs Codex/Claude, exits after round 1 with `DRY_RUN_OK`;
    `loop_run ... --dry-run` runs one iteration then exits. Recorded dry-run round
    shows `GATES_OK` + `APPROVE` stub. Not executed this session.
24. LOOP.md observability — PASS. `update_loop_docs.py --loop-md` regenerates
    state, the human-gate table, next-task, and operator commands.
25. ToonTransfer-workflow compatibility — PASS. ToonTransfer appears only as a
    process analogy in `prompts/`; no ToonTransfer files or `.env` are copied.

## 5. Hugging Face auth + open-license policy addendum

- Token read path — PASS. The token **value** is read only by
  `scripts/model_research/run_with_hf_auth.sh`, which exports it from
  `~/.cache/huggingface/token` for the exec'd command. `hf_auth_preflight.sh` only
  checks existence and `chmod 600` and states the value is not read or printed;
  `create_private_model_env.sh` writes an env file under `PRIVATE_ROOT` (outside
  the repo) and states no token is copied.
- Token never printed/committed — PASS (subject to RA-3 for brand-new files). No
  script echoes the token; the token path is outside the repo and git-ignored;
  `secret_scan` + `git_checkpoint` block obvious leaks in tracked files.
- ToonTransfer files / `.env` not copied — PASS. No copy of either; `.env` reads
  are forbidden and `.env`/`*.env` are git-ignored.
- Model weights excluded from Git — PASS. `/models/`, `models/`, the HF cache, and
  `PRIVATE_ROOT/models` are out of Git; `configs/models/**` (IDs/licenses/
  revisions/configs only) stays tracked via the `!configs/models/**` negation.
- Open-license-only eligibility — PASS. `configs/models/candidates.yaml`
  `public_open` allowlist: apache-2.0, mit, bsd-2-clause, bsd-3-clause, isc,
  cc0-1.0, cc-by-4.0.
- Unknown/missing/gated/custom/other/noncommercial/research-only rejected by
  default — PASS. Listed under `reject_by_default`.
- Download requires metadata/license/revision/disk dry-run — PASS. Encoded as
  `FINK-MR-02` (metadata/license/gated/revision) and `FINK-MR-03` (size dry run, no
  weights), both behind `MODEL_METADATA_NETWORK_APPROVED`.
- Runtime evaluation offline — PASS. `FINK-MR-06` offline load smoke;
  `create_private_model_env.sh` sets `FINK_RUNTIME_OFFLINE=true`,
  `FINK_MODEL_DOWNLOAD_ALLOWED=false`, telemetry off.
- Korean + English benchmarked — PASS. `FINK-MR-08` KO/EN retrieval consistency.
- OCR benchmark covers money/percentages/dates/durations/article numbers — PASS.
  `FINK-MR-07` enumerates exactly these.
- Local LLM cannot create legal evidence or set production risk scores — PASS.
  `FINK-MR-09` boundary test; `docs/model-card.md` states the prohibition.
- Download blocked behind human gates — PASS. `FINK-MR-04` ->
  `MODEL_LICENSES_APPROVED` (OPEN), `FINK-MR-05` -> `MODEL_DOWNLOAD_APPROVED`
  (OPEN), `FINK-MR-10` -> `MODEL_PROFILE_APPROVED` (OPEN); selection blocks all
  three. After F1 these tasks are reachable through the models queue once a human
  approves the relevant gate.

## 6. Boundaries respected by this audit

No product feature implemented; no gate weakened (RA-3/RA-6 are strengthening
only); no human gate approved; no commit; no push; no deploy; no DNS change; the
ICML template under `paper/template/icml2026/` was not touched (the clean
worktree proves all tracked files, including the 8 template files, are
byte-identical to `HEAD`); no test result fabricated; no branch created (only
`main` exists).

BOOTSTRAP_VERDICT: REQUEST_CHANGES
