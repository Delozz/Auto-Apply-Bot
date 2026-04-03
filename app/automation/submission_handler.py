import asyncio
import base64
import concurrent.futures
import json
import sys
import threading

import openai
from playwright.async_api import Page

from app.config import settings
from app.utils.logger import logger


async def verify_form_filled(page: Page) -> tuple[bool, list[str]]:
    """
    Takes a full-page screenshot and asks the vision LLM to identify
    any visibly empty required fields.

    Returns (all_filled: bool, issues: list[str]).
    Non-blocking — returns (True, []) on any error.
    """
    try:
        screenshot_bytes = await page.screenshot(full_page=True)
        b64 = base64.b64encode(screenshot_bytes).decode()

        client = openai.AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        response = await client.chat.completions.create(
            model=settings.vision_model,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a job application form. Examine every visible field. "
                            "List ONLY the required fields (marked with * or 'required') "
                            "that appear empty or unfilled. "
                            "Reply with a JSON object: "
                            '{"all_filled": true/false, "missing": ["Field Name", ...]} '
                            "If all required fields are filled, return all_filled=true and missing=[]."
                        ),
                    },
                ],
            }],
            max_tokens=256,
        )
        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown code fences if present
        if "```" in raw:
            raw = raw.split("```")[1].strip().lstrip("json").strip()
        result = json.loads(raw)
        all_filled = result.get("all_filled", True)
        missing = result.get("missing", [])
        return all_filled, missing
    except Exception as e:
        logger.warning(f"Form verification failed: {e}")
        return True, []


async def pause_for_human_review(
    page: Page,
    job_company: str,
    job_role: str,
    timeout: int = 15,
) -> bool:
    """
    Timed review gate. Shows a countdown and auto-submits on timeout.
    User can type 's' to submit now, 'k' to skip, 'e' to end the bot.

    Returns True to submit, False to skip. Raises KeyboardInterrupt to end.
    """
    logger.info("=" * 60)
    logger.info(f"  REVIEW: {job_role} @ {job_company}")
    logger.info("  [s] submit now  |  [k] skip  |  [e] end bot")
    logger.info("=" * 60)

    loop = asyncio.get_event_loop()
    fut: asyncio.Future[str] = loop.create_future()

    def _reader() -> None:
        try:
            line = sys.stdin.readline().strip().lower()
        except Exception:
            line = ""
        if not fut.done():
            loop.call_soon_threadsafe(fut.set_result, line)

    threading.Thread(target=_reader, daemon=True).start()

    for remaining in range(timeout, 0, -1):
        if fut.done():
            break
        print(f"\r  Auto-submitting in {remaining:2d}s... [s/k/e]: ", end="", flush=True)
        await asyncio.sleep(1)

    print()  # newline after countdown

    if not fut.done():
        fut.set_result("")  # timeout → auto-submit
        logger.info("⏰ Timeout — auto-submitting")

    decision = await fut

    if decision.startswith("e"):
        logger.info("🛑 Bot stopped by user")
        raise KeyboardInterrupt
    elif decision.startswith("k"):
        logger.info("⏭️  Skipped")
        return False
    else:
        # 's', '', or any other key → submit
        if decision:
            logger.info("✅ Submitting (manual)")
        return True


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


async def handle_verification_code(page: Page, sender_hint: str = "") -> bool:
    """
    After clicking submit, check if a verification code input has appeared.
    Gmail polling starts immediately in a background thread so email and DOM
    detection race in parallel — whichever is slower doesn't block the other.

    Returns True if the code was entered and the confirm button clicked.
    """
    from app.utils.email_reader import fetch_verification_code

    code_input_selectors = [
        'input[autocomplete="one-time-code"]',
        'input[type="text"][maxlength="8"]',
        'input[type="text"][maxlength="6"]',
        'input[name*="code"]',
        'input[name*="verification"]',
        'input[name*="token"]',
        'input[id*="code"]',
        'input[id*="verification"]',
        'input[placeholder*="code"]',
        'input[placeholder*="verification"]',
        # Broad fallback: any visible text input on the verification page
        'input[type="text"]',
        'input:not([type="hidden"]):not([type="submit"]):not([type="checkbox"]):not([type="radio"])',
    ]

    # Start Gmail polling immediately in a background thread so it runs
    # while we wait for the code input field to appear on the page.
    loop = asyncio.get_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    email_future = loop.run_in_executor(
        executor,
        fetch_verification_code,
        sender_hint,
    )

    # Wait up to 30 seconds for a code input field to appear on the page.
    code_input = None
    for _ in range(30):
        for selector in code_input_selectors:
            try:
                el = await page.query_selector(selector)
                if el and await el.is_visible():
                    code_input = (el, selector)
                    break
            except Exception:
                pass
        if code_input:
            break
        await asyncio.sleep(1)

    if not code_input:
        logger.warning("No verification code input detected after 30s — skipping email poll")
        email_future.cancel()
        executor.shutdown(wait=False)
        return False

    el, selector = code_input
    logger.info("Verification code field detected — waiting for code from Gmail...")

    # Now wait for the Gmail poll to return (it may already be done).
    try:
        code = await asyncio.wait_for(asyncio.shield(email_future), timeout=90)
    except asyncio.TimeoutError:
        code = None
    finally:
        executor.shutdown(wait=False)

    if not code:
        logger.warning("Could not retrieve verification code — manual entry required")
        manual = input("  Enter verification code manually (or press Enter to skip): ").strip()
        if not manual:
            return False
        code = manual

    logger.info(f"Entering verification code into '{selector}': {code}")

    # Check for individual character boxes (maxlength="1" inputs — common in ATS).
    # Collect ALL visible single-char inputs on the page; if their count matches
    # the code length, fill each box individually instead of using a single field.
    char_boxes = []
    try:
        all_single = await page.query_selector_all('input[maxlength="1"]')
        char_boxes = [b for b in all_single if await b.is_visible()]
    except Exception:
        pass

    if len(char_boxes) == len(code):
        logger.info(f"Detected {len(char_boxes)} individual character boxes — filling each")
        for box, char in zip(char_boxes, code):
            await box.click()
            await box.fill(char)
            await page.wait_for_timeout(50)
    else:
        # Single text field — try programmatic fill then keystroke fallback
        try:
            await el.click()
            await page.fill(selector, "")
            await page.fill(selector, code)
        except Exception:
            await el.click(click_count=3)
            await page.keyboard.type(code)

    await page.wait_for_timeout(500)

    confirm_selectors = [
        'button[type="submit"]',
        'button:has-text("Verify")',
        'button:has-text("Confirm")',
        'button:has-text("Submit")',
        'button:has-text("Continue")',
        'input[type="submit"]',
    ]
    for sel in confirm_selectors:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                logger.info(f"Verification submitted via: {sel}")
                await page.wait_for_timeout(2000)
                return True
        except Exception:
            continue

    logger.warning("Could not find confirm button after entering code")
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
