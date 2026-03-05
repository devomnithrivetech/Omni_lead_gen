"""
Fast keyword filler - no scraping, no API calls.
Extracts keywords from job_title + job_description already in DB.
Runs in seconds.
"""
import sqlite3
from config import DB_PATH
from keywords import extract_keywords_string


def fill_keywords():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT id, job_title, job_description
           FROM leads
           WHERE (tech_keywords IS NULL OR tech_keywords = '')"""
    ).fetchall()

    if not rows:
        print("All leads already have keywords. Nothing to do.")
        conn.close()
        return

    print("Filling keywords for " + str(len(rows)) + " leads...")

    updated = 0
    for row in rows:
        text = " ".join(filter(None, [
            row["job_title"] or "",
            row["job_description"] or "",
        ]))
        keywords = extract_keywords_string(text)
        conn.execute(
            "UPDATE leads SET tech_keywords = ? WHERE id = ?",
            (keywords, row["id"])
        )
        updated += 1

    conn.commit()
    conn.close()
    print("Done. Updated " + str(updated) + " leads.")


if __name__ == "__main__":
    fill_keywords()
