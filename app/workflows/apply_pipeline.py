import asyncio
from celery import shared_task
from app.utils.validators import CandidateProfile, JobPosting
from app.utils.constants import RESUMES_DIR
from app.utils.logger import logger

from app.scraper.linkedin_scraper import scrape_linkedin_jobs
from app.scraper.greenhouse_scraper import scrape_all_greenhouse
from app.llm.embeddings import filter_jobs_by_score
from app.llm.cover_letter_gen import generate_cover_letter, save_cover_letter
from app.llm.resume_tailor import extract_resume_text, tailor_resume_bullets
from app.automation.playwright_engine import launch_browser, close_browser
from app.automation.form_filler import fill_basic_info, upload_resume
from app.automation.submission_handler import pause_for_human_review, click_submit, confirm_submission

# ─── YOUR DETAILS — update anything that's wrong ─────────────────────────────
CANDIDATE = CandidateProfile(
    name="Devon Lopez",
    email="devoninternships@gmail.com",
    phone="512-787-8221",
    education="Texas A&M University - Computer Science",
    skills=["Python", "C++", "SQL", "Data Structures", "Algorithms"],
    interests=["Quantitative Finance", "Distributed Systems"],
    resume_path=str(RESUMES_DIR / "master_resume.pdf"),
)


@shared_task(name="app.workflows.apply_pipeline.run_apply_pipeline")
def run_apply_pipeline():
    """Entry point for Celery — runs the async pipeline in a sync context."""
    asyncio.run(_apply_pipeline_async())


async def _apply_pipeline_async():
    logger.info("🚀 Starting apply pipeline")

    # ── Step 1: Scrape ───────────────────────────────────────────────────────
    logger.info("Step 1/5 — Scraping jobs")
    linkedin_jobs = await scrape_linkedin_jobs("Software Engineer Intern", "United States")
    greenhouse_jobs = await scrape_all_greenhouse()
    all_jobs = linkedin_jobs + greenhouse_jobs
    logger.info(f"Total scraped: {len(all_jobs)}")

    # ── Step 2: Score & filter by resume similarity ──────────────────────────
    logger.info("Step 2/5 — Scoring jobs against your resume")
    resume_text = extract_resume_text(CANDIDATE.resume_path)
    qualified = filter_jobs_by_score(resume_text, [j.model_dump() for j in all_jobs])
    logger.info(f"Qualified: {len(qualified)}")

    # ── Steps 3–5: Process each qualified job ────────────────────────────────
    for job_data in qualified:
        job = JobPosting(**job_data)
        logger.info(f"\n{'─'*50}\n🏢 {job.role} @ {job.company}\n{'─'*50}")

        try:
            # Step 3: Generate cover letter
            logger.info("Step 3/5 — Generating cover letter")
            cover_letter = generate_cover_letter(CANDIDATE, job)
            cover_letter_path = save_cover_letter(cover_letter, job.company, job.role)

            # Step 4: Resume suggestions
            logger.info("Step 4/5 — Tailoring resume suggestions")
            suggestions = tailor_resume_bullets(resume_text, job)
            logger.info(f"Resume suggestions:\n{suggestions}")

            # Step 5: Fill form + human approval + submit
            logger.info("Step 5/5 — Filling application form")
            playwright, browser, context, page = await launch_browser(headless=False)
            await page.goto(job.application_url, timeout=30000)
            await fill_basic_info(page, CANDIDATE)
            await upload_resume(page, CANDIDATE.resume_path)

            approved = await pause_for_human_review(page, job.company, job.role)

            if approved:
                submitted = await click_submit(page)
                confirmed = await confirm_submission(page) if submitted else False
                status = "submitted" if confirmed else "submit_attempted"
            else:
                status = "skipped"

            await close_browser(playwright, browser)
            logger.info(f"Result: {status} — {job.company}")

        except KeyboardInterrupt:
            logger.info("Pipeline stopped by user")
            break
        except Exception as e:
            logger.error(f"Failed on {job.company}: {e}")
            continue

    logger.info("✅ Apply pipeline complete")
