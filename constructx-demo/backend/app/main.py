"""ConstructX AI demo — FastAPI application entrypoint.

Serves two modules over a shared PostgreSQL database plus a static dashboard:
  * Module 1 — AI-Assisted Subcontractor Management & Performance Monitoring
  * Module 2 — AI-Powered Material Management & Supplier Tracking
"""
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from .database import Base, engine
from .ml import registry
from .routers import material, subcontractor
from .seed import run_seed

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _wait_for_db(retries: int = 20, delay: float = 2.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            print(f"[startup] waiting for database ({attempt}/{retries})...")
            time.sleep(delay)
    raise RuntimeError("Database not reachable after retries")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _wait_for_db()
    Base.metadata.create_all(bind=engine)
    run_seed()
    registry.ensure_trained()  # train/load the RandomForest models
    print("[startup] ConstructX AI demo ready")
    yield


app = FastAPI(
    title="ConstructX AI — Demo API",
    description=(
        "Two AI construction modules on PostgreSQL: Subcontractor Management "
        "and Material Management & Supplier Tracking."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(subcontractor.router)
app.include_router(material.router)


@app.middleware("http")
async def no_cache(request, call_next):
    """Prevent browsers from serving a stale dashboard/JS from cache."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}


@app.get("/api/ml/models", tags=["Machine Learning"])
def ml_models():
    """Metrics + feature importances for every trained model."""
    return registry.model_info()


# Serve the dashboard at "/" and static assets under /static.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
