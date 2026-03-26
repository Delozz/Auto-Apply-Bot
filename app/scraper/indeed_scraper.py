import asyncio
import random
from playwright.async_api import async_playwright
from app.utils.validators import JobPosting
from app.utils.constants import SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX
from app.utils.logger import logger

INDEED_URL = "https://www.indeed.com/jobs?q={query}&l={location}&jt=internship"


async def scrape_indeed_jobs(
    query: str = "Software Engineer Intern",
    location: str = "United+States",
) -> list[JobPosting]:
    """
    Scrapes Indeed job listings using Playwright.
    Note: Indeed has aggressive bot detection — use sparingly with delays.
    """
    jobs: list[JobPosting] = []
    url = INDEED_URL.format(query=query.replace(" ", "+"), location=location)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # visible helps avoid detection
        page = await browser.new_page()

        try:
            logger.info(f"Scraping Indeed: {url}")
            await page.goto(url, timeout=30000)
            await asyncio.sleep(random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX))

            job_cards = await page.query_selector_all(".job_seen_beacon")
            logger.info(f"Found {len(job_cards)} Indeed job cards")

            for card in job_cards[:15]:
                try:
                    title_el = await card.query_selector("h2.jobTitle span")
                    company_el = await card.query_selector("[data-testid='company-name']")
                    location_el = await card.query_selector("[data-testid='text-location']")
                    link_el = await card.query_selector("a.jcs-JobTitle")

                    title = (await title_el.inner_text()).strip() if title_el else ""
                    company = (await company_el.inner_text()).strip() if company_el else ""
                    loc = (await location_el.inner_text()).strip() if location_el else ""
                    href = await link_el.get_attribute("href") if link_el else ""
                    link = f"https://www.indeed.com{href}" if href else ""

                    if title and company:
                        jobs.append(JobPosting(
                            company=company,
                            role=title,
                            location=loc,
                            description="",
                            requirements=[],
                            application_url=link,
                            source="indeed",
                        ))
                except Exception as e:
                    logger.warning(f"Failed to parse Indeed card: {e}")
                    continue

        except Exception as e:
            logger.error(f"Indeed scraper error: {e}")
        finally:
            await browser.close()

    return jobs
