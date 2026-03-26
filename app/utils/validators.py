from pydantic import BaseModel, EmailStr
from typing import Optional


class CandidateProfile(BaseModel):
    name: str
    email: EmailStr
    phone: str
    education: str
    skills: list[str]
    interests: list[str]
    resume_path: str

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Devon Lopez",
                "email": "devoninternships@gmail.com",
                "phone": "512-787-8221",
                "education": "Texas A&M University - Computer Science",
                "skills": ["Python", "C++", "SQL", "Data Structures"],
                "interests": ["Quantitative Finance", "Software Engineering", "Machine Learning"],
                "resume_path": "./data/resumes/master_resume.pdf",
            }
        }


class JobPosting(BaseModel):
    company: str
    role: str
    location: str
    description: str
    requirements: list[str]
    application_url: str
    source: Optional[str] = None
    match_score: Optional[float] = None


class ApplicationResult(BaseModel):
    job: JobPosting
    status: str  # "pending" | "submitted" | "skipped" | "failed"
    cover_letter_path: Optional[str] = None
    resume_path: Optional[str] = None
    submitted_at: Optional[str] = None
    notes: Optional[str] = None
