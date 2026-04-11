import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import InMemoryRateLimiter
from app.api.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.api.routes import patients, trials
from app.api.schemas import HealthResponse
from app.config import settings
from app.db.session import engine, get_db
from app.extraction.pipeline import ExtractionPipeline

logger = logging.getLogger(__name__)
request_logger = logging.getLogger("app.request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.extraction_pipeline = None
    app.state.spacy_model = "unavailable"
    app.state.startup_database = "unavailable"
    app.state.rate_limiter = InMemoryRateLimiter()
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


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    started_at = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id

    log_context = getattr(request.state, "log_context", {})
    route_context = {
        "nct_id": request.path_params.get("nct_id"),
        "trial_id": request.path_params.get("trial_id"),
        "pipeline_run_id": request.path_params.get("run_id"),
    }
    payload = {
        "request_id": request.state.request_id,
        "path": request.url.path,
        "method": request.method,
        "nct_id": log_context.get("nct_id") or route_context["nct_id"],
        "trial_id": log_context.get("trial_id") or route_context["trial_id"],
        "pipeline_run_id": log_context.get("pipeline_run_id") or route_context["pipeline_run_id"],
        "status_code": response.status_code,
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }
    request_logger.info(json.dumps(payload, default=str))
    return response


app.include_router(trials.router, prefix="/api/v1")
app.include_router(patients.router, prefix="/api/v1")


app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    responses={
        500: {
            "description": "Unhandled server error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Internal server error",
                        "code": "internal_server_error",
                        "request_id": "7d3f998a-865f-4adf-a1b9-4cd34a6f70ef",
                    }
                }
            },
        }
    },
)
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
    return JSONResponse(status_code=200 if all_healthy else 503, content=checks)
