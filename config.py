import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Multiple Hunter.io API keys (optional, 25 free credits each)
HUNTER_API_KEYS = []
for i in range(1, 21):
    key = os.getenv("HUNTER_API_KEY_" + str(i), "")
    if key:
        HUNTER_API_KEYS.append(key)
single_key = os.getenv("HUNTER_API_KEY", "")
if single_key and single_key not in HUNTER_API_KEYS:
    HUNTER_API_KEYS.insert(0, single_key)

# --- Scraper Settings ---
SEARCH_QUERIES = [
    "AI Developer",
    "AI Engineer",
    "Machine Learning Engineer",
    "AI Software Engineer",
    "GenAI Developer",
    "LLM Engineer",
    "Deep Learning Engineer",
    "NLP Engineer",
    "Computer Vision Engineer",
    "AI Research Engineer",
    "MLOps Engineer",
    "Full Stack AI Developer",
]

SEARCH_LOCATIONS = [
    "United States",
    "United Kingdom",
    "Germany",
    "France",
    "Netherlands",
    "Ireland",
    "Switzerland",
    "Sweden",
    "Spain",
    "Italy",
    "Poland",
    "Denmark",
    "Belgium",
    "Austria",
    "Norway",
    "Finland",
    "Portugal",
]

TIME_FILTER = "r86400"
MAX_PAGES_PER_QUERY = 2
MIN_DELAY = 4
MAX_DELAY = 10
MAX_LEADS_PER_RUN = 500

# --- Enricher Settings ---
GROQ_MODEL = "llama-3.3-70b-versatile"

TARGET_TITLES = [
    "CTO", "Chief Technology Officer",
    "CEO", "Chief Executive Officer",
    "Founder", "Co-Founder",
    "VP of Engineering", "Vice President Engineering",
    "Head of Engineering", "Head of AI",
    "VP Technology", "Director of Engineering",
    "Chief AI Officer", "Head of Machine Learning",
]

COMPANY_NAME = "Omnithrive Technologies"
COMPANY_PITCH = (
    "Omnithrive Technologies builds and deploys custom AI solutions, "
    "including full-stack AI applications, data pipelines, LLM integrations, "
    "and end-to-end machine learning systems. We help companies ship AI "
    "products in weeks instead of spending months hiring."
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db")

# --- SMTP / Email Sending ---
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)
FROM_NAME = os.getenv("FROM_NAME", "Omnithrive")

# --- IMAP / Reply Tracking ---
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", SMTP_USER)
IMAP_PASS = os.getenv("IMAP_PASS", SMTP_PASS)

# --- Dashboard Server ---
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5000"))
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")


def check_keys():
    print("")
    print("--- Config Status ---")
    print("  GROQ_API_KEY: " + ("OK" if GROQ_API_KEY else "MISSING"))
    print("  ANTHROPIC_API_KEY: " + ("OK (fallback active)" if ANTHROPIC_API_KEY else "not set (no fallback)"))
    if HUNTER_API_KEYS:
        print("  HUNTER_API_KEYS: " + str(len(HUNTER_API_KEYS)) + " keys (~" + str(len(HUNTER_API_KEYS) * 25) + " credits)")
    else:
        print("  HUNTER_API_KEYS: none (free pipeline only)")
    print()


if __name__ == "__main__":
    check_keys()