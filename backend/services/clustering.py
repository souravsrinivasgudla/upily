"""
Story grouping — detect articles from different outlets (or sections) that cover
the same event, and give them a shared `cluster_id`.

Method: TF-IDF cosine similarity over headline + lead text (headline terms
weighted double), computed across all stories fetched in the last few days,
then union-find over pairs that pass all three rules:

  * the two stories come from different outlets (one outlet's stories on a
    similar topic — several breast-cancer features, several SNL recaps — are
    separate stories, and were the main source of false matches),
  * the headlines share at least two terms (one shared word like "Meta" or
    "cell" is not enough),
  * cosine similarity >= SIMILARITY_THRESHOLD.

Thresholds were tuned on labelled pairs in evals/data/cluster_pairs.json;
run `python -m evals.run_eval` to measure precision/recall after changes.

cluster_id is the smallest article id in the group, so it stays stable as new
coverage of an existing story arrives. Singletons get their own id.
"""
import logging
import math
from collections import Counter
from datetime import timedelta
from typing import Dict, Iterable, List, Sequence

from sqlalchemy import select, update

from config import settings
from db.database import AsyncSessionLocal
from db.models import Article
from services.dates import utcnow
from services.search_service import tokenize

log = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.42
MIN_SHARED_TITLE_TERMS = 2
LEAD_CHARS = 300


def _terms(a) -> Counter:
    c = Counter()
    for t in tokenize(a.title):
        c[t] += 2
    for t in tokenize((a.raw_content or a.summary or "")[:LEAD_CHARS]):
        c[t] += 1
    return c


def _vectors(articles: Sequence) -> List[Dict[str, float]]:
    bags = [_terms(a) for a in articles]
    n = len(bags)
    df = Counter(t for bag in bags for t in bag)
    vecs = []
    for bag in bags:
        v = {t: tf * math.log((1 + n) / (1 + df[t])) for t, tf in bag.items() if df[t] > 1}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def similarity_matrix(articles: Sequence) -> Dict[tuple, float]:
    """Cosine similarity for every pair eligible to be grouped (see module docstring)."""
    vecs = _vectors(articles)
    titles = [set(tokenize(a.title)) for a in articles]
    sources = [(a.source or "").strip().lower() for a in articles]
    sims = {}
    for i in range(len(vecs)):
        vi = vecs[i]
        for j in range(i + 1, len(vecs)):
            if sources[i] and sources[i] == sources[j]:
                continue
            if len(titles[i] & titles[j]) < MIN_SHARED_TITLE_TERMS:
                continue
            vj = vecs[j]
            sims[(i, j)] = sum(vi[t] * vj[t] for t in vi.keys() & vj.keys())
    return sims


def cluster(articles: Sequence, threshold: float = SIMILARITY_THRESHOLD) -> Dict[int, int]:
    """Map article id → cluster id (smallest id in its group)."""
    parent = list(range(len(articles)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (i, j), s in similarity_matrix(articles).items():
        if s >= threshold:
            parent[find(i)] = find(j)

    groups: Dict[int, List[int]] = {}
    for i in range(len(articles)):
        groups.setdefault(find(i), []).append(articles[i].id)
    return {aid: min(ids) for ids in groups.values() for aid in ids}


async def recluster(hours: int | None = None) -> int:
    """Recompute cluster ids for recent articles. Returns the number of multi-outlet groups."""
    hours = hours or settings.RETENTION_HOURS
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Article).where(Article.fetched_at >= utcnow() - timedelta(hours=hours))
        )).scalars().all()
        if not rows:
            return 0
        mapping = cluster(rows)
        changed = [(a.id, mapping[a.id]) for a in rows if a.cluster_id != mapping[a.id]]
        for aid, cid in changed:
            await db.execute(update(Article).where(Article.id == aid).values(cluster_id=cid))
        await db.commit()

    sizes = Counter(mapping.values())
    multi = sum(1 for n in sizes.values() if n > 1)
    log.info("Story grouping: %d stories, %d grouped stories, %d ids updated", len(rows), multi, len(changed))
    return multi


def distinct_sources(articles: Iterable) -> List[str]:
    seen: List[str] = []
    for a in articles:
        if a.source and a.source not in seen:
            seen.append(a.source)
    return seen
