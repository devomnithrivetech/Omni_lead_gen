"""
Waterfall Enricher - Smart skip + Hunter fallback.

Skips companies that already have complete data.
Only uses Hunter credits on leads where free methods failed.

Flow:
  1. CHECK  -> skip if lead already has email + description + industry
  2. DDG    -> find website + search snippets
  3. SCRAPE -> crawl /about /team /leadership pages + meta tags
  4. GROQ   -> extract decision maker from real scraped text
  5. EMAIL  -> generate patterns + SMTP verify
  6. HUNTER -> ONLY if still no email (paid credits, last resort)
  7. GROQ   -> company description + industry from real data
"""
import re
import time
import json
import random
import socket
import smtplib
import requests
import dns.resolver
from config import GROQ_API_KEY, GROQ_MODEL, TARGET_TITLES, HUNTER_API_KEYS, ANTHROPIC_API_KEY
from db import get_connection, get_leads_by_status, update_lead, get_stats
from keywords import extract_keywords_string


# ============================================================
#  HUNTER KEY ROTATOR
# ============================================================
class HunterRotator:
    def __init__(self, keys):
        self.keys = list(keys)
        self.exhausted = set()
        self.used = {k: 0 for k in keys}

    def get_key(self):
        for k in self.keys:
            if k not in self.exhausted:
                return k
        return None

    def mark_used(self, key):
        self.used[key] += 1

    def mark_exhausted(self, key):
        self.exhausted.add(key)

    def has_credits(self):
        return bool(self.keys) and len(self.exhausted) < len(self.keys)

    def summary(self):
        if not self.keys:
            return
        total_used = sum(self.used.values())
        if total_used == 0:
            print("  Hunter: 0 credits used (not needed)")
            return
        print("  --- Hunter Credits ---")
        for i, k in enumerate(self.keys):
            label = k[:8] + "..." + k[-4:]
            status = "EXHAUSTED" if k in self.exhausted else "active"
            print("    Key " + str(i + 1) + " (" + label + "): " + str(self.used[k]) + " used [" + status + "]")


hunter = HunterRotator(HUNTER_API_KEYS)


# ============================================================
#  HELPERS
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
    return url.split("/")[0].split("?")[0]


def is_lead_complete(lead):
    """Check if a lead already has all required info."""
    has_email = bool((lead.get("decision_maker_email") or "").strip())
    has_desc = bool((lead.get("company_description") or "").strip())
    has_industry = bool((lead.get("company_industry") or "").strip())
    has_keywords = bool((lead.get("tech_keywords") or "").strip())
    return has_email and has_desc and has_industry and has_keywords


# ============================================================
#  STEP 1: DUCKDUCKGO - Find website + snippets
# ============================================================
def find_company_website(company_name):
    from scrapling.fetchers import StealthyFetcher
    from urllib.parse import unquote, quote_plus

    try:
        query = quote_plus(company_name + " official website")
        url = "https://html.duckduckgo.com/html/?q=" + query
        response = StealthyFetcher.fetch(url, headless=True, disable_resources=True)

        if response.status != 200:
            return "", ""

        links = response.css("a.result__a")
        snippets = response.css("a.result__snippet")
        snippet_texts = []
        for s in snippets[:5]:
            try:
                txt = ""
                if hasattr(s, "text") and s.text:
                    txt = s.text.strip()
                if not txt and hasattr(s, "get_all_text"):
                    txt = (s.get_all_text() or "").strip()
                if txt and len(txt) > 20:
                    snippet_texts.append(txt)
            except Exception:
                continue
        ddg_snippets = " | ".join(snippet_texts[:3])

        skip_domains = [
            "google.", "linkedin.", "facebook.", "twitter.", "youtube.",
            "wikipedia.", "instagram.", "glassdoor.", "indeed.", "yelp.",
            "bloomberg.", "crunchbase.", "x.com", "tiktok.", "duckduckgo.",
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
                if not any(s in actual.lower() for s in skip_domains):
                    return actual, ddg_snippets
            except Exception:
                continue

        return "", ddg_snippets

    except Exception as e:
        print(" DDG error: " + str(e)[:60])
        return "", ""


# ============================================================
#  STEP 2: SCRAPLING - Scrape website pages
# ============================================================
def scrape_company_pages(website_url):
    from scrapling.fetchers import StealthyFetcher

    all_text = ""
    all_emails = []
    meta_descriptions = []

    base = website_url.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base

    pages = [
        base, base + "/about", base + "/about-us",
        base + "/contact", base + "/contact-us",
        base + "/team", base + "/our-team", base + "/leadership",
    ]

    for page_url in pages:
        try:
            response = StealthyFetcher.fetch(
                page_url, headless=True, disable_resources=True,
            )
            if response.status == 200:
                for sel in ['meta[name="description"]', 'meta[property="og:description"]']:
                    try:
                        meta = response.css_first(sel)
                        if meta:
                            content = meta.attrib.get("content", "").strip()
                            if content and len(content) > 20 and content not in meta_descriptions:
                                meta_descriptions.append(content)
                    except Exception:
                        pass
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
        "meta_descriptions": meta_descriptions,
    }


