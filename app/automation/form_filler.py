from playwright.async_api import Page
from app.automation.playwright_engine import human_type, random_delay
from app.utils.validators import CandidateProfile
from app.utils.logger import logger


# ─── EEO answers ─────────────────────────────────────────────────────────────
EEO_ANSWERS = {
    "gender":     "Male",
    "hispanic":   "Yes",
    "race":       "White",
    "veteran":    "I am not a protected veteran",
    "disability": "No, I do not have a disability and have not had one in the past",
}


# ─── React Select helper (used by Cloudflare + many modern Greenhouse forms) ──

async def select_react_dropdown(page: Page, label_text: str, option_text: str) -> bool:
    """
    Handles React Select dropdowns — the custom component Cloudflare and many
    modern Greenhouse forms use instead of native <select> elements.

    Strategy:
    1. Find the dropdown container whose label matches label_text
    2. Click the control to open the dropdown
    3. Type to filter options (faster than scrolling)
    4. Click the matching option

    Args:
        label_text:  Partial text of the label above the dropdown (e.g. "immigration")
        option_text: Exact text of the option to select (e.g. "No")
    """
    try:
        # Find the label that contains our text, then get its parent .select container
        label = await page.query_selector(f'.select__label:has-text("{label_text}")')
        if not label:
            # Try broader search
            label = await page.query_selector(f'label:has-text("{label_text}")')
        if not label:
            logger.debug(f"React dropdown label not found: '{label_text}'")
            return False

        # Get the parent select container
        container = await label.evaluate_handle('el => el.closest(".select") || el.closest("[class*=\'select-shell\']") || el.parentElement.parentElement')

        # Click the control inside the container to open dropdown
        control = await page.query_selector(f'.select__label:has-text("{label_text}") ~ div .select__control--outside-label, .select__label:has-text("{label_text}") ~ .select-shell .select__control')
        if not control:
            # Fallback: find the combobox input near this label and click its parent
            inputs = await page.query_selector_all('input[role="combobox"].select__input')
            # Find the one closest to our label by position
            label_box = await label.bounding_box()
            closest_input = None
            closest_dist = float('inf')
            for inp in inputs:
                box = await inp.bounding_box()
                if box and label_box:
                    dist = abs(box['y'] - label_box['y'])
                    if dist < closest_dist and dist < 200:
                        closest_dist = dist
                        closest_input = inp
            if closest_input:
                # Click the parent control div
                await closest_input.click()
            else:
                logger.debug(f"Could not find control for: '{label_text}'")
                return False
        else:
            await control.click()

        is_location = "location" in label_text.lower() or "city" in label_text.lower()

        await random_delay(0.2, 0.35)

        if is_location:
            try:
                # Find the combobox input closest to this label by y-position
                inputs = await page.query_selector_all('input[role="combobox"].select__input')
                label_box = await label.bounding_box()
                closest_input = None
                closest_dist = float('inf')
                for inp in inputs:
                    box = await inp.bounding_box()
                    if box and label_box:
                        dist = abs(box['y'] - label_box['y'])
                        if dist < closest_dist and dist < 200:
                            closest_dist = dist
                            closest_input = inp

                if not closest_input:
                    logger.warning("Could not find location input element")
                    return False

                # Click the control div (not the input) to activate React Select
                control = await closest_input.evaluate_handle(
                    'el => el.closest(".select__control") || el.parentElement.parentElement'
                )
                await page.evaluate('el => el.click()', control)
                await random_delay(0.3, 0.5)

                # Now type into the input using fill() + dispatchEvent to trigger React
                await closest_input.fill(option_text)
                await closest_input.dispatch_event('input')
                await closest_input.dispatch_event('change')
                await random_delay(1.5, 2.0)

                # Wait for the options menu to appear (rendered in a portal)
                try:
                    await page.wait_for_selector('.select__menu', timeout=3000)
                except Exception:
                    logger.warning(f"Location menu did not appear for: '{option_text}'")
                    await page.keyboard.press('Escape')
                    return False

                # Click the first option in the menu
                first_option = await page.query_selector('.select__menu .select__option')
                if not first_option:
                    first_option = await page.query_selector('.select__option')

                if first_option and await first_option.is_visible():
                    suggestion_text = (await first_option.inner_text()).strip()
                    await first_option.click()
                    await random_delay(0.2, 0.4)
                    logger.debug(f"Location selected: '{suggestion_text}'")
                    return True
                else:
                    await page.keyboard.press('Escape')
                    logger.warning(f"No location options visible for: '{option_text}'")
                    return False

            except Exception as e:
                logger.warning(f"Location fill failed: {e}")
                try:
                    await page.keyboard.press('Escape')
                except Exception:
                    pass
                return False
        else:
            # Standard dropdown: type to filter then click exact match
            await page.keyboard.type(option_text[:8], delay=30)
            await random_delay(0.2, 0.35)

        # For non-location dropdowns: match by exact option text
        option = await page.query_selector(f'.select__option:has-text("{option_text}")')
        if not option:
            option = await page.query_selector(f'[class*="option"]:has-text("{option_text}")')
        if option and await option.is_visible():
            await option.click()
            await random_delay(0.1, 0.2)
            logger.debug(f"React Select: '{label_text}' → '{option_text}'")
            return True
        else:
            await page.keyboard.press('Escape')
            logger.warning(f"Option not found: '{option_text}' in '{label_text}' dropdown")
            return False

    except Exception as e:
        logger.warning(f"React Select failed for '{label_text}': {e}")
        try:
            await page.keyboard.press('Escape')
        except Exception:
            pass
        return False


