from fastapi import APIRouter
from app.api.v1.video import router as video_router

api_router = APIRouter()

@api_router.get("/v1", tags=["Root"])
async def v1_root():
    return {
        "message": "welcome to ai video story maker version 1.0.0",
        "project": "AI Story Video Generator",
        "docs_url": "/docs"  # Quick handy link for testing
    }

api_router.include_router(video_router, prefix="/v1/videos", tags=["Videos"])