# ============================================================
#  STEP 3: GROQ - Extract decision maker from scraped text
# ============================================================
def groq_extract_dm(company_name, site_text, emails_found):
    if not GROQ_API_KEY:
        return None
    from groq import Groq

    emails_str = ", ".join(emails_found[:10]) if emails_found else "none"

    prompt = (
        "I scraped the website of '" + company_name + "'. "
        "Find the best senior person (CTO, CEO, Founder, VP Engineering, Head of AI, etc).\n\n"
        "WEBSITE TEXT:\n" + (site_text[:2500] if site_text else "(none)") + "\n\n"
        "EMAILS FOUND: " + emails_str + "\n\n"
        "ONLY use names you can see in the text. Do NOT invent names.\n"
        "If you see a name + title, return them.\n"
        "If only emails visible, return the best one.\n"
        "If nothing useful, return empty strings.\n\n"
        "Respond ONLY in JSON:\n"
        '{"first_name": "", "last_name": "", "title": "", "email": ""}'
    )

    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "Extract real people from website text. Never invent. JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1, max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        result = json.loads(raw.strip())
        first = result.get("first_name", "").strip()
        last = result.get("last_name", "").strip()
        if first or result.get("email", "").strip():
            return {
                "first_name": first,
                "last_name": last,
                "full_name": (first + " " + last).strip(),
                "title": result.get("title", "").strip(),
                "email": result.get("email", "").strip(),
            }
        return None
    except Exception as e:
        print(" err:" + str(e)[:40])
        return None


# ============================================================
#  STEP 4: EMAIL PATTERNS + STEP 5: SMTP VERIFY
# ============================================================
def generate_email_patterns(first_name, last_name, domain):
    if not first_name or not domain:
        return []
    first = first_name.lower().strip()
    last = last_name.lower().strip() if last_name else ""
    if last:
        return [
            first + "@" + domain,
            first + "." + last + "@" + domain,
            first[0] + last + "@" + domain,
            first + last + "@" + domain,
            first[0] + "." + last + "@" + domain,
            last + "." + first + "@" + domain,
            first + "_" + last + "@" + domain,
            first + last[0] + "@" + domain,
        ]
    return [first + "@" + domain]


def get_mx_record(domain):
    try:
        records = dns.resolver.resolve(domain, "MX")
        mx = sorted(records, key=lambda r: r.preference)[0]
        return str(mx.exchange).rstrip(".")
    except Exception:
        return None


def verify_email_smtp(email, mx_host):
    try:
        smtp = smtplib.SMTP(timeout=10)
        smtp.connect(mx_host, 25)
        smtp.helo("verify.client.com")
        smtp.mail("check@verify.com")
        code, _ = smtp.rcpt(email)
        smtp.quit()
        if code == 250:
            return True
        elif code in (550, 551, 553):
            return False
        return None
    except Exception:
        return None


