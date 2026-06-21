# FInk — AI-assisted financial review of creator contracts

*Identifying cost-bearing clauses and what to check before signing.*

FInk reads a creator's contract — from a phone photo, an image, a PDF, or pasted
text — and shows which clauses could cost money, and what to ask before signing.
It reports four things separately: which clauses to review first, a low/base/high
cost range, when the money moves, and how sure the reading is.

**UNIST · IE412 AI for Finance · 2026 Spring · Final Project.**

> FInk reports a Contractual Financial Review Priority. It is not legal advice,
> and not a verdict on fraud, illegality, validity, unfairness, or guaranteed
> loss.

- Project page: `fink.seonukkim.com` (Cloudflare deploy)
- Docs: [Model Card](docs/model-card.md) · [Privacy](docs/privacy.md) ·
  [Limitations](docs/limitations.md) · [Paper notes](docs/paper/)

## Why

A creator gets a contract full of financial terms, but little time and no finance
background. The clauses that matter most — recoupment, deductions, payment delay —
are the easiest to miss. FInk turns the contract into a short, prioritized review.

## What it does — four separate outputs

1. **Review priority** — which clauses to look at first, in order.
2. **Money: low / base / high** — a cost range from extracted values or editable
   assumptions.
3. **Time** — when money moves: payment timing, recoupment, term, delays.
4. **Confidence** — how sure the reading is; unclear data lowers confidence, not
   the money.

The four are kept separate and never merged into one "total loss" number.

## How it works

```
photo / image / PDF / pasted clause
  → OCR (Korean + English)
  → clause segmentation
  → evidence retrieval from official sources
  → financial risk signals + cash-flow scenarios
  → review report
```

The priority score is computed by deterministic rules, so it is reproducible.
Open models (PaddleOCR-VL, Qwen3, BGE-M3) handle OCR, retrieval, and explanation,
and never set the score. Everything runs on the machine, offline.

## Run the demo

```bash
git clone https://github.com/seonukkim/fink
cd fink
PYTHONPATH=src uv run --with fastapi --with uvicorn \
  uvicorn fink.web.app:create_app --factory --host 127.0.0.1 --port 8000
# wait for "Uvicorn running on http://127.0.0.1:8000", then open that address
# (loopback only; desktop + mobile browser; Korean / English)
```

## Evaluation

No real contract was run through the system for these numbers. Each pipeline step
is checked on synthetic, sanitized examples — that OCR reads money, dates, and
percentages; that retrieval returns the right official evidence; that the
financial formulas compute correctly; and that runs stay offline with nothing
leaked. These are correctness checks, not real-world accuracy. Full logs:
`docs/paper/RESULT_LEDGER.csv` and `scripts/eval/`.

## Responsible use

- No legal verdict: FInk gives review priority and scenarios, not legal
  conclusions; only official (A0–A2) sources support the score.
- No private material: no real contract, key, or model weight is committed.
- No invented numbers: metrics show only when measured; missing inputs lower
  confidence.

See [docs/limitations.md](docs/limitations.md).

## How it was built

FInk was implemented through a bounded, single-branch agent loop: Codex (GPT-5.5)
implemented one scoped task at a time and Claude (Opus 4.8) reviewed and made
fixes, with machine gates for privacy, legal language, finance, and schema
enforced on every task. See [LOOP.md](LOOP.md) and
[scripts/agent_loop/README.md](scripts/agent_loop/README.md).

## Citation

```bibtex
@misc{kim2026fink,
  author       = {Kim, Seonuk},
  title        = {{FInk}: Evidence-Grounded Financial AI for Creator Contract Review},
  year         = {2026},
  note         = {UNIST IE412 AI for Finance (2026 Spring) final project. Work in progress.},
  howpublished = {\url{https://github.com/seonukkim/fink}}
}
```

## License

- Code and docs: **MIT** (see `LICENSE`).
- Synthetic / sanitized data: **CC-BY-4.0** (see `DATA_LICENSE.md`).
- Third-party models keep their own open-source licenses (Apache-2.0 / MIT), and
  weights are not distributed. See `NOTICE.md`.

Private corpora, real contracts, and model weights are never committed.