# ─── Standard HTML helper functions ──────────────────────────────────────────

async def _try_fill(page: Page, selectors: list[str], value: str, label: str) -> bool:
    """Try multiple selectors for a text input — stops at first visible match."""
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                await page.fill(selector, "")
                await page.fill(selector, value)
                await random_delay(0.05, 0.15)
                logger.debug(f"Filled {label} via: {selector}")
                return True
        except Exception:
            continue
    logger.debug(f"Field not found: {label}")
    return False


async def _try_check(page: Page, selectors: list[str], label: str) -> bool:
    """Try multiple selectors for a checkbox."""
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible() and not await el.is_checked():
                await el.check()
                await random_delay(0.05, 0.1)
                logger.debug(f"Checked: {label}")
                return True
        except Exception:
            continue
    logger.debug(f"Checkbox not found: {label}")
    return False


# ─── Field-specific fillers ───────────────────────────────────────────────────

async def _fill_by_label(page: Page, label_text: str, value: str) -> bool:
    """
    Find a text input by its nearby label text and fill it.
    Handles cases where inputs don't have useful id/name attributes
    but their label text is identifiable — common on Cloudflare's Greenhouse form.
    """
    try:
        label = await page.query_selector(f'label:has-text("{label_text}")')
        if not label:
            logger.debug(f'Label not found: "{label_text}"')
            return False
        for_attr = await label.get_attribute("for")
        if for_attr:
            el = await page.query_selector(f'#{for_attr}')
            if el and await el.is_visible():
                await page.fill(f'#{for_attr}', value)
                await random_delay(0.05, 0.1)
                logger.debug(f'Filled by label "{label_text}" via #{for_attr}')
                return True
        # Fallback: find next sibling input
        sibling = await label.evaluate_handle('el => el.nextElementSibling')
        tag = await page.evaluate('el => el ? el.tagName : ""', sibling)
        if tag in ("INPUT", "TEXTAREA"):
            await page.evaluate('(el, v) => el.value = v', sibling, value)
            await page.evaluate('el => el.dispatchEvent(new Event("input", {bubbles: true}))', sibling)
            await random_delay(0.05, 0.1)
            logger.debug(f'Filled by label "{label_text}" via sibling')
            return True
    except Exception as e:
        logger.debug(f'_fill_by_label failed for "{label_text}": {e}')
    return False


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
        filled = await _try_fill(page, [
            'input[id*="linkedin"]', 'input[name*="linkedin"]',
            'input[placeholder*="linkedin"]', 'input[placeholder*="LinkedIn"]',
        ], candidate.linkedin_url, "linkedin")
        if not filled:
            # Cloudflare uses label-adjacent inputs — find by label text
            await _fill_by_label(page, "Linkedin Profile", candidate.linkedin_url)

    if candidate.github_url:
        filled = await _try_fill(page, [
            'input[id*="github"]', 'input[name*="github"]',
            'input[placeholder*="github"]', 'input[placeholder*="GitHub"]',
        ], candidate.github_url, "github")
        if not filled:
            await _fill_by_label(page, "Github Profile", candidate.github_url)

    if candidate.website_url:
        await _try_fill(page, [
            'input[id*="website"]', 'input[name*="website"]',
            'input[id*="portfolio"]',
        ], candidate.website_url, "website")


