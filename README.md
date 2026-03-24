# 🤖 Auto Apply Bot

Semi-automated internship application system for SWE + Quant roles.
Built by Devon Lopez — Texas A&M CS, targeting Summer 2027.

**Stack:** FastAPI · Groq (Llama 3.3) · sentence-transformers · Playwright · PostgreSQL · Redis · Celery

---

## 🚀 Setup & Run

### 1. Install dependencies
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install sentence-transformers
playwright install chromium
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in your Groq API key and set a Postgres password
```

### 3. Drop your resume in place
```
data/resumes/master_resume.pdf
```

### 4. Start Postgres + Redis
```bash
docker-compose up -d postgres redis
```

### 5. Run the API
```bash
uvicorn app.main:app --reload
```

### 6. Trigger a pipeline
Open `http://localhost:8000/docs` and POST to:
- `/run/apply-pipeline` — scrape, score, generate, fill, review, submit
- `/run/outreach-pipeline` — find recruiters and send connection messages

---

## 📁 Structure

```
auto_apply_bot/
├── app/
│   ├── main.py                  # FastAPI + Celery entrypoint
│   ├── config.py                # All settings (reads from .env)
│   ├── scraper/                 # LinkedIn, Greenhouse, Indeed scrapers
│   ├── llm/                     # Cover letter, resume tailor, Q&A, embeddings
│   ├── automation/              # Playwright engine, form filler, submit handler
│   ├── outreach/                # Recruiter finder + LinkedIn message gen
│   ├── db/                      # SQLAlchemy models + queries
│   ├── workflows/               # apply_pipeline + outreach_pipeline (Celery tasks)
│   └── utils/                   # Logger, validators, constants
├── data/
│   ├── resumes/                 # ← put master_resume.pdf here
│   ├── cover_letters/           # auto-generated letters saved here
│   └── logs/
├── prompts/                     # LLM prompt templates
├── .env.example
├── docker-compose.yml
└── requirements.txt
```

---

## ⚠️ Safety Rules

- Every application **pauses for your manual approval** before submitting
- Max **20 applications/day** (constants.py)
- Max **2 recruiter messages/company** (constants.py)
- Random delays between all scraper actions

---

## 🗺️ Roadmap

- [x] Full project scaffold
- [x] Groq + Llama 3.3 integration
- [x] Local embeddings via sentence-transformers
- [ ] Drop in master_resume.pdf and test Greenhouse scraper
- [ ] LinkedIn scraper (authenticated)
- [ ] PostgreSQL tracking dashboard
- [ ] Email/calendar integration for interview invites
- [ ] Feedback loop — track which resumes get responses
# Auto-Apply-Bot
