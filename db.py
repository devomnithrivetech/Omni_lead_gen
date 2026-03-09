import sqlite3
from datetime import datetime
from config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

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

    # Add new columns if upgrading from old schema
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
            pass  # Column already exists

    conn.commit()
    conn.close()
    print("Database ready: " + DB_PATH)


def insert_lead(company_name, job_title, job_description="",
                job_url="", job_location="", company_domain="",
                job_posted_date="", salary=""):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO leads
               (company_name, company_domain, job_title, job_description,
                job_url, job_location, job_posted_date, salary, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'scraped')""",
            (company_name, company_domain, job_title,
             job_description, job_url, job_location, job_posted_date, salary)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_leads_by_status(status):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM leads WHERE status = ?", (status,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_lead(lead_id, **fields):
    if not fields:
        return
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(k + " = ?" for k in fields)
    values = list(fields.values()) + [lead_id]
    conn = get_connection()
    conn.execute("UPDATE leads SET " + set_clause + " WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_existing_companies():
    """Return a set of all company_name values already in the DB (any status)."""
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT company_name FROM leads").fetchall()
    conn.close()
    return {r["company_name"].strip().lower() for r in rows}


def get_all_leads():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM leads ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, COUNT(*) as count FROM leads GROUP BY status"
    ).fetchall()
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
    row = conn.execute("SELECT status FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    if row and row["status"] not in ("replied",):
        update_lead(lead_id, status="opened", opened_at=datetime.now().isoformat())


def mark_replied(lead_id):
    update_lead(lead_id, status="replied", replied_at=datetime.now().isoformat())


def get_lead_by_id(lead_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_lead_by_message_id(message_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM leads WHERE message_id = ?", (message_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_lead_by_email(email):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM leads WHERE decision_maker_email = ? AND status IN ('sent', 'opened')",
        (email,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# Auto-initialize on import
init_db()

if __name__ == "__main__":
    get_stats()