"""
One-time migration script: copies all data from local SQLite to PostgreSQL.
Run this once locally before switching to PostgreSQL on Railway.
"""
import sqlite3
import psycopg2
import psycopg2.extras
import os
from config import DB_PATH

PUBLIC_PG_URL = "postgresql://postgres:hEFHXKZYKnPaYSlxStDcUkjThRDFCjkV@yamanote.proxy.rlwy.net:45703/railway"

def migrate():
    print("Connecting to SQLite...")
    sqlite_conn = sqlite3.connect(DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    rows = sqlite_conn.execute("SELECT * FROM leads ORDER BY id").fetchall()
    rows = [dict(r) for r in rows]
    sqlite_conn.close()
    print(f"Found {len(rows)} leads in SQLite.")

    print("Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(PUBLIC_PG_URL)
    pg_cur = pg_conn.cursor()

    print("Creating table in PostgreSQL...")
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            company_name TEXT NOT NULL,
            company_website TEXT,
            company_domain TEXT,
            company_contact_email TEXT,
            company_description TEXT,
            company_industry TEXT,
            job_title TEXT,
            job_description TEXT,
            job_url TEXT,
            job_location TEXT,
            job_posted_date TEXT,
            salary TEXT,
            decision_maker_name TEXT,
            decision_maker_title TEXT,
            decision_maker_email TEXT,
            decision_maker_linkedin TEXT,
            draft_subject TEXT,
            draft_email TEXT,
            draft_linkedin_note TEXT,
            tech_keywords TEXT,
            status TEXT DEFAULT 'scraped',
            message_id TEXT,
            sent_at TEXT,
            opened_at TEXT,
            replied_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    pg_cur.execute("CREATE INDEX IF NOT EXISTS idx_status ON leads(status)")

    print("Inserting leads...")
    inserted = 0
    skipped = 0
    for row in rows:
        try:
            pg_cur.execute("""
                INSERT INTO leads (
                    id, company_name, company_website, company_domain,
                    company_contact_email, company_description, company_industry,
                    job_title, job_description, job_url, job_location,
                    job_posted_date, salary, decision_maker_name,
                    decision_maker_title, decision_maker_email,
                    decision_maker_linkedin, draft_subject, draft_email,
                    draft_linkedin_note, tech_keywords, status,
                    message_id, sent_at, opened_at, replied_at,
                    created_at, updated_at
                ) VALUES (
                    %(id)s, %(company_name)s, %(company_website)s, %(company_domain)s,
                    %(company_contact_email)s, %(company_description)s, %(company_industry)s,
                    %(job_title)s, %(job_description)s, %(job_url)s, %(job_location)s,
                    %(job_posted_date)s, %(salary)s, %(decision_maker_name)s,
                    %(decision_maker_title)s, %(decision_maker_email)s,
                    %(decision_maker_linkedin)s, %(draft_subject)s, %(draft_email)s,
                    %(draft_linkedin_note)s, %(tech_keywords)s, %(status)s,
                    %(message_id)s, %(sent_at)s, %(opened_at)s, %(replied_at)s,
                    %(created_at)s, %(updated_at)s
                ) ON CONFLICT (id) DO NOTHING
            """, row)
            inserted += 1
        except Exception as e:
            print(f"  Skipped lead id={row.get('id')}: {e}")
            skipped += 1

    # Reset the sequence so new inserts get correct IDs
    pg_cur.execute("SELECT setval('leads_id_seq', (SELECT MAX(id) FROM leads))")

    pg_conn.commit()
    pg_cur.close()
    pg_conn.close()

    print(f"Done! Inserted: {inserted}, Skipped: {skipped}")

if __name__ == "__main__":
    migrate()
