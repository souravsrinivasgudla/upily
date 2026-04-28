import asyncio
from services.llm_service import chat

async def test():
    result = await chat("Test prompt")
    print(result)

if __name__ == "__main__":
    asyncio.run(test())
