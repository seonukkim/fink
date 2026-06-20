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

Dry-run checks:

```bash
bash scripts/agent_loop/doctor.sh --no-llm
bash scripts/agent_loop/run_gates.sh
bash scripts/agent_loop/loop_once.sh --dry-run
bash scripts/agent_loop/loop_run.sh scripts/agent_loop/queue.s1.txt 1 --dry-run
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
