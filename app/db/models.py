from sqlalchemy import Column, String, Float, DateTime, Text, Integer, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime
import uuid
import enum


class Base(DeclarativeBase):
    pass


class ApplicationStatus(str, enum.Enum):
    PENDING = "pending"
    APPLIED = "applied"
    OA_RECEIVED = "oa_received"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    OFFER = "offer"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company = Column(String, nullable=False)
    role = Column(String, nullable=False)
    location = Column(String)
    description = Column(Text)
    requirements = Column(Text)        # stored as JSON string
    application_url = Column(String, unique=True)
    source = Column(String)            # linkedin | greenhouse | indeed
    match_score = Column(Float)
    scraped_at = Column(DateTime, default=datetime.utcnow)


class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING)
    resume_path = Column(String)
    cover_letter_path = Column(String)
    submitted_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company = Column(String, nullable=False)
    recruiter_name = Column(String)
    recruiter_url = Column(String)
    message = Column(Text)
    sent = Column(Integer, default=0)  # 0=pending, 1=sent
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
