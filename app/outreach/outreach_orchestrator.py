"""
outreach_orchestrator.py

Single entry point for post-application LinkedIn recruiter outreach.
Called from run_pipeline.py immediately after mark_as_applied().
"""
from app.outreach.linkedin_auth import get_authenticated_linkedin_page
from app.outreach.recruiter_finder import _search_recruiters_on_page
from app.outreach.connection_handler import _send_connection_on_page
from app.outreach.linkedin_message_gen import generate_recruiter_message
from app.utils.application_tracker import has_outreach_been_sent, mark_outreach_sent
from app.utils.validators import CandidateProfile
from app.automation.playwright_engine import close_browser, random_delay
from app.utils.logger import logger


async def run_post_application_outreach(
    company: str,
    role: str,
    candidate: CandidateProfile,
    max_recruiters: int = 1,
) -> None:
    """
    Full post-application outreach flow:
      1. Skip if outreach already sent for this company.
      2. Authenticate with LinkedIn (loads saved session, re-logs if expired).
      3. Search for a recruiter at the company.
      4. Generate a personalised connection message referencing the role.
      5. Show message + profile URL and ask for human approval.
      6. Send connection request if approved.
      7. Log to outreach_log.json so the same company is never targeted again.
    """
    if has_outreach_been_sent(company):
        logger.info(f"Outreach already sent for {company} — skipping")
        return

    logger.info(f"\nStarting recruiter outreach for {company} ({role})")

    playwright = browser = None
    try:
        playwright, browser, context, page = await get_authenticated_linkedin_page()

        recruiters = await _search_recruiters_on_page(page, company, max_results=max_recruiters)
        if not recruiters:
            logger.warning(f"No recruiters found for {company} — outreach skipped")
            return

        for recruiter in recruiters:
            recruiter_name = recruiter["name"]
            profile_url = recruiter.get("profile_url", "")
            if not profile_url:
                continue

            message = generate_recruiter_message(
                candidate=candidate,
                recruiter_name=recruiter_name,
                company=company,
                role=role,
            )

            sent = await _send_connection_on_page(
                page=page,
                profile_url=profile_url,
                message=message,
                recruiter_name=recruiter_name,
            )

            if sent:
                mark_outreach_sent(company, recruiter_name, profile_url)
                break  # one connection per company per run

            await random_delay(5.0, 10.0)

    except RuntimeError as e:
        logger.error(f"Outreach aborted — LinkedIn auth failed: {e}")
    except Exception as e:
        logger.error(f"Outreach failed for {company}: {e}")
    finally:
        if playwright and browser:
            await close_browser(playwright, browser)
