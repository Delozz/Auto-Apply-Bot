"""
run_pipeline.py

Automated full pipeline — loops through ALL jobs that meet your resume
threshold, generates a tailored resume + cover letter for each, opens
the application form, autofills it, and pauses for your approval.

Run with:
    PYTHONPATH=. python3 app/workflows/run_pipeline.py

Per-company config lives in COMPANY_CONFIG below — add entries as needed.
Any company not in COMPANY_CONFIG gets generic autofill (basic info, resume,
cover letter, EEO). Company-specific fields (SWE area dropdowns etc.) only
fire when configured.
"""
import asyncio
from app.scraper.greenhouse_scraper import scrape_all_greenhouse
from app.llm.resume_tailor import extract_resume_text
from app.llm.embeddings import filter_jobs_by_score
from app.llm.cover_letter_gen import generate_cover_letter, save_cover_letter
from app.llm.resume_pdf_gen import generate_tailored_pdf
from app.automation.playwright_engine import launch_browser, close_browser, random_delay
from app.automation.form_filler import fill_greenhouse_application
from app.automation.adaptive_filler import adaptive_fill
from app.vision.form_analyzer import analyze_form_with_vision
from app.automation.submission_handler import pause_for_human_review, click_submit, confirm_submission
from app.utils.validators import CandidateProfile, JobPosting
from app.utils.constants import RESUMES_DIR
from app.utils.logger import logger

# ─── Your profile ─────────────────────────────────────────────────────────────
CANDIDATE = CandidateProfile(
    name="Devon Lopez",
    email="devoninternships@gmail.com",
    phone="5127878221",
    education="Texas A&M University - Computer Science",
    skills=["Python", "C++", "SQL", "Data Structures", "Algorithms"],
    interests=["Quantitative Finance", "Distributed Systems"],
    resume_path=str(RESUMES_DIR / "master_resume.pdf"),
    graduation_year="2028",
    linkedin_url="https://www.linkedin.com/in/devon-lopez1",   # add yours
    github_url="https://github.com/Delozz",     # add yours
    website_url="",
)

# ─── Per-company config ───────────────────────────────────────────────────────
# Add an entry for each company with company-specific dropdown values.
# Any company NOT listed here gets generic autofill — which still handles
# 80% of fields (basic info, resume, cover letter, EEO, enrollment etc.)
#
# Keys must match the company name in GREENHOUSE_BOARDS exactly.
COMPANY_CONFIG = {
    "Cloudflare": {
        "how_did_you_hear": "Linkedin",
        "city": "Cedar Park, Texas, United States",
        "swe_area_1": "Backend/Systems",
        "swe_area_2": "Full-stack",
        "why_interested": "",  # leave blank to use cover letter text
    },
    "Robinhood": {
        "how_did_you_hear": "LinkedIn",
        "city": "Cedar Park, Texas, United States",
    },
    "Stripe": {
        "how_did_you_hear": "LinkedIn",
        "city": "Cedar Park, Texas, United States",
    },
    "Databricks": {
        "how_did_you_hear": "LinkedIn",
        "city": "Cedar Park, Texas, United States",
    },
    "Coinbase": {
        "how_did_you_hear": "LinkedIn",
        "city": "Cedar Park, Texas, United States",
    },
    # Add more companies here as you run the dump_options script on their forms
}

# ─── Pipeline settings ────────────────────────────────────────────────────────
MAX_APPLICATIONS_PER_RUN = 10   # safety cap — won't apply to more than this
SKIP_ALREADY_APPLIED = True     # set to False to reprocess previously seen jobs


