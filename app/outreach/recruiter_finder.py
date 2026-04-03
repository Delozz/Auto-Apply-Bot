from playwright.async_api import Page
from app.automation.playwright_engine import launch_browser, close_browser, random_delay
from app.utils.logger import logger


async def _search_recruiters_on_page(page: Page, company: str, max_results: int = 2) -> list[dict]:
    """
    Core recruiter search logic operating on an already-authenticated page.
    Does NOT open or close a browser — caller owns the browser lifecycle.
    """
    search_query = f"{company} recruiter university internship"
    url = f"https://www.linkedin.com/search/results/people/?keywords={search_query.replace(' ', '%20')}"

    recruiters: list[dict] = []
    logger.info(f"Searching recruiters for: {company}")
    await page.goto(url, timeout=30000)
    # Wait for profile links to appear — LinkedIn renders results asynchronously
    try:
        await page.wait_for_selector("a[href*='/in/']", timeout=10000)
    except Exception:
        logger.warning("Timed out waiting for profile links — page may be empty or blocked")
        return recruiters

    # LinkedIn now uses obfuscated CSS class names; find profile links structurally.
    # Each search result <li> contains exactly one /in/ profile link.
    profile_links = await page.query_selector_all("a[href*='/in/']")
    logger.info(f"Found {len(profile_links)} profile links on page")

    seen_urls: set[str] = set()
    recruiting_keywords = ["recruit", "talent", "hiring", "university", "campus", "hr", "people", "acquisition"]

    for link_el in profile_links:
        if len(recruiters) >= max_results:
            break
        try:
            href = (await link_el.get_attribute("href") or "").split("?")[0].rstrip("/")
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)

            # LinkedIn embeds the full card (name + connection degree + title + location)
            # into the link's inner text, e.g.:
            #   "Lily Farriss \n • 3rd+\n\nCampus Recruiter at Point72\n\nNew York..."
            raw = (await link_el.inner_text()).strip()
            if not raw or len(raw) < 2:
                continue

            lines = [l.strip() for l in raw.replace(" • ", "\n").split("\n") if l.strip()]
            # lines[0] = name, lines[1] = connection degree (e.g. "3rd+"), lines[2] = title
            name = lines[0] if lines else "Unknown"
            title = lines[2] if len(lines) > 2 else ""

            if not any(kw in raw.lower() for kw in recruiting_keywords):
                continue

            recruiters.append({
                "name": name,
                "title": title,
                "profile_url": href,
                "company": company,
            })
            logger.info(f"  -> {name} ({title})")

        except Exception as e:
            logger.warning(f"Failed to parse profile link: {e}")
            continue

    return recruiters


async def search_recruiters(company: str, max_results: int = 2) -> list[dict]:
    """
    Standalone entry point (backward compatible).
    Opens its own browser. For post-application outreach use
    _search_recruiters_on_page() with an existing authenticated page.
    """
    playwright, browser, context, page = await launch_browser(headless=False)
    try:
        recruiters = await _search_recruiters_on_page(page, company, max_results)
    except Exception as e:
        logger.error(f"Recruiter search failed for {company}: {e}")
        recruiters = []
    finally:
        await close_browser(playwright, browser)
    return recruiters
