<p align="center">
  <img src="site/assets/images/fink-hero.png" alt="FInk project hero" width="100%" />
</p>

# FInk: Evidence-Grounded Financial AI for Creator Contract Review

A Korean/English **Financial AI** system that helps creators review contract
clauses through evidence-grounded financial signals, payout implications, and
scenario-based analysis. FInk reads a contract from a phone photo, an uploaded
image, a PDF, or pasted text, then returns four separated financial views — a
review-priority score, a low/base/high monetary-exposure range, a time-exposure
estimate, and an OCR/evidence-confidence breakdown — each grounded in retrieved
evidence rather than a single opaque "total loss" number.

> **Disclaimer.** FInk provides financial review-priority signals and scenario
> analysis. It does not provide a binding legal opinion, determine fraud or
> illegality, or replace professional legal review.

**Course project.** UNIST · IE412 AI for Finance · 2026 Spring · Final Project ·
Deadline **2026-06-24 23:59 KST**.

**Links:**
[Data Card](docs/data-card.md) ·
[Model Card](docs/model-card.md) ·
[Privacy](docs/privacy.md) ·
[Limitations](docs/limitations.md) ·
Paper — [draft notes](docs/paper/) ·
Project Page — *planned (not yet deployed)* ·
Demo — *planned (local run only)*

---

## Overview

FInk combines **"Finance"** and **"Ink"**: financial intelligence for contracts,
comics, webtoons, and creator work, written into economic terms. The **"k"** is
an intentional part of the project name.

FInk is for **creators** — webtoon artists, illustrators, writers, and other
independent contributors — who are asked to sign contracts whose financial
mechanics are easy to miss. A creator contract *is* a financial document: its
clauses move real money over time. FInk focuses on the clauses that change a
creator's economics, including

- royalty and revenue-share terms,
- settlement and payout timing,
- deductions and fees,
- minimum-guarantee (MG) recoupment,
- payment delay and late-payment terms,
- IP and rights assignment,
- exclusivity and territory,
- and production-cost responsibility.

Rather than answering "is this contract good or bad," FInk surfaces *where the
money is* and *which clauses deserve a closer financial look*, so a creator can
ask better questions before signing.

## Financial AI framing

FInk is built as an **IE412 AI for Finance** project, not a legal-advice tool.
It draws on three threads from the course:

- **Decision-focused evaluation.** FInk is measured by whether its outputs help
  a creator *prioritize review and understand cash-flow exposure*, not by a
  single accuracy number. Metrics target review-priority quality, monetary-range
  usefulness, and calibration of confidence.
- **LLMs for financial-document analysis.** Local language models read messy,
  bilingual contract text (OCR output included) to help extract and *explain*
  financial terms. The LLM explains retrieved evidence; it does not invent
  numbers.
- **Fraud-/risk-detection methodology, adapted into financial triage.** FInk
  reuses the *shape* of risk-detection pipelines — signal extraction, scoring,
  prioritization — but applies it to **financial review triage**, not fraud
  adjudication. **FInk does not determine fraud**, and it never converts
  uncertainty into a probability-of-fraud value or a single guaranteed-loss
  figure.

## Core output

FInk produces **four separate outputs** and keeps them separate (it never
collapses them into one "total loss" number):

1. **Contractual Financial Review Priority Score** — how much financial review
   attention the document warrants.
2. **Monetary Exposure Range** — low / base / high scenarios, kept as a range.
3. **Time Exposure** — when money moves and how long it is deferred or at risk.
4. **OCR and Evidence Confidence** — how reliable the extraction and supporting
   evidence are.

Each output carries its own evidence and uncertainty; they are reported side by
side, never merged.

## Workflow

```
Camera / Image / PDF / Pasted Clause
        ↓
OCR and Page Reconstruction
        ↓
Clause Segmentation
        ↓
Authority-Aware Evidence Retrieval
        ↓
Financial Risk Signals
        ↓
Cash-Flow Scenario Analysis
        ↓
Mobile-Friendly Review Report
```

Supported inputs: phone-camera images, uploaded images, text-layer PDFs, scanned
(image-only) PDFs, mixed PDFs, multi-page PDFs, and pasted Korean or English
clauses.

## Architecture

FInk is designed as separated layers so that evidence, scoring, and explanation
never blur together:

- **Frontend** — responsive, mobile-friendly review UI.
- **FastAPI app** — local API surface binding the layers together.
- **OCR / PDF layer** — local rasterization, text-layer extraction, and OCR for
  image-only pages.
- **Retrieval** — authority-aware evidence retrieval over a local corpus.
- **Deterministic scoring** — rule- and config-driven, reproducible scoring.
- **Financial scenario analysis** — low/base/high cash-flow modules.
- **Optional local explanation model** — explains retrieved evidence only.
- **Private local storage** — uploads, intermediates, and weights stay local.

