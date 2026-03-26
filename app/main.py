from fastapi import FastAPI
from celery import Celery
from app.config import settings
from app.utils.logger import logger

# ─── FastAPI App ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="Auto Apply Bot",
    description="Semi-automated internship application system for Devon Lopez",
    version="0.1.0",
)

# ─── Celery App ──────────────────────────────────────────────────────────────
celery_app = Celery(
    "auto_apply",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.task_routes = {
    "app.workflows.apply_pipeline.*": {"queue": "apply"},
    "app.workflows.outreach_pipeline.*": {"queue": "outreach"},
}


# ─── Routes ──────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.env}


@app.post("/run/apply-pipeline")
async def trigger_apply_pipeline():
    from app.workflows.apply_pipeline import run_apply_pipeline
    task = run_apply_pipeline.delay()
    logger.info(f"Apply pipeline triggered: task_id={task.id}")
    return {"task_id": task.id, "status": "queued"}


@app.post("/run/outreach-pipeline")
async def trigger_outreach_pipeline():
    from app.workflows.outreach_pipeline import run_outreach_pipeline
    task = run_outreach_pipeline.delay()
    logger.info(f"Outreach pipeline triggered: task_id={task.id}")
    return {"task_id": task.id, "status": "queued"}


@app.on_event("startup")
async def startup_event():
    logger.info("Auto Apply Bot started ✅")
