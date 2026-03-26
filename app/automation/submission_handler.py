from playwright.async_api import Page
from app.utils.logger import logger


async def pause_for_human_review(page: Page, job_company: str, job_role: str) -> bool:
    """
    ⚠️ CRITICAL SAFETY GATE ⚠️
    Pauses and waits for your manual approval before submitting anything.
    The bot will NEVER auto-submit — you always have final say.

    Returns True if approved, False if skipped.
    """
    logger.info("=" * 60)
    logger.info(f"  🔍 REVIEW REQUIRED: {job_role} @ {job_company}")
    logger.info("  Form is filled. Please review in the browser window.")
    logger.info("=" * 60)

    decision = input("\n  Submit? [y=yes / n=skip / q=quit bot]: ").strip().lower()

    if decision == "y":
        logger.info("✅ Approved — submitting")
        return True
    elif decision == "q":
        logger.info("🛑 Bot stopped by user")
        raise KeyboardInterrupt
    else:
        logger.info("⏭️  Skipped")
        return False


async def click_submit(page: Page) -> bool:
    """
    Click the final submit button.
    Tries multiple common selectors across different ATS platforms.
    """
    submit_selectors = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Submit")',
        'button:has-text("Submit Application")',
        'button:has-text("Apply")',
        '[data-testid="submit-button"]',
    ]

    for selector in submit_selectors:
        try:
            btn = await page.query_selector(selector)
            if btn and await btn.is_visible():
                await btn.click()
                logger.info(f"Clicked submit via: {selector}")
                return True
        except Exception:
            continue

    logger.error("❌ Could not find a submit button — manual action needed")
    return False


async def confirm_submission(page: Page) -> bool:
    """Check the page for a success confirmation message after submitting."""
    success_signals = [
        "thank you",
        "application received",
        "successfully submitted",
        "we'll be in touch",
    ]
    try:
        content = (await page.content()).lower()
        for signal in success_signals:
            if signal in content:
                logger.info(f"✅ Submission confirmed — detected: '{signal}'")
                return True
    except Exception as e:
        logger.warning(f"Could not verify submission: {e}")

    logger.warning("⚠️  Could not confirm submission — check the browser manually")
    return False
