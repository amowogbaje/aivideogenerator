import uuid
from sqlalchemy import Column, String, Integer, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class VideoProject(Base):
    __tablename__ = "video_projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String, default="QUEUED")  # QUEUED, PROCESSING, COMPILING, COMPLETED, FAILED
    prompt = Column(Text, nullable=True)
    story_text = Column(Text, nullable=True)
    aspect_ratio = Column(String, default="9:16")
    final_video_url = Column(String, nullable=True)

    scenes = relationship("VideoScene", back_populates="project", cascade="all, delete-orphan")

class VideoScene(Base):
    __tablename__ = "video_scenes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("video_projects.id"))
    scene_number = Column(Integer)
    narration_chunk = Column(Text)
    visual_prompt = Column(Text)
    image_url = Column(String, nullable=True)
    video_url = Column(String, nullable=True)
    duration_seconds = Column(Integer, default=5)

    project = relationship("VideoProject", back_populates="scenes")