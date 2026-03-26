from app.automation.playwright_engine import launch_browser, close_browser, random_delay
from app.utils.logger import logger
from app.utils.constants import MAX_OUTREACH_PER_COMPANY


async def send_connection_request(profile_url: str, message: str) -> bool:
    """
    Navigates to a LinkedIn profile and sends a connection request with a note.
    ⚠️ Stays well under 20 requests/day to avoid LinkedIn rate limits.
    """
    playwright, browser, context, page = await launch_browser(headless=False)

    try:
        await page.goto(profile_url, timeout=30000)
        await random_delay(2.0, 4.0)

        connect_btn = await page.query_selector('button:has-text("Connect")')
        if not connect_btn:
            logger.warning(f"No Connect button found at: {profile_url}")
            return False

        await connect_btn.click()
        await random_delay(1.0, 2.0)

        add_note_btn = await page.query_selector('button:has-text("Add a note")')
        if add_note_btn:
            await add_note_btn.click()
            await random_delay(0.5, 1.0)
            note_textarea = await page.query_selector('textarea[name="message"]')
            if note_textarea:
                await note_textarea.fill(message)
                await random_delay(1.0, 2.0)

        send_btn = await page.query_selector('button:has-text("Send")')
        if send_btn:
            # ⚠️ Human approval before every send
            decision = input(f"\n  Send connection request? [y/n]: ").strip().lower()
            if decision == "y":
                await send_btn.click()
                logger.info("✅ Connection request sent")
                return True
            else:
                logger.info("⏭️  Skipped")
                return False

    except Exception as e:
        logger.error(f"Failed to send connection to {profile_url}: {e}")
        return False
    finally:
        await close_browser(playwright, browser)


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

        await random_delay(30.0, 90.0)  # long delay between requests

    logger.info(f"Outreach complete: {results}")
    return results
