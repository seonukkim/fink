# Claude Audit Addendum: Hugging Face auth and open-license model policy

Audit that:

- The project uses `~/.cache/huggingface/token` only through `scripts/model_research/run_with_hf_auth.sh`.
- The token value is never printed, copied, committed, or written into docs, prompts, logs, LOOP.md, or Git.
- ToonTransfer files and `.env` are not copied.
- ToonTransfer is referenced only as an automated LOOP process analogy.
- Model weights are excluded from Git.
- Only public/open licenses are automatically eligible.
- Unknown, missing, gated, custom, noncommercial, and research-only licenses are rejected by default.
- Download requires metadata, license, revision, and disk dry-run records.
- Runtime evaluation after download runs offline.
- Korean and English are both benchmarked.
- OCR benchmark checks money, percentages, dates, durations, and article numbers.
- The local LLM cannot create legal evidence or directly set production risk scores.
