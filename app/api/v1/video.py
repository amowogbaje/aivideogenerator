import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc
from app.database import get_db
from app.config import settings
from app.models.video import VideoProject
from app.schemas.video import VideoCreateSchema, ProjectResponseSchema
from app.tasks.video_tasks import run_video_pipeline

router = APIRouter()

@router.post("/generate", response_model=ProjectResponseSchema, status_code=status.HTTP_202_ACCEPTED)
async def generate_video(payload: VideoCreateSchema, db: AsyncSession = Depends(get_db)):
    if not payload.prompt and not payload.story_text:
        raise HTTPException(status_code=400, detail="Provide either a brief prompt or complete story_text.")

    # Create tracked project entity inside database state
    project = VideoProject(
        id=uuid.uuid4(),
        status="QUEUED",
        prompt=payload.prompt,
        story_text=payload.story_text,
        aspect_ratio=payload.aspect_ratio.value
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    # Hand off execution thread asynchronously to Celery workforce
    run_video_pipeline.delay(str(project.id), payload.dict())

    return {
        "project_id": project.id,
        "status": project.status,
        "prompt": project.prompt,
        "story_text": project.story_text,
        "aspect_ratio": project.aspect_ratio,
        "final_video_url": project.final_video_url,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }

# 👇 NEW: Fetch all video orchestration tracks
@router.get("", status_code=status.HTTP_200_OK)
async def get_videos(
    limit: int = 20,
    offset: int = 0,
    sortBy: str = Query("created_at"),  # default field
    order: str = Query("desc"),         # desc by default
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a paginated list of all video generation projects in the system.
    """

    # 🔒 Whitelist allowed sort fields (important for security)
    allowed_sort_fields = {
        "created_at": VideoProject.created_at,
        "updated_at": VideoProject.updated_at,
        "id": VideoProject.id,
    }

    sort_column = allowed_sort_fields.get(sortBy)

    if not sort_column:
        sort_column = VideoProject.created_at  # fallback safe default

    # direction
    if order.lower() == "asc":
        order_by_clause = asc(sort_column)
    else:
        order_by_clause = desc(sort_column)

    stmt = (
        select(VideoProject)
        .order_by(order_by_clause)
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(stmt)
    projects = result.scalars().all()

    return projects