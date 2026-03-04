"""
Waterfall Enricher: Find decision makers using multiple sources.

Priority order:
  1. Scrapling - scrape company website (FREE, unlimited)
  2. Hunter.io API (25 free credits per key, multiple keys supported)
  3. Groq LLM guess (free, unlimited - last resort)
"""
import re
import time
import json
import random
import requests
from config import (
    GROQ_API_KEY, GROQ_MODEL,
    HUNTER_API_KEYS, TARGET_TITLES,
)
from db import get_leads_by_status, update_lead, get_stats


# ============================================================
#  HUNTER KEY ROTATOR - cycles through multiple API keys
# ============================================================
class HunterKeyRotator:
    def __init__(self, keys):
        self.keys = list(keys)
        self.credits_per_key = 25
        self.used = {k: 0 for k in self.keys}
        self.current_idx = 0

    def get_key(self):
        """Get next available key with credits remaining."""
        for _ in range(len(self.keys)):
            if self.current_idx >= len(self.keys):
                self.current_idx = 0
            key = self.keys[self.current_idx]
            if self.used[key] < self.credits_per_key:
                return key
            self.current_idx += 1
        return None  # All keys exhausted

    def use(self, key):
        self.used[key] += 1
        # If this key is exhausted, move to next
        if self.used[key] >= self.credits_per_key:
            self.current_idx += 1

    def total_remaining(self):
        total = 0
        for k in self.keys:
            total += self.credits_per_key - self.used[k]
        return total

    def summary(self):
        print("  --- Hunter Key Usage ---")
        for i, k in enumerate(self.keys):
            u = self.used[k]
            r = self.credits_per_key - u
            label = k[:8] + "..." + k[-4:]
            print("    Key " + str(i + 1) + " (" + label + "): " + str(u) + " used, " + str(r) + " remaining")
        print("    Total remaining: " + str(self.total_remaining()))


hunter_keys = HunterKeyRotator(HUNTER_API_KEYS)


# ============================================================
#  LAYER 1: SCRAPLING - Find website + scrape contact info
# ============================================================
def extract_emails_from_text(text):
    pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    emails = re.findall(pattern, text)
    skip = [
        "example.com", "email.com", "domain.com", "yourcompany",
        "sentry.io", "webpack", "babel", ".png", ".jpg", ".gif",
        "wixpress", "schema.org", "noreply", "no-reply",
        "unsubscribe", "mailer-daemon", "postmaster",
    ]
    cleaned = []
    for e in emails:
        e_lower = e.lower()
        if not any(s in e_lower for s in skip) and len(e) < 60:
            cleaned.append(e)
    return list(set(cleaned))


def extract_domain_from_url(url):
    if not url:
        return ""
    url = url.lower().strip()
    for prefix in ["https://", "http://", "www."]:
        if url.startswith(prefix):
            url = url[len(prefix):]
    domain = url.split("/")[0].split("?")[0]
    return domain


def find_company_website(company_name):
    """Use DuckDuckGo HTML to find company website."""
    from scrapling.fetchers import StealthyFetcher
    from urllib.parse import unquote, quote_plus

    try:
        query = quote_plus(company_name + " official website")
        url = "https://html.duckduckgo.com/html/?q=" + query
        response = StealthyFetcher.fetch(url, headless=True, disable_resources=True)

        if response.status != 200:
            return ""

        links = response.css("a.result__a")

        skip_domains = [
            "google.", "linkedin.", "facebook.",
            "twitter.", "youtube.", "wikipedia.",
            "instagram.", "glassdoor.", "indeed.",
            "yelp.", "bloomberg.", "crunchbase.",
            "x.com", "tiktok.", "duckduckgo.",
            "amazon.", "reddit.", "github.",
        ]

        for link in links[:5]:
            try:
                href = link.attrib.get("href", "")
                if "uddg=" in href:
                    encoded = href.split("uddg=")[1].split("&")[0]
                    actual = unquote(encoded)
                elif href.startswith("http"):
                    actual = href
                else:
                    continue

                actual_lower = actual.lower()
                if not any(s in actual_lower for s in skip_domains):
                    return actual
            except Exception:
                continue

        return ""

    except Exception as e:
        print(" DDG error: " + str(e)[:60])
        return ""


