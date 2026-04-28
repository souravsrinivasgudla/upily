import asyncio
from db.database import AsyncSessionLocal
from sqlalchemy import text

async def check():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT category, count(*) FROM articles GROUP BY category;"))
        rows = result.fetchall()
        print("DB categories:", rows)

if __name__ == "__main__":
    asyncio.run(check())
