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
    graduation_year: Optional[str] = "2028"
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    website_url: Optional[str] = None
    cover_letter_path: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Devon Lopez",
                "email": "devoninternships@gmail.com",
                "phone": "512-787-8221",
                "education": "Texas A&M University - Computer Science",
                "skills": ["Python", "Linux", "Object-Oriented Programming", "Data Structures", "Git", "Pandas", "NumPy", "Computer Hardware"],
                "interests": ["Quantitative Finance", "Distributed Systems", "Machine Learning", "Cybersecurity", "Software Development"],
                "resume_path": "./data/resumes/master_resume.pdf",
                "graduation_year": "2028",
                "linkedin_url": "https://www.linkedin.com/in/devon-lopez1/",
                "github_url": "https://github.com/Delozz",
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


class FormField(BaseModel):
    label: str
    field_type: str  # "text" | "textarea" | "select" | "react_select" | "checkbox" | "radio" | "file"
    required: bool = False
    options: list[str] = []
    placeholder: str = ""
    selector_hint: str = ""
    section: str = ""


class FormManifest(BaseModel):
    url: str
    fields: list[FormField]
    analyzed_at: str