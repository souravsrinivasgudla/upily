# Upily evaluation — 2026-09-27

Corpus: 94 stories (frozen snapshot in `evals/data/`).

## Retrieval (chat memory search)

| Questions | n | hit@1 | hit@3 | hit@5 | MRR@5 |
|---|---|---|---|---|---|
| easy | 40 | 100% | 100% | 100% | 1.00 |
| hard | 40 | 52% | 55% | 55% | 0.54 |

Unanswerable questions correctly returning nothing: **67%** (12 questions).

## Story grouping

40 hand-labelled pairs (11 same-story). Current threshold 0.42:

**precision 100% · recall 91% · F1 0.95** (TP 10, FP 0, FN 1, TN 29)

| threshold | precision | recall | F1 |
|---|---|---|---|
| 0.30 | 83% | 91% | 0.87 |
| 0.35 | 83% | 91% | 0.87 |
| 0.40 | 83% | 91% | 0.87 |
| 0.42 ← | 100% | 91% | 0.95 |
| 0.45 | 100% | 82% | 0.90 |
| 0.50 | 100% | 82% | 0.90 |
| 0.55 | 100% | 55% | 0.71 |
| 0.60 | 100% | 45% | 0.62 |

## End-to-end answers (LLM-graded)

| Questions | n | correct | abstained | wrong | hallucinated |
|---|---|---|---|---|---|
| easy | 5 | 80% | 0% | 0% | 20% |
| hard | 5 | 100% | 0% | 0% | 0% |
| negative | 12 | 0% | 100% | 0% | 0% |

For unanswerable questions (negative), *abstained* is the correct outcome.
