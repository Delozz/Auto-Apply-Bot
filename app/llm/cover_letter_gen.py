import json

from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from app.config import settings
from app.utils.validators import CandidateProfile, JobPosting
from app.utils.constants import PROMPTS_DIR, COVER_LETTERS_DIR
from app.utils.logger import logger

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
    return (response.choices[0].message.content or "").strip()


def save_cover_letter(cover_letter: str, company: str, role: str) -> str:
    """Save the generated cover letter as a PDF and return the file path."""
    filename = f"{company.replace(' ', '_')}_{role.replace(' ', '_')}_cover_letter.pdf"
    output_path = COVER_LETTERS_DIR / filename

    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "CoverLetterBody",
        parent=styles["Normal"],
        fontSize=11,
        leading=16,
        spaceAfter=10,
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    story = []
    for paragraph in cover_letter.split("\n\n"):
        text = paragraph.strip()
        if text:
            story.append(Paragraph(text.replace("\n", "<br/>"), body_style))
            story.append(Spacer(1, 4))

    doc.build(story)
    logger.info(f"Cover letter saved: {output_path}")
    return str(output_path)