def find_valid_email(patterns, domain):
    if not patterns:
        return "", "none"
    mx_host = get_mx_record(domain)
    if not mx_host:
        return patterns[0], "pattern_guess"
    for email in patterns:
        result = verify_email_smtp(email, mx_host)
        if result is True:
            return email, "smtp_verified"
        time.sleep(0.5)
    return patterns[0], "pattern_guess"


# ============================================================
#  STEP 6: HUNTER.IO (only for leads still missing email)
# ============================================================
def hunter_search(domain):
    key = hunter.get_key()
    if not key:
        return None

    try:
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": key, "limit": 10},
            timeout=30,
        )
        if resp.status_code in (402, 429):
            hunter.mark_exhausted(key)
            next_key = hunter.get_key()
            if not next_key:
                return None
            resp = requests.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "api_key": next_key, "limit": 10},
                timeout=30,
            )
            key = next_key
            if resp.status_code in (402, 429):
                hunter.mark_exhausted(key)
                return None

        if resp.status_code != 200:
            return None

        hunter.mark_used(key)
        data = resp.json().get("data", {})
        emails_list = data.get("emails", [])
        if not emails_list:
            return None

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

            entry = {"name": name, "title": position, "email": email,
                     "linkedin": person.get("linkedin", "") or ""}

            is_senior = seniority in ("executive", "senior", "c-level")
            if not is_senior:
                for sw in senior_words:
                    if sw in position.lower():
                        is_senior = True
                        break
            if is_senior and name:
                return entry
            if name and not fallback:
                fallback = entry

        return best or fallback
    except Exception as e:
        print(" err:" + str(e)[:40])
        return None


# ============================================================
#  CLAUDE FALLBACKS (used when Groq fails)
# ============================================================
def claude_extract_dm(company_name, site_text, emails_found):
    if not ANTHROPIC_API_KEY:
        return None
    import anthropic

    emails_str = ", ".join(emails_found[:10]) if emails_found else "none"
    prompt = (
        "I scraped the website of '" + company_name + "'. "
        "Find the best senior person (CTO, CEO, Founder, VP Engineering, Head of AI, etc).\n\n"
        "WEBSITE TEXT:\n" + (site_text[:2500] if site_text else "(none)") + "\n\n"
        "EMAILS FOUND: " + emails_str + "\n\n"
        "ONLY use names you can see in the text. Do NOT invent names.\n"
        "If nothing useful, return empty strings.\n\n"
        "Respond ONLY in JSON:\n"
        '{"first_name": "", "last_name": "", "title": "", "email": ""}'
    )
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
        if not m:
            return None
        result = json.loads(m.group(0))
        first = result.get("first_name", "").strip()
        if first or result.get("email", "").strip():
            last = result.get("last_name", "").strip()
            return {
                "first_name": first,
                "last_name": last,
                "full_name": (first + " " + last).strip(),
                "title": result.get("title", "").strip(),
                "email": result.get("email", "").strip(),
            }
        return None
    except Exception as e:
        print(" claude err:" + str(e)[:40])
        return None


