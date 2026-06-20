# FInk Agent Loop

This directory contains the bootstrap automation for the single-main FInk agent
loop. It selects one bounded task, builds a scoped context packet, runs Codex,
runs machine gates, runs Claude review/fix, and either checkpoints accepted work
or rolls back only the selected task's allowed paths.

Operator commands:

```bash
bash scripts/agent_loop/loop_once.sh
bash scripts/agent_loop/loop_run.sh scripts/agent_loop/queue.s1.txt 8
touch loop/STOP
```

Run all queues sequentially (one writer lock, dependency order):

```bash
# dry-run smoke test of every queue (no Codex/Claude/downloads/commits)
bash scripts/agent_loop/run_all_queues.sh --dry-run

# real run, capping each queue (resumes from loop state on re-run)
bash scripts/agent_loop/run_all_queues.sh --max-tasks-per-queue 20

# unattended
nohup bash scripts/agent_loop/run_all_queues.sh --max-tasks-per-queue 20 \
  > .fink/full-loop.out 2>&1 &
```

`run_all_queues.sh` runs the queues in this fixed order:

1. `queue.s0.txt`  (foundation + data validation)
2. `queue.models.txt`  (model research; download/license/profile steps stay
   behind human gates)
3. `queue.s1.txt`  (ingestion + OCR)
4. `queue.s2.txt`  (retrieval + authority grounding)
5. `queue.s3.txt`  (scoring + monetary/time exposure)

It holds the single global writer lock `.fink/agent-loop.lock` for the whole run
and exports `FINK_LOCK_HELD=1` so the per-task `loop_once.sh` does not deadlock
re-acquiring it; no other loop command can run while it holds the lock. It stops
immediately if `loop/STOP` exists, stops on a blocked task or any non-zero phase
result (later queues are not run), and when a queue stops cleanly it names the
exact human gate(s) blocking the remaining tasks. Timestamped logs are written
under `.fink/runs/full-loop/<UTC>/`. It never pushes and never approves a gate.

Dry-run checks:

```bash
bash scripts/agent_loop/doctor.sh --no-llm
bash scripts/agent_loop/run_gates.sh
uv run pytest
bash scripts/agent_loop/loop_once.sh --dry-run
bash scripts/agent_loop/loop_run.sh scripts/agent_loop/queue.s1.txt 1 --dry-run
bash scripts/agent_loop/run_all_queues.sh --dry-run
```

Rules:

- Only branch `main` is valid.
- The worktree must be clean at task start.
- No task branches, worktrees, pushes, deploys, or repository-wide `git clean`.
- Failed tasks preserve logs and binary diffs under `.fink/runs/`, then restore
  only the task's `allowed_paths`.
- Hugging Face tokens are loaded only through
  `scripts/model_research/run_with_hf_auth.sh`; token values are never printed or
  committed.
