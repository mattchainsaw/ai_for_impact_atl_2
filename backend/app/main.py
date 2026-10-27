"""FastAPI entrypoint for RescueGuard backend (Phase 0 scaffold).

Per Part 2 line 1168: 'FastAPI app with GET /api/health only'.
"""

from fastapi import FastAPI

from backend.app.config import get_settings
from schemas.api import HealthResponse

app = FastAPI(
    title="RescueGuard Backend API",
    description=(
        "Resilient Food Equity & Surplus Broker (Atlanta) — "
        "FastAPI Supervisor with Vertex AI ADK Guide Agent."
    ),
    version="0.1.0",
)


@app.get("/api/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return runtime health status and non-secret active configuration."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        project=settings.google_cloud_project,
        dataset=settings.bq_dataset_starter,
        model_id=settings.model_id,
    )
