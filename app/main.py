import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes import trials
from app.config import settings
from app.db.session import engine, get_db
from app.extraction.pipeline import ExtractionPipeline

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.extraction_pipeline = None
    app.state.spacy_model = "unavailable"
    app.state.startup_database = "unavailable"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        app.state.startup_database = "connected"
    except Exception:
        logger.exception("Database unavailable during startup")
    try:
        pipeline = ExtractionPipeline()
        app.state.extraction_pipeline = pipeline
        app.state.spacy_model = pipeline.loaded_model_name
    except Exception:
        logger.exception("Extraction pipeline unavailable during startup")
    yield


app = FastAPI(
    title="Clinical Trial Matching",
    version=settings.pipeline_version,
    lifespan=lifespan,
)

app.include_router(trials.router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled request error for %s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "internal_server_error"},
    )


@app.get("/api/v1/health")
def health_check(request: Request, db: Session = Depends(get_db)):
    checks = {"pipeline_version": settings.pipeline_version}

    # DB check
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception:
        checks["database"] = "unavailable"

    checks["spacy_model"] = getattr(request.app.state, "spacy_model", "unavailable")

    all_healthy = checks["database"] == "connected" and checks["spacy_model"] != "unavailable"
    checks["status"] = "healthy" if all_healthy else "degraded"
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content=checks,
    )
