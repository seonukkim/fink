# FInk Agent-Loop Bootstrap Audit

- Auditor: Claude Opus 4.8 (effort max), independent audit + scoped repair.
- Date: 2026-06-21.
- Branch at audit: `main` (only local branch is `main`).
- Base commit (loop BASE/state): `b3803bfa4df0e72a1b8623e271d8f202eba3dbd1`.
- HEAD at audit: `b0f9644`.
- Scope: agent-loop infrastructure only. No product feature implemented, no human
  gate approved, no commit, no push, no deploy, no DNS change, no ICML template
  edit, no branch created, no Hugging Face token read.

This audit both **ran** the verification commands and **repaired** the objective
defects in-tree (uncommitted, on `main`). The machine-readable repair list is in
`loop/reviews/BOOTSTRAP_REQUIRED_ACTIONS.yaml`; the narrative is in
`loop/reviews/BOOTSTRAP_REPAIR_SUMMARY.md`.

## 0. Verdict summary

`APPROVE`.

The one objective gate blocker — the forbidden-legal-verdict scanner flagging its
own policy-definition literal — is fixed and verified: `run_gates.sh` now reports
`GATES_OK` with 19 `[PASS]` gates. Every required verification command was executed
this session and passed (section 1). The loop is single-`main`, deterministic,
dependency/human-gate gated, flock+STOP guarded, bounded to four rounds, runs the
pinned Codex GPT-5.5 (xhigh) and Claude Opus 4.8 `claude-opus-4-8` (max) with
schema-validated results, rolls back within `allowed_paths`, enforces (now also on
untracked files) the privacy/secret/legal/license gates, preserves the ICML
template, and never pushes.

Two real-run failure-ergonomics items remain (`RA-1`, `RA-2`). They are **not
blockers**: they are fail-stop, never cause a bad commit or a push, and could only
be execution-tested by driving a real Codex/Claude failure round — which this
session must not do. They are documented with precise required changes and are
recommended before fully unattended multi-task runs. The real loop is safe to
start, supervised, now.

## 1. Verification performed this session (executed, not inferred)

All run sequentially (they intentionally share one writer lock):

- `git branch --show-current` -> `main`; `git branch --list` -> only `main`;
  `git status --short` -> this repair's 11 modified + 2 untracked files; nothing
  staged or committed.
- `bash scripts/agent_loop/doctor.sh --no-llm` -> `DOCTOR_OK branch=main` (rc 0).
- `bash scripts/agent_loop/run_gates.sh` -> `GATES_OK`, 19 `[PASS]` (rc 0),
  including `forbidden legal-verdict scan` and the new
  `queue/backlog task-id consistency`. `ruff`/`mypy`/`pytest` binaries are absent,
  so the style/parse/unittest fallbacks ran; PyYAML + `jsonschema` are present, so
  YAML parsing and JSON-Schema validation ran for real.
- `uv run pytest` -> `21 passed, 7 subtests passed` (rc 0). Previously impossible
  (pytest undeclared + repo root off `sys.path`); both fixed.
- `bash scripts/agent_loop/loop_once.sh --dry-run` -> `DRY_RUN_OK task=FINK-S0-01`.
- `loop_run.sh queue.s0.txt 1 --dry-run` -> `DRY_RUN_OK task=FINK-S0-01`.
- `loop_run.sh queue.models.txt 1 --dry-run` -> `DRY_RUN_OK task=FINK-MR-01`
  (the models lane is reachable).
- `bash scripts/agent_loop/run_all_queues.sh --dry-run` and
  `... --max-tasks-per-queue 20 --dry-run` -> all five queues `QUEUE_DONE`,
  `FULL_LOOP_DONE` (rc 0).

Not run, by design: any non-`--dry-run` loop command. The real `codex` and `claude`
CLIs are installed here, so a real run would invoke the agents on the real repo and
implement product features / commit. Every loop command above used `--dry-run`,
which stubs both agents before the CLIs are reached.

