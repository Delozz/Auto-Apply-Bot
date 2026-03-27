from playwright.async_api import Page
from app.automation.playwright_engine import human_type, random_delay
from app.utils.validators import CandidateProfile
from app.utils.logger import logger


# ─── EEO answers — update to match your preferences ─────────────────────────
EEO_ANSWERS = {
    "gender":        "Male",
    "hispanic":      "No, not Hispanic or Latino",
    "veteran":       "I am not a protected veteran",
    "disability":    "No, I don't have a disability",
    "sponsorship":   "No",
    "enrolled":      "Yes",
    "degree":        "Bachelor's Degree",
}


# ─── Helper: try multiple selectors, stop at first match ─────────────────────

async def _try_fill(page: Page, selectors: list[str], value: str, label: str) -> bool:
    """
    Try multiple CSS selectors for a single field — stops at first visible match.
    Uses page.fill() for speed — no character-by-character typing needed for most fields.
    """
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                await page.fill(selector, "")
                await page.fill(selector, value)
                await random_delay(0.15, 0.35)
                logger.debug(f"Filled {label} via: {selector}")
                return True
        except Exception:
            continue
    logger.debug(f"Field not found: {label}")
    return False


async def _try_select(page: Page, selectors: list[str], value: str, label: str) -> bool:
    """Try multiple selectors for a <select> dropdown."""
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                await page.select_option(selector, label=value)
                await random_delay(0.15, 0.35)
                logger.debug(f"Selected {label}: {value}")
                return True
        except Exception:
            continue
    logger.debug(f"Dropdown not found: {label}")
    return False


async def _try_check(page: Page, selectors: list[str], label: str) -> bool:
    """Try multiple selectors for a checkbox."""
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible() and not await el.is_checked():
                await el.check()
                await random_delay(0.15, 0.3)
                logger.debug(f"Checked: {label}")
                return True
        except Exception:
            continue
    logger.debug(f"Checkbox not found: {label}")
    return False


# ─── Individual field fillers ─────────────────────────────────────────────────

async def fill_basic_info(page: Page, candidate: CandidateProfile):
    """Fill name, email, phone, and optional profile links."""
    first = candidate.name.split()[0]
    last = candidate.name.split()[-1]

    await _try_fill(page, [
        '#first_name', 'input[id="first_name"]',
        'input[name="first_name"]', 'input[name*="first"]',
    ], first, "first name")

    await _try_fill(page, [
        '#last_name', 'input[id="last_name"]',
        'input[name="last_name"]', 'input[name*="last"]',
    ], last, "last name")

    await _try_fill(page, [
        '#email', 'input[id="email"]',
        'input[name="email"]', 'input[type="email"]',
    ], candidate.email, "email")

    await _try_fill(page, [
        '#phone', 'input[id="phone"]',
        'input[name="phone"]', 'input[name*="phone"]',
    ], candidate.phone, "phone")

    if candidate.linkedin_url:
        await _try_fill(page, [
            'input[id*="linkedin"]', 'input[name*="linkedin"]',
        ], candidate.linkedin_url, "linkedin")

    if candidate.github_url:
        await _try_fill(page, [
            'input[id*="github"]', 'input[name*="github"]',
        ], candidate.github_url, "github")

    if candidate.website_url:
        await _try_fill(page, [
            'input[id*="website"]', 'input[name*="website"]',
            'input[id*="portfolio"]', 'input[name*="portfolio"]',
        ], candidate.website_url, "website")


async def fill_location(page: Page, city: str = "College Station, TX"):
    """Fill location/city field."""
    await _try_fill(page, [
        'input[id*="location"]', 'input[name*="location"]',
        'input[id*="city"]', 'input[name*="city"]',
        'input[placeholder*="city"]', 'input[placeholder*="City"]',
    ], city, "location/city")


async def upload_resume(page: Page, resume_path: str):
    """Upload resume PDF — tries resume-specific selectors then falls back to first file input."""
    selectors = [
        'input[type="file"][id*="resume"]',
        'input[type="file"][name*="resume"]',
        'input[type="file"][id*="cv"]',
        'input[type="file"]',
    ]
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                await el.set_input_files(resume_path)
                await random_delay(1.0, 2.0)
                logger.info(f"Resume uploaded via: {selector}")
                return
        except Exception:
            continue
    logger.warning("No file input found for resume")


