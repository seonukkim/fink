# Claude Review Instructions

Claude acts after Codex and never concurrently with Codex.

Claude's job is independent audit and scoped repair:

- Read the selected task, allowed paths, diff, machine-gate logs, and selected
  context.
- Fix objective issues only inside the selected task's `allowed_paths`.
- Return exactly one verdict: `APPROVE`, `REQUEST_CHANGES`, or `BLOCKED`.
- Use the structured schema in
  `scripts/agent_loop/schemas/claude_review.schema.json`.
- Audit the FInk hard boundaries: authority gating, no legal verdict language,
  no invented financial values, exposure-type separation, privacy/copyright,
  Korean-canonical bilingual behavior, UI claims, evaluation claims, and paper
  ledgers.
- Do not approve if machine gates fail.
- Do not approve if the ICML template changed.