def scrape_company_contacts(website_url):
    """Scrape company website for contact info and text content."""
    from scrapling.fetchers import StealthyFetcher

    all_text = ""
    all_emails = []

    base = website_url.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base

    pages = [
        base,
        base + "/about",
        base + "/about-us",
        base + "/contact",
        base + "/contact-us",
        base + "/team",
        base + "/our-team",
        base + "/leadership",
    ]

    for page_url in pages:
        try:
            response = StealthyFetcher.fetch(
                page_url, headless=True, disable_resources=True,
            )
            if response.status == 200:
                try:
                    page_text = response.get_all_text() or ""
                except Exception:
                    page_text = ""
                if page_text:
                    all_text += page_text + "\n"
                    all_emails.extend(extract_emails_from_text(page_text))
            time.sleep(random.uniform(1.5, 3))
        except Exception:
            continue

    return {
        "text": all_text[:5000],
        "emails": list(set(all_emails))[:10],
    }


def classify_email(email, company_domain):
    generic_prefixes = [
        "info@", "contact@", "hello@", "support@", "admin@",
        "sales@", "help@", "team@", "office@", "enquiries@",
        "hr@", "jobs@", "careers@", "press@", "media@",
    ]
    e_lower = email.lower()
    for prefix in generic_prefixes:
        if e_lower.startswith(prefix):
            return "generic"
    return "personal"


def pick_best_email(emails, company_domain):
    personal = []
    generic = []
    other = []

    for email in emails:
        domain = email.split("@")[1].lower() if "@" in email else ""
        etype = classify_email(email, company_domain)

        if company_domain and company_domain in domain:
            if etype == "personal":
                personal.append(email)
            else:
                generic.append(email)
        else:
            other.append(email)

    if personal:
        return personal[0], "personal"
    if generic:
        return generic[0], "generic"
    if other:
        return other[0], "other"
    return "", "none"


def scrapling_enrich(company_name):
    """Layer 1: Use Scrapling to find website and scrape contacts."""
    print("    [Scrapling] Finding website...", end="")
    website = find_company_website(company_name)
    if not website:
        print(" not found")
        return None

    domain = extract_domain_from_url(website)
    print(" " + domain)

    print("    [Scrapling] Scraping contacts...", end="")
    contacts = scrape_company_contacts(website)
    emails = contacts["emails"]
    print(" " + str(len(emails)) + " emails")

    best_email, email_type = pick_best_email(emails, domain)

    return {
        "website": website,
        "domain": domain,
        "emails": emails,
        "text": contacts["text"],
        "best_email": best_email,
        "email_type": email_type,
    }


# ============================================================
#  LAYER 2: HUNTER.IO API (multiple keys)
# ============================================================
def hunter_enrich(domain):
    """Layer 2: Use Hunter.io to find decision makers by domain."""
    key = hunter_keys.get_key()
    if not key:
        return None

    print("    [Hunter] Searching " + domain + "...", end="")

    try:
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": key, "limit": 10},
            timeout=30,
        )

        if resp.status_code == 429:
            print(" rate limited, trying next key")
            hunter_keys.used[key] = hunter_keys.credits_per_key  # Mark exhausted
            # Try next key
            next_key = hunter_keys.get_key()
            if next_key:
                resp = requests.get(
                    "https://api.hunter.io/v2/domain-search",
                    params={"domain": domain, "api_key": next_key, "limit": 10},
                    timeout=30,
                )
                key = next_key
            else:
                print(" all keys exhausted")
                return None

        if resp.status_code == 402:
            print(" credits exhausted, switching key")
            hunter_keys.used[key] = hunter_keys.credits_per_key
            return hunter_enrich(domain)  # Retry with next key

        if resp.status_code != 200:
            print(" error " + str(resp.status_code))
            return None

        data = resp.json().get("data", {})
        hunter_keys.use(key)

        emails_list = data.get("emails", [])
        if not emails_list:
            print(" no results")
            return None

        # Build target keywords
        senior_words = [
            "cto", "ceo", "founder", "co-founder", "vp", "vice president",
            "head", "director", "chief", "partner", "owner",
        ]

        best = None
        fallback = None

        for person in emails_list:
            email = person.get("value", "")
            if not email or person.get("type") == "generic":
                continue

            first = person.get("first_name", "") or ""
            last = person.get("last_name", "") or ""
            name = (first + " " + last).strip()
            position = person.get("position", "") or ""
            seniority = person.get("seniority", "") or ""

            entry = {
                "name": name,
                "title": position,
                "email": email,
                "linkedin": person.get("linkedin", "") or "",
                "source": "hunter.io",
            }

            # Check seniority or position for senior roles
            is_senior = seniority in ("executive", "senior", "c-level")
            pos_lower = position.lower()
            if not is_senior:
                for sw in senior_words:
                    if sw in pos_lower:
                        is_senior = True
                        break

            if is_senior and name:
                best = entry
                break

            if name and not fallback:
                fallback = entry

        result = best or fallback
        if result:
            print(" FOUND: " + result["name"])
        else:
            print(" no decision maker")
        return result

    except Exception as e:
        print(" error: " + str(e)[:60])
        return None


