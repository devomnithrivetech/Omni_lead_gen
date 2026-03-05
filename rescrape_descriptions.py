"""
Re-scrapes job descriptions for leads that are missing them,
then uses Claude to fill company descriptions from the job text.
"""
import os
import time
import sqlite3
from dotenv import load_dotenv

load_dotenv()

from config import DB_PATH
from scraper import scrape_job_description, extract_salary_from_text
from db import update_lead

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def get_company_info_from_claude(client, company_name, job_title, job_description):
    prompt = (
        "Based on this job posting from '" + company_name + "', give me:\n"
        "1. A brief 1-2 sentence description of what this company does\n"
        "2. Their industry (e.g. FinTech, Healthcare AI, SaaS, Cybersecurity, etc.)\n\n"
        "Job Title: " + job_title + "\n\nJob Posting:\n" + job_description[:1500] + "\n\n"
        "Respond ONLY in this format (no extra text):\n"
        "DESCRIPTION: <1-2 sentences>\n"
        "INDUSTRY: <industry>"
    )
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    desc, industry = "", ""
    for line in raw.splitlines():
        if line.startswith("DESCRIPTION:"):
            desc = line.replace("DESCRIPTION:", "").strip()
        elif line.startswith("INDUSTRY:"):
            industry = line.replace("INDUSTRY:", "").strip()
    return desc, industry


def run():
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        return

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, company_name, job_title, job_url, salary "
        "FROM leads "
        "WHERE decision_maker_email IS NOT NULL AND decision_maker_email != '' "
        "AND (company_description IS NULL OR company_description = '') "
        "AND job_url IS NOT NULL AND job_url != ''"
    ).fetchall()
    conn.close()

    total = len(rows)
    print("Re-scraping " + str(total) + " job postings...\n")

    scraped = 0
    described = 0
    failed = 0

    for i, row in enumerate(rows):
        prefix = "[" + str(i + 1) + "/" + str(total) + "] " + row["company_name"]
        print(prefix + " - scraping...", end="", flush=True)

        job_desc = scrape_job_description(row["job_url"])

        if not job_desc:
            print(" no description found")
            failed += 1
            time.sleep(2)
            continue

        scraped += 1
        print(" OK (" + str(len(job_desc)) + " chars)", end="")

        # Extract salary if missing
        fields = {"job_description": job_desc}
        if not (row["salary"] or "").strip():
            sal = extract_salary_from_text(job_desc)
            if sal:
                fields["salary"] = sal

        # Now get company description via Claude
        try:
            desc, industry = get_company_info_from_claude(
                client, row["company_name"], row["job_title"] or "", job_desc
            )
            if desc:
                fields["company_description"] = desc
                fields["company_industry"] = industry
                described += 1
                print(" -> " + industry)
            else:
                print(" (no description extracted)")
        except Exception as e:
            print(" Claude error: " + str(e)[:50])

        update_lead(row["id"], **fields)
        time.sleep(3)  # polite delay between LinkedIn requests

    print("\n--- Done ---")
    print("Job descriptions scraped: " + str(scraped))
    print("Company descriptions filled: " + str(described))
    print("Failed to scrape: " + str(failed))

    if described > 0:
        print("\nRe-run export_xlsx.py to get the updated Excel file.")


if __name__ == "__main__":
    run()
