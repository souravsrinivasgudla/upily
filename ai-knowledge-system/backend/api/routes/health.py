from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok", "service": "AI Knowledge System v2"}