async def upload_cover_letter_file(page: Page, cover_letter_path: str):
    """Upload cover letter as a file if a second file input exists."""
    selectors = [
        'input[type="file"][id*="cover"]',
        'input[type="file"][name*="cover"]',
    ]
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                await el.set_input_files(cover_letter_path)
                await random_delay(0.8, 1.5)
                logger.info(f"Cover letter file uploaded via: {selector}")
                return
        except Exception:
            continue
    logger.debug("No cover letter file input found")


async def fill_cover_letter_text(page: Page, text: str):
    """Paste cover letter text into a textarea if present."""
    selectors = [
        'textarea[id*="cover"]', 'textarea[name*="cover"]',
        '#cover_letter', 'textarea[placeholder*="cover"]',
    ]
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                await page.fill(selector, text)
                await random_delay(0.2, 0.4)
                logger.debug(f"Cover letter text filled via: {selector}")
                return
        except Exception:
            continue
    logger.debug("No cover letter textarea found")


async def fill_text_area(page: Page, selector: str, text: str):
    """Fill a specific textarea by selector — used for essay questions."""
    try:
        el = await page.query_selector(selector)
        if el and await el.is_visible():
            await page.fill(selector, text)
            await random_delay(0.2, 0.4)
            logger.debug(f"Filled textarea: {selector}")
    except Exception as e:
        logger.warning(f"Could not fill textarea '{selector}': {e}")


async def fill_school_typeahead(page: Page, school_name: str = "Texas A&M University- College Station"):
    """
    Handle school field — tries typeahead first, falls back to plain fill.
    """
    selectors = [
        'input[name*="school"]', 'input[name*="university"]',
        'input[id*="school"]', 'input[placeholder*="school"]',
        'input[placeholder*="university"]', 'input[placeholder*="institution"]',
    ]
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                await page.click(selector)
                await page.type(selector, "Texas A&M", delay=60)
                await page.wait_for_timeout(1000)
                option = await page.query_selector(f'text="{school_name}"')
                if option:
                    await option.click()
                    logger.debug(f"Typeahead school selected: {school_name}")
                else:
                    await page.fill(selector, school_name)
                    logger.debug(f"Plain fill school: {school_name}")
                return
        except Exception:
            continue
    logger.debug("No school field found")


async def select_dropdown(page: Page, selector: str, value: str):
    """Select a dropdown by explicit selector and label value."""
    try:
        await page.select_option(selector, label=value)
        await random_delay(0.15, 0.35)
    except Exception as e:
        logger.warning(f"Dropdown select failed '{selector}': {e}")


async def check_checkbox(page: Page, selector: str):
    """Check a checkbox if not already checked."""
    try:
        el = await page.query_selector(selector)
        if el and await el.is_visible() and not await el.is_checked():
            await el.check()
            await random_delay(0.15, 0.3)
    except Exception as e:
        logger.warning(f"Checkbox failed '{selector}': {e}")


async def select_radio(page: Page, name: str, value: str):
    """Select a radio button by name and value."""
    try:
        radio = await page.query_selector(f'input[type="radio"][name*="{name}"][value*="{value}"]')
        if radio and await radio.is_visible():
            await radio.check()
            await random_delay(0.15, 0.3)
    except Exception as e:
        logger.warning(f"Radio select failed '{name}': {e}")


# ─── Greenhouse-specific dropdowns ───────────────────────────────────────────

async def fill_greenhouse_dropdowns(page: Page, candidate: CandidateProfile):
    """
    Fills all the standard Greenhouse dropdown questions:
    sponsorship, enrollment, graduation date, degree type, start date, EEO fields.
    """

    # Immigration sponsorship → No
    await _try_select(page, [
        'select[id*="sponsor"]', 'select[name*="sponsor"]',
        'select[id*="visa"]', 'select[name*="visa"]',
        'select[id*="immigration"]',
    ], "No", "sponsorship")

    # Currently enrolled → Yes
    await _try_select(page, [
        'select[id*="enroll"]', 'select[name*="enroll"]',
        'select[id*="student"]',
    ], "Yes", "enrolled")

    # Graduation date — select closest option to May 2028
    grad_options = ["May 2028", "Spring 2028", "2028"]
    for opt in grad_options:
        result = await _try_select(page, [
            'select[id*="grad"]', 'select[name*="grad"]',
            'select[id*="graduation"]',
        ], opt, "graduation date")
        if result:
            break

    # Degree type → Bachelor's
    await _try_select(page, [
        'select[id*="degree"]', 'select[name*="degree"]',
        'select[id*="education"]',
    ], "Bachelor's Degree", "degree type")

    # Full-time start date — select a reasonable option
    start_options = ["Summer 2028", "Fall 2028", "2028", "June 2028"]
    for opt in start_options:
        result = await _try_select(page, [
            'select[id*="start"]', 'select[name*="start"]',
            'select[id*="available"]',
        ], opt, "start date")
        if result:
            break

    # EEO: Gender
    await _try_select(page, [
        'select[id*="gender"]', 'select[name*="gender"]',
    ], EEO_ANSWERS["gender"], "gender")

    # EEO: Hispanic/Latino
    await _try_select(page, [
        'select[id*="hispanic"]', 'select[name*="hispanic"]',
        'select[id*="latino"]',
    ], EEO_ANSWERS["hispanic"], "hispanic")

    # EEO: Veteran status
    await _try_select(page, [
        'select[id*="veteran"]', 'select[name*="veteran"]',
    ], EEO_ANSWERS["veteran"], "veteran")

    # EEO: Disability
    await _try_select(page, [
        'select[id*="disab"]', 'select[name*="disab"]',
    ], EEO_ANSWERS["disability"], "disability")


