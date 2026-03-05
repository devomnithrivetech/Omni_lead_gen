"""
Fast description filler using Claude API.
No scraping - uses job_description already in DB.
"""
import os
import time
import sqlite3
from dotenv import load_dotenv

load_dotenv()

from config import DB_PATH

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def fill_descriptions():
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        return

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT id, company_name, job_title, job_description
           FROM leads
           WHERE decision_maker_email IS NOT NULL
           AND decision_maker_email != ''
           AND (company_description IS NULL OR company_description = '')"""
    ).fetchall()

    if not rows:
        print("All exported leads already have descriptions.")
        conn.close()
        return

    print("Filling descriptions for " + str(len(rows)) + " leads using Claude...\n")

    updated = 0
    failed = 0

    for row in rows:
        company = row["company_name"]
        job_title = row["job_title"] or ""
        job_desc = row["job_description"] or ""

        if not job_desc and not job_title:
            failed += 1
            continue

        context = "Job Title: " + job_title + "\n\nJob Posting:\n" + job_desc[:1500]

        prompt = (
            "Based on this job posting from '" + company + "', give me:\n"
            "1. A brief 1-2 sentence description of what this company does\n"
            "2. Their industry (e.g. FinTech, Healthcare AI, SaaS, Cybersecurity, etc.)\n\n"
            + context + "\n\n"
            "Respond ONLY in this format (no extra text):\n"
            "DESCRIPTION: <1-2 sentences>\n"
            "INDUSTRY: <industry>"
        )

        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = message.content[0].text.strip()

            desc = ""
            industry = ""
            for line in raw.splitlines():
                if line.startswith("DESCRIPTION:"):
                    desc = line.replace("DESCRIPTION:", "").strip()
                elif line.startswith("INDUSTRY:"):
                    industry = line.replace("INDUSTRY:", "").strip()

            if desc:
                conn.execute(
                    "UPDATE leads SET company_description = ?, company_industry = ? WHERE id = ?",
                    (desc, industry, row["id"])
                )
                conn.commit()
                updated += 1
                print("[" + str(updated) + "/" + str(len(rows)) + "] " + company + " -> " + industry)
            else:
                failed += 1

            time.sleep(0.3)  # stay within rate limits

        except Exception as e:
            print("  ERROR for " + company + ": " + str(e)[:60])
            failed += 1

    conn.close()
    print("\nDone. Updated: " + str(updated) + " | Failed: " + str(failed))
    print("Re-run export_xlsx.py to get the updated Excel file.")


if __name__ == "__main__":
    fill_descriptions()