async def upload_resume(page: Page, resume_path: str):
    """Upload resume PDF."""
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
                logger.info(f"Cover letter uploaded via: {selector}")
                return
        except Exception:
            continue
    logger.debug("No cover letter file input found")


async def fill_cover_letter_text(page: Page, text: str):
    """Paste cover letter text into textarea if present."""
    selectors = [
        'textarea[id*="cover"]', 'textarea[name*="cover"]',
        '#cover_letter', 'textarea[placeholder*="cover"]',
    ]
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                await page.fill(selector, text)
                await random_delay(0.05, 0.1)
                logger.debug(f"Cover letter text filled via: {selector}")
                return
        except Exception:
            continue
    logger.debug("No cover letter textarea found")


async def fill_text_area(page: Page, selector: str, text: str):
    """Fill a specific textarea by selector."""
    try:
        el = await page.query_selector(selector)
        if el and await el.is_visible():
            await page.fill(selector, text)
            await random_delay(0.2, 0.4)
            logger.debug(f"Filled textarea: {selector}")
    except Exception as e:
        logger.warning(f"Could not fill textarea '{selector}': {e}")


async def fill_essay_by_label(page: Page, label_text: str, answer: str) -> bool:
    """
    Find a textarea or text input by its nearby label text and fill it.
    Used for essay questions like 'Why are you interested in...'
    """
    try:
        # Find label, then get associated input/textarea
        label = await page.query_selector(f'label:has-text("{label_text}")')
        if not label:
            logger.debug(f"Essay label not found: '{label_text}'")
            return False
        for_attr = await label.get_attribute('for')
        if for_attr:
            field = await page.query_selector(f'#{for_attr}')
            if field and await field.is_visible():
                await page.fill(f'#{for_attr}', answer)
                await random_delay(0.05, 0.1)
                logger.debug(f"Essay filled: '{label_text}'")
                return True
    except Exception as e:
        logger.warning(f"Essay fill failed for '{label_text}': {e}")
    return False


async def accept_privacy_policy(page: Page):
    """Check the candidate privacy policy acknowledgement checkbox."""
    await _try_check(page, [
        'input[type="checkbox"][id*="privacy"]',
        'input[type="checkbox"][name*="privacy"]',
        'input[type="checkbox"][id*="policy"]',
        'input[type="checkbox"][id*="acknowledge"]',
        'input[type="checkbox"][name*="acknowledge"]',
        'input[type="checkbox"]',   # fallback — first checkbox on page
    ], "privacy policy")


# ─── Master Greenhouse / Cloudflare filler ────────────────────────────────────

