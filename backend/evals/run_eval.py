"""
Offline evaluation of Upily's retrieval (RAG) and story grouping.

    python -m evals.run_eval                  # print report, write evals/results/latest.md
    python -m evals.run_eval --show-misses    # also list failed questions / pairs
    python -m evals.run_eval --answers 10     # + end-to-end answer grading (uses the LLM)

Runs entirely against the frozen snapshot in evals/data/ — no database, no network,
no LLM calls — so results are reproducible and cheap enough to run on every change.

Retrieval metrics (per difficulty):
  hit@k   the story that answers the question is among the top k results
  MRR@5   mean reciprocal rank of that story within the top 5 (0 if absent)
  reject  for questions about events not in the corpus: share that return nothing

Answer metrics (--answers N; the only part that calls the LLM):
  For every unanswerable question and N sampled easy + N hard questions, run the
  real chat prompt over the retrieved stories, then have the LLM grade the answer
  against the reference story: correct / abstained / wrong / hallucinated.
  For unanswerable questions, "abstained" is the right outcome.

Grouping metrics (over hand-labelled pairs):
  precision  of pairs we grouped, share that really are the same story
  recall     of pairs that are the same story, share we grouped
  F1         harmonic mean; plus a threshold sweep to show the trade-off
"""
import argparse
import asyncio
import json
import random
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from services import clustering
from services.search_service import rank

HERE = Path(__file__).parent
DATA = HERE / "data"
RESULTS = HERE / "results"


def load_corpus() -> tuple[list, list]:
    corpus = json.loads((DATA / "corpus.json").read_text(encoding="utf-8"))
    # Retrieval sees what search_memory sees: headline, summary, excerpt, tags
    retrieval_docs = [SimpleNamespace(
        id=c["id"], title=c["title"], summary=c["summary"], raw_content=c["excerpt"],
        deep_explanation=None, tags=c.get("tags") or [], category=c["category"],
        importance_score=0.5, source=c["source"],
    ) for c in corpus]
    # Grouping sees what recluster sees: headline + source lead
    grouping_docs = [SimpleNamespace(
        id=c["id"], title=c["title"], source=c["source"],
        raw_content=c.get("lead") or c["summary"], summary=c["summary"],
    ) for c in corpus]
    return retrieval_docs, grouping_docs


# ── Retrieval ─────────────────────────────────────────────────────────────────

def eval_retrieval(docs) -> dict:
    questions = json.loads((DATA / "questions.json").read_text(encoding="utf-8"))
    by_diff: dict[str, dict] = {}
    misses = []
    for q in questions:
        ranked = [a.id for _, a in rank(q["q"], docs)]
        d = by_diff.setdefault(q["difficulty"], {"n": 0, "hit1": 0, "hit3": 0, "hit5": 0, "rr": 0.0, "reject": 0})
        d["n"] += 1
        if q["difficulty"] == "negative":
            if not ranked:
                d["reject"] += 1
            else:
                misses.append(("negative", q["q"], None, ranked[:2]))
            continue
        pos = ranked.index(q["id"]) + 1 if q["id"] in ranked else None
        d["hit1"] += pos == 1
        d["hit3"] += pos is not None and pos <= 3
        d["hit5"] += pos is not None and pos <= 5
        d["rr"] += 1 / pos if pos and pos <= 5 else 0
        if not pos or pos > 3:
            misses.append((q["difficulty"], q["q"], q["id"], ranked[:2]))

    report = {}
    for diff, d in by_diff.items():
        n = d["n"]
        report[diff] = ({"n": n, "reject": d["reject"] / n} if diff == "negative" else
                        {"n": n, "hit@1": d["hit1"] / n, "hit@3": d["hit3"] / n,
                         "hit@5": d["hit5"] / n, "mrr@5": d["rr"] / n})
    return {"metrics": report, "misses": misses}


# ── End-to-end answers (LLM) ─────────────────────────────────────────────────

