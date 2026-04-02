import asyncio
import random
from playwright.async_api import async_playwright, Page, Browser
from app.utils.logger import logger


async def human_type(page: Page, selector: str, text: str):
    """
    Types text character-by-character with random delays to simulate human input.
    Bots type at a perfectly uniform speed — randomizing delays defeats detection.
    """
    await page.click(selector)
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.04, 0.14))


async def random_delay(min_s: float = 1.5, max_s: float = 4.0):
    """Random sleep between actions to avoid bot detection."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def launch_browser(headless: bool = False):
    """
    Launch a Playwright Chromium browser with stealth settings.
    headless=False so you can watch and approve before submission.
    """
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    # Remove the navigator.webdriver flag that sites use to detect bots
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = await context.new_page()
    return playwright, browser, context, page


async def launch_browser_with_session(session_path, headless: bool = False):
    """
    Launch browser loading stored cookies/localStorage from session_path if it exists.
    Returns same (playwright, browser, context, page) tuple as launch_browser().
    """
    from pathlib import Path
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )
    storage_state = str(session_path) if Path(session_path).exists() else None
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        storage_state=storage_state,
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = await context.new_page()
    return playwright, browser, context, page


async def close_browser(playwright, browser: Browser):
    await browser.close()
    await playwright.stop()
