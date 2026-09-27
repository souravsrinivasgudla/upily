# Upily evaluation harness

This harness measures the two parts of Upily where quality is easy to claim and hard to check:
- **retrieval** for the chat (does the right stored story come back?)
- **story grouping** (are "N outlets" badges right?)

It also offers optional **end-to-end answer grading**.

```bash
cd backend
python -m evals.run_eval                  # offline, deterministic, ~2 s
python -m evals.run_eval --show-misses    # plus every failed question and pair
python -m evals.run_eval --answers 5      # plus LLM-graded answers (needs GROQ_API_KEY)
python -m evals.build_dataset             # rebuild the dataset from the current DB
```

Results are written to [`results/latest.md`](results/latest.md). [`tests/test_evals.py`](../tests/test_evals.py) enforces minimum scores, so a change that makes retrieval or grouping worse fails the test suite.

## Dataset (`data/`)

| File | Contents |
|---|---|
| `corpus.json` | 94 stored stories frozen on 2026-09-27: headline, outlet, section, summary, a 300-character excerpt and the source lead. Evaluation runs on this snapshot, not the live database, so scores stay reproducible as the news rotates. |
| `questions.json` | 40 sampled stories × 2 questions written by the LLM. **easy**: natural phrasing. **hard**: must avoid the headline's distinctive words (describe or paraphrase instead). Plus 12 hand-written **negative** questions about events that don't exist. |
| `cluster_pairs.json` | The 40 most lexically similar story pairs (before the grouping rules apply), **hand-labelled**: 11 "same story", 29 "different story". |

**Labelling rule for pairs:** "same story" means showing both would be redundant, i.e. the same news item. The same event from different angles doesn't count; for example, two different sketches from one SNL episode are different stories.

## Results (2026-09-27)

**Retrieval** (`search_service.rank`):

| Questions | n | hit@1 | hit@3 | MRR@5 |
|---|---|---|---|---|
| easy | 40 | 100% | 100% | 1.00 |
| hard (paraphrased) | 40 | 52% | 55% | 0.54 |
| unanswerable → returns nothing | 12 | | 67% | |

**Story grouping** at threshold 0.42: **precision 100%, recall 91%, F1 0.95** (10 TP, 0 FP, 1 FN).

**End-to-end answers** (`--answers 5`, graded by the LLM, small sample):

| Questions | n | correct | abstained | hallucinated |
|---|---|---|---|---|
| easy | 5 | 80% | 0% | 20% |
| hard | 5 | 100% | 0% | 0% |
| unanswerable | 12 | 0% | **100%** | 0% |

## Findings and decisions

1. **Keyword retrieval breaks down when the wording changes.** Easy questions are perfect, but only 55% of paraphrased questions find their story. For example, "the southern African nation" doesn't match "South Africa". That's the inherent limit of keyword search and the main reason to add embedding-based (hybrid) retrieval. This harness is how that change would be judged.

2. **Rejecting unanswerable questions trades off against recall, so the chat prompt handles it.** Counting query words that no story contains as missing evidence raised the rejection rate from 8/12 to 11/12, but cut hard-question hits from 22/40 to 11/40:

   | Scoring variant | easy | hard | unanswerable rejected |
   |---|---|---|---|
   | **ignore words no story contains (shipped)** | **40/40** | **22/40** | **8/12** |
   | unknown words count ×0.5, min 0.35 | 39/40 | 13/40 | 10/12 |
   | unknown words count ×1.0, min 0.30 | 39/40 | 11/40 | 11/12 |

   The shipped variant keeps recall. The false hits it lets through are handled one layer up: the chat prompt only allows current-event facts found in the retrieved stories. In the end-to-end run, all 12 unanswerable questions were refused, including the 4 where retrieval returned a wrong story.

3. **The grouping threshold was chosen from a sweep.** At 0.40 and below, precision drops to 83%: one false pair (WIRED on pancreatic cells vs The Guardian on sickle cell) shares the headline word "cell" and scores 0.52. That's why pairs must also share *two* headline terms. At 0.45 and above, recall falls to 82%, because "Godzilla Minus Zero" coverage from Variety and The Hollywood Reporter scores 0.43. 0.42 is the best F1. Precision matters more than recall here: a wrong "3 outlets" badge misleads readers, a missing one just looks like one outlet.

4. **The one missed grouping** is BBC's "White casts doubt on Fury-Joshua" vs Sky's "Fury: one per cent chance of AJ fight". It's the same story, but the headlines share only "Fury", because Sky writes "AJ" where the BBC writes "Joshua". Fixing it would need entity aliasing or embeddings.

5. **The evaluation found a production bug.** Grading answers back to back hit Groq's free-tier limit of 8,000 tokens a minute. The news pipeline does the same when it analyses a batch of new stories, and its stop-after-3-failures guard was ending the analysis run early. `llm_service` now reads the provider's "try again in Xs" and waits before retrying.

## Caveats

- **The questions were generated from the stories.** Easy questions in particular share vocabulary with their answers, so treat 100% as an upper bound. The hard set exists to counter this.
- **The pair set is small (40 pairs, one annotator)**, and its candidates are the most similar pairs by one kind of similarity. Recall is measured against those candidates only, so same-story pairs with very different wording aren't counted.
- **The end-to-end grading uses a small sample and an LLM judge.** Its percentages are indicative, not precise.
