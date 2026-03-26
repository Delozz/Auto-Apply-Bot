import numpy as np
from sentence_transformers import SentenceTransformer
from app.utils.constants import EMBEDDING_MODEL, SIMILARITY_THRESHOLD
from app.utils.logger import logger

# Downloads ~80MB on first run, then cached locally forever
model = SentenceTransformer(EMBEDDING_MODEL)


def get_embedding(text: str) -> list[float]:
    """
    Convert text into a vector using a local sentence-transformers model.
    Runs entirely on your machine — no API calls, no cost.
    Think of it like compressing the meaning of text into a list of numbers.
    """
    return model.encode(text.strip()).tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Measure how similar two vectors are by the angle between them.
    Score of 1.0 = identical direction, 0.0 = completely unrelated.
    This is how we match your resume to a job description.
    """
    a_np = np.array(a, dtype="float32")
    b_np = np.array(b, dtype="float32")
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))


def score_job_match(resume_text: str, job_description: str) -> float:
    """Returns a similarity score [0, 1] between a resume and a job description."""
    score = cosine_similarity(get_embedding(resume_text), get_embedding(job_description))
    logger.info(f"Job match score: {score:.3f} (threshold: {SIMILARITY_THRESHOLD})")
    return score


def filter_jobs_by_score(resume_text: str, jobs: list[dict]) -> list[dict]:
    """
    Filter jobs to only those above the similarity threshold.
    Adds a 'match_score' field to each passing job dict.
    """
    qualified = []
    for job in jobs:
        description = job.get("description", "") or job.get("role", "")
        score = score_job_match(resume_text, description)
        if score >= SIMILARITY_THRESHOLD:
            job["match_score"] = round(score, 4)
            qualified.append(job)

    logger.info(f"{len(qualified)}/{len(jobs)} jobs passed similarity threshold")
    return sorted(qualified, key=lambda j: j["match_score"], reverse=True)
