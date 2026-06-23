# FInk — A Financial-Risk Review Assistant for Creator Contracts

*창작자 계약서 금융 위험 검토 도우미 · UNIST · IE412 AI for Finance · 2026 Spring · Final Project*

[![Project Page](https://img.shields.io/badge/Project_Page-fink.seonukkim.com-a31e4e.svg)](https://fink.seonukkim.com)
[![Paper](https://img.shields.io/badge/Paper-PDF-b31b1b.svg)](https://fink.seonukkim.com/fink-paper.pdf)
[![Code](https://img.shields.io/badge/Code-GitHub-24292e.svg)](https://github.com/seonukkim/fink)

FInk is an on-device assistant that reads a creator's contract, detects the
**financial risk** in its clauses, grounds each flag in a curated knowledge base
of official Korean financial and legal sources through BM25 retrieval, and returns
a **prioritized review**: a 0–100 review-attention score, a recommended review
effort, and ranked, source-cited findings. A small local chatbot answers follow-up
questions, and the review can be saved as a one-page brief. Everything runs on the
device — a draft contract never leaves it.

FInk은 창작자 계약서를 읽어 조항 속 **금융 위험**을 찾고, 각 항목을 공식 한국
금융·법률 자료로 만든 지식 베이스에 BM25 검색으로 근거를 연결해, **우선순위
검토**(위험 지수 0–100, 검토 권장 수준, 근거가 달린 항목 목록)로 보여 줍니다.
후속 질문은 기기 안의 챗봇이 답하고, 검토 내용은 한 장짜리 의견서로 저장할 수
있습니다. 모든 과정은 기기 안에서만 이루어집니다.

> FInk is decision support for what to check before signing. It is **not** legal
> advice, and not a verdict on legality, fraud, validity, fairness, or guaranteed
> loss. For important decisions, consult a professional.

## What it does

- **Detects financial risk** across nine cash-flow categories (settlement and
  audit, revenue base and deductions, payment timing, minimum-guarantee and
  recoupment, IP and secondary-rights, term and exclusivity, termination and
  penalties, scope and production cost, and a residual category).
- **Grounds every flag** by retrieving supporting passages from official Korean
  standard contracts and counseling casebooks. An **evidence gate** lets only
  officially backed clauses raise the score; unverified signals raise questions,
  never the number.
- **Prioritizes the review** with a deterministic 0–100 score and a three-level
  recommended effort, then ranks findings so the clauses that move the most money
  come first.
- **Answers follow-up questions** with an on-device chat model, and exports a
  one-page brief.

## Run it

Pasted-text analysis runs with the web extra alone:

```bash
git clone https://github.com/seonukkim/fink
cd fink
uv sync --extra web
uv run fink-web --host 127.0.0.1 --port 8000
# wait for "Uvicorn running on http://127.0.0.1:8000", then open that address
```

Photo/PDF input and the on-device chat model are optional:

```bash
uv sync --extra ocr      # PP-OCR for images and scanned PDFs
uv sync --extra chat     # on-device chat model runtime
FINK_MODEL_DOWNLOAD_ALLOWED=true uv run fink-models download   # one-time chat-model fetch
```

## Models

| Stage | Component |
|---|---|
| OCR (optional) | PaddleOCR PP-OCR, Korean configuration |
| Retrieval | BM25 sparse index over the curated knowledge base |
| Risk score | Deterministic review-attention formula (0–100) |
| Chat (optional) | Qwen2.5-1.5B-Instruct, 4-bit, via llama.cpp |

Retrieval uses BM25 by design: the corpus is small and curated, exact Korean
legal terms matter, and a sparse index runs on device with no model to host.

## Privacy

Ingestion, OCR, retrieval, scoring, and the chat model run locally. The app makes
no outbound calls during analysis, keeps no telemetry, and uses no cloud OCR or
remote LLM. After optional model assets are fetched once, analysis stays offline.

## Evaluation

No real contract was used for any number here. Each pipeline step is measured on
synthetic, sanitized fixtures: risk detection (rule / model / hybrid), evidence
grounding and authority-tier correctness, decision-aware ordering under a reading
budget, formula correctness, and offline/privacy gates. These are
measured-on-fixture checks, not real-contract or deployment-performance claims.
Logs: [`docs/paper/RESULT_LEDGER.csv`](docs/paper/RESULT_LEDGER.csv) and
`scripts/eval/`.

## Paper

The project report is in [`paper/`](paper/) (`fink_paper.tex`, built to
`fink_paper.pdf`). It centers the financial-AI design: the evidence-gated risk
score, the on-device RAG grounding, and a decision-focused evaluation of whether
the ordering helps a creator cover financial exposure under a small reading
budget.

## How it was built, and use of AI tools

The knowledge base was built from official Korean sources (standard contracts and
counseling casebooks) and two creator-law reference books; official sources were
preprocessed into Markdown with **Claude Opus 4.8** and the two books with
**ChatGPT 5.5 Pro**, then indexed. The system was implemented with **OpenAI Codex**
and **Anthropic Claude Code** under a specification-driven loop, with machine gates
for privacy, legal language, finance, and schema run on every change. The build
harness and detailed specifications are kept in [`archive/`](archive/). All
AI-assisted outputs were verified by the author through gates, tests, and manual
review; raw source text, real contracts, and model weights are never committed.

## Citation

```bibtex
@misc{kim2026fink,
  author       = {Kim, Seonuk},
  title        = {{FInk}: An On-Device, Evidence-Gated Retrieval System for
                  Financial-Risk Review of Creator Contracts},
  year         = {2026},
  note         = {UNIST IE412 AI for Finance (2026 Spring) final project},
  howpublished = {\url{https://fink.seonukkim.com}}
}
```

## License

- Code and docs: **MIT** (see `LICENSE`).
- Synthetic / sanitized data: **CC-BY-4.0** (see `DATA_LICENSE.md`).
- Third-party models keep their own open-source licenses; weights are not
  distributed (see `NOTICE.md`).
