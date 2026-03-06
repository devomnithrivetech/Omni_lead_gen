"""
LinkedIn Job Scraper - USA + Europe, past 72 hours only.
Uses Scrapling StealthyFetcher for anti-detection.
Pulls full job descriptions from detail pages.
"""
import random
import re
import time
from urllib.parse import quote_plus

from config import (
    SEARCH_QUERIES, SEARCH_LOCATIONS, TIME_FILTER,
    MAX_PAGES_PER_QUERY, MIN_DELAY, MAX_DELAY, MAX_LEADS_PER_RUN,
)
from db import insert_lead, get_stats, get_existing_companies


# ---------------------------------------------------------------------------
#  JOB RELEVANCE FILTER
# ---------------------------------------------------------------------------
_JAVA_RE = re.compile(r'\bjava\b', re.IGNORECASE)

# Job title must contain at least one of these to be kept
_AI_TITLE_MUST = [
    "ai", "artificial intelligence", "machine learning", "ml engineer",
    "deep learning", "nlp", "natural language", "computer vision",
    "llm", "large language", "genai", "generative ai", "gen ai",
    "neural", "mlops", "llmops", "agentic", "data scientist",
    "data science", "prompt engineer", "ai research",
]


def is_relevant_job(title):
    """
    Return True only if the job title is genuinely AI/ML related
    AND does not reference Java (the language).
    """
    if not title:
        return False
    t = title.lower()
    # Hard-drop Java developer / Java engineer roles
    # But do NOT drop roles that mention JavaScript (a valid AI stack skill)
    if _JAVA_RE.search(t) and "javascript" not in t:
        return False
    # Must contain at least one AI-related term
    return any(kw in t for kw in _AI_TITLE_MUST)


def human_delay(min_s=None, max_s=None):
    min_s = min_s or MIN_DELAY
    max_s = max_s or MAX_DELAY
    time.sleep(random.uniform(min_s, max_s))


def build_linkedin_url(query, location="", start=0, time_filter=""):
    base = "https://www.linkedin.com/jobs/search/"
    q = quote_plus(query)
    url = base + "?keywords=" + q + "&position=1&pageNum=0&start=" + str(start)
    if location:
        url += "&location=" + quote_plus(location)
    if time_filter:
        url += "&f_TPR=" + time_filter
    return url


def css_first(element, selector):
    results = element.css(selector)
    if results and len(results) > 0:
        return results[0]
    return None


def get_text(element, selector):
    el = css_first(element, selector)
    if el is not None:
        try:
            t = el.text
            if t:
                return t.strip()
        except Exception:
            pass
    return ""


def get_attr(element, selector, attr):
    el = css_first(element, selector)
    if el is not None:
        try:
            return el.attrib.get(attr, "")
        except Exception:
            pass
    return ""


