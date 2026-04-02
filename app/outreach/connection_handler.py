from playwright.async_api import Page
from app.automation.playwright_engine import launch_browser, close_browser, random_delay
from app.utils.logger import logger
from app.utils.constants import MAX_OUTREACH_PER_COMPANY


async def _send_connection_on_page(
    page: Page,
    profile_url: str,
    message: str,
    recruiter_name: str,
) -> bool:
    """
    Core connection-request logic operating on an already-authenticated page.
    Does NOT open or close a browser — caller owns the browser lifecycle.

    Handles:
    - "Connect" hidden behind a "More" dropdown
    - "Follow"-only profiles (creator accounts / connection requests disabled)
    - Modal dismissal on user decline
    - Missing "Add a note" button (sends without note, logs warning)
    """
    try:
        await page.goto(profile_url, timeout=30000)
        await random_delay(2.0, 4.0)

        # Attempt 1: top-level Connect button
        connect_btn = await page.query_selector('button:has-text("Connect")')

        # Attempt 2: Connect hidden behind "More" overflow menu
        if not connect_btn:
            more_btn = await page.query_selector('button:has-text("More")')
            if more_btn:
                await more_btn.click()
                await random_delay(0.5, 1.0)
                connect_btn = await page.query_selector(
                    '.artdeco-dropdown__content button:has-text("Connect")'
                )

        if not connect_btn:
            logger.warning(
                f"No Connect button found at {profile_url} — "
                "profile may be Follow-only or already connected"
            )
            return False

        await connect_btn.click()
        await random_delay(1.0, 2.0)

        # Add personalised note
        add_note_btn = await page.query_selector('button:has-text("Add a note")')
        if add_note_btn:
            await add_note_btn.click()
            await random_delay(0.5, 1.0)
            note_textarea = await page.query_selector('textarea[name="message"]')
            if note_textarea:
                await note_textarea.fill(message)
                await random_delay(1.0, 2.0)
        else:
            logger.warning("'Add a note' button not found — will send without note")

        send_btn = await page.query_selector('button:has-text("Send")')
        if not send_btn:
            logger.warning("Send button not found after clicking Connect")
            return False

        # Human approval gate — show full context before sending
        print(f"\n{'='*60}")
        print(f"  Recruiter : {recruiter_name}")
        print(f"  Profile   : {profile_url}")
        print(f"  Message   : {message}")
        print(f"{'='*60}")
        decision = input("  Send connection request? [y/n]: ").strip().lower()

        if decision == "y":
            await send_btn.click()
            await random_delay(1.0, 2.0)
            logger.info(f"Connection request sent to {recruiter_name}")
            return True
        else:
            # Dismiss modal to avoid leaving stale UI
            cancel_btn = await page.query_selector(
                'button:has-text("Discard"), button[aria-label="Dismiss"]'
            )
            if cancel_btn:
                await cancel_btn.click()
            logger.info(f"Skipped outreach to {recruiter_name}")
            return False

    except Exception as e:
        logger.error(f"Failed to send connection to {profile_url}: {e}")
        return False


async def send_connection_request(profile_url: str, message: str) -> bool:
    """
    Standalone entry point (backward compatible).
    Opens its own browser. For post-application outreach use
    _send_connection_on_page() with an existing authenticated page.
    """
    playwright, browser, context, page = await launch_browser(headless=False)
    try:
        success = await _send_connection_on_page(
            page, profile_url, message, recruiter_name="recruiter"
        )
    except Exception as e:
        logger.error(f"send_connection_request failed: {e}")
        success = False
    finally:
        await close_browser(playwright, browser)
    return success


async def send_batch_outreach(outreach_list: list[dict]) -> dict:
    """
    Send connection requests with per-company limits enforced automatically.
    """
    company_counts: dict[str, int] = {}
    results = {"sent": 0, "skipped": 0, "failed": 0}

    for item in outreach_list:
        company = item["company"]
        company_counts[company] = company_counts.get(company, 0)

        if company_counts[company] >= MAX_OUTREACH_PER_COMPANY:
            logger.info(f"Outreach limit reached for {company} — skipping")
            results["skipped"] += 1
            continue

        success = await send_connection_request(item["profile_url"], item["message"])
        company_counts[company] += 1
        results["sent" if success else "failed"] += 1

        await random_delay(30.0, 90.0)

    logger.info(f"Outreach complete: {results}")
    return results