# ============================================================
#  LAYER 3: GROQ LLM GUESS (last resort)
# ============================================================
def groq_enrich(company_name, domain, scraped_data):
    """Layer 3: Use Groq to guess decision maker from scraped data."""
    if not GROQ_API_KEY:
        return None

    from groq import Groq

    print("    [Groq] Analyzing scraped data...", end="")

    emails_str = ", ".join(scraped_data.get("emails", [])[:5])
    site_text = scraped_data.get("text", "")[:1500]

    prompt = (
        "I am researching " + company_name + " (domain: " + domain + ") "
        "to find the best decision maker to contact about AI services.\n\n"
        "Website text:\n" + (site_text if site_text else "(none)") + "\n\n"
        "Emails found: " + (emails_str if emails_str else "none") + "\n\n"
        "Based on this, identify the most likely CTO/VP/Founder.\n"
        "If you can see names on the website, use them.\n"
        "If not, pick the best email from the list.\n\n"
        "Respond ONLY in JSON, no markdown:\n"
        '{"name": "Name", "title": "Title", "email": "email@domain.com", '
        '"linkedin": ""}'
    )

    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You identify decision makers at companies. "
                        "Respond with valid JSON only, no markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=200,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        result = json.loads(raw)
        result["source"] = "groq"
        if result.get("email"):
            print(" FOUND: " + result.get("name", "?"))
        else:
            print(" no result")
        return result if result.get("email") else None

    except Exception as e:
        print(" error: " + str(e)[:60])
        return None


# ============================================================
#  COMPANY INFO EXTRACTOR - desc + industry via Groq
# ============================================================
def extract_company_info(company_name, site_text, job_description=""):
    """Use Groq to extract company description and industry from scraped text."""
    if not GROQ_API_KEY:
        return "", ""

    from groq import Groq

    context = ""
    if site_text:
        context += "Website text:\n" + site_text[:2000] + "\n\n"
    if job_description:
        context += "Job posting:\n" + job_description[:1000] + "\n\n"

    if not context.strip():
        return "", ""

    prompt = (
        "Based on the text below about " + company_name + ", "
        "provide:\n"
        "1. A brief 1-2 sentence description of what the company does\n"
        "2. The industry they work in (e.g. 'FinTech', 'Healthcare', 'SaaS', "
        "'E-commerce', 'Cybersecurity', 'AI/ML', 'Cloud Computing', etc.)\n\n"
        + context +
        "Respond ONLY in JSON, no markdown:\n"
        '{"description": "What the company does in 1-2 sentences", '
        '"industry": "Industry name"}'
    )

    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract company information. "
                        "Be concise and accurate. "
                        "Respond with valid JSON only, no markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=200,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        result = json.loads(raw)
        desc = result.get("description", "")
        industry = result.get("industry", "")
        if desc:
            print("    [Groq] Company info: " + industry)
        return desc, industry

    except Exception as e:
        print("    [Groq] Info error: " + str(e)[:40])
        return "", ""


