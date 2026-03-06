# Omnithrive Lead Generation Pipeline

An AI-powered B2B lead generation system that scrapes LinkedIn job postings, filters for genuine AI roles, finds decision maker contacts, generates formal personalized cold emails, and sends + tracks them through a web dashboard — all automated.

Built for **Omnithrive Technologies** to target companies actively hiring AI engineers (a strong buying signal for AI services).

---

## How It Works — Full Pipeline

```
LinkedIn Jobs
     |
     v
[1] SCRAPER       scraper.py
     |  Searches for AI/ML roles (past 24-72h) — USA + 16 EU countries
     |  Filters: drops Java roles, keeps only genuine AI/ML titles
     |  Scrapes full Job Description for every kept lead
     v
[2] ENRICHER      enricher.py
     |  Finds company website via DuckDuckGo
     |  Scrapes website for decision maker (CTO, CEO, VP Eng, etc.)
     |  Extracts + SMTP-validates email
     |  Falls back to Hunter.io if SMTP fails
     |  Extracts company description + industry via Groq → Claude Haiku fallback
     |  Extracts 400+ AI/tech keywords from job description
     v
[3] DRAFTER       draft_emails.py / redraft_all.py
     |  Formal cold email per lead using Claude Haiku (cheapest)
     |  Reads actual JD to personalize — not generic
     |  Includes 1/10th salary pitch (their $100K hire vs our ~$10K)
     |  Strict 230-250 word limit enforced in prompt
     |  "Dear [Name]," or "Dear [Company] Team," salutation, stat hook, Warm regards closing
     v
[4] DASHBOARD     server.py  →  http://localhost:5000
     |  Review drafted emails, click "Send" per lead
     |  email_sender.py sends via SMTP (multipart/alternative — looks hand-typed)
     |  Open tracking: 1x1 ghost pixel in the HTML part
     |  Reply tracking: IMAP poller matches replies → updates status
     v
[5] EXPORT        export_xlsx.py  (optional — DB is the source of truth)
     |  Exports to leads_export.xlsx (deduplicated by company)
     v
leads_export.xlsx  (optional backup / offline review)
```

---

## File Structure

| File | Purpose |
|---|---|
| `run.py` | Master runner — full pipeline or individual stages |
| `config.py` | All settings: API keys, SMTP/IMAP, search queries, limits |
| `db.py` | SQLite database layer — schema, insert, update, tracking helpers |
| `scraper.py` | LinkedIn scraper with Java/relevance filter + JD fetcher |
| `enricher.py` | Contact + company enrichment waterfall (Groq + Claude fallback) |
| `drafter.py` | Basic Groq-based email drafter (used by `run.py draft`) |
| `draft_emails.py` | Formal Claude Haiku email drafter — recommended |
| `redraft_all.py` | Overwrites ALL existing emails with updated prompt |
| `keywords.py` | 400+ AI/ML/tech keyword extractor (11 categories) |
| `export_xlsx.py` | Formatted Excel export with deduplication + auto-filter |
| `fill_job_data.py` | Backfill missing job descriptions + company descriptions |
| `fill_keywords.py` | Backfill tech keywords for existing leads (no API cost) |
| `fill_descriptions.py` | Backfill company descriptions via Claude Haiku |
| `fill_salaries.py` | Extract salary info (regex + Claude) |
| `rescrape_descriptions.py` | Re-scrape job URLs for missing descriptions |
| **`server.py`** | **Flask dashboard server + REST API + open-tracking pixel** |
| **`email_sender.py`** | **Deliverability-optimised SMTP sender (multipart/alternative)** |
| **`reply_tracker.py`** | **IMAP inbox poller — auto-marks replied leads in DB** |
| **`templates/dashboard.html`** | **Frontend CRM dashboard (metrics bar + lead table + send UI)** |

---

## Database Schema

SQLite file: `leads.db`

