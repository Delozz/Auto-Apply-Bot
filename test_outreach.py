"""
test_outreach.py

Standalone test for the LinkedIn recruiter outreach flow.
Runs auth → search → message gen → connection request WITHOUT the full pipeline.

Usage:
    PYTHONPATH=. python3 test_outreach.py
    PYTHONPATH=. python3 test_outreach.py --company "Stripe" --role "SWE Intern" --dry-run
"""
import asyncio
import argparse
from app.outreach.linkedin_auth import get_authenticated_linkedin_page
from app.outreach.recruiter_finder import _search_recruiters_on_page
from app.outreach.connection_handler import _send_connection_on_page
from app.outreach.linkedin_message_gen import generate_recruiter_message
from app.automation.playwright_engine import close_browser
from app.utils.validators import CandidateProfile
from app.utils.constants import RESUMES_DIR
from app.utils.logger import logger

CANDIDATE = CandidateProfile(
    name="Devon Lopez",
    email="devoninternships@gmail.com",
    phone="5127878221",
    education="Texas A&M University - Computer Science",
    skills=["Python", "C++", "SQL", "Data Structures", "Algorithms"],
    interests=["Quantitative Finance", "Distributed Systems"],
    resume_path=str(RESUMES_DIR / "Devon_Lopez_SWE_Quant.pdf"),
    graduation_year="2028",
    linkedin_url="https://www.linkedin.com/in/devon-lopez1",
    github_url="https://github.com/Delozz",
    website_url="",
)


async def test_outreach(company: str, role: str, dry_run: bool):
    print(f"\n{'='*60}")
    print(f"  Outreach test — {company} / {role}")
    print(f"  Dry run: {dry_run}")
    print(f"{'='*60}\n")

    playwright = browser = None
    try:
        # ── Step 1: Auth ──────────────────────────────────────────────
        print("[ 1/4 ] Authenticating with LinkedIn...")
        playwright, browser, context, page = await get_authenticated_linkedin_page()
        print("        ✓ Authenticated\n")

        # ── Step 2: Search recruiters ─────────────────────────────────
        print(f"[ 2/4 ] Searching for recruiters at {company}...")
        recruiters = await _search_recruiters_on_page(page, company, max_results=3)
        if not recruiters:
            print(f"        ✗ No recruiters found for {company}")
            print("          Try a larger company name, or LinkedIn may have blocked the search.")
            return

        print(f"        ✓ Found {len(recruiters)} recruiter(s):")
        for r in recruiters:
            print(f"           • {r['name']} — {r['title']}")
        print()

        # ── Step 3: Generate messages ─────────────────────────────────
        print("[ 3/4 ] Generating outreach messages...")
        for r in recruiters:
            r["message"] = generate_recruiter_message(
                candidate=CANDIDATE,
                recruiter_name=r["name"],
                company=company,
                role=role,
            )
            print(f"        {r['name']}: {r['message'][:80]}...")
        print()

        # ── Step 4: Send (or preview) ─────────────────────────────────
        if dry_run:
            print("[ 4/4 ] DRY RUN — skipping connection requests")
            print("\n  Full messages that would be sent:")
            for r in recruiters:
                print(f"\n  → {r['name']} ({r['profile_url']})")
                print(f"    {r['message']}")
        else:
            print("[ 4/4 ] Sending connection request to first recruiter...")
            r = recruiters[0]
            sent = await _send_connection_on_page(
                page=page,
                profile_url=r["profile_url"],
                message=r["message"],
                recruiter_name=r["name"],
            )
            print(f"\n        {'✓ Sent' if sent else '✗ Not sent'} — {r['name']}")

    except RuntimeError as e:
        print(f"\n  ✗ Auth failed: {e}")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
    finally:
        if playwright and browser:
            try:
                input("\n  Press Enter to close browser...")
            except EOFError:
                pass
            await close_browser(playwright, browser)

    print(f"\n{'='*60}")
    print("  Test complete")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test LinkedIn outreach in isolation")
    parser.add_argument("--company", default="Point72", help="Company to search recruiters for")
    parser.add_argument("--role", default="Quantitative Researcher Intern", help="Role you applied to")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview messages without sending (default: True). Use --no-dry-run to actually send.",
    )
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    args = parser.parse_args()

    asyncio.run(test_outreach(args.company, args.role, args.dry_run))
