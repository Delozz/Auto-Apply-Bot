import asyncio
import random
from app.automation.playwright_engine import launch_browser, close_browser, random_delay
from app.utils.logger import logger


async def search_recruiters(company: str, max_results: int = 2) -> list[dict]:
    """
    Searches LinkedIn for recruiters at a given company.
    Targets: Recruiter, Talent Acquisition, University Recruiting titles.
    Requires an active LinkedIn session in the browser.
    """
    search_query = f"{company} recruiter university internship"
    url = f"https://www.linkedin.com/search/results/people/?keywords={search_query.replace(' ', '%20')}"

    recruiters = []
    playwright, browser, context, page = await launch_browser(headless=False)

    try:
        logger.info(f"Searching recruiters for: {company}")
        await page.goto(url, timeout=30000)
        await random_delay(2.0, 4.0)

        cards = await page.query_selector_all(".entity-result__item")
        logger.info(f"Found {len(cards)} people results")

        for card in cards[:max_results * 2]:  # search more, filter down
            try:
                name_el = await card.query_selector(".entity-result__title-text a")
                title_el = await card.query_selector(".entity-result__primary-subtitle")
                link_el = await card.query_selector(".entity-result__title-text a")

                name = (await name_el.inner_text()).strip() if name_el else "Unknown"
                title = (await title_el.inner_text()).strip() if title_el else ""
                profile_url = await link_el.get_attribute("href") if link_el else ""

                recruiting_keywords = ["recruit", "talent", "hiring", "university", "campus"]
                if any(kw in title.lower() for kw in recruiting_keywords):
                    recruiters.append({
                        "name": name,
                        "title": title,
                        "profile_url": profile_url,
                        "company": company,
                    })
                    logger.info(f"  → {name} ({title})")

                if len(recruiters) >= max_results:
                    break

            except Exception as e:
                logger.warning(f"Failed to parse recruiter card: {e}")
                continue

    except Exception as e:
        logger.error(f"Recruiter search failed for {company}: {e}")
    finally:
        await close_browser(playwright, browser)

    return recruiters
