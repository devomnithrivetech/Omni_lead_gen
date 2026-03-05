"""
Fill missing salaries for existing leads using Groq (Claude fallback).
Uses job_description already in DB - no scraping needed.
"""
import sqlite3
import time
from config import DB_PATH, GROQ_API_KEY, GROQ_MODEL, ANTHROPIC_API_KEY
from scraper import extract_salary_from_text


PROMPT_TEMPLATE = (
    "Does this job posting mention a salary, pay range, or compensation? "
    "If yes, extract it as a short string (e.g. '$120K - $150K', '£80,000 - £100,000', '€70k-€90k'). "
    "If not mentioned, reply with exactly: NOT_MENTIONED\n\n"
    "Job Posting:\n{text}\n\n"
    "Reply with ONLY the salary string or NOT_MENTIONED. No extra text."
)


def ask_groq(text):
    if not GROQ_API_KEY:
        return ""
    from groq import Groq
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(text=text[:1500])}],
            temperature=0,
            max_tokens=50,
        )
        result = response.choices[0].message.content.strip()
        if result and result != "NOT_MENTIONED" and len(result) < 80:
            return result
        return ""
    except Exception as e:
        print(" groq err:" + str(e)[:80])
        return ""


def ask_claude(text):
    if not ANTHROPIC_API_KEY:
        return ""
    import anthropic
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(text=text[:1500])}],
        )
        result = message.content[0].text.strip()
        if result and result != "NOT_MENTIONED" and len(result) < 80:
            return result
        return ""
    except Exception as e:
        print(" claude err:" + str(e)[:40])
        return ""


def fill_salaries():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, company_name, job_description FROM leads "
        "WHERE (salary IS NULL OR salary = '') "
        "AND job_description IS NOT NULL AND job_description != ''"
    ).fetchall()

    if not rows:
        print("No leads missing salary with job descriptions available.")
        conn.close()
        return

    print("Checking salary for " + str(len(rows)) + " leads...\n")

    found = 0
    not_mentioned = 0

    for i, row in enumerate(rows):
        prefix = "[" + str(i + 1) + "/" + str(len(rows)) + "] " + row["company_name"]
        job_desc = row["job_description"] or ""

        # Try regex first (free + instant)
        salary = extract_salary_from_text(job_desc)

        if not salary:
            # Use Claude directly for bulk operation (avoids Groq rate limits)
            salary = ask_claude(job_desc) if ANTHROPIC_API_KEY else ask_groq(job_desc)

        if salary:
            conn.execute("UPDATE leads SET salary = ? WHERE id = ?", (salary, row["id"]))
            conn.commit()
            found += 1
            print(prefix + " -> " + salary)
        else:
            not_mentioned += 1

        time.sleep(2)

    conn.close()
    print("\nDone. Found salary: " + str(found) + " | Not mentioned: " + str(not_mentioned))
    if found > 0:
        print("Re-run export_xlsx.py to get the updated Excel file.")


if __name__ == "__main__":
    fill_salaries()
