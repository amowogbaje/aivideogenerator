from fastapi import APIRouter
from app.api.v1.video import router as video_router

api_router = APIRouter()
api_router.include_router(video_router, prefix="/v1/videos", tags=["Videos"])