JUDGE = """You grade a news assistant's answer.

QUESTION: {q}
REFERENCE: {ref}
ANSWER: {a}

Classify the ANSWER:
- "correct": answers the question consistently with the reference story
- "abstained": says it has no coverage / doesn't know
- "wrong": attempts an answer that contradicts or misses the reference
- "hallucinated": presents specific facts about an event that the reference doesn't support
  (for "no such story exists", any confident factual answer is hallucinated)

Return ONLY JSON: {{"verdict": "correct" | "abstained" | "wrong" | "hallucinated"}}"""


async def eval_answers(docs, n_per_difficulty: int) -> dict:
    from agents.qa_agent import SYSTEM, build_prompt, clean_answer
    from services import llm_service
    from services.text import extract_json

    questions = json.loads((DATA / "questions.json").read_text(encoding="utf-8"))
    by_id = {d.id: d for d in docs}
    rng = random.Random(11)
    picked = [q for q in questions if q["difficulty"] == "negative"]
    for diff in ("easy", "hard"):
        pool = [q for q in questions if q["difficulty"] == diff]
        picked += rng.sample(pool, min(n_per_difficulty, len(pool)))

    counts: dict[str, dict[str, int]] = {}
    examples = []
    for q in picked:
        memory = [{"id": a.id, "title": a.title, "summary": a.summary, "excerpt": a.raw_content,
                   "source": a.source, "category": a.category}
                  for _, a in rank(q["q"], docs)[:5]]
        answer = clean_answer(await llm_service.chat(
            build_prompt(q["q"], None, memory, [], []), system=SYSTEM, max_tokens=500))
        ref = ("No such story exists in the coverage." if q["id"] is None else
               f"{by_id[q['id']].title}. {by_id[q['id']].summary}")
        raw = await llm_service.chat(JUDGE.format(q=q["q"], ref=ref, a=answer[:1500]), max_tokens=60, temperature=0)
        verdict = (extract_json(raw) or {}).get("verdict", "unparsed")
        counts.setdefault(q["difficulty"], {}).setdefault(verdict, 0)
        counts[q["difficulty"]][verdict] += 1
        if (q["id"] is None and verdict != "abstained") or (q["id"] is not None and verdict in ("wrong", "hallucinated")):
            examples.append((q["difficulty"], verdict, q["q"], answer[:200]))
    return {"counts": counts, "examples": examples}


def render_answers(ans: dict) -> str:
    lines = ["", "## End-to-end answers (LLM-graded)", "",
             "| Questions | n | correct | abstained | wrong | hallucinated |", "|---|---|---|---|---|---|"]
    for diff in ("easy", "hard", "negative"):
        c = ans["counts"].get(diff)
        if not c:
            continue
        n = sum(c.values())
        lines.append(f"| {diff} | {n} | " + " | ".join(_pct(c.get(k, 0) / n) for k in
                     ("correct", "abstained", "wrong", "hallucinated")) + " |")
    lines += ["", "For unanswerable questions (negative), *abstained* is the correct outcome."]
    return "\n".join(lines) + "\n"


# ── Grouping ──────────────────────────────────────────────────────────────────

def _prf(pairs, mapping) -> dict:
    tp = fp = fn = tn = 0
    wrong = []
    for p in pairs:
        predicted = mapping[p["a"]] == mapping[p["b"]]
        if predicted and p["same_story"]:
            tp += 1
        elif predicted:
            fp += 1
            wrong.append(("false group", p))
        elif p["same_story"]:
            fn += 1
            wrong.append(("missed", p))
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn, "wrong": wrong}


def eval_grouping(docs) -> dict:
    pairs = [p for p in json.loads((DATA / "cluster_pairs.json").read_text(encoding="utf-8"))
             if p.get("same_story") is not None]
    current = _prf(pairs, clustering.cluster(docs))
    sweep = []
    for t in (0.30, 0.35, 0.40, 0.42, 0.45, 0.50, 0.55, 0.60):
        r = _prf(pairs, clustering.cluster(docs, threshold=t))
        sweep.append({"threshold": t, **{k: r[k] for k in ("precision", "recall", "f1")}})
    return {"n": len(pairs), "positives": sum(p["same_story"] for p in pairs),
            "current": current, "sweep": sweep}


