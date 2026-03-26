from playwright.async_api import Page
from app.automation.playwright_engine import human_type, random_delay
from app.utils.validators import CandidateProfile
from app.utils.logger import logger


async def fill_basic_info(page: Page, candidate: CandidateProfile):
    """
    Fills standard fields found on most ATS applications.
    Selectors are generalized — tweak per ATS if needed
    (Greenhouse, Lever, and Workday each differ slightly).
    """
    field_map = {
        'input[name*="first"]': candidate.name.split()[0],
        'input[name*="last"]': candidate.name.split()[-1],
        'input[type="email"]': candidate.email,
        'input[name*="phone"]': candidate.phone,
        'input[name*="school"], input[name*="university"]': candidate.education,
    }

    for selector, value in field_map.items():
        try:
            element = await page.query_selector(selector)
            if element:
                await human_type(page, selector, value)
                await random_delay(0.5, 1.2)
                logger.debug(f"Filled: {selector}")
        except Exception as e:
            logger.warning(f"Could not fill field '{selector}': {e}")


async def fill_text_area(page: Page, selector: str, text: str):
    """Fill a textarea — used for cover letters and essay questions."""
    try:
        await page.click(selector)
        await random_delay(0.3, 0.8)
        await page.fill(selector, text)
        logger.debug(f"Filled textarea: {selector}")
    except Exception as e:
        logger.warning(f"Could not fill textarea '{selector}': {e}")


async def upload_resume(page: Page, resume_path: str):
    """Handle file input for resume upload."""
    try:
        file_input = await page.query_selector('input[type="file"]')
        if file_input:
            await file_input.set_input_files(resume_path)
            await random_delay(1.0, 2.5)
            logger.info(f"Resume uploaded: {resume_path}")
        else:
            logger.warning("No file input found on page")
    except Exception as e:
        logger.error(f"Resume upload failed: {e}")


async def select_dropdown(page: Page, selector: str, value: str):
    """Select a dropdown option by visible text."""
    try:
        await page.select_option(selector, label=value)
        await random_delay(0.4, 1.0)
        logger.debug(f"Selected dropdown '{selector}': {value}")
    except Exception as e:
        logger.warning(f"Dropdown select failed '{selector}': {e}")


async def check_checkbox(page: Page, selector: str):
    """Check a checkbox if not already checked."""
    try:
        checkbox = await page.query_selector(selector)
        if checkbox and not await checkbox.is_checked():
            await checkbox.check()
            await random_delay(0.3, 0.7)
    except Exception as e:
        logger.warning(f"Checkbox check failed '{selector}': {e}")
