from openai import OpenAI
from app.config import settings
from app.utils.validators import CandidateProfile, JobPosting
from app.utils.constants import PROMPTS_DIR, COVER_LETTERS_DIR
from app.utils.logger import logger
import json

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


def load_prompt_template() -> str:
    return (PROMPTS_DIR / "cover_letter.txt").read_text()


def generate_cover_letter(candidate: CandidateProfile, job: JobPosting) -> str:
    """Generates a tailored cover letter using Llama 3.3 via Groq."""
    template = load_prompt_template()
    prompt = template.format(
        candidate_profile=json.dumps(candidate.model_dump(), indent=2),
        job_description=json.dumps(job.model_dump(), indent=2),
    )

    logger.info(f"Generating cover letter for {job.company} - {job.role}")
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def save_cover_letter(cover_letter: str, company: str, role: str) -> str:
    """Save the generated cover letter to disk and return the file path."""
    filename = f"{company.replace(' ', '_')}_{role.replace(' ', '_')}.txt"
    output_path = COVER_LETTERS_DIR / filename
    output_path.write_text(cover_letter)
    logger.info(f"Cover letter saved: {output_path}")
    return str(output_path)
