"""
Test script: runs Playwright against the local dummy form.
Watch the browser window fill itself out, then approve or skip at the prompt.
"""
import asyncio
from pathlib import Path
from app.automation.playwright_engine import launch_browser, close_browser, random_delay
from app.automation.form_filler import fill_greenhouse_application, fill_text_area
from app.automation.submission_handler import pause_for_human_review, click_submit, confirm_submission
from app.utils.validators import CandidateProfile
from app.utils.constants import RESUMES_DIR
from app.utils.logger import logger

# ─── Local test form ──────────────────────────────────────────────────────────
FORM_PATH = Path(__file__).parent / "test_form.html"
FORM_URL = f"file://{FORM_PATH.resolve()}"

# ─── Your candidate profile ───────────────────────────────────────────────────
CANDIDATE = CandidateProfile(
    name="Devon Lopez",
    email="devoninternships@gmail.com",
    phone="512-787-8221",
    education="Texas A&M University - Computer Science",
    skills=["Python", "C++", "SQL", "Data Structures", "Algorithms"],
    interests=["Quantitative Finance", "Distributed Systems"],
    resume_path=str(RESUMES_DIR / "master_resume.pdf"),
    graduation_year="2028",
    linkedin_url="",
    github_url="",
    website_url="",
)

COVER_LETTER = """As a computer science student with a strong foundation in Python and C++,
I am excited to apply for this role. My experience with data structures and algorithms,
combined with my interest in quantitative finance, makes me a strong fit for this position."""

WHY_US = """I am drawn to this firm's rigorous approach to research and technology-driven
solutions. The opportunity to work on real systems alongside experienced engineers aligns
directly with my goal of building a career at the intersection of software and finance."""


async def test_form_fill():
    logger.info("🎭 Launching Playwright test against dummy form")
    playwright, browser, context, page = await launch_browser(headless=False)

    try:
        await page.goto(FORM_URL)
        await random_delay(1.0, 2.0)
        logger.info("Form loaded — starting autofill")

        # Run the master filler — handles all standard ATS field types
        await fill_greenhouse_application(page, CANDIDATE, COVER_LETTER)

        # Fill any extra essay/open-ended fields specific to this form
        # On real Greenhouse apps these will vary by company — fill them manually
        # at the approval gate if the bot doesn't catch them
        await fill_text_area(page, 'textarea[name="why_us"]', WHY_US)
        await random_delay(0.3, 0.6)

        logger.info("✅ All fields attempted — awaiting your review")

        # Human approval gate — YOU decide whether to submit
        approved = await pause_for_human_review(page, "Test Company", "Test Role")

        if approved:
            submitted = await click_submit(page)
            if submitted:
                confirmed = await confirm_submission(page)
                if confirmed:
                    logger.info("🎉 Test submission confirmed successfully!")
                else:
                    logger.warning("Could not confirm — check browser")
        else:
            logger.info("Skipped — test complete")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
    finally:
        await random_delay(2.0, 3.0)
        await close_browser(playwright, browser)


if __name__ == "__main__":
    asyncio.run(test_form_fill())