# ============================================================
#  MAIN WATERFALL ENRICHER
# ============================================================
def enrich_lead(lead, seen_companies):
    """Run the waterfall enrichment for a single lead."""
    company = lead["company_name"]
    company_key = company.lower().strip()

    # Check cache
    if company_key in seen_companies:
        cached = seen_companies[company_key]
        if cached:
            update_lead(lead["id"], **cached, status="enriched")
            return "cached_hit"
        else:
            update_lead(lead["id"], status="no_match")
            return "cached_miss"

    print("  --- " + company + " ---")

    # ---- LAYER 1: Scrapling ----
    scraped = scrapling_enrich(company)

    website = ""
    domain = ""
    all_emails = []
    site_text = ""

    if scraped:
        website = scraped.get("website", "")
        domain = scraped.get("domain", "")
        all_emails = scraped.get("emails", [])
        site_text = scraped.get("text", "")

        if scraped["email_type"] == "personal" and scraped["best_email"]:
            fields = {
                "company_website": website,
                "company_domain": domain,
                "company_contact_email": ", ".join(all_emails[:3]),
                "decision_maker_email": scraped["best_email"],
                "decision_maker_name": "",
                "decision_maker_title": "",
                "decision_maker_linkedin": "",
            }
            dm = None
            if domain:
                dm = hunter_enrich(domain)
            if dm:
                fields["decision_maker_name"] = dm.get("name", "")
                fields["decision_maker_title"] = dm.get("title", "")
                fields["decision_maker_email"] = dm.get("email", "") or fields["decision_maker_email"]
                fields["decision_maker_linkedin"] = dm.get("linkedin", "")

            # Extract company description + industry
            desc, industry = extract_company_info(
                company, site_text, lead.get("job_description", "")
            )
            fields["company_description"] = desc
            fields["company_industry"] = industry

            update_lead(lead["id"], **fields, status="enriched")
            seen_companies[company_key] = fields
            return "enriched"

    # ---- LAYER 2: Hunter.io ----
    dm = None
    if domain:
        dm = hunter_enrich(domain)

    # ---- LAYER 3: Groq guess ----
    if not dm and GROQ_API_KEY and scraped:
        dm = groq_enrich(company, domain, {
            "emails": all_emails,
            "text": site_text,
        })

    # Extract company description + industry
    desc, industry = "", ""
    if site_text or lead.get("job_description"):
        desc, industry = extract_company_info(
            company, site_text, lead.get("job_description", "")
        )

    # Save whatever we found
    if dm and dm.get("email"):
        fields = {
            "company_website": website,
            "company_domain": domain,
            "company_contact_email": ", ".join(all_emails[:3]),
            "company_description": desc,
            "company_industry": industry,
            "decision_maker_name": dm.get("name", ""),
            "decision_maker_title": dm.get("title", ""),
            "decision_maker_email": dm.get("email", ""),
            "decision_maker_linkedin": dm.get("linkedin", ""),
        }
        update_lead(lead["id"], **fields, status="enriched")
        seen_companies[company_key] = fields
        return "enriched"
    elif website:
        fields = {
            "company_website": website,
            "company_domain": domain,
            "company_contact_email": ", ".join(all_emails[:3]),
            "company_description": desc,
            "company_industry": industry,
        }
        update_lead(lead["id"], **fields, status="no_match")
        seen_companies[company_key] = None
        return "partial"
    else:
        update_lead(lead["id"], status="no_match")
        seen_companies[company_key] = None
        return "no_match"


def run_enricher():
    print("")
    print("=" * 60)
    print("  WATERFALL ENRICHER")
    print("  Scrapling -> Hunter.io -> Groq")
    print("=" * 60)
    print("")

    apis = ["Scrapling (unlimited)"]
    if HUNTER_API_KEYS:
        total = len(HUNTER_API_KEYS) * 25
        apis.append("Hunter.io (" + str(len(HUNTER_API_KEYS)) + " keys, ~" + str(total) + " credits)")
    if GROQ_API_KEY:
        apis.append("Groq LLM (unlimited)")
    print("  Active providers: " + ", ".join(apis))
    print("")

    leads = get_leads_by_status("scraped")
    if not leads:
        print("No scraped leads to enrich.")
        return 0

    print("Found " + str(len(leads)) + " leads to enrich.")
    print("")

    enriched = 0
    partial = 0
    no_match = 0
    seen_companies = {}

    for lead in leads:
        result = enrich_lead(lead, seen_companies)

        if result == "enriched" or result == "cached_hit":
            enriched += 1
        elif result == "partial":
            partial += 1
        else:
            no_match += 1

        if result not in ("cached_hit", "cached_miss"):
            time.sleep(random.uniform(2, 4))

    print("")
    print("=" * 60)
    msg = "  ENRICHER DONE: " + str(enriched) + " enriched"
    msg += ", " + str(partial) + " partial"
    msg += ", " + str(no_match) + " no match"
    print(msg)
    hunter_keys.summary()
    print("=" * 60)

    get_stats()
    return enriched


if __name__ == "__main__":
    run_enricher()