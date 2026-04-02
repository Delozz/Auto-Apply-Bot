"""
application_tracker.py

Persists submitted application URLs to data/applied_jobs.json so the
pipeline skips already-applied jobs on repeated runs.
"""
import json
from datetime import datetime
from pathlib import Path

from app.utils.constants import APPLIED_JOBS_FILE
from app.utils.logger import logger


def load_applied_urls() -> set[str]:
    """Return set of application URLs already submitted."""
    if not APPLIED_JOBS_FILE.exists():
        return set()
    try:
        with APPLIED_JOBS_FILE.open() as f:
            data = json.load(f)
        return {entry["url"] for entry in data}
    except Exception as e:
        logger.warning(f"Could not read applied_jobs.json: {e}")
        return set()


def mark_as_applied(url: str, company: str, role: str) -> None:
    """Append a successfully submitted job to the tracker file."""
    try:
        existing: list[dict] = []
        if APPLIED_JOBS_FILE.exists():
            with APPLIED_JOBS_FILE.open() as f:
                existing = json.load(f)
        existing.append({
            "url": url,
            "company": company,
            "role": role,
            "submitted_at": datetime.utcnow().isoformat(),
        })
        with APPLIED_JOBS_FILE.open("w") as f:
            json.dump(existing, f, indent=2)
        logger.info(f"Tracked: {company} — {role}")
    except Exception as e:
        logger.warning(f"Could not update applied_jobs.json: {e}")