# ── Report ────────────────────────────────────────────────────────────────────

def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render(retrieval: dict, grouping: dict, corpus_size: int) -> str:
    m = retrieval["metrics"]
    lines = [
        f"# Upily evaluation — {date.today().isoformat()}",
        "",
        f"Corpus: {corpus_size} stories (frozen snapshot in `evals/data/`).",
        "",
        "## Retrieval (chat memory search)",
        "",
        "| Questions | n | hit@1 | hit@3 | hit@5 | MRR@5 |",
        "|---|---|---|---|---|---|",
    ]
    for diff in ("easy", "hard"):
        if diff in m:
            r = m[diff]
            lines.append(f"| {diff} | {r['n']} | {_pct(r['hit@1'])} | {_pct(r['hit@3'])} | "
                         f"{_pct(r['hit@5'])} | {r['mrr@5']:.2f} |")
    if "negative" in m:
        lines += ["", f"Unanswerable questions correctly returning nothing: "
                      f"**{_pct(m['negative']['reject'])}** ({m['negative']['n']} questions)."]
    c = grouping["current"]
    lines += [
        "",
        "## Story grouping",
        "",
        f"{grouping['n']} hand-labelled pairs ({grouping['positives']} same-story). "
        f"Current threshold {clustering.SIMILARITY_THRESHOLD}:",
        "",
        f"**precision {_pct(c['precision'])} · recall {_pct(c['recall'])} · F1 {c['f1']:.2f}** "
        f"(TP {c['tp']}, FP {c['fp']}, FN {c['fn']}, TN {c['tn']})",
        "",
        "| threshold | precision | recall | F1 |",
        "|---|---|---|---|",
    ]
    for s in grouping["sweep"]:
        mark = " ←" if abs(s["threshold"] - clustering.SIMILARITY_THRESHOLD) < 1e-9 else ""
        lines.append(f"| {s['threshold']:.2f}{mark} | {_pct(s['precision'])} | {_pct(s['recall'])} | {s['f1']:.2f} |")
    return "\n".join(lines) + "\n"


def main(show_misses: bool, answers: int = 0) -> dict:
    retrieval_docs, grouping_docs = load_corpus()
    retrieval = eval_retrieval(retrieval_docs)
    grouping = eval_grouping(grouping_docs)
    report = render(retrieval, grouping, len(retrieval_docs))
    ans = None
    if answers:
        ans = asyncio.run(eval_answers(retrieval_docs, answers))
        report += render_answers(ans)
    print(report)
    if ans and show_misses:
        print("## Answer failures\n")
        for diff, verdict, q, a in ans["examples"]:
            print(f"- [{diff}] {verdict}: {q}\n    answer: {a}")

    if show_misses:
        titles = {d.id: d.title for d in retrieval_docs}
        print("## Retrieval misses (answer not in top 3)\n")
        for diff, q, want, got in retrieval["misses"]:
            print(f"- [{diff}] {q}\n    want: {titles.get(want, '— nothing —')}\n"
                  f"    got:  {[titles[i][:50] for i in got]}")
        print("\n## Grouping errors\n")
        for kind, p in grouping["current"]["wrong"]:
            print(f"- {kind}: {p['a_title'][:60]}\n           {p['b_title'][:60]}")

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "latest.md").write_text(report, encoding="utf-8")
    return {"retrieval": retrieval["metrics"],
            "grouping": {k: v for k, v in grouping["current"].items() if k != "wrong"}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show-misses", action="store_true")
    ap.add_argument("--answers", type=int, default=0, metavar="N",
                    help="also grade end-to-end answers for N easy + N hard questions (+ all unanswerable)")
    args = ap.parse_args()
    main(args.show_misses, args.answers)
