from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RESUMES_DIR = DATA_DIR / "resumes"
COVER_LETTERS_DIR = DATA_DIR / "cover_letters"
PROMPTS_DIR = BASE_DIR / "prompts"

# ─── Job Filters ─────────────────────────────────────────────────────────────
TARGET_ROLES = ["Software Engineer Intern", "SWE Intern", "Quant Developer Intern", "Quantitative Research Intern"]
TARGET_KEYWORDS = ["Python", "Algorithms", "Trading", "Distributed Systems", "C++"]
TARGET_LOCATIONS = ["New York", "Chicago", "Remote", "San Francisco", "Austin"]

# ─── Scraper Settings ────────────────────────────────────────────────────────
SCRAPE_DELAY_MIN = 2.0   # seconds (anti-detection)
SCRAPE_DELAY_MAX = 5.0
MAX_JOBS_PER_RUN = 50

# ─── Embeddings (local via sentence-transformers, free) ──────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # ~80MB, downloads once on first run
SIMILARITY_THRESHOLD = 0.75            # min score to apply to a job

# ─── Application Settings ────────────────────────────────────────────────────
MAX_APPLICATIONS_PER_DAY = 20
MAX_OUTREACH_PER_COMPANY = 2
