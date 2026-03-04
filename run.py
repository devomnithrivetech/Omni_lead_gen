"""
Omnithrive Lead Generation Pipeline.

Usage:
  python run.py              Full pipeline (scrape + enrich + draft)
  python run.py scrape       Scrape LinkedIn jobs only
  python run.py enrich       Find websites + decision makers
  python run.py draft        Draft emails only
  python run.py stats        Pipeline statistics
  python run.py review       Review all drafted emails
  python run.py export       Export leads to Excel
"""
import sys
import os
from db import get_stats, get_leads_by_status, get_all_leads
from scraper import run_scraper
from enricher import run_enricher
from drafter import run_drafter


def review_drafts():
    drafts = get_leads_by_status("drafted")
    if not drafts:
        print("No drafted emails to review.")
        return
    print("")
    print("=" * 70)
    print("  DRAFTED EMAILS (" + str(len(drafts)) + " total)")
    print("=" * 70)
    for i, lead in enumerate(drafts, 1):
        print("")
        print("--- Lead #" + str(i) + " ---")
        print("Company:    " + str(lead["company_name"]))
        print("Website:    " + str(lead.get("company_website", "")))
        desc = str(lead.get("company_description", ""))
        if desc:
            print("About:      " + desc[:100])
        ind = str(lead.get("company_industry", ""))
        if ind:
            print("Industry:   " + ind)
        print("Job:        " + str(lead["job_title"]))
        print("Location:   " + str(lead.get("job_location", "")))
        dm = str(lead.get("decision_maker_name", ""))
        dt = str(lead.get("decision_maker_title", ""))
        print("Contact:    " + dm + " (" + dt + ")")
        print("Email:      " + str(lead.get("decision_maker_email", "")))
        li = str(lead.get("decision_maker_linkedin", ""))
        if li:
            print("LinkedIn:   " + li)
        print("")
        print("Subject:    " + str(lead.get("draft_subject", "")))
        print("")
        print(str(lead.get("draft_email", "")))
        print("_" * 70)


def export_xlsx():
    from export_xlsx import export
    export()


def run_full_pipeline():
    print("=" * 60)
    print("  OMNITHRIVE LEAD GENERATION PIPELINE v3")
    print("  USA + Europe | AI Roles | Past 24 Hours")
    print("=" * 60)

    run_scraper()
    run_enricher()
    run_drafter()

    print("")
    print("=" * 60)
    print("  PIPELINE COMPLETE")
    print("=" * 60)
    get_stats()
    print("Next steps:")
    print("  python run.py review   - See drafted emails")
    print("  python run.py export   - Export leads to Excel")
    print("")


COMMANDS = {
    "scrape": run_scraper,
    "enrich": run_enricher,
    "draft": run_drafter,
    "stats": get_stats,
    "review": review_drafts,
    "export": export_xlsx,
}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in COMMANDS:
            COMMANDS[cmd]()
        else:
            print("Unknown command: " + cmd)
            print("Available: " + ", ".join(COMMANDS.keys()))
    else:
        run_full_pipeline()