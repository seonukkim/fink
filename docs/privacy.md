# FInk Privacy

FInk is local-first. Runtime analysis must not require a remote LLM, cloud RAG,
external legal search, telemetry, cloud OCR, or runtime model download.

FInk's public and runtime boundary is selective, evidence-gated cash-flow triage:
uploaded creator contracts stay local and ephemeral, while public artifacts use
only synthetic or sanitized examples.

Privacy boundaries:

- User contracts, uploads, OCR text, clauses, raw filenames, and temporary paths
  are `P3_USER_EPHEMERAL`.
- Uploaded PDFs, page rasters, OCR intermediates, and image inputs are deleted on
  clear, timeout, session end, and shutdown.
- Logs may contain opaque IDs, counts, timings, and error codes only.
- `.fink/`, contracts, uploads, private corpus data, PDFs, ZIPs, indexes, models,
  and unsanitized data must not be tracked.
- `.env` must never be read by automation.
- Optional local models are metadata-only in public Git. A model is treated as
  installed for runtime only after private weights are outside the repository
  and a local offline health/smoke check passes.
