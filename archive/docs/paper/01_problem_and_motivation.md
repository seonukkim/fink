# Problem and Motivation

## Course Mapping

This note covers the course report's problem definition and motivation parts
(`CLM-S7-MAP-PROBLEM`). It explains why FInk focuses on Contractual Financial
Review Priority rather than legal conclusions.

## Problem Definition

Creators may face contract clauses whose financial effects are difficult to
compare across settlement transparency, revenue basis, payment timing,
recoupment, secondary-rights monetization, exclusivity, termination exposure,
and production-cost burden. FInk frames those clauses as review-priority signals
that should help a user decide which issues to scrutinize or ask about before
signing (`CLM-S7-FRAME-REVIEW`).

## Motivation

The project is motivated by a local-first privacy boundary: uploaded contracts,
OCR text, and temporary artifacts are treated as local and ephemeral, while
paper and demo artifacts use only synthetic or sanitized evaluation material.
This keeps the paper aligned with the system boundary that user contract content
must not appear in public artifacts (`CLM-S7-PRIVACY-BOUNDARY`).

## Current Boundary

The paper must not state current-law validation while HR-01 remains open, and
dated source figures are not presented as current. Any result value in the paper
must come from `RESULT_LEDGER.csv`; this section intentionally avoids empirical
performance claims.
