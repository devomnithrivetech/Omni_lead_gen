import json
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, COMPANY_NAME, COMPANY_PITCH
from db import get_leads_by_status, update_lead, get_stats


SYSTEM_MSG = (
    "You are a B2B sales copywriter. You write short, "
    "direct, personalized cold emails. Always respond "
    "with valid JSON only, no markdown fences. "
    'JSON keys must be: subject, email, linkedin_note'
)


def build_prompt(lead):
    parts = [
        "You are writing a cold email on behalf of " + COMPANY_NAME + ",",
        "a company described as: " + COMPANY_PITCH,
        "",
        "TARGET COMPANY: " + lead["company_name"],
        "WEBSITE: " + str(lead.get("company_website", "")),
        "ABOUT: " + str(lead.get("company_description", "")),
        "INDUSTRY: " + str(lead.get("company_industry", "")),
        "HIRING FOR: " + lead["job_title"],
        "LOCATION: " + str(lead.get("job_location", "")),
        "",
        "JOB DESCRIPTION:",
        str(lead.get("job_description", "AI-related role"))[:800],
        "",
        "SENDING TO: " + str(lead.get("decision_maker_name", "")),
        "THEIR ROLE: " + str(lead.get("decision_maker_title", "")),
        "",
        "Write a short, personalized cold email (under 150 words) that:",
        "1. Acknowledges they are actively building their AI team",
        "2. References something specific from the job description",
        "3. Offers our AI development services as a faster alternative",
        "4. Ends with a soft call-to-action to book a 15-min call",
        "5. Sounds like a real human, not a template",
        "",
        "Also write:",
        "- A subject line (under 50 characters)",
        "- A short LinkedIn connection note (under 280 characters)",
        "",
        'Respond ONLY in valid JSON: {"subject": "...", "email": "...", "linkedin_note": "..."}',
    ]
    return "\n".join(parts)


def draft_email(lead):
    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY not set")
        return None

    client = Groq(api_key=GROQ_API_KEY)

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user", "content": build_prompt(lead)},
            ],
            temperature=0.7,
            max_tokens=500,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        result = json.loads(raw)
        return result

    except json.JSONDecodeError:
        print("    WARNING: LLM returned invalid JSON.")
        return None
    except Exception as e:
        print("    ERROR: Groq API failed: " + str(e))
        return None


def run_drafter():
    print("")
    print("=" * 60)
    print("  DRAFTER: Generating personalized cold emails")
    print("=" * 60)

    leads = get_leads_by_status("enriched")
    if not leads:
        print("No enriched leads to draft for.")
        return 0

    print("Found " + str(len(leads)) + " leads to draft emails for.")
    drafted = 0

    for lead in leads:
        company = lead["company_name"]
        contact = str(lead.get("decision_maker_name", "Decision Maker"))
        print("  Drafting for " + contact + " at " + company + "...", end="")

        result = draft_email(lead)

        if result:
            update_lead(
                lead["id"],
                draft_subject=result.get("subject", ""),
                draft_email=result.get("email", ""),
                draft_linkedin_note=result.get("linkedin_note", ""),
                status="drafted",
            )
            drafted += 1
            print(" DONE")
        else:
            print(" FAILED")

    print("Drafter done: " + str(drafted) + " emails drafted.")
    get_stats()
    return drafted


if __name__ == "__main__":
    run_drafter()