```
leads
  id                      INTEGER PRIMARY KEY
  company_name            TEXT
  company_website         TEXT
  company_domain          TEXT
  company_contact_email   TEXT
  company_description     TEXT       -- 1-2 sentence summary
  company_industry        TEXT       -- e.g. FinTech, SaaS, Healthcare AI
  job_title               TEXT       -- what they are hiring for
  job_description         TEXT       -- full scraped job posting text
  job_url                 TEXT       -- LinkedIn job URL
  job_location            TEXT
  job_posted_date         TEXT
  salary                  TEXT       -- extracted if mentioned in JD
  decision_maker_name     TEXT       -- CTO, CEO, VP Eng, etc.
  decision_maker_title    TEXT
  decision_maker_email    TEXT       -- verified via SMTP
  decision_maker_linkedin TEXT
  draft_subject           TEXT       -- generated email subject line
  draft_email             TEXT       -- generated email body
  draft_linkedin_note     TEXT       -- LinkedIn connection note
  tech_keywords           TEXT       -- comma-separated AI/tech stack
  status                  TEXT       -- scraped | enriched | drafted | sent | opened | replied
  message_id              TEXT       -- SMTP Message-ID for reply matching
  sent_at                 TEXT       -- ISO timestamp when email was sent
  opened_at               TEXT       -- ISO timestamp of first open
  replied_at              TEXT       -- ISO timestamp of first reply
  created_at              TEXT
  updated_at              TEXT
```

Unique constraint on `(company_name, job_title)` prevents duplicates across runs.

---

## Lead Statuses

| Status | Meaning |
|---|---|
| `scraped` | Found on LinkedIn, not yet enriched |
| `enriched` | Website + decision maker found |
| `drafted` | Email generated, ready to send |
| `no_match` | Could not find website/contact — permanently skipped on future runs |
| `sent` | Email dispatched via SMTP |
| `opened` | Recipient opened the email (tracking pixel fired) |
| `replied` | Recipient replied (detected via IMAP) |

---

## Scraper — Job Relevance Filter

Every job card is evaluated before being stored:

- **Java filter**: drops any title containing `\bjava\b` (word boundary) — e.g. "Senior Java Engineer" is dropped, but "JavaScript AI Developer" passes.
- **AI relevance filter**: title must contain at least one of: `ai`, `machine learning`, `llm`, `nlp`, `natural language`, `computer vision`, `genai`, `deep learning`, `mlops`, `data scientist`, `prompt engineer`, `agentic`, etc.
- **JD scraping**: after filtering, the full job description is scraped from the LinkedIn detail page for every kept lead.

---

## Enrichment Waterfall

For each lead, the enricher runs this sequence:

```
1. DuckDuckGo search  ->  find company website
2. Scrapling           ->  scrape website for contact info + page text
3. Regex patterns      ->  extract emails from page source
4. Groq (llama-3.3-70b) -> identify best decision maker from scraped text
   -> Claude Haiku fallback if Groq fails or rate-limits (429)
5. SMTP verification   ->  validate email deliverability
6. Hunter.io           ->  professional email lookup (supports up to 20 keys)
7. Groq / Claude       ->  extract company description + industry
8. keywords.py         ->  tag 400+ AI/tech keywords from job description
```

Lead marked `enriched` if a valid email is found. Marked `no_match` if website cannot be found (permanently skipped in future runs — no wasted retries).

---

## Email Generation

Every email generated by `draft_emails.py` / `redraft_all.py` follows these enforced rules:

| Rule | Detail |
|---|---|
| **Salutation** | `Dear [Name],` if DM known, else `Dear Hiring Manager,` |
| **JD Personalization** | References 1-2 specific responsibilities or tech from the actual job posting |
| **Salary pitch** | States we deliver for 1/10th of their hire budget (e.g. `~$10,000 vs $100,000/year`). If no salary in JD, defaults to $100K baseline |
| **Stat hook** | One of: "75% of AI projects fail ROI (IBM, 2025)" or "88% of AI pilots never reach production" |
| **CTA** | Free 2-Day AI Opportunity Audit → `cal.com/omnithrivetech-ceo` |
| **Tone** | Formal, professional — no casual language |
| **Closing** | `Warm regards,` |
| **Word count** | Strictly 230–250 words |

Model: `claude-sonnet-4-6`

To regenerate all existing emails with the latest prompt:
```bash
python redraft_all.py
```

---

## Setup

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure `.env`

```env
# Required
GROQ_API_KEY=your_groq_key

# Required for email drafting + enrichment fallback
ANTHROPIC_API_KEY=your_anthropic_key

# Optional — 25 free credits each, supports up to 20 keys
HUNTER_API_KEY=key1
HUNTER_API_KEY_2=key2
HUNTER_API_KEY_3=key3

# --- Email Sending (Module 1) ---
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=admin@omnithrivetech.com
SMTP_PASS=your_app_password        # Gmail: use an App Password, not your main password
FROM_EMAIL=admin@omnithrivetech.com
FROM_NAME=Omnithrive

# --- Reply Tracking (Module 2) ---
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=admin@omnithrivetech.com
IMAP_PASS=your_app_password

# --- Dashboard (Module 3) ---
SERVER_PORT=5000
BASE_URL=https://your-public-domain.com   # Public URL — required for tracking pixels to fire
```

