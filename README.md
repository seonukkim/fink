# FInk: Selective, Evidence-Gated Cash-Flow Triage for Creator Contracts

*Contractual Financial Review Priority for creator contracts.*

FInk is an on-device tool for creator contracts that triages cash-flow
questions before signing. It marks the clauses that may affect settlement,
deductions, recoupment, payment timing, IP revenue, exclusivity, penalties,
or production costs; only items backed by official evidence count toward the
score; and it shows the result as four separate parts: what to review first,
a low/base/high cost range, when the money moves, and how reliable the reading is.

FInk은 창작자가 서명 전에 확인할 현금흐름 관련 조항을 먼저 추려 주는, 기기
안에서만 동작하는 도구입니다. 정산, 공제, 선급금 회수, 지급 시점, 2차 수익,
독점, 위약금, 제작비와 관련된 조항을 짚어 주고, 공식 근거가 있는 항목만 점수에
반영하며, 결과는 검토 우선순위, 예상 금액 범위(낮음·적정·높음), 돈이 오가는
시점, 판독 신뢰도로 나눠 보여 줍니다.

**UNIST · IE412 AI for Finance · 2026 Spring · Final Project.**

> FInk reports a Contractual Financial Review Priority. It is not legal advice,
> and not a verdict on fraud, illegality, validity, unfairness, or guaranteed
> loss.

- Project page source: [site/index.html](site/index.html)
- Docs: [Model Card](docs/model-card.md) · [Privacy](docs/privacy.md) ·
  [Limitations](docs/limitations.md) · [Paper notes](docs/paper/)

## Why

A creator gets a contract full of financial terms, but little time and no finance
background. The clauses that matter most — recoupment, deductions, payment delay,
IP revenue, exclusivity, termination exposure, and production-cost burden — are
easy to miss. FInk turns the contract into a selective review list and
cash-flow scenario brief.

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
  → evidence-gated review signals
  → cash-flow scenarios
  → review report
```

Review priority is computed by deterministic rules, so the review order is
reproducible. Optional local models may assist OCR, retrieval, or explanation
only when they are privately installed and pass the offline health/smoke gate;
they do not create evidence, set review-priority values, or invent financial
amounts. Runtime analysis does not require a remote LLM, cloud RAG, external
legal search, telemetry, or cloud OCR; after optional OCR/model assets are
fetched once, analysis stays local.

## Run the demo

```bash
git clone https://github.com/seonukkim/fink
cd fink
uv sync --extra web
uv run fink-web --host 127.0.0.1 --port 8000
# wait for "Uvicorn running on http://127.0.0.1:8000", then open that address
# (loopback only; desktop + mobile browser; Korean / English)
```

### Download the models

```bash
FINK_MODEL_DOWNLOAD_ALLOWED=true uv run fink-models download   # embedding, reranker, on-device chat LLM
uv sync --extra ocr                                            # image/scanned-PDF OCR (PP-OCR)
```

The default bind is loopback. To expose the demo to a trusted device on the same
private LAN, bind a specific private interface and acknowledge the warning:

```bash
uv run fink-web --host 192.168.1.25 --port 8000 --allow-lan --trusted-lan-ack
```

## Evaluation

No real contract was run through the system for these numbers. Each pipeline step
is checked on synthetic, sanitized examples — that OCR reads money, dates, and
percentages; that retrieval returns the right official evidence; that the
financial formulas compute correctly; and that runs stay offline with nothing
leaked. These are measured fixture checks, not real-contract performance,
predicted exposure-value, or deployment-performance claims. Full logs:
[docs/paper/RESULT_LEDGER.csv](docs/paper/RESULT_LEDGER.csv) and `scripts/eval/`.

## Responsible use

- No legal verdict: FInk gives review priority and cash-flow scenarios, not
  legal conclusions; only official A0–A2 sources support score-eligible
  review-priority signals.
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
  title        = {{FInk}: Selective, Evidence-Gated Cash-Flow Triage for Creator Contracts},
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
