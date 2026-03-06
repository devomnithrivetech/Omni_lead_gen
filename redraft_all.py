"""
Redraft ALL existing emails in the DB using the updated prompt.

Overwrites draft_subject and draft_email for every lead that has
a decision_maker_email, regardless of whether a draft already exists.

Run: python redraft_all.py
"""
import sqlite3
import time
from config import DB_PATH, ANTHROPIC_API_KEY
from draft_emails import generate_email


def run():
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        return

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    all_candidates = conn.execute(
        """SELECT * FROM leads
           WHERE decision_maker_email IS NOT NULL
           AND decision_maker_email != ''
           ORDER BY company_name"""
    ).fetchall()

    if not all_candidates:
        print("No leads with emails found.")
        conn.close()
        return

    # Pick ONE best row per company: score = DM name (3) + has JD (2) + has desc (1)
    best_per_company = {}
    for row in all_candidates:
        r = dict(row)
        key = r["company_name"]
        score = (
            (3 if (r.get("decision_maker_name") or "").strip() else 0) +
            (2 if (r.get("job_description") or "").strip() else 0) +
            (1 if (r.get("company_description") or "").strip() else 0)
        )
        if key not in best_per_company or score > best_per_company[key][0]:
            best_per_company[key] = (score, r)

    rows = [v[1] for v in sorted(best_per_company.values(), key=lambda x: x[1]["company_name"])]

    total = len(rows)
    print("")
    print("=" * 60)
    print("  REDRAFT ALL: " + str(total) + " unique companies (from " + str(len(all_candidates)) + " total leads)")
    print("  Using updated formal prompt + 1/10th salary pitch")
    print("=" * 60)
    print("")

    done = 0
    failed = 0

    for i, lead in enumerate(rows):
        company = lead["company_name"]
        dm_name = (lead.get("decision_maker_name") or "").strip()
        salary = (lead.get("salary") or "not listed")
        prefix = "[" + str(i + 1) + "/" + str(total) + "] " + company

        try:
            subject, body = generate_email(client, lead)
            if subject and body:
                conn.execute(
                    "UPDATE leads SET draft_subject = ?, draft_email = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (subject, body, lead["id"])
                )
                conn.commit()
                done += 1
                dm_label = dm_name if dm_name else "(no DM name)"
                print(prefix + " -> " + dm_label + " [salary: " + salary + "]")
            else:
                failed += 1
                print(prefix + " FAILED (empty response)")
        except Exception as e:
            failed += 1
            print(prefix + " ERROR: " + str(e)[:80])

        time.sleep(0.5)

    conn.close()

    print("")
    print("=" * 60)
    print("  Done. Redrafted: " + str(done) + " | Failed: " + str(failed))
    print("=" * 60)

    if done > 0:
        print("\nExporting updated Excel...")
        from export_xlsx import export
        export()


if __name__ == "__main__":
    run()
