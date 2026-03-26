from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Job, Application, ApplicationStatus
from app.utils.validators import JobPosting
import json


async def job_exists(db: AsyncSession, url: str) -> bool:
    result = await db.execute(select(Job).where(Job.application_url == url))
    return result.scalar_one_or_none() is not None


async def insert_job(db: AsyncSession, job: JobPosting) -> Job:
    new_job = Job(
        company=job.company,
        role=job.role,
        location=job.location,
        description=job.description,
        requirements=json.dumps(job.requirements),
        application_url=job.application_url,
        source=job.source,
        match_score=job.match_score,
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    return new_job


async def create_application(
    db: AsyncSession,
    job_id: str,
    resume_path: str,
    cover_letter_path: str,
) -> Application:
    app = Application(
        job_id=job_id,
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
        status=ApplicationStatus.PENDING,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def update_application_status(
    db: AsyncSession,
    application_id: str,
    status: ApplicationStatus,
):
    result = await db.execute(select(Application).where(Application.id == application_id))
    app = result.scalar_one_or_none()
    if app:
        app.status = status
        await db.commit()


async def get_all_applications(db: AsyncSession) -> list[Application]:
    result = await db.execute(
        select(Application).order_by(Application.created_at.desc())
    )
    return result.scalars().all()