def claude_extract_company_info(company_name, site_text="", job_description="",
                                job_title="", meta_descriptions=None, ddg_snippets=""):
    if not ANTHROPIC_API_KEY:
        return "", ""
    import anthropic

    parts = []
    if meta_descriptions:
        parts.append("Meta descriptions:\n" + "\n".join(meta_descriptions[:3]))
    if ddg_snippets:
        parts.append("Search snippets:\n" + ddg_snippets)
    if site_text:
        parts.append("Website text:\n" + site_text[:1500])
    if job_description:
        parts.append("Job posting:\n" + job_description[:500])
    if not parts:
        return "", ""

    context = "\n\n".join(parts)
    prompt = (
        "From the real data below about '" + company_name + "', give:\n"
        "1. Brief 1-2 sentence description of what they do\n"
        "2. Industry (e.g. FinTech, Healthcare, SaaS, Cybersecurity, AI/ML, etc.)\n\n"
        "ONLY use info from data below.\n\n"
        "--- DATA ---\n" + context + "\n--- END ---\n\n"
        'Respond ONLY in JSON: {"description": "...", "industry": "..."}'
    )
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
        if not m:
            return "", ""
        result = json.loads(m.group(0))
        return result.get("description", ""), result.get("industry", "")
    except Exception as e:
        print("    [Info] claude err:" + str(e)[:40])
        return "", ""


# ============================================================
#  STEP 7: COMPANY INFO FROM REAL DATA
# ============================================================
def extract_company_info(company_name, site_text="", job_description="",
                         job_title="", meta_descriptions=None, ddg_snippets=""):
    if not GROQ_API_KEY:
        return "", ""
    from groq import Groq

    parts = []
    if meta_descriptions:
        parts.append("Meta descriptions:\n" + "\n".join(meta_descriptions[:3]))
    if ddg_snippets:
        parts.append("Search snippets:\n" + ddg_snippets)
    if site_text:
        parts.append("Website text:\n" + site_text[:1500])
    if job_description:
        parts.append("Job posting:\n" + job_description[:500])
    if not parts:
        return "", ""

    context = "\n\n".join(parts)
    prompt = (
        "From the real data below about '" + company_name + "', give:\n"
        "1. Brief 1-2 sentence description of what they do\n"
        "2. Industry (e.g. FinTech, Healthcare, SaaS, Cybersecurity, AI/ML, etc.)\n\n"
        "ONLY use info from data below.\n\n"
        "--- DATA ---\n" + context + "\n--- END ---\n\n"
        'Respond ONLY in JSON: {"description": "...", "industry": "..."}'
    )

    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "Extract company info. JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2, max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        result = json.loads(raw.strip())
        return result.get("description", ""), result.get("industry", "")
    except Exception as e:
        print("    [Info] err:" + str(e)[:40])
        return "", ""


# ============================================================
#  EMAIL HELPERS
# ============================================================
def classify_email(email):
    generic = ["info@", "contact@", "hello@", "support@", "admin@",
               "sales@", "help@", "team@", "office@", "hr@", "jobs@",
               "careers@", "press@", "media@", "enquiries@"]
    for p in generic:
        if email.lower().startswith(p):
            return "generic"
    return "personal"


def pick_best_email(emails, company_domain):
    personal, generic, other = [], [], []
    for email in emails:
        domain = email.split("@")[1].lower() if "@" in email else ""
        etype = classify_email(email)
        if company_domain and company_domain in domain:
            (personal if etype == "personal" else generic).append(email)
        else:
            other.append(email)
    if personal:
        return personal[0], "personal"
    if generic:
        return generic[0], "generic"
    if other:
        return other[0], "other"
    return "", "none"


