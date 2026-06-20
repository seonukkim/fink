# Loop Charter

This charter is immutable during ordinary task runs.

FInk's loop exists to implement the approved master specification one bounded
task at a time. Each task must preserve:

- single branch: `main`;
- clean worktree at task start;
- one accepted local commit on `main`;
- no automatic push or deploy;
- no repository-wide `git clean`;
- rollback only within the selected task's `allowed_paths`;
- no `.env` reads, private input commits, model-weight commits, PDF/ZIP commits,
  or `.fink` commits;
- authority-gated scoring, no legal verdict language, no invented financial
  values, exposure-type separation, Korean-canonical evidence, and local-first
  privacy.