The production score stays **deterministic and authority-grounded**. A local
language model may *explain* retrieved evidence, but it cannot create evidence,
set the production score directly, or fabricate financial impact.

## Privacy and local runtime

Creator contracts are sensitive, so FInk is built to run locally:

- Sensitive contracts are handled **on the local machine**.
- Raw uploads and OCR intermediates are **temporary** and removed on clear /
  session end.
- Contract text **should not enter logs**.
- Private books, contracts, local indexes, tokens, and model weights are
  **never committed** to Git.
- Local models may **explain** evidence but **cannot create legal evidence or
  directly set scores**.

See [docs/privacy.md](docs/privacy.md) for the full privacy posture.

## Current status / TODO

Work in progress. The agent-loop infrastructure that builds and reviews FInk is
in place; the FInk product features below are not yet implemented. Only items
with repository evidence of completion are checked.

**Foundation and data**
- [ ] Import upstream corpus, reconcile taxonomy/features, load evidence and B/C cards
- [ ] Typed schemas and CI invariant gates (authority, exposure separation, privacy)

**Agent LOOP**
- [x] Single-`main` Codex/Claude loop: selection, gates, scoped rollback, run artifacts
- [x] Machine gates (`run_gates.sh`), queue/backlog consistency gate, schema validation
- [x] Sequential runners (`run_all_queues.sh`, `run_backlog.sh`) and dry-run pipeline

**Local model research**
- [ ] Hugging Face metadata/license/revision inventory and size dry-runs
- [ ] Open-license shortlist, approved download, offline load smoke tests, KO/EN + OCR benchmarks

**Input and OCR**
- [ ] Ingestion (camera/image/PDF/paste), local OCR, page reorder/rotate, correction flow

**Retrieval and authority grounding**
- [ ] Local hierarchical index, bilingual canonical-ID resolution, authority-gated retrieval

**Scoring and financial analysis**
- [ ] Rule-based risk signals, deterministic aggregation, FIM cash-flow modules, time exposure

**Responsive web app**
- [ ] FastAPI app + responsive UI, ingestion/correction UI, four-dimension report, export

**Evaluation**
- [ ] OCR/extraction/retrieval/risk/financial metrics on synthetic, frozen split

**Project page**
- [ ] Static, synthetic-only project page (image assets present; page not yet built)

**Paper and final submission**
- [ ] Populate paper notes + ledgers from measured results; pre-submission checklist

> This checklist is synchronized manually with [LOOP.md](LOOP.md) and
> [loop/BACKLOG.yaml](loop/BACKLOG.yaml).

## Agentic development workflow

FInk is built by a bounded, auditable agent loop with a human in the loop:

- **Codex GPT-5.5 (xhigh)** implements one scoped task at a time.
- **Claude Opus 4.8 (max)** reviews, audits, and makes scoped fixes — and never
  runs concurrently with Codex in the same worktree.
- Gates auto-resolve under an encoded **conservative + open-license policy**
  (HD-12), enforced by machine gates on every task; the single remaining human
  step is the author's **release attestation** (`HR-08`).
- **One branch only: `main`** — no task branches or worktrees.
- **No automatic push** — accepted work is committed locally; publishing is a
  human decision.

See [scripts/agent_loop/README.md](scripts/agent_loop/README.md) and
[LOOP.md](LOOP.md) for operation.

## Environment setup

FInk targets a local Linux environment (developed on **WSL2 Ubuntu 24.04**).

```bash
# Public repo (this repository)
cd ~/fai/fink

# Private, git-ignored root for tokens, weights, private corpora, run inputs
#   ~/fai/fink-private
# Local environment definition (defines PRIVATE_ROOT and runtime flags)
source "$HOME/fai/fink-env.sh"

# Python environment (managed with uv)
uv sync

# Tests
uv run pytest

# Repository health and machine gates
bash scripts/agent_loop/doctor.sh --no-llm
bash scripts/agent_loop/run_gates.sh
```

> `~/fai/fink-env.sh` and `~/fai/fink-private` live **outside** this repository
> and are never committed.

## Hugging Face and local models

- The Hugging Face token is read only from the cached path
  `~/.cache/huggingface/token`, via
  [`scripts/model_research/run_with_hf_auth.sh`](scripts/model_research/run_with_hf_auth.sh).
- The token value is **never printed, logged, copied, or committed**.
- Only **public/open** licenses are automatically eligible (Apache-2.0, MIT, BSD,
  ISC, CC0, CC-BY-4.0).
- **Gated, unknown, custom, noncommercial, and research-only** licenses are
  **rejected by default**.
- Model **downloads require human approval** (`MODEL_DOWNLOAD_APPROVED`).
- Model **weights stay outside Git** (under `~/fai/fink-private` or the Hugging
  Face cache).

License policy and candidate registry: [`configs/models/candidates.yaml`](configs/models/candidates.yaml).

## Development commands

