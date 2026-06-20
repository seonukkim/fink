You are GPT-5.5 Codex with xhigh reasoning.

Build the FInk automated agent-loop infrastructure from the approved master
specification.

This run is infrastructure bootstrap only. Do not implement the full product.

## Read first

- docs/FINK_MASTER_SPEC.md
- every file under docs/specs/
- loop/HUMAN_GATES.yaml
- pyproject.toml
- .gitignore
- paper/template/icml2026/

## Single-main Git policy

Use exactly one branch: `main`.

- `origin` is the remote name.
- Do not create or use `master`, `develop`, task branches, or worktrees.
- Do not switch branches.
- Operate sequentially in one worktree.
- Before every task, verify branch `main`, a clean tree, and save
  `BASE_COMMIT=$(git rev-parse HEAD)`.
- Accepted work receives one local commit directly on `main`.
- Never push automatically.
- Failed work is not committed.
- On failure, preserve logs and a binary diff, then restore only the task's
  declared `allowed_paths` to `BASE_COMMIT`.
- Never run repository-wide `git clean`.

## Role split

Codex GPT-5.5 xhigh:

- deterministically selects one eligible bounded task,
- implements only that task,
- adds tests,
- updates implementation and paper notes,
- repairs findings returned by Claude.

Claude Opus 4.8 Max:

- independently audits the diff and machine logs,
- actively fixes objective issues within the task's allowed paths,
- requests Codex repair when issues remain,
- verifies financial formulas, authority boundaries, privacy, bilingual
  behavior, UI, evaluation, and paper claims.

Never run Codex and Claude concurrently.

## Create root documents

- AGENTS.md
- CLAUDE.md
- LOOP.md
- docs/ai-use-log.md
- docs/data-card.md
- docs/model-card.md
- docs/privacy.md
- docs/limitations.md
- docs/paper Markdown skeleton and claim/result/figure ledgers if absent

## Create machine state

- loop/CHARTER.md
- loop/ACCEPTANCE.md
- loop/RUBRIC.md
- loop/BACKLOG.yaml
- loop/STATE.json
- preserve loop/HUMAN_GATES.yaml
- loop/STOP.example

Derive BACKLOG from `docs/specs/08_IMPLEMENTATION_BACKLOG.yaml`.
CHARTER, ACCEPTANCE, and RUBRIC are immutable during ordinary task runs.

## Create scripts under scripts/agent_loop

- doctor.sh
- run_gates.sh
- select_next.py
- build_task_context.py
- run_codex.py
- run_claude.py
- apply_verdict.py
- rollback_failed_task.py
- update_loop_docs.py
- git_checkpoint.sh
- loop_once.sh
- loop_run.sh
- queue.s0.txt
- queue.s1.txt
- queue.s2.txt
- queue.s3.txt
- README.md

## Create prompts

- scripts/agent_loop/prompts/codex_builder.md
- scripts/agent_loop/prompts/codex_repair.md
- scripts/agent_loop/prompts/claude_review_fix.md

## Create JSON Schemas

- scripts/agent_loop/schemas/task.schema.json
- scripts/agent_loop/schemas/codex_result.schema.json
- scripts/agent_loop/schemas/claude_review.schema.json
- scripts/agent_loop/schemas/state.schema.json

## Automatic task selection

A task is eligible only when:

- status is READY,
- every dependency is DONE,
- required human gates are approved,
- no task is already active,
- no allowed-path lock conflicts exist.

Select deterministically by:

1. highest priority,
2. shortest estimated scope,
3. lexical task ID.

## Task flow

1. acquire a writer lock,
2. stop if `loop/STOP` exists,
3. verify current branch is `main`,
4. verify clean working tree,
5. save BASE_COMMIT,
6. select one eligible task,
7. create a run directory,
8. save task snapshot and selected context,
9. invoke Codex GPT-5.5 xhigh,
10. run machine gates,
11. invoke Claude Opus 4.8 Max,
12. permit Claude scoped fixes,
13. run machine gates again,
14. on REQUEST_CHANGES invoke bounded Codex repair,
15. repeat at most four rounds,
16. on APPROVE plus all gates:
    - update task status,
    - update LOOP.md,
    - update docs/ai-use-log.md,
    - update required paper notes and ledgers,
    - create one local commit directly on main,
17. never push or deploy,
18. on BLOCKED or exhausted rounds:
    - preserve BASE_COMMIT, status, binary patch, and logs,
    - restore tracked files only in task allowed_paths,
    - remove task-created untracked files only in allowed_paths,
    - leave main clean,
    - mark the task BLOCKED.

## Run artifacts

Store ignored files under:

`.fink/runs/<RUN_ID>/<TASK_ID>/round-XX/`

Required:

- task.json
- selected_context.txt
- codex_prompt.md
- codex_events.jsonl
- codex_result.json
- gates_after_codex.log
- claude_prompt.md
- claude_review.json
- gates_after_claude.log
- diff.patch
- summary.md

Task-level failure files:

- BASE_COMMIT.txt
- FAILED.patch
- FAILED.status

## Claude verdicts

Exactly:

- APPROVE
- REQUEST_CHANGES
- BLOCKED

The structured review must include:

- verdict
- summary
- blocking_issues
- major_issues
- minor_issues
- fixes_applied
- required_codex_actions
- required_tests
- financial_reasoning_concerns
- legal_language_concerns
- authority_source_concerns
- privacy_copyright_concerns
- bilingual_concerns
- ui_concerns
- paper_claim_concerns
- changed_files
- confidence

## Machine gates

Include:

- branch is main,
- clean tree at task start,
- ruff format --check,
- ruff check,
- mypy,
- pytest,
- JSON/JSONL/YAML/CSV parsing,
- schema validation,
- secret scan,
- `.fink` and private-input tracking scan,
- PDF/ZIP tracking scan,
- long private-quotation heuristic,
- forbidden legal-verdict scan,
- authority-tier scoring invariant,
- financial-formula tests,
- upload-deletion tests when relevant,
- offline-network test when relevant,
- responsive-page smoke test when relevant,
- claim-evidence ledger validation,
- AI-use-log update check,
- required-documentation check,
- allowed-path scope validation,
- ICML template hash preservation.

Do not weaken a gate to make it pass.

## Safety

- never read `.env`,
- never access outside this repository,
- never commit `.fink`,
- never commit private books or contracts,
- never create or switch branches,
- never push,
- never deploy,
- never change DNS,
- never change frozen evaluation labels,
- never require a remote runtime API,
- never alter the ICML template,
- never use repository-wide `git clean`.

## Operator UX

Preserve these commands:

```bash
bash scripts/agent_loop/loop_once.sh
bash scripts/agent_loop/loop_run.sh scripts/agent_loop/queue.s1.txt 8
touch loop/STOP
```

LOOP.md must show task, base commit, round, gates, Claude verdict, fixes,
paper-sync status, human gates, next tasks, run paths, and latest successful
commit.

## Bootstrap acceptance

- `uv sync` succeeds,
- `doctor.sh --no-llm` succeeds,
- doctor confirms branch main,
- `run_gates.sh` succeeds,
- `loop_once.sh --dry-run` succeeds,
- `loop_run.sh <queue> 1 --dry-run` succeeds,
- failed-task rollback is tested,
- schemas validate,
- LOOP.md is generated,
- `.fink`, PDF, and ZIP files are not tracked,
- no non-main branch is created,
- ICML template hashes remain unchanged,
- operator README contains exact commands,
- no product feature beyond scaffold is implemented.

Run all available checks, update LOOP.md, and stop.
