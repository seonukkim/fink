# FInk Data Card

Status: scaffold.

FInk public Git may contain specifications, schemas, synthetic or sanitized
examples, paper notes, public-safe configs, benchmark summaries, and selected
model profiles. It must not contain real contracts, uploaded user content,
private books, private corpus text, `.fink` inputs, PDFs, ZIPs, API keys, or
model weights.

Current data posture:

- Upstream private/specification inputs remain under ignored `.fink/`.
- Runtime uploads are future `P3_USER_EPHEMERAL` data and must be deleted after
  use.
- Evaluation data must be synthetic or sanitized and labeled as such.
- Frozen evaluation labels must not be altered by ordinary loop tasks.