async def process_job(job: JobPosting, resume_text: str) -> str:
    """
    Full pipeline for a single job:
    1. Generate tailored resume PDF
    2. Generate tailored cover letter
    3. Open form + autofill
    4. Human approval gate
    Returns: "submitted" | "skipped" | "failed"
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {job.role} @ {job.company}")
    logger.info(f"Match score: {job.match_score:.3f}")
    logger.info(f"URL: {job.application_url}")
    logger.info(f"{'='*60}")

    try:
        # Step 1: Generate tailored resume
        logger.info("Generating tailored resume PDF...")
        tailored_resume_path = generate_tailored_pdf(
            master_resume_path=CANDIDATE.resume_path,
            job=job,
        )
        logger.info(f"Tailored resume: {tailored_resume_path}")

        # Update candidate to use tailored resume for this application
        candidate_for_job = CANDIDATE.model_copy(update={
            "resume_path": tailored_resume_path
        })

        # Step 2: Generate cover letter
        logger.info("Generating cover letter...")
        cover_letter = generate_cover_letter(candidate_for_job, job)
        cover_letter_path = save_cover_letter(cover_letter, job.company, job.role)

        print(f"\n--- COVER LETTER ---\n{cover_letter}\n---\n")

        # Step 3: Get company-specific config
        config = COMPANY_CONFIG.get(job.company, {})
        why = config.get("why_interested", "") or cover_letter
        city = config.get("city", "Cedar Park, Texas, United States")
        how_heard = config.get("how_did_you_hear", "LinkedIn")
        swe1 = config.get("swe_area_1", "")
        swe2 = config.get("swe_area_2", "")

        input(f"\n  Press Enter to open {job.company} application form...")

        # Step 4: Open form and autofill
        playwright, browser, context, page = await launch_browser(headless=False)

        try:
            await page.goto(job.application_url, timeout=30000)
            await random_delay(2.0, 3.0)

            # Vision analysis — discovers all fields + probes dropdown options
            logger.info("Running vision form analysis...")
            try:
                manifest = await analyze_form_with_vision(page, job.application_url)
            except Exception as e:
                logger.warning(f"Vision analysis failed, proceeding without manifest: {e}")
                manifest = None

            # Try adaptive filler first — works on any ATS without config
            logger.info("Running adaptive form fill...")
            await adaptive_fill(
                page=page,
                candidate=candidate_for_job,
                job=job,
                resume_path=candidate_for_job.resume_path,
                cover_letter=cover_letter,
                cover_letter_path=cover_letter_path,
                why_interested=why,
                manifest=manifest,
            )

            # Then run Greenhouse-specific filler as a second pass to catch
            # React Select dropdowns and fields the adaptive filler may have missed
            if job.source == "greenhouse" or "greenhouse.io" in job.application_url:
                logger.info("Running Greenhouse-specific pass for React Select dropdowns...")
                await fill_greenhouse_application(
                    page=page,
                    candidate=candidate_for_job,
                    cover_letter_text=cover_letter,
                    cover_letter_path=cover_letter_path,
                    city=city,
                    why_interested=why,
                    how_did_you_hear=how_heard,
                    swe_area_1=swe1,
                    swe_area_2=swe2,
                )

            logger.info("Autofill complete — review the form before submitting")

            # Step 5: Human approval gate
            approved = await pause_for_human_review(page, job.company, job.role)

            if approved:
                submitted = await click_submit(page)
                if submitted:
                    confirmed = await confirm_submission(page)
                    status = "submitted" if confirmed else "submit_attempted"
                else:
                    status = "submit_failed"
            else:
                status = "skipped"

        except KeyboardInterrupt:
            logger.info("Stopped by user")
            await close_browser(playwright, browser)
            raise
        finally:
            try:
                input("\n  Press Enter to close browser and move to next job...")
            except Exception:
                pass
            await close_browser(playwright, browser)

        logger.info(f"Result: {status} — {job.company}")
        return status

    except KeyboardInterrupt:
        raise
    except Exception as e:
        logger.error(f"Failed on {job.company}: {e}")
        return "failed"


async def run_full_pipeline():
    """
    Main entry point — scrapes all jobs, scores them, and processes
    each qualifying job one at a time with human approval between each.
    """
    logger.info("🚀 Starting automated apply pipeline")

    # Step 1: Scrape
    logger.info("Scraping jobs from all Greenhouse boards...")
    jobs = await scrape_all_greenhouse()
    logger.info(f"Total scraped: {len(jobs)}")

    # Step 2: Score against resume
    logger.info("Scoring jobs against your resume...")
    resume_text = extract_resume_text(CANDIDATE.resume_path)
    qualified = filter_jobs_by_score(resume_text, [j.model_dump() for j in jobs])
    logger.info(f"Qualified (above threshold): {len(qualified)}")

    if not qualified:
        logger.warning("No jobs passed the threshold — lower SIMILARITY_THRESHOLD in constants.py")
        return

    # Cap applications per run
    to_process = qualified[:MAX_APPLICATIONS_PER_RUN]
    logger.info(f"Will process up to {len(to_process)} jobs this run")

    # Show the list before starting
    print("\n📋 Jobs queued for this run:")
    for i, j in enumerate(to_process):
        print(f"  {i+1}. [{j['match_score']:.3f}] {j['company']} — {j['role']}")

    input(f"\n  Press Enter to begin (or Ctrl+C to cancel)...")

    # Step 3: Process each job
    results = {"submitted": 0, "skipped": 0, "failed": 0, "stopped": 0}

    for job_data in to_process:
        job = JobPosting(**job_data)
        try:
            status = await process_job(job, resume_text)
            results[status] = results.get(status, 0) + 1
        except KeyboardInterrupt:
            logger.info("\n🛑 Pipeline stopped by user")
            results["stopped"] += 1
            break

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("✅ Pipeline complete")
    logger.info(f"   Submitted: {results.get('submitted', 0)}")
    logger.info(f"   Skipped:   {results.get('skipped', 0)}")
    logger.info(f"   Failed:    {results.get('failed', 0)}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(run_full_pipeline())