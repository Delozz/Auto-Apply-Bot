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

        # Primary path: Connect is almost always behind the "More" overflow menu
        # for 3rd+ connections. Try that first, fall back to top-level button.
        connect_btn = None
        # There are two "More" buttons: one in the top-right nav (~y=3) and one
        # in the profile's action bar (~y=400+). Pick the profile one by finding
        # the button whose top edge is more than 100px from the viewport top.
        more_btn = await page.evaluate_handle("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            return btns.find(b =>
                b.innerText.trim().startsWith('More') &&
                b.getBoundingClientRect().top > 100
            ) || null;
        }""")
        # evaluate_handle returns JSHandle; check if it resolved to an element
        more_el = more_btn.as_element()
        if more_el:
            await more_el.scroll_into_view_if_needed()
            await random_delay(0.5, 1.0)
            await more_el.click()
            await random_delay(0.8, 1.5)
            # Wait for the dropdown to appear then find Connect inside it
            try:
                await page.wait_for_selector('[role="menu"]', timeout=5000)
            except Exception:
                pass
            # LinkedIn renders "Connect" in the More dropdown as an <a role="menuitem">
            # with aria-label="Invite [Name] to connect" — not a <button>.
            connect_btn = await page.query_selector(
                '[role="menuitem"][aria-label*="connect" i], '
                '[role="menuitem"]:has-text("Connect"), '
                'a[href*="custom-invite"]'
            )

        # Fallback: top-level Connect button (1st/2nd degree or different layout)
        if not connect_btn:
            connect_btn = await page.query_selector('button:has-text("Connect")')

        if not connect_btn:
            logger.warning(
                f"No Connect button found at {profile_url} — "
                "profile may be Follow-only or already connected"
            )
            return False

        await connect_btn.click()
        await random_delay(1.5, 2.5)

        # Click "Add a note" to reveal the message textarea
        add_note_btn = await page.query_selector('button[aria-label="Add a note"]')
        if not add_note_btn:
            logger.warning("'Add a note' button not found — skipping outreach")
            await page.keyboard.press("Escape")
            return False

        await add_note_btn.click()
        await random_delay(0.8, 1.5)

        # Fill the textarea — it has no name/id so just select the first visible textarea
        note_textarea = await page.query_selector('textarea')
        if not note_textarea:
            logger.warning("Note textarea not found — skipping outreach")
            await page.keyboard.press("Escape")
            return False

        await note_textarea.fill(message)
        await random_delay(0.5, 1.0)

        # Human approval gate
        print(f"\n{'='*60}")
        print(f"  Recruiter : {recruiter_name}")
        print(f"  Profile   : {profile_url}")
        print(f"  Message   : {message}")
        print(f"{'='*60}")
        decision = input("  Send connection request? [y/n]: ").strip().lower()

        if decision == "y":
            send_btn = await page.query_selector('button[aria-label="Send invitation"]')
            if not send_btn:
                logger.warning("Send button not found")
                return False
            await send_btn.click()
            await random_delay(1.0, 2.0)
            logger.info(f"Connection request sent to {recruiter_name}")
            return True
        else:
            cancel_btn = await page.query_selector('button[aria-label="Cancel adding a note"]')
            if cancel_btn:
                await cancel_btn.click()
            else:
                await page.keyboard.press("Escape")
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
