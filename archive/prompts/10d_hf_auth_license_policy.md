# Binding Addendum: Hugging Face auth and open-license model policy

Use the existing Hugging Face token at `~/.cache/huggingface/token`.

Rules:

- Load it only through `scripts/model_research/run_with_hf_auth.sh`.
- Do not print, log, commit, copy, or document the token value.
- Do not copy ToonTransfer files or `.env`.
- ToonTransfer is only a process analogy for the automated LOOP style.
- Store model weights under `$PRIVATE_ROOT/models` or the Hugging Face cache, never Git.
- Public Git may contain only model IDs, licenses, pinned revisions, configs, benchmark summaries, and selected profiles.

License policy:

- Default floor is `public_open`.
- Automatically eligible licenses are Apache-2.0, MIT, BSD, ISC, CC0, and CC-BY-4.0 style licenses.
- Unknown, missing, gated, custom, noncommercial, and research-only licenses are rejected by default.
- Download requires metadata, license, exact revision, and disk-size dry-run records.
- Actual download requires a human gate.

Required model-research tasks:

- hardware and software inventory
- Hugging Face metadata, license, gated status, and exact revision inventory
- download-size dry run
- open-license filtered shortlist
- private model download after approval
- offline load smoke tests
- OCR benchmark for money, percentages, dates, durations, and article numbers
- Korean/English retrieval benchmark
- local explanation benchmark
- selected-profile report

Production rule:

The local LLM may explain retrieved evidence.
It must not create legal evidence, directly set production risk scores, or fabricate financial impact.
