import httpx
from app.utils.validators import JobPosting
from app.utils.logger import logger

# Add or remove companies here.
# Find a token by visiting: https://boards.greenhouse.io/{token}
# Most companies list it publicly — just Google "[company] greenhouse jobs"
GREENHOUSE_BOARDS = {
    "Jane Street": "janestreet",
    "Two Sigma": "twosigma",
    "Citadel": "citadel",
    "Hudson River Trading": "hudsonrivertrading",
    "DE Shaw": "deshaw",
}


async def scrape_greenhouse_board(company_name: str, board_token: str) -> list[JobPosting]:
    """
    Uses Greenhouse's public JSON API to fetch job listings.
    No Playwright or login needed — clean REST call.
    This is the easiest scraper to test first.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    jobs: list[JobPosting] = []

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            for job in data.get("jobs", []):
                title: str = job.get("title", "")
                if "intern" not in title.lower():
                    continue

                jobs.append(JobPosting(
                    company=company_name,
                    role=title,
                    location=job.get("location", {}).get("name", ""),
                    description=job.get("content", ""),
                    requirements=[],
                    application_url=job.get("absolute_url", ""),
                    source="greenhouse",
                ))

        except Exception as e:
            logger.error(f"Greenhouse scrape failed for {company_name}: {e}")

    logger.info(f"Greenhouse [{company_name}]: {len(jobs)} internship roles found")
    return jobs


async def scrape_all_greenhouse() -> list[JobPosting]:
    """Scrape all configured Greenhouse boards."""
    all_jobs: list[JobPosting] = []
    for company, token in GREENHOUSE_BOARDS.items():
        jobs = await scrape_greenhouse_board(company, token)
        all_jobs.extend(jobs)
    return all_jobs