async def fill_greenhouse_application(
    page: Page,
    candidate: CandidateProfile,
    cover_letter_text: str = "",
    cover_letter_path: str = "",
    city: str = "Cedar Park, Texas, United States",
    why_interested: str = "",
    how_did_you_hear: str = "LinkedIn",
    swe_area_1: str = "",
    swe_area_2: str = "",
):
    """
    Master function — fills a complete Greenhouse/Cloudflare application.

    Handles both standard HTML fields AND React Select custom dropdowns.
    All dropdowns are found by their label text so order on the page doesn't matter.

    Fields covered:
      Basic info, phone, email, linkedin, github
      Location/city (React Select typeahead)
      Resume upload
      Cover letter (file + text)
      How did you hear (React Select)
      Immigration sponsorship (React Select)
      Currently enrolled (React Select)
      Graduation date (React Select)
      Degree type (React Select)
      Full-time start date (React Select)
      SWE area of interest 1 & 2 (React Select, Cloudflare-specific)
      Why interested essay
      Privacy policy checkbox
      EEO: gender, hispanic, veteran, disability (React Select)
    """
    logger.info("Filling Greenhouse application...")

    # 1. Basic text fields
    await fill_basic_info(page, candidate)
    await random_delay(0.1, 0.2)

    # 2. Country — React Select (phone country code flag dropdown)
    await select_react_dropdown(page, "Country", "United States +1")

    # 3. Location — React Select typeahead (type city name, select from suggestions)
    await select_react_dropdown(page, "Location", city)

    # 3. Resume upload
    await upload_resume(page, candidate.resume_path)

    # 4. Cover letter
    if cover_letter_path:
        await upload_cover_letter_file(page, cover_letter_path)
    if cover_letter_text:
        await fill_cover_letter_text(page, cover_letter_text)

    # 5. How did you hear — React Select
    await select_react_dropdown(page, "How did you hear", how_did_you_hear)

    # 6. Immigration sponsorship — React Select
    await select_react_dropdown(page, "immigration", "No")

    # 7. Privacy policy checkbox
    await accept_privacy_policy(page)

    # 8. Currently enrolled — React Select
    await select_react_dropdown(page, "currently enrolled", "Yes")

    # 9. Graduation date — React Select
    # Try common date formats — the form uses month/year combos
    if not await select_react_dropdown(page, "when do you expect to graduate", "June 2028"):
        await select_react_dropdown(page, "when do you expect to graduate", "December 2028")

    # 10. Degree type — React Select
    await select_react_dropdown(page, "what degree are you", "Bachelor's")

    # 11. Full-time start date — React Select
    await select_react_dropdown(page, "when would you be available", "Need to return to school and available upon graduation")

    # 12. SWE area of interest (Cloudflare-specific)
    if swe_area_1:
        await select_react_dropdown(page, "1st choice", swe_area_1)
    if swe_area_2:
        await select_react_dropdown(page, "2nd choice", swe_area_2)

    # 13. Why interested essay
    if why_interested:
        filled = await fill_essay_by_label(page, "Why are you interested", why_interested)
        if not filled:
            # Fallback: try textarea selectors
            essay_selectors = [
                'textarea[id*="why"]', 'textarea[name*="why"]',
                'textarea[id*="interest"]',
            ]
            for sel in essay_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        await page.fill(sel, why_interested)
                        await random_delay(0.2, 0.4)
                        logger.debug(f"Why interested filled via: {sel}")
                        break
                except Exception:
                    continue

    # 14. EEO fields — React Select
    await select_react_dropdown(page, "Gender", EEO_ANSWERS["gender"])
    await select_react_dropdown(page, "Hispanic/Latino", EEO_ANSWERS["hispanic"])
    await select_react_dropdown(page, "Race", EEO_ANSWERS["race"])
    await select_react_dropdown(page, "Veteran Status", EEO_ANSWERS["veteran"])
    await select_react_dropdown(page, "Disability Status", EEO_ANSWERS["disability"])

    logger.info("Greenhouse application fill complete ✅")