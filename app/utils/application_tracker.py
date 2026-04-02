"""
application_tracker.py

Persists submitted application URLs to data/applied_jobs.json so the
pipeline skips already-applied jobs on repeated runs.
"""
import json
from datetime import datetime
from pathlib import Path

from app.utils.constants import APPLIED_JOBS_FILE, OUTREACH_LOG_FILE
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


def has_outreach_been_sent(company: str) -> bool:
    """Return True if any outreach has already been logged for this company."""
    if not OUTREACH_LOG_FILE.exists():
        return False
    try:
        with OUTREACH_LOG_FILE.open() as f:
            data = json.load(f)
        return any(entry["company"].lower() == company.lower() for entry in data)
    except Exception as e:
        logger.warning(f"Could not read outreach_log.json: {e}")
        return False


def mark_outreach_sent(company: str, recruiter_name: str, profile_url: str) -> None:
    """Append a sent-outreach record to outreach_log.json."""
    try:
        existing: list[dict] = []
        if OUTREACH_LOG_FILE.exists():
            with OUTREACH_LOG_FILE.open() as f:
                existing = json.load(f)
        existing.append({
            "company": company,
            "recruiter_name": recruiter_name,
            "profile_url": profile_url,
            "sent_at": datetime.utcnow().isoformat(),
        })
        with OUTREACH_LOG_FILE.open("w") as f:
            json.dump(existing, f, indent=2)
        logger.info(f"Outreach logged: {recruiter_name} @ {company}")
    except Exception as e:
        logger.warning(f"Could not update outreach_log.json: {e}")
