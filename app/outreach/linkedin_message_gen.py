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
    Generates a short, personalized LinkedIn connection message.
    Target length: ~280 characters (LinkedIn connection note limit).
    """
    template = (PROMPTS_DIR / "recruiter_message.txt").read_text()
    prompt = template.format(
        candidate_name=candidate.name,
        candidate_school=candidate.education,
        recruiter_name=recruiter_name,
        company=company,
        role=role,
        skills=", ".join(candidate.skills[:4]),
    )

    logger.info(f"Generating outreach message → {recruiter_name} @ {company}")
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.75,
        max_tokens=120,
    )
    message = response.choices[0].message.content.strip()

    # Enforce LinkedIn note character cap
    if len(message) > 295:
        message = message[:292] + "..."

    return message


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
