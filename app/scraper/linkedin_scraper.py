import asyncio
import random
from playwright.async_api import async_playwright
from app.utils.validators import JobPosting
from app.utils.constants import SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX
from app.utils.logger import logger

LINKEDIN_JOBS_URL = (
    "https://www.linkedin.com/jobs/search/?keywords={query}&location={location}&f_E=1&f_JT=I"
)


async def scrape_linkedin_jobs(
    query: str = "Software Engineer Intern",
    location: str = "United States",
) -> list[JobPosting]:
    """
    Scrapes LinkedIn job listings for internship roles using Playwright.
    Returns a list of normalized JobPosting objects.
    """
    jobs: list[JobPosting] = []
    url = LINKEDIN_JOBS_URL.format(
        query=query.replace(" ", "%20"),
        location=location.replace(" ", "%20"),
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            logger.info(f"Scraping LinkedIn: {url}")
            await page.goto(url, timeout=30000)
            await asyncio.sleep(random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX))

            for _ in range(3):
                await page.keyboard.press("End")
                await asyncio.sleep(1.5)

            job_cards = await page.query_selector_all(".base-card")
            logger.info(f"Found {len(job_cards)} job cards")

            for card in job_cards[:20]:
                try:
                    title_el = await card.query_selector(".base-search-card__title")
                    company_el = await card.query_selector(".base-search-card__subtitle")
                    location_el = await card.query_selector(".job-search-card__location")
                    link_el = await card.query_selector("a.base-card__full-link")

                    title = (await title_el.inner_text()).strip() if title_el else ""
                    company = (await company_el.inner_text()).strip() if company_el else ""
                    loc = (await location_el.inner_text()).strip() if location_el else ""
                    link = await link_el.get_attribute("href") if link_el else ""

                    if title and company and link:
                        jobs.append(JobPosting(
                            company=company,
                            role=title,
                            location=loc,
                            description="",
                            requirements=[],
                            application_url=link,
                            source="linkedin",
                        ))
                except Exception as e:
                    logger.warning(f"Failed to parse job card: {e}")
                    continue

        except Exception as e:
            logger.error(f"LinkedIn scraper error: {e}")
        finally:
            await browser.close()

    logger.info(f"LinkedIn scrape complete: {len(jobs)} jobs found")
    return jobs