async def accept_privacy_policy(page: Page):
    """Check the candidate privacy policy acknowledgement checkbox."""
    await _try_check(page, [
        'input[type="checkbox"][id*="privacy"]',
        'input[type="checkbox"][name*="privacy"]',
        'input[type="checkbox"][id*="policy"]',
        'input[type="checkbox"][id*="acknowledge"]',
        'input[type="checkbox"][name*="acknowledge"]',
    ], "privacy policy")


# ─── Master Greenhouse filler ─────────────────────────────────────────────────

async def fill_greenhouse_application(
    page: Page,
    candidate: CandidateProfile,
    cover_letter_text: str = "",
    cover_letter_path: str = "",
    city: str = "College Station, TX",
    why_interested: str = "",
    how_did_you_hear: str = "LinkedIn",
    swe_area_1: str = "",
    swe_area_2: str = "",
):
    """
    Master function — fills a complete Greenhouse application.
    Handles every field on the Cloudflare SWE intern form and most other Greenhouse forms.

    Fields covered:
    - Basic info: first/last name, email, phone, linkedin, github
    - Location/city
    - Resume file upload
    - Cover letter (file or text)
    - School typeahead
    - All dropdowns: sponsorship, enrollment, graduation, degree, start date
    - Privacy policy checkbox
    - EEO/demographic fields
    - Essay: why interested (passed in as argument)
    - How did you hear about this job
    - SWE area of interest dropdowns (Cloudflare-specific)
    """
    logger.info("Filling Greenhouse application...")

    # 1. Basic info
    await fill_basic_info(page, candidate)

    # 2. Location
    await fill_location(page, city)

    # 3. Resume upload
    await upload_resume(page, candidate.resume_path)

    # 4. Cover letter
    if cover_letter_path:
        await upload_cover_letter_file(page, cover_letter_path)
    if cover_letter_text:
        await fill_cover_letter_text(page, cover_letter_text)

    # 5. How did you hear
    await _try_select(page, [
        'select[id*="hear"]', 'select[name*="hear"]',
        'select[id*="source"]', 'select[name*="source"]',
    ], how_did_you_hear, "how did you hear")

    # 6. School
    await fill_school_typeahead(page, "Texas A&M University- College Station")

    # 7. All Greenhouse standard dropdowns
    await fill_greenhouse_dropdowns(page, candidate)

    # 8. Privacy policy checkbox
    await accept_privacy_policy(page)

    # 9. SWE area of interest (Cloudflare-specific)
    if swe_area_1:
        await _try_select(page, [
            'select[id*="area_1"]', 'select[id*="interest_1"]',
            'select[name*="area_1"]',
        ], swe_area_1, "SWE area 1")
    if swe_area_2:
        await _try_select(page, [
            'select[id*="area_2"]', 'select[id*="interest_2"]',
            'select[name*="area_2"]',
        ], swe_area_2, "SWE area 2")

    # 10. Why interested essay
    if why_interested:
        essay_selectors = [
            'textarea[id*="why"]', 'textarea[name*="why"]',
            'textarea[id*="interest"]', 'textarea[name*="interest"]',
        ]
        filled = False
        for sel in essay_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await page.fill(sel, why_interested)
                    await random_delay(0.2, 0.4)
                    logger.debug(f"Why interested filled via: {sel}")
                    filled = True
                    break
            except Exception:
                continue
        if not filled:
            logger.warning("Why interested textarea not found — fill manually")

    logger.info("Greenhouse application fill complete ✅")