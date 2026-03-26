import asyncio
from celery import shared_task
from app.workflows.apply_pipeline import CANDIDATE
from app.outreach.recruiter_finder import search_recruiters
from app.outreach.linkedin_message_gen import batch_generate_messages
from app.outreach.connection_handler import send_batch_outreach
from app.utils.logger import logger

# ─── Companies to reach out to — add after you've applied ────────────────────
OUTREACH_TARGETS = [
    {"company": "Jane Street", "role": "Software Engineer Intern"},
    {"company": "Citadel", "role": "Quantitative Research Intern"},
    {"company": "Two Sigma", "role": "Software Engineer Intern"},
    {"company": "Hudson River Trading", "role": "Software Engineer Intern"},
]


@shared_task(name="app.workflows.outreach_pipeline.run_outreach_pipeline")
def run_outreach_pipeline():
    asyncio.run(_outreach_pipeline_async())


async def _outreach_pipeline_async():
    logger.info("📨 Starting outreach pipeline")
    all_outreach = []

    for target in OUTREACH_TARGETS:
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
