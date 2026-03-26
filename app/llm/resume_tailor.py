from openai import OpenAI
import pdfplumber
from app.config import settings
from app.utils.validators import CandidateProfile, JobPosting
from app.utils.logger import logger

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


def extract_resume_text(resume_path: str) -> str:
    """Extract raw text from a PDF resume using pdfplumber."""
    with pdfplumber.open(resume_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    logger.info(f"Extracted {len(text)} chars from resume: {resume_path}")
    return text


def tailor_resume_bullets(resume_text: str, job: JobPosting) -> str:
    """
    Ask the LLM to suggest which resume bullets to emphasize or rewrite
    based on the job description. Returns a markdown suggestion block.

    Think of this like a smart highlighter — it tells you what to move to
    the top and what to tweak rather than rewriting your whole resume.
    """
    prompt = f"""
You are a professional resume coach specializing in tech and quant finance roles.

Given the resume below and the job description, do the following:
1. Identify the 3-5 resume bullets most relevant to this role.
2. Suggest 1-2 rewrites to better match the job language.
3. Flag any missing skills worth adding if the candidate has them.

Resume:
{resume_text}

Job Title: {job.role} at {job.company}
Requirements: {", ".join(job.requirements)}
Description: {job.description[:1000]}

Respond in clean markdown with sections: Highlight, Rewrite, Add.
"""
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    return response.choices[0].message.content.strip()
