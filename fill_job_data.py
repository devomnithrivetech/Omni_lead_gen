"""
Fill missing job descriptions + company descriptions for all leads.

Step 1: Scrape job descriptions from LinkedIn for leads missing them (has job_url)
Step 2: Use Claude to fill company description + industry from job text

Run: python fill_job_data.py
     python fill_job_data.py 100    # limit to 100 scrapes per run (default: 50)
"""
import sys
import time
import sqlite3
from config import DB_PATH
from scraper import scrape_job_description, extract_salary_from_text
from ai_providers import generate as ai_generate


def _company_prompt(company_name, job_title, location=""):
    loc_str = f" based in {location}" if location else ""
    return (
        f"You are a business researcher. The company '{company_name}'{loc_str} "
        f"is hiring for '{job_title}'.\n\n"
        "Based on the company name and role they are hiring for, provide:\n"
        "1. A concise 1-2 sentence description of what this company likely does\n"
        "2. Their most likely industry (e.g. FinTech, Healthcare AI, SaaS, "
        "Cybersecurity, EdTech, Logistics, Manufacturing, etc.)\n\n"
        "Respond ONLY in this exact format (no extra text):\n"
        "DESCRIPTION: <1-2 sentences>\n"
        "INDUSTRY: <industry>"
    )


def _parse_desc_industry(raw):
    desc, industry = "", ""
    for line in raw.splitlines():
        if line.startswith("DESCRIPTION:"):
            desc = line.replace("DESCRIPTION:", "").strip()
        elif line.startswith("INDUSTRY:"):
            industry = line.replace("INDUSTRY:", "").strip()
    return desc, industry


def get_company_info_from_ai(company_name, job_title, location=""):
    """Use AI provider chain to generate company description + industry (no JD available)."""
    prompt = _company_prompt(company_name, job_title, location)
    raw = ai_generate(prompt, max_tokens=150)
    if raw:
        return _parse_desc_industry(raw)
    return "", ""


def get_company_info_from_jd(company_name, job_title, job_description):
    """Extract company description + industry from a real job description."""
    prompt = (
        "Based on this job posting from '" + company_name + "', give me:\n"
        "1. A brief 1-2 sentence description of what this company does\n"
        "2. Their industry (e.g. FinTech, Healthcare AI, SaaS, Cybersecurity, etc.)\n\n"
        "Job Title: " + job_title + "\n\nJob Posting:\n" + job_description[:1500] + "\n\n"
        "Respond ONLY in this format (no extra text):\n"
        "DESCRIPTION: <1-2 sentences>\n"
        "INDUSTRY: <industry>"
    )
    raw = ai_generate(prompt, max_tokens=200)
    if raw:
        return _parse_desc_industry(raw)
    return "", ""



