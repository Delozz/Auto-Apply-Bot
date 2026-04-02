import asyncio
import json
from celery import shared_task
from app.workflows.apply_pipeline import CANDIDATE
from app.outreach.recruiter_finder import search_recruiters
from app.outreach.linkedin_message_gen import batch_generate_messages
from app.outreach.connection_handler import send_batch_outreach
from app.utils.constants import APPLIED_JOBS_FILE
from app.utils.logger import logger


def _load_outreach_targets() -> list[dict]:
    """Read company+role pairs from applied_jobs.json."""
    if not APPLIED_JOBS_FILE.exists():
        logger.warning("applied_jobs.json not found — no outreach targets")
        return []
    try:
        with APPLIED_JOBS_FILE.open() as f:
            data = json.load(f)
        return [{"company": e["company"], "role": e["role"]} for e in data]
    except Exception as e:
        logger.warning(f"Could not read applied_jobs.json for outreach: {e}")
        return []


@shared_task(name="app.workflows.outreach_pipeline.run_outreach_pipeline")
def run_outreach_pipeline():
    asyncio.run(_outreach_pipeline_async())


async def _outreach_pipeline_async():
    logger.info("📨 Starting outreach pipeline")
    all_outreach = []

    targets = _load_outreach_targets()
    logger.info(f"Loaded {len(targets)} outreach target(s) from applied_jobs.json")
    for target in targets:
        company = target["company"]
        role = target["role"]
        logger.info(f"\nSearching recruiters: {company}")

        recruiters = await search_recruiters(company, max_results=2)
        if not recruiters:
            logger.warning(f"No recruiters found for {company}")
            continue

        for r in recruiters:
            r["role"] = role

        with_messages = batch_generate_messages(CANDIDATE, recruiters)
        all_outreach.extend(with_messages)
        logger.info(f"  Generated {len(with_messages)} messages for {company}")

    logger.info(f"\nTotal outreach queued: {len(all_outreach)}")
    results = await send_batch_outreach(all_outreach)
    logger.info(f"✅ Outreach pipeline complete: {results}")
