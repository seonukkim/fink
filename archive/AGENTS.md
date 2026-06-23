# FInk Agent Instructions

FInk uses a single-main, local-first agent loop.

- Work only on branch `main`.
- Do not create task branches, worktrees, `master`, or `develop`.
- Do not push, deploy, change DNS, or require a remote runtime API.
- Before each loop task, verify branch `main`, a clean worktree, and record
  `BASE_COMMIT=$(git rev-parse HEAD)`.
- Implement only the selected task and only within its `allowed_paths`.
- Preserve `.fink/`, private inputs, contracts, PDFs, ZIPs, model weights, and
  Hugging Face tokens outside public Git.
- Never read `.env`.
- Keep FInk's output framed as Contractual Financial Review Priority, never a
  legal, fraud, validity, unfairness, or guaranteed-loss verdict.
- Update tests, `LOOP.md`, `docs/ai-use-log.md`, and required paper notes for
  accepted work.

Operator commands are documented in `scripts/agent_loop/README.md`.