def extract_salary_from_text(text):
    """Extract salary/compensation info from job description text."""
    if not text:
        return ""

    patterns = [
        # up to $150K / up to £80,000
        r'up\s+to\s+[\$£€][\d,]+[kK]?',
        # $120,000 - $180,000 / $120K - $180K
        r'[\$£€][\d,]+[kK]?\s*[-–to]+\s*[\$£€][\d,]+[kK]?\s*(?:per\s+(?:year|annum|hr|hour))?',
        # between $120k and $180k
        r'between\s+[\$£€][\d,]+[kK]?\s+and\s+[\$£€][\d,]+[kK]?',
        # $120,000/year or $120K/yr
        r'[\$£€][\d,]+[kK]?\s*/?\s*(?:year|yr|annum|annually|per\s+year|per\s+annum|hour|hr|per\s+hour)',
        # salary/compensation: $120K - $180K
        r'(?:salary|compensation|pay|range|base|OTE)[:\s]*[\$£€][\d,]+[kK]?\s*[-–to]+\s*[\$£€][\d,]+[kK]?',
        # 120k-150k (no currency, with k)
        r'\b\d{2,3}[kK]\s*[-–]\s*\d{2,3}[kK]\b',
        # 120,000 - 180,000 USD/EUR/GBP/CHF
        r'[\d,]+[kK]?\s*[-–to]+\s*[\d,]+[kK]?\s*(?:USD|EUR|GBP|CHF)',
        # standalone $150K or £80,000
        r'[\$£€][\d,]+[kK]?\b',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            salary = match.group(0).strip()
            salary = re.sub(r'\s+', ' ', salary)
            return salary

    return ""


def scrape_job_description(job_url):
    """Fetch the full job description from a LinkedIn job detail page."""
    if not job_url:
        return ""

    from scrapling.fetchers import StealthyFetcher

    try:
        # Don't disable resources - LinkedIn needs JS to render descriptions
        response = StealthyFetcher.fetch(
            job_url,
            headless=True,
            disable_resources=False,
        )

        if response.status != 200:
            return ""

        # Try multiple selectors for job description
        for selector in [
            "div.show-more-less-html__markup",
            "div.description__text",
            "section.description",
            "div.decorated-job-posting__details",
            "article.jobs-description__container",
            "div.jobs-description-content__text",
            "div.jobs-box__html-content",
        ]:
            text = get_text(response, selector)
            if text and len(text) > 50:
                return text[:1500]

        # Fallback: grab all visible text and look for description-like content
        try:
            full_text = response.get_all_text() or ""
            if len(full_text) > 200:
                # Extract middle portion (skip nav/header, stop before footer)
                lines = full_text.split("\n")
                content_lines = []
                started = False
                for line in lines:
                    line = line.strip()
                    if not line or len(line) < 10:
                        continue
                    # Start capturing after job title indicators
                    lower = line.lower()
                    if any(w in lower for w in ["about the role", "about this role",
                            "job description", "what you'll do", "responsibilities",
                            "about the job", "the role", "overview",
                            "what we're looking for", "requirements"]):
                        started = True
                    if started:
                        content_lines.append(line)
                    if len(content_lines) > 30:
                        break
                if content_lines:
                    return "\n".join(content_lines)[:1500]
        except Exception:
            pass

        return ""

    except Exception as e:
        print("      Desc fetch error: " + str(e)[:80])
        return ""


def scrape_linkedin_jobs(query, location):
    """Scrape LinkedIn public job listings for a query+location combo."""
    from scrapling.fetchers import StealthyFetcher

    jobs = []

    for page in range(MAX_PAGES_PER_QUERY):
        start = page * 25
        url = build_linkedin_url(query, location, start, TIME_FILTER)
        print("    Page " + str(page + 1) + ": " + url[:90] + "...")

        try:
            response = StealthyFetcher.fetch(
                url,
                headless=True,
                disable_resources=True,
            )

            if response.status != 200:
                print("      Got status " + str(response.status) + ", skipping.")
                human_delay()
                continue

            job_cards = response.css("div.base-card")
            if not job_cards:
                job_cards = response.css("div.job-search-card")

            if not job_cards:
                print("      No job cards found.")
                break

            print("      Found " + str(len(job_cards)) + " cards.")

            for card in job_cards:
                try:
                    company = get_text(card, "a.hidden-nested-link")
                    if not company:
                        company = get_text(card, "h4.base-search-card__subtitle")
                    if not company:
                        company = get_text(card, ".base-search-card__subtitle")

                    title = get_text(card, "h3.base-search-card__title")
                    if not title:
                        title = get_text(card, "h3")

                    job_url = get_attr(card, "a.base-card__full-link", "href")
                    if not job_url:
                        job_url = get_attr(card, "a", "href")

                    job_loc = get_text(card, "span.job-search-card__location")
                    if not job_loc:
                        job_loc = get_text(card, ".base-search-card__metadata")

                    # Get posted date from time element
                    posted = get_attr(card, "time", "datetime")

                    # Get salary if shown on card
                    salary = get_text(card, "span.job-search-card__salary-info")
                    if not salary:
                        salary = get_text(card, ".base-search-card__salary")
                    if not salary:
                        salary = get_text(card, ".job-search-card__salary")

                    if company and title:
                        if not is_relevant_job(title):
                            continue  # drop Java / non-AI roles
                        jobs.append({
                            "company_name": company,
                            "job_title": title,
                            "job_url": job_url,
                            "job_location": job_loc,
                            "job_posted_date": posted,
                            "job_description": "",
                            "salary": salary,
                        })
                except Exception:
                    continue

        except Exception as e:
            print("      ERROR: " + str(e)[:100])

        human_delay()

    return jobs


def run_scraper():
    print("")
    print("=" * 60)
    print("  SCRAPER: AI jobs in USA + Europe (past 72 hours)")
    print("=" * 60)
    print("")

    # Build all query+location combos and shuffle
    combos = []
    for q in SEARCH_QUERIES:
        for loc in SEARCH_LOCATIONS:
            combos.append((q, loc))
    random.shuffle(combos)

    total_combos = len(combos)
    print("Total search combos: " + str(total_combos))
    print("(Will stop at " + str(MAX_LEADS_PER_RUN) + " leads or when done)")
    print("")

    existing_companies = get_existing_companies()
    print("Companies already in DB (will skip): " + str(len(existing_companies)))
    print("")

    total_new = 0
    total_skip = 0

    for i, (query, location) in enumerate(combos):
        idx = str(i + 1) + "/" + str(total_combos)
        print("[" + idx + "] " + query + " in " + location)
        print("-" * 50)

        jobs = scrape_linkedin_jobs(query, location)

        for job in jobs:
            if job["company_name"].strip().lower() in existing_companies:
                total_skip += 1
                continue
            inserted = insert_lead(
                company_name=job["company_name"],
                job_title=job["job_title"],
                job_description=job["job_description"],
                job_url=job["job_url"],
                job_location=job["job_location"],
                job_posted_date=job["job_posted_date"],
                salary=job.get("salary", ""),
            )
            if inserted:
                total_new += 1
                existing_companies.add(job["company_name"].strip().lower())
                msg = "  + " + job["company_name"] + " -- " + job["job_title"]
                if job["job_location"]:
                    msg += " (" + job["job_location"] + ")"
                sal = job.get("salary", "")
                if sal:
                    msg += " [" + sal + "]"
                print(msg)
            else:
                total_skip += 1

        if total_new >= MAX_LEADS_PER_RUN:
            print("Hit max leads limit (" + str(MAX_LEADS_PER_RUN) + "). Stopping.")
            break

        # Longer delay between different combos
        if i < len(combos) - 1:
            wait = random.uniform(6, 12)
            print("  Waiting " + str(int(wait)) + "s...")
            time.sleep(wait)

    print("")
    print("Scraping complete: " + str(total_new) + " new, " + str(total_skip) + " skipped")

    # Phase 2: Fetch job descriptions for new leads
    from db import get_leads_by_status, update_lead
    scraped = get_leads_by_status("scraped")
    leads_needing_desc = [l for l in scraped if not l.get("job_description")]

    if leads_needing_desc:
        print("")
        print("Fetching job descriptions for " + str(len(leads_needing_desc)) + " leads...")
        desc_count = 0
        for lead in leads_needing_desc:
            url = lead.get("job_url", "")
            if url:
                print("  Fetching desc: " + lead["company_name"] + "...", end="")
                desc = scrape_job_description(url)
                if desc:
                    fields = {"job_description": desc}
                    # Extract salary from description if not already found
                    if not (lead.get("salary") or "").strip():
                        sal = extract_salary_from_text(desc)
                        if sal:
                            fields["salary"] = sal
                            print(" OK (" + str(len(desc)) + " chars) [Salary: " + sal + "]")
                        else:
                            print(" OK (" + str(len(desc)) + " chars)")
                    else:
                        print(" OK (" + str(len(desc)) + " chars)")
                    update_lead(lead["id"], **fields)
                    desc_count += 1
                else:
                    print(" no description found")
                human_delay(3, 7)
        print("Got descriptions for " + str(desc_count) + " leads.")

    get_stats()
    return total_new


if __name__ == "__main__":
    run_scraper()