> **Gmail note**: Enable 2FA and create a 16-character App Password at myaccount.google.com/apppasswords. Use that as `SMTP_PASS` and `IMAP_PASS`. For the tracking pixel to fire on recipients' email clients, `BASE_URL` must be a publicly reachable URL (not `localhost`).

### 3. Run

```bash
# Full pipeline (scrape + enrich + basic draft)
python run.py

# Individual stages
python run.py scrape    # LinkedIn scraping + JD fetch
python run.py enrich   # Website + DM + email enrichment
python run.py stats    # Show DB statistics
python run.py review   # Preview drafted emails in terminal
python run.py export   # Export to Excel

# Recommended email drafting (formal, Claude Haiku)
python draft_emails.py      # Draft only new leads (no existing email)
python redraft_all.py       # Redraft ALL leads with latest prompt

# Backfill utilities (run in order for best results)
python fill_job_data.py 50       # Scrape missing JDs + fill company descriptions (50/run)
python fill_keywords.py          # Add AI/tech keywords (no API cost)
python fill_descriptions.py      # Fill company descriptions via Claude Haiku
python fill_salaries.py          # Extract salary from JDs (regex + Claude)
python export_xlsx.py            # Re-export Excel anytime

# --- Dashboard + Email Sending (NEW) ---
python server.py                 # Start the web dashboard → http://localhost:5000
python reply_tracker.py          # One-shot inbox check (also runs automatically inside server.py)
```

---

## Complete Run Guide

### Fresh Start (first time / new batch of leads)

```bash
# Step 1 — Scrape new AI job postings from LinkedIn
python run.py scrape

# Step 2 — Enrich: find company websites, decision makers, emails
python run.py enrich

# Step 3 — Backfill missing job descriptions (repeat until 0 remaining)
python fill_job_data.py 50
# If LinkedIn scraping fails for a lead, Gemini auto-generates a company
# description from just the company name + job title (no JD needed).
# Run multiple times until all leads are filled:
python fill_job_data.py 50   # run again
python fill_job_data.py 50   # run again (until "Missing job description: 0")

# Step 4 — Fill AI/tech keywords (free, no API cost)
python fill_keywords.py

# Step 5 — Draft formal emails for all enriched leads
python redraft_all.py
# ^ auto-exports leads_export.xlsx when done
```

### Daily Pipeline (ongoing — after initial setup)

```bash
# 1. Scrape new jobs + enrich + draft in one command
python run.py

# 2. Fill any new leads that are missing JDs
python fill_job_data.py 50

# 3. Draft emails for new leads only (skips existing drafts)
python draft_emails.py

# 4. Export latest Excel
python export_xlsx.py
```

### Regenerate All Emails (after prompt changes)

```bash
python redraft_all.py
# Overwrites every draft_email and draft_subject in DB
# Auto-exports Excel when complete
```

### Check Stats at Any Time

```bash
python run.py stats
```

### Export Excel at Any Time

```bash
python export_xlsx.py
```

---

## Recommended Workflow (Right Now)

```bash
# 1. Fill missing job descriptions (run until "Missing job description: 0")
python fill_job_data.py 50

# 2. Redraft all emails with the updated formal prompt
python redraft_all.py
# ^ auto-exports Excel when complete
```

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `SEARCH_QUERIES` | 12 AI job titles | What to search on LinkedIn |
| `SEARCH_LOCATIONS` | USA + 16 EU countries | Where to search |
| `TIME_FILTER` | `r86400` (24h) | How recent jobs must be |
| `MAX_PAGES_PER_QUERY` | 2 | Pages per search query |
| `MAX_LEADS_PER_RUN` | 500 | Stop after this many new leads |
| `MIN_DELAY / MAX_DELAY` | 4s / 10s | Human-like delay between requests |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | LLM for enrichment |
| `TARGET_TITLES` | CTO, CEO, Founder, VP Eng... | Decision maker titles to target |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Scraping | Scrapling StealthyFetcher (anti-detection, headless browser) |
| Database | SQLite via `sqlite3` |
| AI (enrichment) | Groq llama-3.3-70b + Claude Haiku 4.5 fallback |
| AI (company desc fallback) | Gemini 2.0 Flash Lite (free tier, no billing required) |
| AI (email drafting) | Claude Haiku 4.5 (cheapest, fastest) |
| Email finding | DuckDuckGo + SMTP verification + Hunter.io |
| **Email sending** | **Python smtplib + STARTTLS (multipart/alternative)** |
| **Open tracking** | **1×1 transparent GIF pixel served by Flask** |
| **Reply tracking** | **Python imaplib IMAP4_SSL polling (5-min interval)** |
| **Dashboard** | **Flask 3 (backend) + vanilla HTML/CSS/JS (frontend)** |
| Export | openpyxl (styled Excel with freeze panes + auto-filter) |
| Config | python-dotenv |

