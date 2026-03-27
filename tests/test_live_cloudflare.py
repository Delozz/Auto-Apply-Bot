"""
Live application: Cloudflare Software Engineer Intern (Summer 2026) - Austin, TX
URL: https://boards.greenhouse.io/cloudflare/jobs/7206269
"""
import asyncio
from app.scraper.greenhouse_scraper import scrape_greenhouse_board
from app.llm.cover_letter_gen import generate_cover_letter, save_cover_letter
from app.llm.resume_tailor import extract_resume_text, tailor_resume_bullets
from app.automation.playwright_engine import launch_browser, close_browser, random_delay
from app.automation.form_filler import fill_greenhouse_application
from app.automation.submission_handler import pause_for_human_review, click_submit, confirm_submission
from app.utils.validators import CandidateProfile, JobPosting
from app.utils.constants import RESUMES_DIR
from app.utils.logger import logger

# ─── Target job ───────────────────────────────────────────────────────────────
TARGET_URL = "https://boards.greenhouse.io/cloudflare/jobs/7206269?gh_jid=7206269"
TARGET_ROLE = "Software Engineer Intern (Summer 2026) - Austin, TX"
TARGET_COMPANY = "Cloudflare"

# ─── Your profile ─────────────────────────────────────────────────────────────
CANDIDATE = CandidateProfile(
    name="Devon Lopez",
    email="devoninternships@gmail.com",
    phone="5127878221",           # no dashes — Cloudflare's phone field prefers digits only
    education="Texas A&M University - Computer Science",
    skills=["Python", "C++", "SQL", "Data Structures", "Algorithms"],
    interests=["Quantitative Finance", "Distributed Systems"],
    resume_path=str(RESUMES_DIR / "master_resume.pdf"),
    graduation_year="2028",
    linkedin_url="https://www.linkedin.com/in/devon-lopez1/",              # add yours: https://linkedin.com/in/yourprofile
    github_url="https://github.com/Delozz",                # add yours: https://github.com/yourhandle
    website_url="",
)

# ─── Cloudflare-specific answers ─────────────────────────────────────────────
# Fill these in before running — they are REQUIRED fields on the form

HOW_DID_YOU_HEAR = "Linkedin"   # exact text from form   # options: LinkedIn, Indeed, Referral, Company Website, etc.

# Your 1st choice area of interest — open the form and check what options exist
# Common options: Backend, Frontend, Full Stack, Infrastructure, Security, ML/AI
SWE_AREA_1 = "Backend/Systems"   # options: "Backend/Systems", "Full-stack", "Frontend"
SWE_AREA_2 = "Full-stack"   # optional 2nd choice

# Why are you interested in Cloudflare? (required, ~2-3 sentences min)
# The bot will use the generated cover letter text if you leave this blank,
# but you should write something specific to this question
WHY_INTERESTED = "I am excited about the opportunity to work at Cloudflare because of its commitment to building a better Internet. I admire Cloudflare's innovative approach to security and performance, and I believe my skills in software engineering align well with the company's mission."


async def run():
    # ── Step 1: Fetch job details ────────────────────────────────────────────
    logger.info("Step 1/4 — Fetching Cloudflare job details")
    jobs = await scrape_greenhouse_board(TARGET_COMPANY, "cloudflare")
    job = next((j for j in jobs if "7206269" in j.application_url), None)
    if not job:
        logger.error("Could not find job — check the URL token")
        return
    logger.info(f"Found: {job.role} | {job.location}")

    # ── Step 2: Generate cover letter ───────────────────────────────────────
    logger.info("Step 2/4 — Generating tailored cover letter")
    cover_letter = generate_cover_letter(CANDIDATE, job)
    cover_letter_path = save_cover_letter(cover_letter, TARGET_COMPANY, TARGET_ROLE)
    logger.info("\n" + "─" * 60)
    logger.info("GENERATED COVER LETTER:")
    logger.info("─" * 60)
    print(cover_letter)
    logger.info("─" * 60)

    # ── Step 3: Resume suggestions ───────────────────────────────────────────
    logger.info("Step 3/4 — Resume tailoring suggestions")
    resume_text = extract_resume_text(CANDIDATE.resume_path)
    suggestions = tailor_resume_bullets(resume_text, job)
    print("\nRESUME SUGGESTIONS:")
    print(suggestions)

    # Use cover letter text as why_interested fallback if not set
    why = WHY_INTERESTED if WHY_INTERESTED else cover_letter

    # Pause to review before opening browser
    print("\n" + "=" * 60)
    print("=" * 60)
    input("\n  Press Enter to open the application form...")

    # ── Step 4: Open and fill the form ───────────────────────────────────────
    logger.info("Step 4/4 — Opening Cloudflare application form")
    playwright, browser, context, page = await launch_browser(headless=False)

    try:
        await page.goto(TARGET_URL, timeout=30000)
        await random_delay(2.0, 3.0)
        logger.info("Form loaded — starting autofill")

        await fill_greenhouse_application(
            page=page,
            candidate=CANDIDATE,
            cover_letter_text=cover_letter,
            cover_letter_path=cover_letter_path,
            city="Cedar Park, Texas, United States",
            why_interested=why,
            how_did_you_hear=HOW_DID_YOU_HEAR,
            swe_area_1=SWE_AREA_1,
            swe_area_2=SWE_AREA_2,
        )

        logger.info("✅ Autofill complete — REVIEW EVERYTHING in the browser")
        logger.info("   Manually fill any fields the bot missed before submitting")

        # ⚠️ HUMAN APPROVAL GATE
        approved = await pause_for_human_review(page, TARGET_COMPANY, TARGET_ROLE)

        if approved:
            submitted = await click_submit(page)
            if submitted:
                confirmed = await confirm_submission(page)
                if confirmed:
                    logger.info("🎉 Application submitted to Cloudflare!")
                else:
                    logger.warning("⚠️  Could not auto-confirm — check the browser")
        else:
            logger.info("⏭️  Skipped — no application submitted")

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error during form fill: {e}")
        raise
    finally:
        try:
            input("\n  Press Enter to close the browser...")
        except Exception:
            pass
        await close_browser(playwright, browser)


if __name__ == "__main__":
    asyncio.run(run())