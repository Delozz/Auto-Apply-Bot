"""
resume_pdf_gen.py

Takes the master resume PDF + LLM bullet rewrites and generates a
tailored PDF for a specific job. Only rewording — no fake skills added.
"""
import json
import pdfplumber
from pathlib import Path
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

from app.config import settings
from app.utils.validators import JobPosting
from app.utils.constants import RESUMES_DIR
from app.utils.logger import logger

client = OpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


def extract_resume_sections(resume_path: str) -> dict:
    """
    Extract raw text from the PDF and split into sections.
    Returns a dict like:
    {
      "header": "Devon Lopez\n...",
      "education": "...",
      "experience": [...bullets...],
      "projects": [...bullets...],
      "skills": "...",
      "raw": "full text"
    }
    """
    with pdfplumber.open(resume_path) as pdf:
        raw = "\n".join(page.extract_text() or "" for page in pdf.pages)

    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    sections = {"raw": raw, "lines": lines}
    return sections


def get_tailored_bullets(resume_text: str, job: JobPosting) -> dict:
    """
    Ask the LLM to rewrite resume bullets to better match the job.

    STRICT RULES enforced in prompt:
    - Only reword existing content — no new technologies
    - No fabricated experience
    - Keep bullet count the same
    - Returns structured JSON for easy parsing
    """
    prompt = f"""You are a professional resume editor helping a CS student tailor their resume.

STRICT RULES — you MUST follow these:
1. ONLY reword existing bullet points — do not add any new technologies, tools, or experiences
2. Do NOT invent anything the candidate hasn't done
3. Keep the same number of bullet points
4. Only change phrasing to better align with the job description language
5. Small wording changes only — do not completely rewrite bullets beyond recognition
6. You MAY reorder emphasis within a bullet (put the most relevant part first)
7. Return ONLY valid JSON — no markdown, no explanation

Job: {job.role} at {job.company}
Requirements: {", ".join(job.requirements[:8])}
Job description excerpt: {job.description[:600]}

Resume text:
{resume_text}

Return this exact JSON structure:
{{
  "rewrites": [
    {{"original": "exact original bullet text", "rewritten": "reworded version"}},
    ...
  ],
  "summary": "1-2 sentence tailored professional summary for this role"
}}

Only include bullets that would benefit from rewording. Leave unchanged bullets out of the rewrites array."""

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    raw_response = response.choices[0].message.content.strip()

    try:
        # Strip markdown code fences if present
        if raw_response.startswith("```"):
            raw_response = raw_response.split("```")[1]
            if raw_response.startswith("json"):
                raw_response = raw_response[4:]
        return json.loads(raw_response.strip())
    except json.JSONDecodeError as e:
        logger.warning(f"Could not parse LLM resume response as JSON: {e}")
        return {"rewrites": [], "summary": ""}


def apply_rewrites(resume_text: str, rewrites: list[dict]) -> str:
    """Replace original bullets with rewritten versions in the resume text."""
    updated = resume_text
    for item in rewrites:
        original = item.get("original", "").strip()
        rewritten = item.get("rewritten", "").strip()
        if original and rewritten and original in updated:
            updated = updated.replace(original, rewritten)
            logger.debug(f"Rewrite applied: '{original[:40]}...'")
    return updated


def generate_tailored_pdf(
    master_resume_path: str,
    job: JobPosting,
    output_dir: Path = RESUMES_DIR,
) -> str:
    """
    Main function — generates a tailored PDF resume for a specific job.

    Steps:
    1. Extract text from master PDF
    2. Ask LLM to suggest bullet rewrites (no fake skills)
    3. Apply rewrites to the text
    4. Generate a clean PDF with the updated content
    5. Save as {company}_{role}_resume.pdf
    6. Return the path to the new PDF

    The tailored PDF is what gets uploaded to the application — not the master.
    """
    logger.info(f"Generating tailored resume for: {job.role} @ {job.company}")

    # Step 1: Extract resume text
    sections = extract_resume_sections(master_resume_path)
    resume_text = sections["raw"]

    # Step 2: Get LLM rewrites
    logger.info("Requesting bullet rewrites from LLM...")
    result = get_tailored_bullets(resume_text, job)
    rewrites = result.get("rewrites", [])
    summary = result.get("summary", "")
    logger.info(f"Got {len(rewrites)} bullet rewrites")

    # Step 3: Apply rewrites to raw text
    updated_text = apply_rewrites(resume_text, rewrites)

    # Step 4: Generate PDF
    safe_company = job.company.replace(" ", "_").replace("/", "-")
    safe_role = job.role[:30].replace(" ", "_").replace("/", "-")
    filename = f"{safe_company}_{safe_role}_resume.pdf"
    output_path = output_dir / filename

    _write_pdf(updated_text, summary, str(output_path))
    logger.info(f"Tailored resume saved: {output_path}")

    return str(output_path)


def _write_pdf(resume_text: str, summary: str, output_path: str):
    """
    Write the tailored resume text to a clean, professional PDF.
    Preserves the original structure — just formats it nicely.
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    name_style = ParagraphStyle(
        "Name", parent=styles["Normal"],
        fontSize=16, fontName="Helvetica-Bold",
        alignment=TA_CENTER, spaceAfter=2,
        textColor=colors.HexColor("#1a1a1a"),
    )
    contact_style = ParagraphStyle(
        "Contact", parent=styles["Normal"],
        fontSize=9, alignment=TA_CENTER, spaceAfter=8,
        textColor=colors.HexColor("#444444"),
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Normal"],
        fontSize=11, fontName="Helvetica-Bold",
        spaceBefore=10, spaceAfter=3,
        textColor=colors.HexColor("#1a1a1a"),
        borderPad=0, borderColor=colors.HexColor("#cccccc"),
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9.5, spaceAfter=2,
        textColor=colors.HexColor("#222222"),
        leading=14,
    )
    bullet_style = ParagraphStyle(
        "Bullet", parent=styles["Normal"],
        fontSize=9.5, spaceAfter=2,
        leftIndent=12, bulletIndent=0,
        textColor=colors.HexColor("#222222"),
        leading=14,
    )

    story = []
    lines = resume_text.splitlines()

    # Track if we've added the summary
    summary_added = False

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # First non-empty line = name
        if i == 0 or (not story and line):
            story.append(Paragraph(line, name_style))
            continue

        # Contact info lines (short lines near the top with @ or | or phone patterns)
        if len(story) <= 3 and ("|" in line or "@" in line or line.replace("-", "").replace("(", "").replace(")", "").replace(" ", "").replace("+", "").isdigit()):
            story.append(Paragraph(line, contact_style))
            continue

        # Section headers (ALL CAPS or short lines that look like headers)
        if line.isupper() or (len(line) < 30 and line.replace(" ", "").isalpha() and not line.startswith("•")):
            # Add separator line
            story.append(Spacer(1, 2))
            story.append(Paragraph(f"<u>{line}</u>", section_style))

            # Add tailored summary after the first section header if we have one
            if summary and not summary_added and "SUMMARY" not in line and "OBJECTIVE" not in line:
                pass  # We'll add summary if there's a summary section

        # Bullet points
        elif line.startswith("•") or line.startswith("-") or line.startswith("*"):
            clean = line.lstrip("•-* ").strip()
            story.append(Paragraph(f"• {clean}", bullet_style))

        # Regular body text
        else:
            story.append(Paragraph(line, body_style))

    doc.build(story)
