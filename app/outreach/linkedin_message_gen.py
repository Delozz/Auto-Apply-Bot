from openai import OpenAI
from app.config import settings
from app.utils.validators import CandidateProfile
from app.utils.constants import PROMPTS_DIR
from app.utils.logger import logger

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


def generate_recruiter_message(
    candidate: CandidateProfile,
    recruiter_name: str,
    company: str,
    role: str,
) -> str:
    """
    Generates a LinkedIn connection note under 200 characters.
    The opening line is built in code; the LLM only generates a short
    closing question to fill the remaining space.
    """
    first_name = recruiter_name.split()[0]
    opening = (
        f"Hello {first_name}, my name is {candidate.name} and I am excited "
        f"to apply for the position of {role} at {company}. "
    )
    remaining = 200 - len(opening)

    prompt = (
        f"Write a single closing question (max {remaining} characters) for a LinkedIn "
        f"connection note to a recruiter at {company}. Keep it simple and non-technical. "
        f"Ask something genuine about what they look for in candidates or about the role. "
        f"Do not include any names. Output the question only — no quotes."
    )

    logger.info(f"Generating outreach message → {recruiter_name} @ {company}")
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.75,
        max_tokens=60,
    )
    question = (response.choices[0].message.content or "").strip()

    # Hard cap the question if the LLM overshoots
    if len(opening) + len(question) > 200:
        question = question[:200 - len(opening) - 3] + "..."

    return opening + question


def batch_generate_messages(
    candidate: CandidateProfile,
    recruiters: list[dict],
) -> list[dict]:
    """Generate outreach messages for a list of recruiters."""
    return [
        {
            **rec,
            "message": generate_recruiter_message(
                candidate=candidate,
                recruiter_name=rec["name"],
                company=rec["company"],
                role=rec.get("role", "Software Engineer Intern"),
            )
        }
        for rec in recruiters
    ]
