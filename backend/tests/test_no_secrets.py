"""Phase 0 secret and hardcoded-project-ID scanner test."""

from pathlib import Path
import re
import subprocess

from backend.app.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]

_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
]


def test_dotenv_gitignored_and_example_clean() -> None:
    """Verify .env is git-ignored and .env.example uses placeholders only."""
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "GOOGLE_CLOUD_PROJECT=your-gcp-project-id" in env_example

    res = subprocess.run(
        ["git", "check-ignore", ".env"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, ".env must be ignored by git"


def test_no_hardcoded_project_id_or_secrets_in_tracked_files() -> None:
    """Ensure active GCP project ID and secrets never appear in code, schemas, or docs outside docs/handoffs/."""
    active_project = get_settings().google_cloud_project
    assert active_project and active_project != "your-gcp-project-id"

    skip_dirs = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
    allowed_project_id_paths = {
        REPO_ROOT / ".env",
    }

    violations = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path in allowed_project_id_paths:
            continue
        # Handoff build records under docs/handoffs/ are explicitly permitted to record the literal project ID
        rel_parts = path.relative_to(REPO_ROOT).parts
        is_handoff = len(rel_parts) >= 2 and rel_parts[0] == "docs" and rel_parts[1] == "handoffs"

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                violations.append(f"Secret pattern matched in {path.relative_to(REPO_ROOT)}")

        if not is_handoff and active_project in text:
            violations.append(
                f"Literal project ID '{active_project}' found in {path.relative_to(REPO_ROOT)}"
            )

    assert not violations, "Secret / hardcoded project ID violations:\n" + "\n".join(violations)

