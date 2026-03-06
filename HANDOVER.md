# Omnithrive Lead Generation Pipeline — Full Technical Handover

**Prepared for:** Head of Engineering / Setup Lead
**Project:** Omnithrive AI Lead Generation System
**Purpose:** Automated B2B outreach — scrape LinkedIn AI job postings → find decision maker contacts → generate personalised cold emails → send + track replies via a web dashboard.

---

## Table of Contents

1. [What This System Does](#1-what-this-system-does)
2. [Architecture Overview](#2-architecture-overview)
3. [File-by-File Breakdown](#3-file-by-file-breakdown)
4. [How Each Component Works (Deep Dive)](#4-how-each-component-works-deep-dive)
   - 4.1 Scraper
   - 4.2 Database Layer
   - 4.3 Enricher
   - 4.4 AI Provider Chain
   - 4.5 Email Drafter
   - 4.6 Email Sender
   - 4.7 Open Tracking
   - 4.8 Reply Tracker
   - 4.9 Dashboard Server
   - 4.10 Excel Exporter
5. [Data Flow — End to End](#5-data-flow--end-to-end)
6. [Database Schema](#6-database-schema)
7. [Lead Status Lifecycle](#7-lead-status-lifecycle)
8. [Local Setup Guide (Step by Step)](#8-local-setup-guide-step-by-step)
9. [Environment Variables Reference](#9-environment-variables-reference)
10. [Running the Pipeline](#10-running-the-pipeline)
11. [Common Issues & Fixes](#11-common-issues--fixes)

---

## 1. What This System Does

The pipeline targets companies that are **actively hiring AI engineers** — this is a strong buying signal that they need AI capabilities but haven't yet built them. Omnithrive's pitch: we deliver those AI capabilities at 1/10th the cost of a full-time hire.

**Automated flow:**
1. Scrape LinkedIn for AI/ML job postings posted in the last 24 hours across US + Europe
2. Filter out irrelevant jobs (Java, non-AI roles)
3. Find the company website, decision maker (CTO/CEO/VP Eng), and their email address
4. Generate a personalised formal cold email using Claude AI (references their specific JD)
5. Send the email from `admin@omnithrivetech.com` via SMTP
6. Track when it is opened (tracking pixel) and when they reply (IMAP polling)
7. View everything in a web dashboard at `http://localhost:5000`

---

## 2. Architecture Overview

```
LinkedIn (public job listings)
        |
        v
[scraper.py]  ←  Scrapling StealthyFetcher (headless browser, anti-detection)
        |         Filters: AI-only titles, drops Java roles
        |         Extracts: company, job title, location, salary, job URL, full JD
        v
[leads.db]  ←  SQLite database (single file, no server needed)
        |
        v
[enricher.py]  ←  Waterfall contact finder
        |          Step 1: Scrape company website (Scrapling)
        |          Step 2: DuckDuckGo search for email addresses
        |          Step 3: AI extracts decision maker from scraped text (Groq/Claude)
        |          Step 4: Hunter.io API for verified email lookup
        |          Step 5: SMTP verification (connects to mail server to check if email exists)
        |          Step 6: DNS MX record validation
        |          Step 7: AI extracts company description + industry
        v
[leads.db]  (status updated: scraped → enriched)
        |
        v
[draft_emails.py]  ←  Claude Haiku (AI email drafter)
        |              One email per unique company (deduplication)
        |              Reads actual JD to personalise — references real tech stack
        |              Includes 1/10th salary pitch
        |              Strict 230-250 word limit
        v
[leads.db]  (draft_subject + draft_email saved; status → drafted)
        |
        v
[server.py]  ←  Flask web dashboard at http://localhost:5000
        |        Review drafted emails, click "Send" per lead
        v
[email_sender.py]  ←  SMTP sender via Gmail
        |              multipart/alternative: plain text + ghost HTML with tracking pixel
        |              Message-ID stored to DB for reply matching
        v
[reply_tracker.py]  ←  IMAP poller (runs every 5 min as background thread)
                         Detects replies by matching In-Reply-To header or sender email
                         Updates status → replied in DB
```

---

## 3. File-by-File Breakdown

| File | Purpose |
|---|---|
| `config.py` | Central config — all API keys, SMTP/IMAP settings, search queries, limits. Reads from `.env` |
| `db.py` | SQLite database layer — schema creation, insert, update, all helper functions |
| `scraper.py` | LinkedIn scraper — fetches job listings, filters AI-only roles, scrapes full JDs |
| `enricher.py` | Contact enrichment waterfall — website scrape → AI → Hunter.io → SMTP verify |
| `ai_providers.py` | Unified AI fallback chain — Groq → Cerebras → SambaNova → Together → Claude Haiku |
| `draft_emails.py` | Formal email drafter using Claude Haiku — one email per company, no duplicates |
| `redraft_all.py` | Overwrites ALL existing draft emails with an updated prompt |
| `email_sender.py` | SMTP email sender with multipart/alternative structure + tracking pixel |
| `reply_tracker.py` | IMAP inbox poller — auto-detects replies and updates lead status |
| `server.py` | Flask dashboard server + REST API + open-tracking pixel endpoint |
| `keywords.py` | 400+ AI/ML tech keyword extractor (11 categories) |
| `export_xlsx.py` | Exports leads to styled Excel file with Java filter + deduplication |
| `fill_job_data.py` | Backfill utility — scrapes missing job descriptions, fills company info |
| `fill_keywords.py` | Backfill utility — adds tech keywords to existing leads (no API cost) |
| `fill_descriptions.py` | Backfill utility — fills company descriptions via AI |
| `fill_salaries.py` | Backfill utility — extracts salary info from JDs (regex + AI) |
| `rescrape_descriptions.py` | Re-scrapes job URLs for leads missing descriptions |
| `run.py` | Master runner — orchestrates full pipeline or individual stages |
| `templates/dashboard.html` | Frontend CRM dashboard — vanilla HTML/CSS/JS, no npm needed |
| `leads.db` | SQLite database file (auto-created on first run) |
| `leads_export.xlsx` | Excel export (regenerated by export_xlsx.py) |
| `.env` | Secret keys and credentials — NEVER commit to git |

---

## 4. How Each Component Works (Deep Dive)

### 4.1 Scraper (`scraper.py`)

**Technology:** Scrapling `StealthyFetcher` — a headless browser wrapper with anti-bot detection built in. It rotates user agents, handles JavaScript rendering, and mimics real browser behaviour. LinkedIn blocks standard `requests` calls; Scrapling bypasses this.

**What it does:**
1. Builds LinkedIn job search URLs for every combination of `SEARCH_QUERIES` × `SEARCH_LOCATIONS` in `config.py` (e.g. "AI Engineer" in "United States", "LLM Engineer" in "Germany", etc.)
2. For each URL, fetches up to `MAX_PAGES_PER_QUERY` pages (default: 2) with a random delay between `MIN_DELAY` and `MAX_DELAY` seconds to mimic human browsing
3. Parses each job card: company name, job title, location, salary (if shown), job URL
4. Applies two filters before saving:
   - **Java filter:** drops any title matching `\bjava\b` (word boundary regex) but allows "JavaScript" through
   - **AI relevance filter:** only keeps titles containing at least one of 20+ AI/ML terms (llm, genai, machine learning, mlops, agentic, nlp, etc.)
5. For jobs that pass the filter, fetches the full job description from the LinkedIn detail page
6. Extracts salary from the JD text using regex patterns
7. Saves to `leads.db` via `insert_lead()` — the unique index on `(company_name, job_title)` prevents duplicates across runs

**Time filter:** `TIME_FILTER = "r86400"` = past 24 hours only. This ensures fresh leads every time.

**Key settings in `config.py`:**
```
SEARCH_QUERIES     → list of job titles to search
SEARCH_LOCATIONS   → list of countries/regions
TIME_FILTER        → "r86400" = last 24h | "r604800" = last 7 days
MAX_PAGES_PER_QUERY → how many pages per search (default: 2)
MAX_LEADS_PER_RUN  → hard cap on total leads per run (default: 500)
MIN_DELAY / MAX_DELAY → random delay between requests (default: 4-10 seconds)
```

---

### 4.2 Database Layer (`db.py`)

**Technology:** Python's built-in `sqlite3`. No external database server needed — everything is stored in `leads.db`, a single file in the project folder.

**Auto-initialisation:** `db.py` calls `init_db()` on every import. This means the database is created automatically the first time any script runs. The schema uses `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN` with exception handling, so upgrading an existing DB is safe.

**Key functions:**

| Function | What it does |
|---|---|
| `init_db()` | Creates the table and indexes. Safe to call multiple times |
| `insert_lead(...)` | Inserts one lead. Returns False (no error) if duplicate — uses SQLite's UNIQUE constraint |
| `get_leads_by_status(status)` | Returns all leads with a given status |
| `update_lead(lead_id, **fields)` | Generic updater — pass any field names as kwargs |
| `get_all_leads()` | Returns all leads ordered by created_at DESC |
| `get_stats()` | Prints and returns status counts |
| `mark_sent(lead_id, message_id)` | Sets status=sent, stores Message-ID, records sent_at timestamp |
| `mark_opened(lead_id)` | Sets status=opened (only if not already replied) |
| `mark_replied(lead_id)` | Sets status=replied, records replied_at timestamp |
| `get_lead_by_message_id(mid)` | Used by reply tracker to match incoming emails |
| `get_lead_by_email(email)` | Fallback match for reply tracker |

**Unique constraint:** `(company_name, job_title)` — so the same job at the same company can never be inserted twice, even across multiple scraping runs.

---

### 4.3 Enricher (`enricher.py`)

This is the most complex component. It takes leads with status `scraped` and tries to find:
- The company website
- A decision maker (CTO, CEO, VP Engineering, Head of AI, etc.) and their email
- A company description and industry

**Enrichment Waterfall (in order):**

**Step 1 — Find company website**
- DuckDuckGo search: `"{company_name}" site:linkedin.com OR official website`
- Tries to extract the official domain from search results
- Falls back to guessing `{company_name}.com`

**Step 2 — Scrape company website**
- Uses Scrapling to fetch the company's homepage and About/Team pages
- Extracts raw text, meta descriptions, and any email addresses found on the page

**Step 3 — AI extracts decision maker**
- Sends the scraped website text + any found emails to the AI chain (`ai_providers.py`)
- Prompt: "Find the CTO/CEO/Founder from this website text. Return JSON. Do NOT invent names."
- Returns: `{first_name, last_name, title, email}`

**Step 4 — Hunter.io API**
- If AI couldn't find a verified email, queries Hunter.io's domain search API
- Looks for people with titles matching `TARGET_TITLES` in `config.py`
- Hunter.io returns verified business emails
- Supports up to 20 Hunter API keys (25 credits each = 500 lookups free)
- Keys rotate automatically via `HunterRotator` class

**Step 5 — SMTP verification**
- For any candidate email, connects to the company's mail server and issues `RCPT TO:` command
- Checks if the server accepts the address (without actually sending email)
- Filters out invalid/bouncing addresses before storing

**Step 6 — DNS MX record check**
- Validates that the company's domain has valid mail exchange records
- Prevents storing emails for domains that don't accept email at all

**Step 7 — AI extracts company description + industry**
- Feeds website text, job description, meta descriptions, and DuckDuckGo snippets to AI
- Returns: `{description: "...", industry: "..."}`
- Stored in `company_description` and `company_industry` columns

**Step 8 — Tech keyword extraction**
- Calls `keywords.py` to extract AI/ML keywords from job title + JD + website text
- 400+ keywords across 11 categories (LLM frameworks, cloud, MLOps, etc.)

**Final update:** If a valid decision maker email was found, status is set to `enriched`. If nothing was found after all steps, status is set to `no_match` (permanently skipped on future runs).

**Key settings:**
```
TARGET_TITLES → list of seniority titles the enricher looks for (CTO, CEO, Founder, etc.)
HUNTER_API_KEYS → list of Hunter.io keys for rotation
```

---

### 4.4 AI Provider Chain (`ai_providers.py`)

A unified wrapper that tries AI providers in order and returns the first successful response. Used by the enricher for all AI tasks (DM extraction, company description).

**Provider order:**
1. **Groq** (free tier, fast) — uses `llama-3.3-70b-versatile` via Groq Python SDK
2. **Cerebras** (free, 1M tokens/day) — OpenAI-compatible REST API
3. **SambaNova** (free, rate-limited) — OpenAI-compatible REST API
4. **Together AI** ($25 free credit) — OpenAI-compatible REST API
5. **Claude Haiku** (paid fallback, ~$0.001/call) — Anthropic Python SDK

**How it works:**
```python
text = generate("Your prompt here", max_tokens=200, system="Optional system prompt")
# Returns "" if all providers fail
```

Cerebras, SambaNova, and Together all use the same OpenAI-compatible REST format (`POST /v1/chat/completions` with a Bearer token), so no extra SDKs are needed — just `requests`.

If a provider fails (rate limit, timeout, API error), it prints a short error tag and moves to the next one. The email drafter (`draft_emails.py`) does NOT use this chain — it always uses Claude directly because email quality is critical.

---

### 4.5 Email Drafter (`draft_emails.py` and `redraft_all.py`)

**Technology:** Claude Haiku (`claude-haiku-4-5-20251001`) — the cheapest Claude model, ~$0.002 per email.

**Deduplication logic:** Both scripts pick exactly ONE email per company before drafting. Companies often have multiple rows in the DB (different job titles). The script scores each row and picks the best:
- DM name present = 3 points
- Job description present = 2 points
- Company description present = 1 point

The highest-scoring row per company is selected.

**`draft_emails.py`** — only drafts leads that do NOT already have a draft email. Safe to run repeatedly.

**`redraft_all.py`** — overwrites ALL existing drafts with the latest prompt. Run this when you update the email prompt.

**Two prompt templates:**
- `PROMPT_WITH_DM` — used when a decision maker name is known → "Dear [Name],"
- `PROMPT_WITHOUT_DM` — used when only the company is known → "Dear [Company] Team,"

**What each generated email must include (enforced in the prompt):**
1. Personalised salutation (name or company team)
2. Reference to 1-2 specific items from the job description (to show research)
3. Salary pitch: "we deliver this for 1/10th of your hiring budget" (specific dollar amounts)
4. One urgency stat: either "75% of AI projects fail to deliver ROI (IBM)" or "88% of AI pilots never reach production (CIO Magazine)"
5. CTA: book a free 2-Day AI Opportunity Audit at `cal.com/omnithrivetech-ceo`
6. Formal closing: "Warm regards,"
7. Subject line under 60 characters, curiosity-driven, no spam trigger words
8. Strict 230-250 word body length

**Output is parsed** by splitting on `SUBJECT:` and `EMAIL:` markers in Claude's response.

---

### 4.6 Email Sender (`email_sender.py`)

**Technology:** Python's built-in `smtplib` with STARTTLS. No third-party email library needed.

**Deliverability design:**

The email is sent as `multipart/alternative` with two parts:

```
multipart/alternative
  ├─ text/plain   ← The actual readable email (what recipients see)
  └─ text/html    ← Ghost version: exact same text, zero CSS/styling
                    + 1×1 transparent tracking pixel at the end
```

Email clients that render HTML (Gmail, Outlook) will load the pixel silently and trigger open tracking. Plain-text clients (rare) show the text version only.

**Why this approach works:**
- No HTML templates, no `<table>` layouts, no inline styles → does not look like a marketing email
- The HTML part is raw text wrapped in `<html><body>` with `<br>` line breaks — visually identical to plain text
- Plain text signature only: `\n\nOmnithrive` — no image logos, no HTML branding
- The `Message-ID` header (generated by `email.utils.make_msgid`) is stored in the database immediately after send — this is used for reply matching

**SMTP flow:**
1. Connect to `SMTP_HOST:SMTP_PORT` (default: `smtp.gmail.com:587`)
2. `server.ehlo()` → identifies our client
3. `server.starttls()` → upgrades connection to TLS
4. `server.login(SMTP_USER, SMTP_PASS)` → authenticate
5. `server.sendmail(FROM_EMAIL, [to_email], msg.as_string())`
6. Call `mark_sent(lead_id, message_id)` → updates DB

---

### 4.7 Open Tracking

**How it works:**
1. The ghost HTML part of every email contains an `<img>` tag pointing to:
   `{BASE_URL}/api/track/open/{lead_id}`
2. When a recipient opens the email in an HTML-rendering client, the image loads
3. Flask serves a 1×1 transparent GIF from that endpoint
4. Before serving the image, it calls `mark_opened(lead_id)` in the DB
5. Status upgrades: `sent` → `opened`

**Important:** `BASE_URL` must be a publicly accessible URL for this to work. If you run the server only on `localhost`, the pixel will never fire for recipients. Use a tool like `ngrok` for testing or deploy to a VPS with a real domain.

**No-cache headers** are set on the pixel response so email clients always make a fresh request.

---

### 4.8 Reply Tracker (`reply_tracker.py`)

**Technology:** Python's built-in `imaplib` with `IMAP4_SSL`.

**How it works:**
1. Runs as a daemon background thread inside `server.py` (polls every 5 minutes)
2. Can also be run standalone: `python reply_tracker.py` (one-shot check)
3. Connects to `IMAP_HOST:IMAP_PORT` (default: `imap.gmail.com:993`)
4. Searches for `UNSEEN` (unread) messages in INBOX
5. For each unread message, tries two matching strategies:

   **Strategy 1 — Message-ID header match (most reliable):**
   - Reads `In-Reply-To` and `References` headers from the incoming email
   - Extracts all `<msgid>` tokens
   - Looks each one up in the DB via `get_lead_by_message_id()`
   - If found, marks the lead as replied

   **Strategy 2 — Sender email fallback:**
   - If no Message-ID match, reads the `From:` header of the incoming email
   - Extracts the sender's email address
   - Looks it up via `get_lead_by_email()` (only matches leads with status `sent`)
   - If found, marks the lead as replied

6. Status upgrades: `sent`/`opened` → `replied`

**Note:** The thread is a daemon thread — it automatically stops when the main process (server.py) exits. It will not block shutdown.

---

### 4.9 Dashboard Server (`server.py`)

**Technology:** Flask 3 (Python web framework). Single file server, no complex web setup needed.

**Endpoints:**

| Endpoint | Method | What it does |
|---|---|---|
| `/` | GET | Serves `templates/dashboard.html` |
| `/api/leads` | GET | Returns all leads as JSON (truncates JD to 200 chars) |
| `/api/stats` | GET | Returns aggregate counts: scraped/enriched/sent/opened/replied |
| `/api/leads/<id>/send` | POST | Triggers email send for a specific lead |
| `/api/track/open/<id>` | GET | Serves tracking pixel + marks lead as opened |

**Dashboard frontend (`templates/dashboard.html`):**
- Vanilla HTML/CSS/JavaScript — zero npm, zero webpack, zero build step
- Dark theme
- Metrics bar at the top: live counts from `/api/stats`
- Lead table: company, email, job title, keywords, JD snippet, drafted email preview, status badge, "Review & Send" button
- Search bar: filters across company name, keywords, email, email body
- Status dropdown filter: show all / scraped / enriched / drafted / sent / opened / replied
- Review modal: shows full To / Subject / Body before confirming send
- Auto-refreshes every 60 seconds
- Toast notifications for send success/failure

**On startup:**
- Calls `start_background_thread()` from `reply_tracker.py` → IMAP poll loop starts as daemon thread
- Logs to console: lead IDs, send events, open tracking events

---

### 4.10 Excel Exporter (`export_xlsx.py`)

**Technology:** `openpyxl` library for styled Excel output.

**What it exports:**
- Only leads that have a `decision_maker_email` (enriched leads)
- Filtered: Java jobs are excluded (safety net even if they somehow got into the DB)
- Deduplicated: one row per company (keeps the row with most filled fields)

**Columns exported (in order):**
Company Name, Company Website, Company Description, Industry, Hiring For (Job Title), Location, Salary, Tech Keywords, Decision Maker, DM Title, DM Email, DM LinkedIn, Job Description, Email Subject, Draft Email

**Styling:** Blue header row, alternating light-blue row fills, freeze panes on row 1, auto-filter enabled, column widths pre-set, Arial font throughout.

**Output file:** `leads_export.xlsx` in the project folder. Overwritten on every run.

---

## 5. Data Flow — End to End

```
run.py scrape
    → scraper.py fetches LinkedIn
    → is_relevant_job() filters titles
    → insert_lead() → leads.db (status: scraped)

run.py enrich
    → enricher.py picks all status=scraped leads
    → website scrape → AI → Hunter.io → SMTP verify
    → update_lead() → leads.db (status: enriched or no_match)

python draft_emails.py
    → picks best lead per company (score-based dedup)
    → Claude Haiku generates subject + body
    → UPDATE leads SET draft_subject, draft_email
    → leads.db (status remains enriched)

python server.py
    → Flask dashboard at :5000
    → User clicks "Review & Send"
    → POST /api/leads/<id>/send
    → email_sender.py sends via SMTP
    → mark_sent() → leads.db (status: sent)
    → reply_tracker daemon polls IMAP every 5 min
    → mark_replied() → leads.db (status: replied)
    → GET /api/track/open/<id> fires when email opened
    → mark_opened() → leads.db (status: opened)

python export_xlsx.py
    → reads leads.db
    → writes leads_export.xlsx
```

---

## 6. Database Schema

**File:** `leads.db` (SQLite, auto-created)

```sql
CREATE TABLE leads (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name            TEXT NOT NULL,
    company_website         TEXT,
    company_domain          TEXT,
    company_contact_email   TEXT,
    company_description     TEXT,    -- 1-2 sentence description of what company does
    company_industry        TEXT,    -- e.g. FinTech, SaaS, Healthcare AI
    job_title               TEXT,    -- the role they were hiring for
    job_description         TEXT,    -- full text of the LinkedIn JD
    job_url                 TEXT,    -- LinkedIn job posting URL
    job_location            TEXT,
    job_posted_date         TEXT,
    salary                  TEXT,    -- extracted salary string
    decision_maker_name     TEXT,    -- CTO, CEO, VP Eng, etc.
    decision_maker_title    TEXT,
    decision_maker_email    TEXT,    -- verified via SMTP
    decision_maker_linkedin TEXT,
    draft_subject           TEXT,    -- generated email subject line
    draft_email             TEXT,    -- generated email body
    draft_linkedin_note     TEXT,
    tech_keywords           TEXT,    -- comma-separated AI/ML keywords
    status                  TEXT DEFAULT 'scraped',
    message_id              TEXT,    -- SMTP Message-ID for reply matching
    sent_at                 TEXT,    -- ISO timestamp
    opened_at               TEXT,    -- ISO timestamp of first open
    replied_at              TEXT,    -- ISO timestamp of first reply
    created_at              TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at              TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Prevents duplicate (company, job) combinations
CREATE UNIQUE INDEX idx_company_job ON leads(company_name, job_title);
CREATE INDEX idx_status ON leads(status);
```

---

## 7. Lead Status Lifecycle

```
scraped → enriched → (drafted) → sent → opened → replied
    ↘
    no_match  (website/email not found — skipped in future runs)
```

| Status | Meaning |
|---|---|
| `scraped` | Found on LinkedIn, not yet enriched |
| `enriched` | Website scraped, decision maker + email found |
| `drafted` | Email generated by Claude (draft_email saved) |
| `no_match` | Could not find website or contact — permanently skipped |
| `sent` | Email dispatched via SMTP |
| `opened` | Recipient opened the email (tracking pixel fired) |
| `replied` | Recipient replied (detected via IMAP) |

Status never regresses — once `replied`, it stays `replied` even if the open pixel fires again.

---

## 8. Local Setup Guide (Step by Step)

### Prerequisites

- Python 3.10 or higher
- pip
- Git
- A Gmail account with 2FA enabled (for SMTP sending)
- An Anthropic API key (for email drafting)
- A Groq API key (free, for enrichment AI calls)

### Step 1 — Clone the repository

```bash
git clone <repository-url>
cd omni-leadgen
```

### Step 2 — Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate       # Linux / macOS
# OR
venv\Scripts\activate          # Windows
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

The `requirements.txt` includes:
```
python-dotenv==1.0.0    # loads .env file
requests==2.31.0        # HTTP calls (Hunter.io, free AI providers)
dnspython==2.4.2        # DNS MX record validation
groq==0.4.2             # Groq SDK (free LLM)
openpyxl==3.1.2         # Excel export
google-genai>=1.0.0     # Gemini (optional)
flask>=3.0.0            # Dashboard web server
anthropic>=0.40.0       # Claude SDK (email drafting)
```

You also need Scrapling for the scraper and enricher:
```bash
pip install scrapling
scrapling install        # downloads browser binaries
```

### Step 4 — Create the `.env` file

Create a file named `.env` in the project root (same folder as `config.py`):

```env
# ===== AI Keys =====
# REQUIRED for email drafting
ANTHROPIC_API_KEY=sk-ant-...

# REQUIRED for enrichment AI calls (free at console.groq.com)
GROQ_API_KEY=gsk_...

# Optional free AI fallbacks (all free tiers, no card needed)
CEREBRAS_API_KEY=...        # cloud.cerebras.ai — 1M tokens/day free
SAMBANOVA_API_KEY=...       # cloud.sambanova.ai — unlimited (rate-limited) free
TOGETHER_API_KEY=...        # api.together.ai — $25 free credit

# Optional: contact finding (25 free credits per key, supports up to 20 keys)
HUNTER_API_KEY=...
HUNTER_API_KEY_2=...
HUNTER_API_KEY_3=...

# ===== Email Sending =====
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=admin@omnithrivetech.com
SMTP_PASS=xxxx xxxx xxxx xxxx    # 16-char Gmail App Password (NOT your login password)
FROM_EMAIL=admin@omnithrivetech.com
FROM_NAME=Omnithrive

# ===== Reply Tracking =====
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=admin@omnithrivetech.com
IMAP_PASS=xxxx xxxx xxxx xxxx    # same App Password as above

# ===== Dashboard =====
SERVER_PORT=5000
# For open tracking to work, BASE_URL must be publicly reachable.
# Use localhost if you only need sending, not tracking.
BASE_URL=http://localhost:5000
```

### Step 5 — Get a Gmail App Password

The Gmail account used for sending must have:
1. **2-Factor Authentication** enabled at myaccount.google.com/security
2. An **App Password** created at myaccount.google.com/apppasswords
   - Select "Mail" and "Other (custom name)" → name it "Leadgen"
   - Copy the 16-character password (with spaces is fine)
   - Paste it as `SMTP_PASS` and `IMAP_PASS` in `.env`

### Step 6 — Verify the setup

```bash
source venv/bin/activate
python config.py
```

Expected output:
```
--- Config Status ---
  GROQ_API_KEY:      OK
  ANTHROPIC_API_KEY: OK
  ...
```

### Step 7 — Initialise the database

```bash
python db.py
```

Output: `Database ready: /path/to/leads.db`

---

## 9. Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | YES | Claude API key for email drafting |
| `GROQ_API_KEY` | YES | Groq API key for enrichment AI (free) |
| `CEREBRAS_API_KEY` | No | Free AI fallback (1M tokens/day) |
| `SAMBANOVA_API_KEY` | No | Free AI fallback (rate-limited) |
| `TOGETHER_API_KEY` | No | Free AI fallback ($25 credit) |
| `HUNTER_API_KEY` | No | Hunter.io for email finding (25 credits) |
| `HUNTER_API_KEY_2` ... `HUNTER_API_KEY_20` | No | Additional Hunter keys |
| `SMTP_HOST` | YES (for sending) | SMTP server (default: smtp.gmail.com) |
| `SMTP_PORT` | YES (for sending) | SMTP port (default: 587) |
| `SMTP_USER` | YES (for sending) | Gmail address |
| `SMTP_PASS` | YES (for sending) | Gmail App Password |
| `FROM_EMAIL` | No | Sender address (defaults to SMTP_USER) |
| `FROM_NAME` | No | Display name (default: Omnithrive) |
| `IMAP_HOST` | No | IMAP server for reply tracking (default: imap.gmail.com) |
| `IMAP_PORT` | No | IMAP port (default: 993) |
| `IMAP_USER` | No | IMAP login (defaults to SMTP_USER) |
| `IMAP_PASS` | No | IMAP password (defaults to SMTP_PASS) |
| `SERVER_PORT` | No | Dashboard port (default: 5000) |
| `BASE_URL` | No | Public URL for tracking pixels (default: http://localhost:5000) |

---

## 10. Running the Pipeline

### First time / fresh batch

```bash
source venv/bin/activate

# Step 1: Scrape LinkedIn for new AI job listings
python run.py scrape

# Step 2: Enrich leads (find contacts, company info)
python run.py enrich

# Step 3: Draft personalised cold emails
python draft_emails.py

# Step 4: Export to Excel (optional, for review)
python export_xlsx.py

# Step 5: Launch dashboard and start sending
python server.py
# → open http://localhost:5000 in browser
# → find a lead, click "Review & Send", confirm
```

### Subsequent runs (add new leads)

```bash
source venv/bin/activate
python run.py scrape    # adds new leads (skips already-seen company+job combos)
python run.py enrich   # enriches new scraped leads only
python draft_emails.py # drafts emails for newly enriched leads only
python server.py       # continue sending from dashboard
```

### Backfill utilities (for existing leads missing data)

```bash
python fill_job_data.py 50      # scrape missing JDs + fill company descriptions (50/run)
python fill_keywords.py         # add AI tech keywords (no API cost)
python fill_descriptions.py     # fill missing company descriptions via AI
python fill_salaries.py         # extract salary from JDs
python export_xlsx.py           # re-export Excel anytime
```

### Redraft all emails (when prompt is updated)

```bash
python redraft_all.py    # overwrites ALL draft emails with latest prompt
```

### Check pipeline stats

```bash
python run.py stats    # prints counts per status
# or
python db.py
```

### One-shot inbox check (without running full server)

```bash
python reply_tracker.py
```

---

## 11. Common Issues & Fixes

**Scrapling install fails**
```bash
pip install scrapling
scrapling install
# If browser download fails, try: scrapling install --browser chromium
```

**LinkedIn blocks requests / returns empty pages**
- Scrapling uses anti-detection but LinkedIn can still throttle.
- Increase `MIN_DELAY` and `MAX_DELAY` in `config.py` (try 8 and 20).
- Run during off-peak hours.
- Never run with `MAX_LEADS_PER_RUN` above 500 in a single session.

**SMTP authentication failed**
- Make sure 2FA is enabled on the Gmail account.
- Use an App Password (16 chars), not the Gmail login password.
- Check that `SMTP_USER` and `SMTP_PASS` are set correctly in `.env`.
- Test with: `python -c "from email_sender import send_email; print('OK')"` — if this imports cleanly, credentials are at least loading.

**Claude API errors during drafting**
- Check `ANTHROPIC_API_KEY` is set and has credit.
- The drafter uses Haiku (~$0.002/email). 150 emails ≈ $0.30.
- Rate limit errors are transient — rerun `draft_emails.py`, it skips already-drafted leads.

**Groq API errors during enrichment**
- Free tier has rate limits. The AI chain automatically falls back to Cerebras/SambaNova/Together/Claude.
- Add more free provider keys to `.env` for resilience.

**Open tracking pixel not firing**
- `BASE_URL` must be a publicly reachable URL.
- For local testing: use `ngrok http 5000` and set `BASE_URL=https://your-ngrok-url.ngrok.io`.
- For production: deploy `server.py` to a VPS (DigitalOcean, Hetzner, etc.) and set `BASE_URL` to your domain.

**Reply tracker not detecting replies**
- Ensure IMAP is enabled on the Gmail account: Gmail Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP.
- `IMAP_USER` and `IMAP_PASS` must match the inbox where sent emails land.
- The tracker only checks `UNSEEN` messages — if you read a reply manually before the tracker runs, it will miss it.

**Duplicate companies in Excel**
- The export deduplicates by company name (case-insensitive). If you see duplicates, check for slight spelling differences in `company_name`.

**Java jobs appearing in export**
- `export_xlsx.py` has a built-in Java filter. If they still appear, run:
  ```bash
  python3 -c "
  import sqlite3, re
  conn = sqlite3.connect('leads.db')
  j = re.compile(r'\bjava\b', re.I)
  rows = conn.execute('SELECT id, job_title FROM leads').fetchall()
  ids = [r[0] for r in rows if j.search(r[1] or '') and 'javascript' not in (r[1] or '').lower()]
  print('Java leads to delete:', ids)
  conn.execute('DELETE FROM leads WHERE id IN (%s)' % ','.join('?'*len(ids)), ids)
  conn.commit()
  print('Done')
  "
  ```

---

*Document prepared for internal handover. Do not share publicly.*
