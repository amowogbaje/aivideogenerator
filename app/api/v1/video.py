import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
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
        "status": "QUEUED",
        "message": "Orchestration pipeline worker triggered successfully."
    }