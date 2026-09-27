"""
Build the evaluation dataset from the current database.

    python -m evals.build_dataset --sample 40

Writes three files under evals/data/:
  corpus.json         frozen snapshot of stored stories (headline, outlet, section,
                      short excerpt) — evaluation runs against this, not the live DB,
                      so scores are reproducible as the news rotates
  questions.json      for each sampled story, two LLM-written questions it answers:
                        easy — natural phrasing (may reuse headline words)
                        hard — must avoid the headline's distinctive words (tests
                               vocabulary mismatch: synonyms, descriptions)
                      plus hand-written questions about events NOT in the corpus
  cluster_pairs.json  candidate story pairs for the grouping eval (label them — see
                      evals/README.md); existing labels are kept when regenerating

Needs an LLM key (a few calls). Everything else in evals/ runs offline.
"""
import argparse
import asyncio
import json
import random
from pathlib import Path

from sqlalchemy import select

from db.database import AsyncSessionLocal
from db.models import Article
from services import llm_service
from services.clustering import _vectors
from services.text import extract_json

DATA = Path(__file__).parent / "data"
EXCERPT_CHARS = 300   # keep the snapshot to headline + a short excerpt

# Events that are not in any corpus — retrieval should return nothing for these
NEGATIVES = [
    "What happened with the Mars colony independence vote?",
    "Latest on the Klingon peace treaty negotiations",
    "Who won the 2026 intergalactic chess olympiad in Tokyo?",
    "Why did the Atlantis underwater city project get cancelled?",
    "How did the dragon sighting affect tourism in Wales?",
    "What did the unicorn conservation summit agree on?",
    "Why was the Moon's time zone changed last week?",
    "Who is the new mayor of the floating city of Neo-Venice?",
    "What caused the worldwide teleportation network outage?",
    "How are the time-travel tourism regulations being enforced?",
    "What did scientists find inside the hollow Earth expedition?",
    "Who won the robot boxing world championship final?",
]


def _snapshot(a: Article) -> dict:
    return {
        "id": a.id, "title": a.title, "source": a.source, "category": a.category,
        "summary": (a.summary or "")[:280],
        "excerpt": (a.deep_explanation or a.raw_content or "")[:EXCERPT_CHARS],   # for retrieval
        "lead": (a.raw_content or a.summary or "")[:EXCERPT_CHARS],               # for grouping
        "tags": a.tags or [],
    }


async def _questions(sample: list[dict]) -> list[dict]:
    out = []
    for i in range(0, len(sample), 20):
        batch = sample[i:i + 20]
        listing = "\n".join(f"{s['id']}. {s['title']} — {s['summary']}" for s in batch)
        prompt = (
            "For each news story below write two questions a reader might ask that the story answers.\n"
            '- "easy": natural phrasing, as a real person would ask.\n'
            '- "hard": the same information need, but do NOT use any distinctive word from the headline '
            "(names, places, key nouns) — describe them instead, or use synonyms.\n"
            'Return ONLY a JSON array of objects {"id": <id>, "easy": "...", "hard": "..."}.\n\n' + listing
        )
        raw = await llm_service.chat(prompt, max_tokens=3000, temperature=0.4)
        for item in extract_json(raw, expect=list, items=dict) or []:
            if item.get("id") in {s["id"] for s in batch}:
                out.append({"id": item["id"], "q": item["easy"], "difficulty": "easy"})
                out.append({"id": item["id"], "q": item["hard"], "difficulty": "hard"})
    return out


def _candidate_pairs(corpus: list[dict], top: int, keep: dict) -> list[dict]:
    """Top pairs by raw similarity (before the grouping rules), for labelling."""
    from types import SimpleNamespace
    docs = [SimpleNamespace(**{**c, "raw_content": c["lead"]}) for c in corpus]
    vecs = _vectors(docs)
    scored = []
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            s = sum(vecs[i][t] * vecs[j][t] for t in vecs[i].keys() & vecs[j].keys())
            scored.append((s, i, j))
    scored.sort(reverse=True)
    pairs = []
    for s, i, j in scored[:top]:
        a, b = corpus[i], corpus[j]
        key = f"{min(a['id'], b['id'])}-{max(a['id'], b['id'])}"
        pairs.append({
            "a": a["id"], "b": b["id"],
            "a_title": f"[{a['source']}] {a['title']}", "b_title": f"[{b['source']}] {b['title']}",
            "same_story": keep.get(key),   # null until labelled
        })
    return pairs


async def main(sample_size: int, pairs: int, seed: int) -> None:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Article).order_by(Article.id))).scalars().all()
    corpus = [_snapshot(a) for a in rows]
    if not corpus:
        raise SystemExit("The database has no stories — run the app (or the pipeline) first.")

    random.seed(seed)
    sample = random.sample(corpus, min(sample_size, len(corpus)))
    questions = await _questions(sample)
    questions += [{"id": None, "q": q, "difficulty": "negative"} for q in NEGATIVES]

    old = DATA / "cluster_pairs.json"
    keep = {}
    if old.exists():
        for p in json.loads(old.read_text(encoding="utf-8")):
            keep[f"{min(p['a'], p['b'])}-{max(p['a'], p['b'])}"] = p.get("same_story")

    DATA.mkdir(exist_ok=True)
    (DATA / "corpus.json").write_text(json.dumps(corpus, indent=1, ensure_ascii=False), encoding="utf-8")
    (DATA / "questions.json").write_text(json.dumps(questions, indent=1, ensure_ascii=False), encoding="utf-8")
    (DATA / "cluster_pairs.json").write_text(
        json.dumps(_candidate_pairs(corpus, pairs, keep), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"corpus: {len(corpus)} stories | questions: {len(questions)} | pairs to label: {pairs}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=40, help="stories to write questions for")
    ap.add_argument("--pairs", type=int, default=40, help="candidate pairs for the grouping eval")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    asyncio.run(main(args.sample, args.pairs, args.seed))
