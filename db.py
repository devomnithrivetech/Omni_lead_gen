import os
import sqlite3
from datetime import datetime
from config import DB_PATH

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_connection():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn


def _fetchall(cursor):
    if USE_POSTGRES:
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    else:
        return [dict(r) for r in cursor.fetchall()]


def _fetchone(cursor):
    if USE_POSTGRES:
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))
    else:
        row = cursor.fetchone()
        return dict(row) if row else None


def _ph():
    return "%s" if USE_POSTGRES else "?"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db():
    conn = get_connection()
    c = conn.cursor()

    if USE_POSTGRES:
        c.execute("""
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
        c.execute("CREATE INDEX IF NOT EXISTS idx_status ON leads(status)")
    else:
        c.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_status ON leads(status)")
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_company_job
            ON leads(company_name, job_title)
        """)
        for col_name, col_type in [
            ("company_description", "TEXT"),
            ("company_industry", "TEXT"),
            ("tech_keywords", "TEXT"),
            ("salary", "TEXT"),
            ("message_id", "TEXT"),
            ("sent_at", "TEXT"),
            ("opened_at", "TEXT"),
            ("replied_at", "TEXT"),
        ]:
            try:
                c.execute("ALTER TABLE leads ADD COLUMN " + col_name + " " + col_type)
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()
    backend = "PostgreSQL" if USE_POSTGRES else "SQLite:" + DB_PATH
    print("Database ready: " + backend)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def insert_lead(company_name, job_title, job_description="",
                job_url="", job_location="", company_domain="",
                job_posted_date="", salary=""):
    conn = get_connection()
    ph = _ph()
    try:
        if USE_POSTGRES:
            conn.cursor().execute(
                f"""INSERT INTO leads
                   (company_name, company_domain, job_title, job_description,
                    job_url, job_location, job_posted_date, salary, status)
                   VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},'scraped')
                   ON CONFLICT DO NOTHING""",
                (company_name, company_domain, job_title,
                 job_description, job_url, job_location, job_posted_date, salary)
            )
        else:
            conn.execute(
                f"""INSERT INTO leads
                   (company_name, company_domain, job_title, job_description,
                    job_url, job_location, job_posted_date, salary, status)
                   VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},'scraped')""",
                (company_name, company_domain, job_title,
                 job_description, job_url, job_location, job_posted_date, salary)
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_leads_by_status(status):
    conn = get_connection()
    ph = _ph()
    c = conn.cursor()
    c.execute(f"SELECT * FROM leads WHERE status = {ph}", (status,))
    rows = _fetchall(c)
    conn.close()
    return rows


def update_lead(lead_id, **fields):
    if not fields:
        return
    fields["updated_at"] = datetime.now().isoformat()
    ph = _ph()
    if USE_POSTGRES:
        set_clause = ", ".join(k + " = %s" for k in fields)
    else:
        set_clause = ", ".join(k + " = ?" for k in fields)
    values = list(fields.values()) + [lead_id]
    conn = get_connection()
    conn.cursor().execute(
        f"UPDATE leads SET {set_clause} WHERE id = {ph}", values
    )
    conn.commit()
    conn.close()


def get_existing_companies():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT company_name FROM leads")
    rows = _fetchall(c)
    conn.close()
    return {r["company_name"].strip().lower() for r in rows}


def get_all_leads():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM leads ORDER BY created_at DESC")
    rows = _fetchall(c)
    conn.close()
    return rows


def get_stats():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) as count FROM leads GROUP BY status")
    rows = _fetchall(c)
    conn.close()

    print("")
    print("--- Pipeline Stats ---")
    total = 0
    for r in rows:
        print("  " + r["status"].ljust(16) + ": " + str(r["count"]))
        total += r["count"]
    print("  " + "TOTAL".ljust(16) + ": " + str(total))
    print("----------------------")
    print("")
    return {r["status"]: r["count"] for r in rows}


def mark_sent(lead_id, message_id):
    update_lead(lead_id, status="sent", message_id=message_id,
                sent_at=datetime.now().isoformat())


def mark_opened(lead_id):
    conn = get_connection()
    ph = _ph()
    c = conn.cursor()
    c.execute(f"SELECT status FROM leads WHERE id = {ph}", (lead_id,))
    row = _fetchone(c)
    conn.close()
    if row and row["status"] not in ("replied",):
        update_lead(lead_id, status="opened", opened_at=datetime.now().isoformat())


def mark_replied(lead_id):
    update_lead(lead_id, status="replied", replied_at=datetime.now().isoformat())


def get_lead_by_id(lead_id):
    conn = get_connection()
    ph = _ph()
    c = conn.cursor()
    c.execute(f"SELECT * FROM leads WHERE id = {ph}", (lead_id,))
    row = _fetchone(c)
    conn.close()
    return row


def get_lead_by_message_id(message_id):
    conn = get_connection()
    ph = _ph()
    c = conn.cursor()
    c.execute(f"SELECT * FROM leads WHERE message_id = {ph}", (message_id,))
    row = _fetchone(c)
    conn.close()
    return row


def get_lead_by_email(email):
    conn = get_connection()
    ph = _ph()
    c = conn.cursor()
    c.execute(
        f"SELECT * FROM leads WHERE decision_maker_email = {ph} AND status IN ('sent', 'opened')",
        (email,)
    )
    row = _fetchone(c)
    conn.close()
    return row


# Auto-initialize on import
init_db()

if __name__ == "__main__":
    get_stats()
