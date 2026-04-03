from openai import OpenAI
from app.config import settings
from app.utils.validators import CandidateProfile, JobPosting
from app.utils.constants import PROMPTS_DIR
from app.utils.logger import logger
import json

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


def answer_application_question(
    question: str,
    candidate: CandidateProfile,
    job: JobPosting,
    max_words: int = 150,
) -> str:
    """
    Generates a tailored answer to an application question.
    Stays concise and authentic — avoids buzzword soup.
    """
    template = (PROMPTS_DIR / "qa_prompt.txt").read_text()
    prompt = template.format(
        question=question,
        candidate_profile=json.dumps(candidate.model_dump(), indent=2),
        job_description=f"{job.role} at {job.company}: {job.description[:500]}",
        max_words=max_words,
    )

    logger.info(f"Answering question: '{question[:60]}...'")
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
    )
    return response.choices[0].message.content.strip()

