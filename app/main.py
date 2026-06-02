from fastapi import FastAPI
from app.api.router import api_router
from app.database import engine, Base

def create_app() -> FastAPI:
    app = FastAPI(title="AI Story Video Generator API", version="1.0.0")
    
    @app.on_event("startup")
    async def startup():
        # Automatically creates tables in your database during local MVP development
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    app.include_router(api_router, prefix="/api")
    return app