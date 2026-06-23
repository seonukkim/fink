# README Content Guide

Maintenance notes for `README.md`. The goal is a clean, academic project README
that frames FInk as an **IE412 AI for Finance** project and keeps the canonical
cash-flow triage boundary intact.

## Chosen title rationale

- **Title (exact, single):** `FInk: Selective, Evidence-Gated Cash-Flow Triage
  for Creator Contracts`.
- **Short subtitle:** `Contractual Financial Review Priority for creator
  contracts.`
- **"FInk" = "Finance" + "Ink".** Financial intelligence for contracts, comics,
  webtoons, and creator work. The **"k"** is an intentional part of the name and
  is not expanded.
- **Avoided** by design: "Local-First" in the title; "Inked Creator" /
  "Inked Creator Contracts"; the long "Creator Contract Risk Review and Cash-Flow
  Analysis" title/subtitle; and any legal-chatbot framing.
- **Framing:** selective, evidence-gated cash-flow triage, not legal AI. The
  README leads with review-priority signals, payout implications, and cash-flow
  scenarios.

## README section map

1. **Hero** — title, hero image, one-paragraph summary, disclaimer, course
   context, links.
2. **Overview** — audience, why a creator contract is a financial document, which
   clauses matter (royalties, settlement, deductions, MG recoupment, payment
   delay, IP, exclusivity, production cost).
3. **Cash-flow triage framing** — IE412 ties: decision-focused evaluation,
   financial-document analysis, and risk-detection methodology adapted into
   review-priority triage; explicit "does not determine fraud".
4. **Core output** — the four separated outputs.
5. **Workflow** — the input → report pipeline.
6. **Architecture** — frontend, FastAPI app, OCR/PDF, retrieval, deterministic
   scoring, financial scenarios, optional local explanation model, private local
   storage.
7. **Privacy and local runtime.**
8. **Current status / TODO** — GitHub checkboxes, synchronized manually with
   `LOOP.md` and `loop/BACKLOG.yaml`.
9. **Agentic development workflow** — Codex implements, Claude reviews, human
   approves, single `main`, no auto push.
10. **Environment setup** — WSL2/Linux, `~/fai/fink`, `~/fai/fink-private`,
    `source "$HOME/fai/fink-env.sh"`, `uv sync`, `uv run pytest`, doctor/gates.
11. **Hugging Face and local models** — optional/when-installed only; token path
    never printed/committed; open-license-only; gated/unknown/custom/
    noncommercial/research-only rejected; download requires approval; weights
    outside Git; no model is claimed active without a passing offline health
    check.
12. **Development commands** — only commands that exist.
13. **Repository structure** — annotated tree.
14. **Evaluation** — planned metrics only.
15. **Paper and project page** — ICML template, paper notes, ledgers, planned page
    and planned domain.
16. **Responsible use** — the disclaimer.
17. **Citation** — provisional BibTeX only.
18. **License and data policy** — pending until the license files state otherwise.

## Image assets used

From `site/assets/images/` (all present at time of writing):

- `fink-hero.png` — used as the top hero image (`<p align="center">` block).
- `fink-icon.svg`, `fink-icon-32.png`, `fink-icon-512.png` — available for the
  project page / favicons; **not** currently embedded in the README.

If `fink-hero.png` is ever removed, replace the hero block with an HTML comment
placeholder rather than leaving a broken image link.

## Visual / brand direction

- Pink ink, clean academic-paper style; creator-contracts-and-finance, **not**
  courtroom/legal-verdict imagery and **not** generic robot/AI branding.

| Token | Hex |
|---|---|
| Ink Pink | `#E83E8C` |
| Deep Pink | `#B91C5C` |
| Pale Pink | `#FFF1F7` |
| Charcoal | `#1F2937` |
| Paper White | `#FFFDFC` |
| Finance Navy | `#17324D` |

## Missing assets or links

- **Project Page** — source lives at `site/index.html`; deployment is not
  required or claimed by the README.
- **Demo** — local run only through `uv sync --extra web` and `uv run fink-web`.
- **Paper** — links to draft notes under `docs/paper/`; there is no compiled
  paper artifact to link yet.
- **Domain `fink.seonukkim.com`** — do not claim deployment unless a later task
  records deployment evidence; the loop itself must not push or deploy.
- All other README links are repo-relative and verified to resolve.

## TODO update rules

- Use `[x]` **only** when repository evidence proves completion (committed code +
  passing gates/tests, or a backlog task marked `DONE` in `loop/BACKLOG.yaml`).
- Scaffolding, placeholders, empty directories, or an OPEN human gate are **not**
  completion — keep `[ ]`.
- Keep the checklist synchronized manually with `LOOP.md` and
  `loop/BACKLOG.yaml`. When a backlog task flips to `DONE`, check its item.

## What can be checked automatically

- Relative link and image-path existence (`test -e` on each target).
- Backlog task status counts (`loop/BACKLOG.yaml` → `DONE` vs `READY`) to drive
  TODO boxes.
- Forbidden-content / legal-language and secret scans over the README and this
  guide via `bash scripts/agent_loop/run_gates.sh` (the gate engine scans tracked
  **and** untracked-non-ignored text files).
- Presence of license files and whether they are empty (licensing pending).

## What needs manual review

- That prose framing stays **financial**, not legal-advisory.
- That no unmeasured result, real-contract performance, predicted exposure-value,
  deployed URL, or completed feature is implied before it exists.
- That the disclaimer text is present and unmodified.
- The provisional citation (no invented venue/DOI/status/URL).

## Rules for not overstating completion

- Describe implemented infrastructure (the agent loop) in the past tense; describe
  product features (OCR, retrieval, scoring, web app, evaluation, project page,
  paper) as **planned / in progress** until proven done.
- Never claim a deployment, a live demo, a published paper, or measured numbers.
- Never claim a license the files do not actually grant.
- Keep FInk framed as review-priority + scenario analysis; never describe it as
  determining fraud, illegality, validity, voidness, unfairness, guaranteed loss,
  or any legal outcome.
