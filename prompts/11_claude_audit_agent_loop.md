You are Claude Opus 4.8 with maximum effort.

Audit and actively repair the FInk automated-loop bootstrap.

Read:

- docs/FINK_MASTER_SPEC.md
- every file under docs/specs/
- AGENTS.md
- CLAUDE.md
- LOOP.md
- loop/
- scripts/agent_loop/
- pyproject.toml
- .gitignore
- tests/

You may edit files and run the explicitly allowed local commands.

## Mandatory Git policy

Use exactly one branch: `main`.

- `origin` is only the remote name.
- Never create or use master, develop, task branches, or worktrees.
- Never switch away from main.
- Accepted work commits directly to local main.
- Never push automatically.
- Every task starts from a clean main and saved BASE_COMMIT.
- A failed task preserves patch/status/logs, restores only declared
  allowed_paths, leaves main clean, and is not committed.
- Repository-wide `git clean` is prohibited.

## Audit and fix

1. deterministic task selection,
2. dependency and human-gate enforcement,
3. lock and STOP behavior,
4. main-branch enforcement,
5. clean-tree and BASE_COMMIT checks,
6. absence of branch creation/switching,
7. local direct commit on success,
8. safe allowed-path rollback on failure,
9. Codex GPT-5.5 xhigh invocation,
10. Claude Opus 4.8 Max invocation,
11. JSON Schema validation,
12. maximum four repair rounds,
13. allowed-path enforcement,
14. all machine gates,
15. local-only runtime constraints,
16. private corpus exclusion,
17. legal-language safeguards,
18. financial-formula gate coverage,
19. paper-note and ledger synchronization,
20. AI-use logging,
21. complete run artifacts,
22. no push/deploy/DNS mutation,
23. dry-run correctness,
24. LOOP.md observability,
25. compatibility with the user's ToonTransfer workflow.

Fix objectively incorrect or missing infrastructure, but do not implement
product features, weaken gates, approve human gates, push, deploy, change DNS,
alter the ICML template, fabricate test success, or create a branch.

Run:

```bash
git branch --show-current
git branch --list
bash scripts/agent_loop/doctor.sh --no-llm
bash scripts/agent_loop/run_gates.sh
uv run pytest
bash scripts/agent_loop/loop_once.sh --dry-run
bash scripts/agent_loop/loop_run.sh scripts/agent_loop/queue.s0.txt 1 --dry-run
```

Create:

- loop/reviews/BOOTSTRAP_AUDIT.md
- loop/reviews/BOOTSTRAP_REQUIRED_ACTIONS.yaml

The final line of BOOTSTRAP_AUDIT.md must be exactly one of:

- BOOTSTRAP_VERDICT: APPROVE
- BOOTSTRAP_VERDICT: REQUEST_CHANGES
- BOOTSTRAP_VERDICT: BLOCKED

Stop after audit, fixes, and verification.