---

## Output: `leads_export.xlsx`

Exported columns (in order):

| # | Column | Description |
|---|---|---|
| 1 | Company Name | |
| 2 | Company Website | |
| 3 | Company Description | 1-2 sentence AI-generated summary |
| 4 | Industry | e.g. FinTech, SaaS, Healthcare AI |
| 5 | Hiring For (Job Title) | Role they posted |
| 6 | Location | |
| 7 | Salary | Extracted from JD or LinkedIn card |
| 8 | Tech Keywords | Matched from 400+ AI/tech terms |
| 9 | Decision Maker | Name |
| 10 | DM Title | e.g. CTO, VP Engineering |
| 11 | DM Email | SMTP-verified |
| 12 | DM LinkedIn | Profile URL |
| 13 | Job Description | Full scraped JD text |
| 14 | Email Subject | Generated subject line |
| 15 | Draft Email | Full formal email body (230-250 words) |

One row per company (deduplicated — keeps the row with the most filled fields).

---

## Cost Estimate

| Operation | Model | Approx. Cost |
|---|---|---|
| Enrichment — DM + company info | Groq free tier | Free |
| Enrichment fallback | Claude Haiku 4.5 | ~$0.001 per lead |
| JD description fill | Claude Haiku 4.5 | ~$0.001 per lead |
| Company desc (no JD) | Gemini 2.0 Flash Lite | Free (1500 req/day) |
| Email drafting | Claude Haiku 4.5 | ~$0.002 per email |
| Email finding | Hunter.io | 25 credits/key (free) |

For 150 leads: approximately $0.50–$1.00 total in API costs (switched to Haiku from Sonnet).

---

## Dashboard & Sending — Quick Start

```bash
# 1. Add SMTP / IMAP / BASE_URL to .env (see Setup section above)
# 2. Make sure leads have been drafted
python draft_emails.py

# 3. Launch the dashboard
source venv/bin/activate
python server.py
# → open http://localhost:5000
```

The dashboard auto-refreshes every 60 seconds. To send an email: find the lead row, click **Review & Send**, review the full email in the modal, confirm.

Reply tracking runs automatically as a background thread inside `server.py` (polls inbox every 5 minutes). To run it standalone:

```bash
python reply_tracker.py
```

---

## Email Deliverability Design

Every outbound email is sent with `multipart/alternative` structure:

```
multipart/alternative
  ├─ text/plain   ← the actual email (what recipients read)
  └─ text/html    ← ghost version: zero CSS, zero styling
                    same plain text + 1×1 invisible tracking pixel
```

- **No HTML templates, no inline styles** — the ghost HTML is just raw text wrapped in `<html><body>` with `<br>` line breaks
- **Plain-text signature only**: `Omnithrive` (no image logos)
- Email clients that render HTML load the tracking pixel silently; plain-text clients show the text version only
- The `Message-ID` header is stored in the DB and used to match reply threads

---

## What's Been Added (Topic-by-Topic)

### Scraper Improvements
- **Java filter**: Drops any job title containing `\bjava\b` (word boundary) — kills "Java Engineer" but keeps "JavaScript AI Developer"
- **AI relevance filter**: Only keeps jobs whose title contains at least one genuine AI/ML term (e.g. `llm`, `genai`, `machine learning`, `mlops`, `agentic`, etc.)
- **Full JD capture**: After filtering, the scraper fetches the full job description from the LinkedIn detail page for every kept lead
- **Salary extraction**: Extracts salary from both the job card and the job description text