## 2. Repairs applied by this audit (in-tree, uncommitted)

See `BOOTSTRAP_REPAIR_SUMMARY.md` section 2 for the full table. In brief:

- **Legal-verdict self-scan** — definition literals live in a sentinel-delimited
  block that `scannable_text()` strips from this module's own source (keyed
  strictly to its resolved path); every other file is scanned in full. Confirmed
  load-bearing: only the third (literal) pattern self-matched, and the redaction
  removes exactly that while keeping the real code.
- **`queue_consistency` gate** — fails on an unknown queue id, a cross-queue
  duplicate, or an in-queue dependency-order violation; wired into the gate suite.
- **Model pin + schema validation** — Claude pinned to `claude-opus-4-8` (the
  ambiguous `opus` alias removed); reviews schema-validated before persisting.
- **Untracked-file scan coverage** — content scanners now also read
  untracked-non-ignored files, closing the "new file committed before scan" window.
- **`run_all_queues.sh`** — sequential five-queue runner under one writer lock
  (`loop_once.sh` now honors `FINK_LOCK_HELD=1` to avoid self-deadlock).
- **`uv run pytest`** — declared PyYAML (a real runtime dep), added a dev group,
  set `pythonpath`.

## 3. Audit matrix (25 required dimensions)

Legend: PASS = correct by reading + executed verification this session;
CONCERN = non-blocking item recorded in the RA list.

1. Deterministic task selection — PASS. `(priority, scope, lexical id)`;
   `FINK-S0-01` selected first (asserted by tests + observed in every dry-run).
2. Dependency + human-gate enforcement — PASS. Deps must be `DONE`; each
   `human_gate` must be approved/RESOLVED. `--explain` names the blocking gate.
3. Lock + STOP behavior — PASS. `flock -n 9` writer lock; `loop/STOP` honored in
   `loop_once.sh`, `loop_run.sh`, and `run_all_queues.sh` (observed halting).
4. Main-branch enforcement — PASS. `branch_gate` + `loop_once.sh` require `main`
   and reject any non-`main` local branch.
5. Clean-tree + BASE_COMMIT — PASS. Clean tree required at real task start;
   `BASE_COMMIT` recorded; dry-run downgrades to a notice.
6. No branch creation/switching/worktrees — PASS. None anywhere in `scripts/`.
7. Local direct commit on success — PASS. `git_checkpoint.sh` commits on `main`
   only, refuses prohibited tracked paths, never pushes.
8. Safe allowed-path rollback on failure — PASS (Claude-verdict paths, unit-tested)
   with CONCERN `RA-1`/`RA-2` for the gate-failure / sub-tool-failure path
   (fail-stop; no bad commit; graceful rollback + status persistence deferred).
9. Codex GPT-5.5 xhigh — PASS. `codex exec --model gpt-5.5 -c model_reasoning_effort="xhigh" --json` (codex-cli 0.128.0 has no `--reasoning-effort` flag; effort is a `-c` config override).
10. Claude Opus 4.8 max — PASS. `claude -p --model claude-opus-4-8 --effort max
    --permission-mode acceptEdits --output-format json` (exact id pinned).
11. JSON-Schema validation — PASS. `task`/`state`/`codex_result`/`claude_review`
    schemas validated in gates and at emit time (Codex and now Claude); graceful
    no-op only when `jsonschema` is absent (it is present here).
12. Max four repair rounds — PASS. `for round in 1 2 3 4`; exhaustion rolls back.
13. Allowed-path enforcement — PASS. `allowed_path_scope` on real runs; rollback
    refuses unsafe/absolute/`..` paths.
