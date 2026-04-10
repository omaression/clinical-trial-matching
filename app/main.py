from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import trials
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load spaCy model, verify DB connection
    yield
    # Shutdown: cleanup


app = FastAPI(
    title="Clinical Trial Matching",
    version=settings.pipeline_version,
    lifespan=lifespan,
)

app.include_router(trials.router, prefix="/api/v1")


@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy", "pipeline_version": settings.pipeline_version}
