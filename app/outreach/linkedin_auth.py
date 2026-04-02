"""
linkedin_auth.py — LinkedIn login and session persistence.

Saves browser storage state (cookies + localStorage) to
data/linkedin_session.json after a successful login so subsequent
runs skip the login page entirely.
"""
from app.automation.playwright_engine import (
    launch_browser_with_session, close_browser, random_delay, human_type,
)
from app.utils.constants import LINKEDIN_SESSION_FILE
from app.config import settings
from app.utils.logger import logger


async def ensure_linkedin_session(page) -> bool:
    """Return True if the browser is already authenticated on LinkedIn."""
    try:
        await page.goto("https://www.linkedin.com/feed/", timeout=30000)
        await random_delay(2.0, 3.0)
        nav = await page.query_selector("nav.global-nav")
        if nav:
            logger.info("LinkedIn session active — no login needed")
            return True
        return False
    except Exception as e:
        logger.warning(f"Could not verify LinkedIn session: {e}")
        return False


async def linkedin_login(page, context) -> bool:
    """
    Full email/password login. Saves storage state on success.
    Pauses for manual CAPTCHA completion if a checkpoint is detected.
    """
    email = settings.linkedin_email
    password = settings.linkedin_password
    if not email or not password:
        logger.error("linkedin_email and linkedin_password must be set in .env")
        return False
    try:
        await page.goto("https://www.linkedin.com/login", timeout=30000)
        await random_delay(1.5, 3.0)
        await human_type(page, 'input[name="session_key"]', email)
        await random_delay(0.5, 1.2)
        await human_type(page, 'input[name="session_password"]', password)
        await random_delay(0.8, 1.5)
        submit_btn = await page.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
        await random_delay(3.0, 5.0)
        # Handle checkpoint / CAPTCHA
        if "checkpoint" in page.url or "challenge" in page.url:
            logger.warning(
                "LinkedIn checkpoint detected — complete it in the browser then press Enter"
            )
            input("  Press Enter after completing the checkpoint...")
            await random_delay(2.0, 3.0)
        nav = await page.query_selector("nav.global-nav")
        if not nav:
            logger.error("LinkedIn login failed — check credentials")
            return False
        await context.storage_state(path=str(LINKEDIN_SESSION_FILE))
        logger.info(f"LinkedIn session saved to {LINKEDIN_SESSION_FILE}")
        return True
    except Exception as e:
        logger.error(f"LinkedIn login error: {e}")
        return False


async def get_authenticated_linkedin_page():
    """
    Launch browser with saved session; re-login if session is expired/missing.
    Returns (playwright, browser, context, page) or raises RuntimeError.
    """
    playwright, browser, context, page = await launch_browser_with_session(
        session_path=LINKEDIN_SESSION_FILE,
        headless=False,
    )
    logged_in = await ensure_linkedin_session(page)
    if not logged_in:
        logger.info("Session expired or missing — logging in...")
        success = await linkedin_login(page, context)
        if not success:
            await close_browser(playwright, browser)
            raise RuntimeError("Could not authenticate with LinkedIn")
    return playwright, browser, context, page
