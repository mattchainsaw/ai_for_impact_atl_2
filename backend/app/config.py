"""Runtime configuration module for RescueGuard.

Reads GOOGLE_CLOUD_PROJECT from environment variables (.env) or gcloud config
at runtime. Never hardcodes any GCP project ID.
"""

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import shutil
import subprocess
from dotenv import load_dotenv


_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env", override=False)

# Phase 0 Named Constants (Hard Gate 1 & Architectural Locks)
CRATES_PER_PALLET: int = int(os.getenv("CRATES_PER_PALLET", "20"))
CHECKER_MAX_ATTEMPTS: int = int(os.getenv("CHECKER_MAX_ATTEMPTS", "3"))
HOLD_MINUTES: int = int(os.getenv("HOLD_MINUTES", "10"))
OPENFDA_MAX_CALLS_PER_RUN: int = int(os.getenv("OPENFDA_MAX_CALLS_PER_RUN", "240"))



def _resolve_gcloud_project() -> str:
    """Resolve active GCP project from environment or gcloud config."""
    env_proj = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    if env_proj and env_proj != "your-gcp-project-id":
        return env_proj

    gcloud_candidates = [
        shutil.which("gcloud"),
        str(Path.home() / "google-cloud-sdk" / "bin" / "gcloud"),
        "/google/google-cloud-sdk/bin/gcloud",
    ]
    for candidate in gcloud_candidates:
        if candidate and Path(candidate).exists():
            try:
                out = subprocess.check_output(
                    [candidate, "config", "get-value", "project"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=5,
                ).strip()
                if out and out != "(unset)":
                    return out
            except Exception:
                continue

    return env_proj or "unconfigured-project"


@dataclass(frozen=True)
class Settings:
    """Frozen runtime settings loaded from .env / environment / gcloud config."""

    google_cloud_project: str
    google_cloud_location: str
    cloud_run_region: str
    google_genai_use_vertexai: bool
    bq_dataset_starter: str
    bq_dataset_app: str
    model_id: str
    checker_max_attempts: int
    hold_minutes: int
    openfda_max_calls_per_run: int
    crates_per_pallet: int
    firestore_location: str
    mcp_bigquery_endpoint: str
    default_tenant_id: str
    service_name: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance populated from environment."""
    return Settings(
        google_cloud_project=_resolve_gcloud_project(),
        google_cloud_location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1").strip(),
        cloud_run_region=os.getenv("CLOUD_RUN_REGION", "us-east1").strip(),
        google_genai_use_vertexai=os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE").upper() == "TRUE",
        bq_dataset_starter=os.getenv("BQ_DATASET_STARTER", "a4i_food").strip(),
        bq_dataset_app=os.getenv("BQ_DATASET_APP", "rescueguard_app").strip(),
        model_id=os.getenv("MODEL_ID", "gemini-2.5-flash").strip(),
        checker_max_attempts=int(os.getenv("CHECKER_MAX_ATTEMPTS", "3")),
        hold_minutes=int(os.getenv("HOLD_MINUTES", "10")),
        openfda_max_calls_per_run=int(os.getenv("OPENFDA_MAX_CALLS_PER_RUN", "240")),
        crates_per_pallet=int(os.getenv("CRATES_PER_PALLET", "20")),
        firestore_location=os.getenv("FIRESTORE_LOCATION", "nam5").strip(),
        mcp_bigquery_endpoint=os.getenv(
            "MCP_BIGQUERY_ENDPOINT", "https://bigquery.googleapis.com/mcp"
        ).strip(),
        default_tenant_id=os.getenv("DEFAULT_TENANT_ID", "atlanta-metro").strip(),
        service_name=os.getenv("SERVICE_NAME", "rescueguard-backend").strip(),
    )

