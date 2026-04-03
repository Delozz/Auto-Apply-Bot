from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RESUMES_DIR = DATA_DIR / "resumes"
COVER_LETTERS_DIR = DATA_DIR / "cover_letters"
APPLIED_JOBS_FILE = DATA_DIR / "applied_jobs.json"
OUTREACH_LOG_FILE = DATA_DIR / "outreach_log.json"
LINKEDIN_SESSION_FILE = DATA_DIR / "linkedin_session.json"
PROMPTS_DIR = BASE_DIR / "prompts"

# ─── Job Filters ─────────────────────────────────────────────────────────────
TARGET_ROLES = [
    "Software Engineer Intern",
    "SWE Intern",
    "Software Development Intern",
    "Software Developer Intern",
    "Backend Engineer Intern",
    "Frontend Engineer Intern",
    "Full Stack Engineer Intern",
    "Infrastructure Engineer Intern",
    "Platform Engineer Intern",
    "Quant Developer Intern",
    "Quantitative Developer Intern",
    "Quantitative Research Intern",
    "Quantitative Trader Intern",
    "Data Engineer Intern",
    "Data Scientist Intern",
    "Machine Learning Engineer Intern",
    "Cybersecurity Intern",
    "DevOps Intern",
    "Software Security Intern",
    "Algorithm Engineer Intern",
    "Algorithm Developer Intern",
]

TARGET_KEYWORDS = [
    "Python", "C++", "Java", "Algorithms",
    "Data Structures", "Distributed Systems",
    "Backend", "APIs", "Trading", "Systems",
]
TARGET_LOCATIONS = ["New York", "Chicago", "Remote", "San Francisco", "Austin", "Rayleigh", "Seattle", "Boston", "Washington D.C.", "Denver", "Atlanta", "Los Angeles", "Pittsburgh", "Philadelphia", "Dallas", "Miami"]

# ─── Scraper Settings ────────────────────────────────────────────────────────
SCRAPE_DELAY_MIN = 2.0   # seconds (anti-detection)
SCRAPE_DELAY_MAX = 5.0
MAX_JOBS_PER_RUN = 50

# ─── Embeddings (local via sentence-transformers, free) ──────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # ~80MB, downloads once on first run
SIMILARITY_THRESHOLD = 0.30            # min score to apply to a job

# ─── Application Settings ────────────────────────────────────────────────────
MAX_APPLICATIONS_PER_DAY = 20
MAX_OUTREACH_PER_COMPANY = 2