All commands below exist in this repository today:

```bash
# Doctor (environment + branch + required docs), no LLM
bash scripts/agent_loop/doctor.sh --no-llm

# Machine gates (privacy, legal-language, financial, queue/backlog, schema, ...)
bash scripts/agent_loop/run_gates.sh

# Dry-run a single loop task (no Codex/Claude/commit)
bash scripts/agent_loop/loop_once.sh --dry-run

# Run a single queue
bash scripts/agent_loop/loop_run.sh scripts/agent_loop/queue.s0.txt 1 --dry-run

# Run all queues in dependency order (s0 -> models -> s1 -> s2 -> s3)
bash scripts/agent_loop/run_all_queues.sh --dry-run

# Drain the whole backlog at once (every phase S0..S8 + MR)
bash scripts/agent_loop/run_backlog.sh --dry-run

# Stop the loop after the current task
touch loop/STOP
```

Loop progress and the next eligible task are summarized in [LOOP.md](LOOP.md).

## Repository structure

```
fink/
├── app/                      # web entrypoint (placeholder; planned)
├── src/                      # FInk Python packages, src/fink/* (placeholder; planned)
├── configs/
│   └── models/               # model license policy + candidate registry
├── docs/                     # specs, cards, privacy, limitations
│   └── paper/                # paper-section notes + claim/result/figure ledgers
├── paper/
│   └── template/icml2026/    # ICML 2026 template (do not modify)
├── site/                     # static project-page assets (images present)
├── scripts/
│   ├── agent_loop/           # single-main Codex/Claude agent loop + gates
│   └── model_research/       # Hugging Face auth + local model env scaffolding
├── tests/                    # gate-safety + agent-loop tests
├── artifacts/                # run artifacts (placeholder; planned)
├── loop/                     # BACKLOG, HUMAN_GATES, STATE, CHARTER, reviews
└── .fink/                    # local-only runtime artifacts (git-ignored)
```

`app/`, `src/`, `artifacts/`, and `data/` are present as placeholders for
upcoming phases; product code is not implemented yet. `.fink/` and private data
roots are git-ignored.

## Evaluation

Planned metrics only — **no measured results are reported yet**. The evaluation
plan targets, on **synthetic / sanitized** data with a frozen split:

- OCR character/word error rate (KO + EN), including money, percentages, dates,
  durations, and article numbers.
- Financial-term exact-match extraction.
- Clause segmentation quality.
- Retrieval recall and authority-tier correctness; KO/EN consistency.
- Risk-signal quality and benign false-positive rate across rule / model /
  hybrid arms.
- Financial-formula and scenario unit correctness.
- Latency, memory, offline behavior, and privacy redaction.

Results, once measured, are tracked in the ledgers under
[docs/paper/](docs/paper/) (`CLAIM_LEDGER.csv`, `RESULT_LEDGER.csv`,
`FIGURE_REGISTRY.csv`).

## Paper and project page

- **ICML 2026 template** lives under
  [`paper/template/icml2026/`](paper/template/icml2026/) and is treated as
  read-only (byte-preserved by the loop's gates).
- **Paper notes** are drafted per section under [docs/paper/](docs/paper/).
- **Claim / result / figure ledgers** keep every paper claim traceable to a
  measured artifact; no value is written without evidence.
- A **static project page** is planned (synthetic demos only). Image assets are
  under `site/assets/images/`; the page itself is **not yet built or deployed**.
- A project-page domain `fink.seonukkim.com` is **planned and not deployed**.

## Responsible use

> **Disclaimer.** FInk provides financial review-priority signals and scenario
> analysis. It does not provide a binding legal opinion, determine fraud or
> illegality, or replace professional legal review.

FInk never claims to determine fraud, illegality, contract validity, voidness,
definitive unfairness, guaranteed loss, or any legal outcome. Authority-grounded
scoring uses only official (A0–A2) sources; educational and creator-practical
(B/C) sources may add explanations, terminology, and practice questions but
contribute **zero** to authority-supported scoring. See
[docs/limitations.md](docs/limitations.md).

## Citation

Provisional citation for a work in progress (no published venue, DOI, or
results):

```bibtex
@misc{kim2026fink,
  author       = {Kim, Seonuk},
  title        = {{FInk}: Evidence-Grounded Financial AI for Creator Contract Review},
  year         = {2026},
  note         = {UNIST IE412 AI for Finance (2026 Spring) final project.
                  Work in progress; provisional citation, no published results.},
  howpublished = {\url{https://github.com/seonukkim/fink}}
}
```

## License and data policy

Licensing is **pending**. `LICENSE`, `DATA_LICENSE.md`, and `NOTICE.md` are
present but currently empty; no license is granted until those files state one.
Until then, treat this repository as **all rights reserved** by the author and do
not assume reuse rights. Private corpora, contracts, and model weights are out of
scope of this repository entirely and are never committed.