# ============================================================
#  MAIN ENRICHER
# ============================================================
def enrich_lead(lead, seen_companies):
    company = lead["company_name"]
    company_key = company.lower().strip()

    # CHECK: Already complete? Skip instantly.
    if is_lead_complete(lead):
        return "already_complete"

    # Check cache from this run
    if company_key in seen_companies:
        cached = seen_companies[company_key]
        if cached:
            update_lead(lead["id"], **cached, status="enriched")
            return "cached_hit"
        else:
            # Even cached miss - check if we need desc/industry
            if not lead.get("company_description"):
                update_lead(lead["id"], status="no_match")
            return "cached_miss"

    print("  --- " + company + " ---")

    # Check what's already in DB for this lead
    existing_website = lead.get("company_website", "") or ""
    existing_domain = lead.get("company_domain", "") or ""
    existing_email = lead.get("decision_maker_email", "") or ""
    existing_desc = lead.get("company_description", "") or ""
    need_email = not existing_email
    need_desc = not existing_desc

    # ---- STEP 1: Find website (skip if already have it) ----
    website = existing_website
    domain = existing_domain
    ddg_snippets = ""

    if not website:
        print("    [DDG] Searching...", end="")
        website, ddg_snippets = find_company_website(company)
        if not website:
            print(" no website")
            # Still extract keywords from job title + description
            kw_text = " ".join(filter(None, [
                lead.get("job_title", ""), lead.get("job_description", ""),
            ]))
            tech_kw = extract_keywords_string(kw_text)
            save_fields = {"tech_keywords": tech_kw}
            if ddg_snippets and need_desc:
                desc, industry = extract_company_info(
                    company, ddg_snippets=ddg_snippets,
                    job_description=lead.get("job_description", ""),
                    job_title=lead.get("job_title", ""),
                )
                if desc:
                    save_fields["company_description"] = desc
                    save_fields["company_industry"] = industry
            update_lead(lead["id"], **save_fields, status="no_match")
            seen_companies[company_key] = None
            return "no_match"
        domain = extract_domain_from_url(website)
        print(" " + domain)
    else:
        if not domain:
            domain = extract_domain_from_url(website)
        print("    [Cached] " + domain)

    # ---- STEP 2: Scrape website ----
    print("    [Scrape] Crawling...", end="")
    pages = scrape_company_pages(website)
    site_text = pages["text"]
    scraped_emails = pages["emails"]
    meta_descs = pages["meta_descriptions"]
    print(" " + str(len(scraped_emails)) + " emails")

    dm_name = lead.get("decision_maker_name", "") or ""
    dm_title = lead.get("decision_maker_title", "") or ""
    dm_email = existing_email
    dm_linkedin = lead.get("decision_maker_linkedin", "") or ""

    if need_email:
        # ---- STEP 3: Groq extract decision maker (Claude fallback) ----
        print("    [Groq] Finding DM...", end="")
        dm = groq_extract_dm(company, site_text, scraped_emails)
        if not dm and ANTHROPIC_API_KEY:
            print(" (Groq failed, trying Claude...)", end="")
            dm = claude_extract_dm(company, site_text, scraped_emails)

        if dm:
            dm_name = dm.get("full_name", "") or dm_name
            dm_title = dm.get("title", "") or dm_title
            if dm.get("email"):
                dm_email = dm["email"]
                print(" " + dm_name + " - " + dm_email)
            elif dm.get("first_name"):
                print(" " + dm_name + " (no email yet)")
                # ---- STEP 4+5: Email patterns + SMTP ----
                print("    [SMTP] Verifying...", end="")
                patterns = generate_email_patterns(dm["first_name"], dm.get("last_name", ""), domain)
                if patterns:
                    dm_email, src = find_valid_email(patterns, domain)
                    if dm_email:
                        print(" " + dm_email + " (" + src + ")")
                    else:
                        print(" none verified")
            else:
                print(" no person found")
        else:
            print(" nothing found")
            # Fallback: best scraped email
            if scraped_emails:
                best, etype = pick_best_email(scraped_emails, domain)
                if best and etype == "personal":
                    dm_email = best
                    print("    [Fallback] " + dm_email)

        # ---- STEP 6: HUNTER (only if STILL no email) ----
        if not dm_email and domain and hunter.has_credits():
            print("    [Hunter] Searching...", end="")
            h_result = hunter_search(domain)
            if h_result and h_result.get("email"):
                dm_name = h_result.get("name", "") or dm_name
                dm_title = h_result.get("title", "") or dm_title
                dm_email = h_result["email"]
                dm_linkedin = h_result.get("linkedin", "") or dm_linkedin
                print(" FOUND: " + dm_name + " - " + dm_email)
            else:
                print(" no result")

    # ---- STEP 7: Company description (only if missing, Claude fallback) ----
    desc = existing_desc
    industry = lead.get("company_industry", "") or ""
    if need_desc:
        desc, industry = extract_company_info(
            company, site_text, lead.get("job_description", ""),
            lead.get("job_title", ""),
            meta_descriptions=meta_descs, ddg_snippets=ddg_snippets,
        )
        if not desc and ANTHROPIC_API_KEY:
            desc, industry = claude_extract_company_info(
                company, site_text, lead.get("job_description", ""),
                lead.get("job_title", ""),
                meta_descriptions=meta_descs, ddg_snippets=ddg_snippets,
            )
        if desc:
            print("    [Info] " + industry)

    # ---- EXTRACT TECH KEYWORDS ----
    kw_text = " ".join(filter(None, [
        lead.get("job_title", ""),
        lead.get("job_description", ""),
        site_text,
    ]))
    tech_kw = extract_keywords_string(kw_text)
    if tech_kw:
        kw_count = len(tech_kw.split(", "))
        print("    [Keywords] " + str(kw_count) + " found")

    # ---- SAVE ----
    fields = {
        "company_website": website,
        "company_domain": domain,
        "company_contact_email": ", ".join(scraped_emails[:3]),
        "company_description": desc,
        "company_industry": industry,
        "decision_maker_name": dm_name,
        "decision_maker_title": dm_title,
        "decision_maker_email": dm_email,
        "decision_maker_linkedin": dm_linkedin,
        "tech_keywords": tech_kw,
    }

    if dm_email:
        update_lead(lead["id"], **fields, status="enriched")
        seen_companies[company_key] = fields
        return "enriched"
    else:
        update_lead(lead["id"], **fields, status="no_match")
        seen_companies[company_key] = None
        return "partial"


