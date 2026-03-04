import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Multiple Hunter.io API keys - rotate through them (25 credits each)
# Add as HUNTER_API_KEY_1, HUNTER_API_KEY_2, etc. in .env
HUNTER_API_KEYS = []
for i in range(1, 20):
    key = os.getenv("HUNTER_API_KEY_" + str(i), "")
    if key:
        HUNTER_API_KEYS.append(key)
# Also support single key for backward compat
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

# LinkedIn time filter: r86400=24h, r259200=72h, r604800=1week
TIME_FILTER = "r86400"  # Past 24 hours

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

# --- Company Info for Outreach ---
COMPANY_NAME = "Omnithrive Technologies"
COMPANY_PITCH = (
    "Omnithrive Technologies builds and deploys custom AI solutions, "
    "including full-stack AI applications, data pipelines, LLM integrations, "
    "and end-to-end machine learning systems. We help companies ship AI "
    "products in weeks instead of spending months hiring."
)

# --- Database ---
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db")


def check_keys():
    print("")
    print("--- API Key Status ---")
    print("  GROQ_API_KEY: " + ("OK" if GROQ_API_KEY else "MISSING"))
    print("  HUNTER_API_KEYS: " + str(len(HUNTER_API_KEYS)) + " keys loaded")
    for i, k in enumerate(HUNTER_API_KEYS):
        print("    Key " + str(i + 1) + ": " + k[:8] + "..." + k[-4:])
    total_credits = len(HUNTER_API_KEYS) * 25
    print("  Total Hunter credits: ~" + str(total_credits) + "/month")
    print()


if __name__ == "__main__":
    check_keys()