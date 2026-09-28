"""
Copy stories from a local SQLite database into the PostgreSQL database in DATABASE_URL.

    python -m scripts.copy_sqlite_to_postgres                 # from backend/upily.db
    python -m scripts.copy_sqlite_to_postgres --source old.db
    python -m scripts.copy_sqlite_to_postgres --replace       # empty the target first

Run `alembic upgrade head` first (the app also does this on startup). Article ids are
kept, so links and story groups survive; the id sequence is moved past the copied rows.
Refuses to write into a non-empty target unless --replace is given.
"""
import argparse
import asyncio
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, insert, select, text

from db.database import BACKEND_DIR, AsyncSessionLocal, engine, is_sqlite
from db.models import Article

COLUMNS = [c.name for c in Article.__table__.columns]
DATETIME_COLUMNS = {"published_at", "fetched_at"}


def _datetime(value):
    if value in (None, ""):
        return None
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)   # SQLite stored UTC without an offset


def _row(raw: sqlite3.Row) -> dict:
    row = {c: raw[c] for c in COLUMNS if c in raw.keys()}
    for c in DATETIME_COLUMNS & row.keys():
        row[c] = _datetime(row[c])
    if isinstance(row.get("tags"), str):
        row["tags"] = json.loads(row["tags"] or "[]")
    if "is_trending" in row:
        row["is_trending"] = bool(row["is_trending"])
    return row


async def main(source: Path, replace: bool) -> None:
    if is_sqlite:
        sys.exit("DATABASE_URL points at SQLite. Set it to your PostgreSQL database first.")
    if not source.exists():
        sys.exit(f"Source database not found: {source}")

    conn = sqlite3.connect(source)
    conn.row_factory = sqlite3.Row
    rows = [_row(r) for r in conn.execute("SELECT * FROM articles ORDER BY id")]
    conn.close()
    print(f"Read {len(rows)} stories from {source.name}")

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(func.count(Article.id)))).scalar_one()
        if existing and not replace:
            sys.exit(f"Target already has {existing} stories. Re-run with --replace to overwrite them.")
        if existing:
            await db.execute(text("TRUNCATE articles RESTART IDENTITY"))
        for i in range(0, len(rows), 200):
            await db.execute(insert(Article), rows[i:i + 200])
        # Continue ids after the copied ones, so new stories don't collide
        await db.execute(text(
            "SELECT setval(pg_get_serial_sequence('articles', 'id'), COALESCE((SELECT MAX(id) FROM articles), 1))"
        ))
        await db.commit()
        copied = (await db.execute(select(func.count(Article.id)))).scalar_one()
        groups = (await db.execute(select(func.count(func.distinct(Article.cluster_id))))).scalar_one()
    await engine.dispose()
    print(f"PostgreSQL now has {copied} stories in {groups} story groups")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, default=BACKEND_DIR / "upily.db")
    ap.add_argument("--replace", action="store_true", help="empty the target table first")
    args = ap.parse_args()
    asyncio.run(main(args.source, args.replace))