# ============================================================
#  RUN ENRICHER - processes ALL leads, skips complete ones
# ============================================================
def run_enricher():
    print("")
    print("=" * 60)
    print("  ENRICHER (Smart Skip + Hunter Fallback)")
    print("=" * 60)
    print("")

    providers = ["DuckDuckGo", "Scrapling", "Groq", "SMTP Verify"]
    if HUNTER_API_KEYS:
        providers.append("Hunter.io (" + str(len(HUNTER_API_KEYS)) + " keys)")
    print("  Providers: " + ", ".join(providers))
    print("")

    # Get ALL leads, not just "scraped"
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM leads WHERE status != 'no_match' ORDER BY company_name"
    ).fetchall()
    conn.close()
    all_leads = [dict(r) for r in rows]

    if not all_leads:
        print("No leads in database.")
        return 0

    # Count what we have
    total = len(all_leads)
    already_complete = sum(1 for l in all_leads if is_lead_complete(l))
    need_work = total - already_complete

    print("  Total leads: " + str(total) + " (no_match excluded)")
    print("  Already complete (skipping): " + str(already_complete))
    print("  Need enrichment: " + str(need_work))
    print("")

    if need_work == 0:
        print("All leads are complete! Nothing to do.")
        get_stats()
        return 0

    enriched = 0
    partial = 0
    no_match = 0
    skipped = 0
    seen_companies = {}

    for lead in all_leads:
        result = enrich_lead(lead, seen_companies)

        if result == "already_complete":
            skipped += 1
        elif result in ("enriched", "cached_hit"):
            enriched += 1
        elif result == "partial":
            partial += 1
        elif result in ("no_match", "cached_miss"):
            no_match += 1

        if result not in ("already_complete", "cached_hit", "cached_miss"):
            time.sleep(random.uniform(2, 4))

    print("")
    print("=" * 60)
    print("  DONE:")
    print("    Skipped (already complete): " + str(skipped))
    print("    Newly enriched: " + str(enriched))
    print("    Partial (no email): " + str(partial))
    print("    No website: " + str(no_match))
    hunter.summary()
    print("=" * 60)

    get_stats()
    return enriched


if __name__ == "__main__":
    run_enricher()