### Database & Backfill
- **`fill_job_data.py`**: Two-step backfill script
  - Step 1: Scrapes missing job descriptions from LinkedIn URLs (batched, 3s delay)
  - Step 2: Uses Claude Haiku to generate `company_description` + `industry` from the JD text
  - **Gemini fallback**: When LinkedIn scraping fails entirely, Gemini 2.0 Flash Lite generates company description from just the company name + job title (no JD needed)
- **`fill_keywords.py`**: Tags 400+ AI/tech keywords from job descriptions (no API cost)
- **`fill_salaries.py`**: Extracts salary from stored JDs using regex + Claude
- **`fill_descriptions.py`**: Fills company descriptions via Claude Haiku for leads that have JDs but no description

### Email Drafting
- **Formal prompts**: Complete rewrite of both `PROMPT_WITH_DM` and `PROMPT_WITHOUT_DM` with 9 mandatory rules enforced in the prompt
- **Smart salutation**:
  - If DM name known → `Dear [Name],`
  - If no DM name → `Dear [Company Name] Team,` (never "Dear Hiring Manager")
- **JD personalization**: Prompt requires referencing 1-2 specific items from the actual job description — not generic filler
- **Salary pitch**: 1/10th of their annual hire budget injected into every email (defaults to $100K/$10K if no salary found)
- **Spam-safe subject lines**: Prompt explicitly bans spam trigger words (`free`, `guaranteed`, `offer`, `act now`, etc.) and requires curiosity-driven, company-specific subjects
- **Switched to Claude Haiku**: 10x cheaper than Sonnet (~$0.002/email vs $0.015), still high quality
- **`redraft_all.py`**: Overwrites ALL existing emails with the latest prompt — run this after any prompt change
- **Word limit**: Strictly 230–250 words, enforced in prompt

### Export
- **Job Description column added**: `leads_export.xlsx` now exports 15 columns including the full JD text
- **Deduplication**: One row per company, keeps the row with the most filled fields

### AI Stack Additions
- **Gemini 2.0 Flash Lite** (`google-genai` SDK): Free tier fallback for company descriptions when LinkedIn JD scraping fails. 1,500 requests/day free, no billing required
- **Groq → Claude Haiku fallback**: JSON parsing in `enricher.py` fixed with regex extraction to handle Claude adding explanation text after the JSON block

### Configuration
- `GEMINI_API_KEY` added to `config.py` and `.env`
- All three AI providers configurable via `.env`: Groq, Anthropic, Gemini

### Email Sending — Module 1 (`email_sender.py`)
- `multipart/alternative` email construction — primary payload is strict `text/plain`
- Ghost `text/html` part: zero CSS, zero styling, raw text + 1×1 tracking pixel only
- Plain-text signature appended: `Omnithrive` (no image logos, no HTML branding)
- STARTTLS SMTP with configurable `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`
- `Message-ID` generated via `email.utils.make_msgid` and stored to DB on send

### Tracking Engine — Module 2 (`reply_tracker.py` + `db.py` + `server.py`)
- **New DB columns**: `message_id`, `sent_at`, `opened_at`, `replied_at` (migration-safe)
- **New statuses**: `sent` → `opened` → `replied` (status never regresses)
- **Open tracking**: `GET /api/track/open/<lead_id>` serves a 1×1 transparent GIF (`image/gif`, no-cache headers) and calls `mark_opened()`
- **Reply tracking**: IMAP4_SSL poller runs as a daemon thread, checks `UNSEEN` messages every 5 minutes. Match priority: `In-Reply-To`/`References` header → sender email fallback
- **New DB helpers**: `mark_sent`, `mark_opened`, `mark_replied`, `get_lead_by_id`, `get_lead_by_message_id`, `get_lead_by_email`

### Frontend Dashboard — Module 3 (`server.py` + `templates/dashboard.html`)
- **REST API** (`/api/leads`, `/api/stats`, `/api/leads/<id>/send`) served by Flask 3
- **Metrics bar**: Scraped / Enriched / Sent / Opened / Replied / No Reply — live from DB
- **Lead table**: Company + recipient email, Job Title, Keywords, JD Snippet, Drafted Email preview, Status badge, "Review & Send" action button
- **Review modal**: full To / Subject / Body visible before confirming send
- Search bar (company, keywords, email, body) and status dropdown filter
- Auto-refresh every 60 seconds; toast notifications for send success/error
- Dark theme, zero dependencies — single HTML file, no npm/webpack needed
