from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes import trials
from app.config import settings
from app.db.session import get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Clinical Trial Matching",
    version=settings.pipeline_version,
    lifespan=lifespan,
)

app.include_router(trials.router, prefix="/api/v1")


@app.get("/api/v1/health")
def health_check(db: Session = Depends(get_db)):
    checks = {"pipeline_version": settings.pipeline_version}

    # DB check
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception:
        checks["database"] = "unavailable"

    # spaCy model check
    try:
        import spacy
        spacy.load(settings.spacy_model)
        checks["spacy_model"] = settings.spacy_model
    except Exception:
        try:
            import spacy
            spacy.load("en_core_web_sm")
            checks["spacy_model"] = "en_core_web_sm (fallback)"
        except Exception:
            checks["spacy_model"] = "unavailable"

    all_healthy = checks["database"] == "connected" and checks["spacy_model"] != "unavailable"
    checks["status"] = "healthy" if all_healthy else "degraded"
    return checks
