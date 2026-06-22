# Creator-Contract Checkpoint Knowledge Base

## What It Is

`data/knowledge/creator_contract_checkpoints.yaml` is a small public
knowledge base for future creator-contract chatbot grounding. It contains
original Korean summaries, practical checkpoint lists, and negotiation
questions for FInk financial risk categories F1 through F9.

This dataset is for conversation grounding only. It is not wired into the web
chat yet, and it does not change scoring, signal detection, or the A0-A2
authority invariant.

## Source Types

The checkpoint topics are distilled from source types, not copied source text:

- Official law and regulation principles at a general level.
- Public summaries of precedent themes.
- Creator and content-industry standard-contract guides.
- Internal practice notes and implementation observations.

No raw private corpus, copyrighted book passage, contract text, PDF, ZIP,
model weight, token, or source excerpt is committed with this dataset.

## Distillation Method

The method is: read source materials, extract only general principles, map
those principles to FInk's F1-F9 cash-flow categories, and rewrite them as new
creator-facing summaries and checkpoint questions.

The committed text is original prose. It does not quote statutes, decisions,
guides, sample contracts, private notes, or paid materials. Provenance is
recorded only as high-level source types plus the note that the result was
distilled without source-text copying.

## License Rationale

The YAML is intended to be publicly shareable and committable because it is a
transformative summary-and-checkpoint artifact. It expresses general review
ideas in new wording and does not include raw source text, long excerpts, scans,
or private materials.

Private or copyrighted inputs may inform future distillation, but the inputs
themselves must remain outside public Git. Only newly written, source-type
provenanced checkpoints should be committed.

## Boundary

This knowledge base provides general contract-review orientation for creator
cash-flow conversations. It is not legal advice and should not be presented as
a legal, fraud, validity, unfairness, or guaranteed-loss verdict.

FInk per-contract scoring remains governed by the existing authority gate:
score-eligible signals must be grounded by A0-A2 official evidence. This
conversation knowledge base may support explanations or follow-up questions,
but it must not create score contributions.

## How To Extend

When adding a new topic or revising an entry:

1. Keep Korean canonical and creator-facing.
2. Read sources only to understand general patterns.
3. Write new summaries, checkpoints, and negotiation questions from scratch.
4. Record provenance as source types, not source names, source IDs, or excerpts.
5. Do not commit private materials, raw contracts, PDFs, ZIPs, screenshots, or
   copied guide text.
6. Verify that the new entry is conversation grounding only and does not alter
   scoring, retrieval authority rules, or A0-A2 invariants.
7. Run the focused knowledge-base tests and full repository gates before
   committing.