def run(limit=50):
    print("")
    print("=" * 60)
    print("  FILL JOB DATA: Job Descriptions + Company Descriptions")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Stats before
    total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    missing_job = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE (job_description IS NULL OR job_description = '') "
        "AND job_url IS NOT NULL AND job_url != ''"
    ).fetchone()[0]
    missing_desc = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE (company_description IS NULL OR company_description = '') "
        "AND job_description IS NOT NULL AND job_description != ''"
    ).fetchone()[0]

    print(f"  Total leads:              {total}")
    print(f"  Missing job description:  {missing_job} (will process up to {limit})")
    print(f"  Missing company desc:     {missing_desc} (will fill from existing job descriptions)")
    print("")

    # ================================================================
    #  STEP 1: Scrape job descriptions
    # ================================================================
    rows_needing_job = conn.execute(
        "SELECT id, company_name, job_title, job_url, job_location, salary "
        "FROM leads "
        "WHERE (job_description IS NULL OR job_description = '') "
        "AND job_url IS NOT NULL AND job_url != '' "
        "ORDER BY "
        "CASE WHEN decision_maker_email IS NOT NULL AND decision_maker_email != '' THEN 0 ELSE 1 END, "
        "company_name "
        "LIMIT ?", (limit,)
    ).fetchall()

    scraped_count = 0
    failed_count = 0

    if rows_needing_job:
        print(f"--- STEP 1: Scraping job descriptions ({len(rows_needing_job)} leads) ---")
        for i, row in enumerate(rows_needing_job):
            prefix = "[" + str(i + 1) + "/" + str(len(rows_needing_job)) + "] " + row["company_name"]
            print(prefix + " ...", end="", flush=True)

            job_desc = scrape_job_description(row["job_url"])

            if job_desc:
                fields = {"job_description": job_desc}
                # Extract salary if missing
                if not (row["salary"] or "").strip():
                    sal = extract_salary_from_text(job_desc)
                    if sal:
                        fields["salary"] = sal
                        print(" OK (" + str(len(job_desc)) + " chars) [" + sal + "]")
                    else:
                        print(" OK (" + str(len(job_desc)) + " chars)")
                else:
                    print(" OK (" + str(len(job_desc)) + " chars)")

                conn.execute(
                    "UPDATE leads SET job_description = ?, salary = COALESCE(NULLIF(salary,''), ?), "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (job_desc, fields.get("salary", ""), row["id"])
                )
                conn.commit()
                scraped_count += 1
            else:
                # Scraping failed — use AI chain to generate company description from name + title
                print(" no JD found, asking AI...", end="", flush=True)
                location = row["job_location"] if "job_location" in row.keys() else ""
                ai_desc, ai_industry = get_company_info_from_ai(
                    row["company_name"], row["job_title"] or "", location or ""
                )
                if ai_desc:
                    conn.execute(
                        "UPDATE leads SET company_description = COALESCE(NULLIF(company_description,''), ?), "
                        "company_industry = COALESCE(NULLIF(company_industry,''), ?), "
                        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (ai_desc, ai_industry, row["id"])
                    )
                    conn.commit()
                    print(f" -> {ai_industry or 'unknown'}")
                else:
                    print(" failed")
                failed_count += 1

            time.sleep(3)

        print("")
        print(f"Step 1 done: {scraped_count} scraped, {failed_count} failed")
    else:
        print("Step 1: No leads missing job descriptions. Skipping.")

    # ================================================================
    #  STEP 2: Fill company descriptions from job descriptions
    # ================================================================
    rows_needing_desc = conn.execute(
        "SELECT id, company_name, job_title, job_description "
        "FROM leads "
        "WHERE (company_description IS NULL OR company_description = '') "
        "AND job_description IS NOT NULL AND job_description != ''"
    ).fetchall()

    described_count = 0
    desc_failed = 0

    if rows_needing_desc:
        print("")
        print(f"--- STEP 2: Filling company descriptions ({len(rows_needing_desc)} leads) ---")

        for i, row in enumerate(rows_needing_desc):
            prefix = "[" + str(i + 1) + "/" + str(len(rows_needing_desc)) + "] " + row["company_name"]
            print(prefix + " ...", end="", flush=True)

            try:
                desc, industry = get_company_info_from_jd(
                    row["company_name"],
                    row["job_title"] or "",
                    row["job_description"]
                )
                if desc:
                    conn.execute(
                        "UPDATE leads SET company_description = ?, company_industry = ?, "
                        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (desc, industry, row["id"])
                    )
                    conn.commit()
                    described_count += 1
                    print(" -> " + (industry or "unknown industry"))
                else:
                    desc_failed += 1
                    print(" (no description extracted)")
            except Exception as e:
                desc_failed += 1
                print(" ERROR: " + str(e)[:50])

            time.sleep(0.5)

        print("")
        print(f"Step 2 done: {described_count} filled, {desc_failed} failed")
    else:
        print("Step 2: No leads missing company descriptions. Skipping.")

    conn.close()

    # Final stats
    print("")
    print("=" * 60)
    conn2 = sqlite3.connect(DB_PATH)
    new_job = conn2.execute(
        "SELECT COUNT(*) FROM leads WHERE job_description IS NOT NULL AND job_description != ''"
    ).fetchone()[0]
    new_desc = conn2.execute(
        "SELECT COUNT(*) FROM leads WHERE company_description IS NOT NULL AND company_description != ''"
    ).fetchone()[0]
    conn2.close()

    print(f"  Job descriptions now:     {new_job} / {total}")
    print(f"  Company descriptions now: {new_desc} / {total}")
    print("=" * 60)

    if described_count > 0 or scraped_count > 0:
        print("\nRe-export to get updated Excel: python export_xlsx.py")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    run(limit)