14. All machine gates — PASS (executed). 19 gates `[PASS]`; `GATES_OK`.
15. Local-only runtime — PASS. No network in the loop; offline fallbacks; local CLIs.
16. Private corpus exclusion — PASS. `.fink/`, contracts, uploads, models, indexes,
    data/private|raw|unsanitized, PDFs, ZIPs, `.env`/`*.env` ignored;
    `FORBIDDEN_TRACKED` + `git_checkpoint` block tracked offenders; 0 tracked `.fink`.
17. Legal-language safeguards — PASS (now stronger). The gate blocks verdict-style
    product claims (that the tool decides fraud, proves illegality, or guarantees a
    loss; "score is a … probability" phrasings; a trained-end-to-end model claim).
    Master spec + `docs/specs/` are excused for definitional text; the scanner now
    excuses only its own sentinel-delimited definitions and scans everything else,
    including untracked files.
18. Financial-formula gate coverage — PASS. FIM-1/2/3/8 sanity vectors pass.
19. Paper-note + ledger sync — PASS. Ledger headers validated; no measured results
    claimed; ICML template byte-unchanged.
20. AI-use logging — PASS. Bootstrap entry + `HR-08` status present.
21. Complete run artifacts — PASS. Per-round prompts, results, both gate logs,
    review, diff, summary, `BASE_COMMIT.txt`, `selection.json` (observed).
22. No push/deploy/DNS mutation — PASS. The loop never pushes; the only `git push`
    is a human-only, env-gated publish tool not invoked by the loop.
23. Dry-run correctness — PASS (executed). Stubs both agents, tolerates a dirty
    tree, exits after round 1; `run_all_queues --dry-run` completes all five queues.
24. LOOP.md observability — PASS. Regenerated; lists `run_all_queues.sh`.
25. ToonTransfer-workflow compatibility — PASS. Process analogy only; no
    ToonTransfer files or `.env` copied.

## 4. Hugging Face auth + open-license policy (verified)

- Token read path — PASS. The token *value* is read only by
  `run_with_hf_auth.sh`, which exports it for the exec'd command and prints nothing;
  `hf_auth_preflight.sh` checks existence + `chmod 600` and states the value is not
  read; `create_private_model_env.sh` writes an env file under `PRIVATE_ROOT` with
  no token copied.
- Token never printed/committed — PASS. No script echoes it; its path is outside
  the repo and ignored; `secret_scan` (now incl. untracked files) + `git_checkpoint`
  block leaks in repo files.
- ToonTransfer files / `.env` not copied — PASS. `.env` reads forbidden; ignored.
- Weights/caches outside Git — PASS. `models/`, the HF cache, and `PRIVATE_ROOT`
  are out of Git; `configs/models/**` (ids/licenses/revisions/configs only) stays
  tracked via the `!configs/models/**` negation.
- Open-license floor + reject-by-default — PASS. `candidates.yaml` allowlist
  (apache-2.0, mit, bsd-2/3-clause, isc, cc0-1.0, cc-by-4.0); rejects unknown,
  missing, custom, other, gated, noncommercial, research-only.
- Download preconditions + human gates — PASS. `FINK-MR-02` metadata/license/
  revision, `FINK-MR-03` size dry-run (no weights); download/profile behind
  `MODEL_LICENSES_APPROVED` / `MODEL_DOWNLOAD_APPROVED` / `MODEL_PROFILE_APPROVED`
  (all OPEN; none approved here). Offline runtime; KO+EN benchmark (`FINK-MR-08`);
  OCR benchmark covers money/percentages/dates/durations/article numbers
  (`FINK-MR-07`); local LLM may explain but not create evidence or set the score
  (`FINK-MR-09`).

## 5. Boundaries respected by this audit

No product feature implemented; no gate weakened (the legal/secret/untracked
changes strengthen coverage); no human gate approved; no commit; no push; no
deploy; no DNS change; `paper/template/icml2026/**` byte-unchanged; no test result
fabricated; no branch created; the Hugging Face token was never read or printed.

BOOTSTRAP_VERDICT: APPROVE
