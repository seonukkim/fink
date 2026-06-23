# Loop Acceptance

This document is immutable during ordinary task runs.

Accepted task work requires:

- branch `main`;
- clean task-start tree and recorded base commit;
- selected task is eligible by status, dependencies, gates, and path locks;
- Codex result is complete and scoped;
- machine gates pass after Codex and after Claude;
- Claude verdict is `APPROVE`;
- required tests, docs, AI-use log, paper notes, and ledgers are updated;
- ICML template hashes are unchanged;
- no prohibited files are tracked;
- exactly one local commit is created on `main`;
- no push or deployment occurs.
