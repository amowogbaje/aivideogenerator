import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import assets, config as config_api, episodes, scenes, series
from app.config import settings
from app.database import Base, engine
from app.pipeline import orchestrator
from app.services import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.media_root()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # MVP: swap for Alembic migrations before production
    await orchestrator.recover_interrupted()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="AI Story Studio", version="2.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
    for r in (config_api.router, series.router, episodes.router, assets.router, scenes.router):
        app.include_router(r, prefix="/api")
    app.mount("/media", StaticFiles(directory=str(storage.media_root())), name="media")

    # If the frontend has been built (npm run build), serve it from the same origin: one process, one port.
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="frontend-assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")   # client-side routes like /series/3
    return app


app = create_app()
