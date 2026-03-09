"""
Personalised Email Drafter using Claude.
Generates a tailored cold email for every lead in the export.
- If decision maker name + title is known -> personalised to them directly
- Otherwise -> personalised to the company/hiring context
Saves draft_subject + draft_email back to DB, then re-exports Excel.
"""
import re
import sqlite3
import time
from config import DB_PATH, ANTHROPIC_API_KEY

# ============================================================
#  OMNITHRIVE CONTEXT (loaded once, used in every prompt)
# ============================================================
OMNITHRIVE_CONTEXT = """
Company: Omnithrive Technologies
Tagline: AI Value Acceleration Studio
Founder & CEO: Shivakumar C
Location: Bangalore, India
Website: www.omnithrivetech.com
Contact: admin@omnithrivetech.com | WhatsApp: +91 97426 09264

Core Promise: Production-grade GenAI and agentic AI systems for enterprise environments.
Not prototypes, not research, not demos. Deployable, observable, client-ready AI applications.

Key differentiators:
- Skilled AI engineers based in Bangalore, available on-demand
- 1/8th to 1/10th the cost of a US/UK senior AI hire, with zero benefits overhead and no equity dilution
- 2-week integration time vs months for a senior hire
- Scalable capacity - up or down across projects without fixed headcount
- Team behind every engineer: peer review, architectural oversight, delivery continuity
- Production-ready systems built to enterprise standards, not POCs

Tech stack our engineers work with:
- Agentic AI: LangChain, LangGraph, AutoGen, CrewAI, LangFuse
- RAG pipelines: hybrid retrieval, reranking, vector and graph database integrations
- Context engineering, multi-agent orchestration
- MLOps end-to-end, secure cloud environments: AWS, GCP, Azure
- LLMs: GPT-4, Claude, Llama, Mistral, Gemini
- Automation: n8n, Zapier, Make (Integromat)

Ideal clients: Mid-to-large enterprises (200-2,000 employees) in Consulting, Logistics,
Manufacturing, Healthcare, Finance, SaaS, Retail.
"""

# ============================================================
#  PROMPT: WITH decision maker name + WITH salary data
# ============================================================
PROMPT_WITH_DM_WITH_SALARY = """You are writing a formal cold outreach email on behalf of Shivakumar C, Founder and CEO of Omnithrive Technologies.

OMNITHRIVE CONTEXT:
{omnithrive}

TARGET LEAD:
- Decision Maker: {dm_name} ({dm_title})
- Company: {company}
- Industry: {industry}
- What they do: {description}
- Currently hiring for: {job_title}
- Tech stack / keywords from their JD: {keywords}
- Salary band for this hire: {salary_budget}/year
- 1/10th cost equivalent: {salary_tenth}/year

JOB DESCRIPTION EXCERPT:
{job_description}

INSTRUCTIONS — write the email in the EXACT structure below. Do not skip or reorder any section.

---

SECTION 1 - OPENING (2 sentences):
Start with: "We have yet to be properly introduced, I am Shivakumar, Founder and CEO of Omnithrive Technologies."
Then in one sentence: say you came across {company}'s {job_title} opening and wanted to reach out directly.

SECTION 2 - VALUE HOOK (1-2 sentences):
State that Omnithrive can meaningfully support the kind of AI delivery work their team is scaling - in a way that extends capacity without the cost and lead time of a senior hire in their market.

SECTION 3 - COMPANY DESCRIPTION (3-4 sentences):
Introduce Omnithrive as an AI Value Acceleration Studio based in Bangalore. Emphasise: production-grade GenAI and agentic AI systems for enterprise environments - not prototypes, not research, not demos. Deployable, observable, client-ready AI applications.

SECTION 4 - "Why Omnithrive is relevant to what {company} is building" (use this as a heading, substituting the actual company name):
Open with 2-3 sentences observing that their {job_title} role description is unusually precise - and explain WHY, drawing directly from the JD excerpt. Reference specific technical requirements, tools, or responsibilities you see in their JD (e.g. specific LLM frameworks, deployment environments, MLOps requirements, data pipeline needs). Show that you have actually read their job description.
Then write 3-4 sentences describing Omnithrive's engineers at this same level - referencing the same technical areas pulled from the JD. Be specific about what the engineers have shipped, not just what they know.

SECTION 5 - COMPARISON BULLETS (introduce with: "Here is how a partnership with Omnithrive compares to a direct senior hire:"):
Write exactly 4 bullet points:
- Cost: State that a dedicated senior AI engineer through Omnithrive costs roughly 1/8th to 1/10th of the {salary_budget} salary band, with zero benefits overhead and no equity dilution.
- Speed: A vetted engineer can be integrated with their delivery team within 2 weeks, not the months a senior search typically takes.
- Scalability: Tie this to their specific business model or industry ({industry}) - explain how variable demand in their context makes on-demand capacity preferable to fixed headcount.
- Quality assurance: They are not hiring an individual contractor - they get a team behind the engineer, with peer review, architectural oversight, and delivery continuity across projects.

SECTION 6 - INDUSTRY/CONTEXT PARAGRAPH (3-4 sentences):
Acknowledge their specific business context ({industry}, {description}). Show you understand the stakes in their environment - e.g. client delivery quality, speed, credibility, security, or outcomes measurement. Draw a direct parallel between how they measure success and how Omnithrive is built around the same premise.

SECTION 7 - SOFT CTA (follow this structure closely):
Start with: "I am not asking for a long conversation. Just 20 minutes."
Then say you will walk them through: profiles of engineers who match their technical requirements directly, how Omnithrive integrates with existing delivery teams, and address any questions about client confidentiality, security protocols, or IP protection upfront.
End with: "Would you be open to a brief call this week or next? or you can book a meeting on my calender as per your availability -  https://cal.com/omnithrivetech-ceo"

SECTION 8 - CLOSING:
Close with exactly:
Best regards,
Shivakumar C
Founder & CEO, Omnithrive Technologies
www.omnithrivetech.com
+919880283664

---

HARD RULES:
- ADDRESS: Start with "Dear {dm_name}," on the very first line
- TONE: Formal, authoritative, peer-to-peer. Not salesy. Not sycophantic. No filler phrases like "I hope this finds you well."
- SPECIFICITY: Every technical reference must come from the actual JD excerpt above. Do not invent requirements.
- PUNCTUATION: No em-dashes or en-dashes. Use plain hyphens (-). Use straight quotes only.
- LENGTH: 450 to 520 words for the email body. Count carefully.

SUBJECT LINE RULES:
- Under 60 characters
- Specific to {company} or their {job_title} role - curiosity-driven, not salesy
- Good examples: "A thought on {company}'s AI build" | "{company}'s AI hiring - a perspective" | "Re: your {job_title} search"
- NEVER use: free, guaranteed, limited time, act now, offer, deal, click, earn, discount, prize, winner, congratulations, urgent, no cost, 100%, !!!, $$$

Respond ONLY in this exact format:
SUBJECT: <subject line>
EMAIL:
<email body>"""


# ============================================================
#  PROMPT: WITH decision maker name + NO salary data
# ============================================================
PROMPT_WITH_DM_NO_SALARY = """You are writing a formal cold outreach email on behalf of Shivakumar C, Founder and CEO of Omnithrive Technologies.

OMNITHRIVE CONTEXT:
{omnithrive}

TARGET LEAD:
- Decision Maker: {dm_name} ({dm_title})
- Company: {company}
- Industry: {industry}
- What they do: {description}
- Currently hiring for: {job_title}
- Tech stack / keywords from their JD: {keywords}

JOB DESCRIPTION EXCERPT:
{job_description}

INSTRUCTIONS — write the email in the EXACT structure below. Do not skip or reorder any section.

---

SECTION 1 - OPENING (2 sentences):
Start with: "We have yet to be properly introduced, I am Shivakumar, Founder and CEO of Omnithrive Technologies."
Then in one sentence: say you came across {company}'s {job_title} opening and wanted to reach out directly.

SECTION 2 - VALUE HOOK (1-2 sentences):
State that Omnithrive can meaningfully support the kind of AI delivery work their team is scaling - in a way that extends capacity without the cost and lead time of a senior hire in their market.

SECTION 3 - COMPANY DESCRIPTION (3-4 sentences):
Introduce Omnithrive as an AI Value Acceleration Studio based in Bangalore. Emphasise: production-grade GenAI and agentic AI systems for enterprise environments - not prototypes, not research, not demos. Deployable, observable, client-ready AI applications.

SECTION 4 - "Why Omnithrive is relevant to what {company} is building" (use this as a heading, substituting the actual company name):
Open with 2-3 sentences observing that their {job_title} role description is unusually precise - and explain WHY, drawing directly from the JD excerpt. Reference specific technical requirements, tools, or responsibilities you see in their JD. Show that you have actually read their job description.
Then write 3-4 sentences describing Omnithrive's engineers at this same level - referencing the same technical areas pulled from the JD. Be specific about what the engineers have shipped, not just what they know.

SECTION 5 - COMPARISON BULLETS (introduce with: "Here is how a partnership with Omnithrive compares to a direct senior hire:"):
Write exactly 4 bullet points:
- Cost: State that a dedicated senior AI engineer through Omnithrive costs a fraction of what a comparable US or UK market hire would command - with zero benefits overhead and no equity dilution. Do NOT invent or assume any specific salary figure.
- Speed: A vetted engineer can be integrated with their delivery team within 2 weeks, not the months a senior search typically takes.
- Scalability: Tie this to their specific business model or industry ({industry}) - explain how variable demand makes on-demand capacity preferable to fixed headcount.
- Quality assurance: They are not hiring an individual contractor - they get a team behind the engineer, with peer review, architectural oversight, and delivery continuity.

SECTION 6 - INDUSTRY/CONTEXT PARAGRAPH (3-4 sentences):
Acknowledge their specific business context ({industry}, {description}). Show you understand the stakes in their environment. Draw a direct parallel between how they measure success and how Omnithrive is built.

SECTION 7 - SOFT CTA:
Start with: "I am not asking for a long conversation. Just 20 minutes."
Then say you will walk them through: profiles of engineers matching their technical requirements, how Omnithrive integrates with existing delivery teams, and address questions about confidentiality, security, or IP protection upfront.
End with: "Would you be open to a brief call this week or next?"

SECTION 8 - CLOSING:
Best regards,
Shivakumar C
Founder & CEO, Omnithrive Technologies
www.omnithrivetech.com

---

HARD RULES:
- ADDRESS: Start with "Dear {dm_name}," on the very first line
- TONE: Formal, authoritative, peer-to-peer. Not salesy. Not sycophantic. No filler phrases.
- SPECIFICITY: Every technical reference must come from the actual JD excerpt above. Do not invent requirements.
- PUNCTUATION: No em-dashes or en-dashes. Use plain hyphens (-). Straight quotes only.
- LENGTH: 450 to 520 words for the email body. Count carefully.

SUBJECT LINE RULES:
- Under 60 characters
- Specific to {company} or their {job_title} role - curiosity-driven, not salesy
- Good examples: "A thought on {company}'s AI build" | "{company}'s AI hiring - a perspective" | "Re: your {job_title} search"
- NEVER use: free, guaranteed, limited time, act now, offer, deal, click, earn, discount, prize, winner, congratulations, urgent, no cost, 100%, !!!, $$$

Respond ONLY in this exact format:
SUBJECT: <subject line>
EMAIL:
<email body>"""


# ============================================================
#  PROMPT: NO decision maker name + WITH salary data
# ============================================================
PROMPT_WITHOUT_DM_WITH_SALARY = """You are writing a formal cold outreach email on behalf of Shivakumar C, Founder and CEO of Omnithrive Technologies.

OMNITHRIVE CONTEXT:
{omnithrive}

TARGET LEAD:
- Company: {company}
- Industry: {industry}
- What they do: {description}
- Currently hiring for: {job_title}
- Tech stack / keywords from their JD: {keywords}
- Salary band for this hire: {salary_budget}/year
- 1/10th cost equivalent: {salary_tenth}/year

JOB DESCRIPTION EXCERPT:
{job_description}

INSTRUCTIONS — write the email in the EXACT structure below. Do not skip or reorder any section.

---

SECTION 1 - OPENING (2 sentences):
Start with: "We have yet to be properly introduced, I am Shivakumar, Founder and CEO of Omnithrive Technologies."
Then in one sentence: say you came across {company}'s {job_title} opening and wanted to reach out directly.

SECTION 2 - VALUE HOOK (1-2 sentences):
State that Omnithrive can meaningfully support the kind of AI delivery work their team is scaling - in a way that extends capacity without the cost and lead time of a senior hire in their market.

SECTION 3 - COMPANY DESCRIPTION (3-4 sentences):
Introduce Omnithrive as an AI Value Acceleration Studio based in Bangalore. Emphasise: production-grade GenAI and agentic AI systems for enterprise environments - not prototypes, not research, not demos. Deployable, observable, client-ready AI applications.

SECTION 4 - "Why Omnithrive is relevant to what {company} is building" (use this as a heading, substituting the actual company name):
Open with 2-3 sentences observing that their {job_title} role description is unusually precise - and explain WHY, drawing directly from the JD excerpt. Reference specific technical requirements, tools, or responsibilities you see in their JD.
Then write 3-4 sentences describing Omnithrive's engineers at this same level - referencing the same technical areas pulled from the JD.

SECTION 5 - COMPARISON BULLETS (introduce with: "Here is how a partnership with Omnithrive compares to a direct senior hire:"):
Write exactly 4 bullet points:
- Cost: Roughly 1/8th to 1/10th of the {salary_budget} salary band, with zero benefits overhead and no equity dilution.
- Speed: A vetted engineer integrated within 2 weeks, not the months a senior search takes.
- Scalability: Tie to their industry ({industry}) and how on-demand capacity suits their business model.
- Quality assurance: A team behind every engineer - peer review, architectural oversight, delivery continuity.

SECTION 6 - INDUSTRY/CONTEXT PARAGRAPH (3-4 sentences):
Acknowledge their business context ({industry}, {description}). Draw a parallel between how they measure success and how Omnithrive is built.

SECTION 7 - SOFT CTA:
Start with: "I am not asking for a long conversation. Just 20 minutes."
List 3 call agenda items: engineer profiles matching requirements, integration approach, confidentiality/security/IP.
End with: "Would you be open to a brief call this week or next?"

SECTION 8 - CLOSING:
Best regards,
Shivakumar C
Founder & CEO, Omnithrive Technologies
www.omnithrivetech.com

---

HARD RULES:
- ADDRESS: Start with "Dear {company} Team," on the very first line. Never "Dear Hiring Manager."
- TONE: Formal, authoritative, peer-to-peer. Not salesy. No filler phrases.
- SPECIFICITY: Every technical reference must come from the actual JD excerpt. Do not invent requirements.
- PUNCTUATION: No em-dashes or en-dashes. Use plain hyphens (-). Straight quotes only.
- LENGTH: 450 to 520 words for the email body. Count carefully.

SUBJECT LINE RULES:
- Under 60 characters. Curiosity-driven, not salesy.
- Good examples: "A thought on {company}'s AI build" | "{company}'s AI hiring - a perspective" | "Re: your {job_title} search"
- NEVER use: free, guaranteed, limited time, act now, offer, deal, click, earn, discount, prize, winner, congratulations, urgent, no cost, 100%, !!!, $$$

Respond ONLY in this exact format:
SUBJECT: <subject line>
EMAIL:
<email body>"""


# ============================================================
#  PROMPT: NO decision maker name + NO salary data
# ============================================================
PROMPT_WITHOUT_DM_NO_SALARY = """You are writing a formal cold outreach email on behalf of Shivakumar C, Founder and CEO of Omnithrive Technologies.

OMNITHRIVE CONTEXT:
{omnithrive}

TARGET LEAD:
- Company: {company}
- Industry: {industry}
- What they do: {description}
- Currently hiring for: {job_title}
- Tech stack / keywords from their JD: {keywords}

JOB DESCRIPTION EXCERPT:
{job_description}

INSTRUCTIONS — write the email in the EXACT structure below. Do not skip or reorder any section.

---

SECTION 1 - OPENING (2 sentences):
Start with: "We have yet to be properly introduced, I am Shivakumar, Founder and CEO of Omnithrive Technologies."
Then in one sentence: say you came across {company}'s {job_title} opening and wanted to reach out directly.

SECTION 2 - VALUE HOOK (1-2 sentences):
State that Omnithrive can meaningfully support the kind of AI delivery work their team is scaling - in a way that extends capacity without the cost and lead time of a senior hire in their market.

SECTION 3 - COMPANY DESCRIPTION (3-4 sentences):
Introduce Omnithrive as an AI Value Acceleration Studio based in Bangalore. Emphasise: production-grade GenAI and agentic AI systems for enterprise environments - not prototypes, not research, not demos. Deployable, observable, client-ready AI applications.

SECTION 4 - "Why Omnithrive is relevant to what {company} is building" (use this as a heading, substituting the actual company name):
Open with 2-3 sentences observing that their {job_title} role description is unusually precise - and explain WHY, drawing directly from the JD excerpt. Reference specific technical requirements, tools, or responsibilities you see in their JD.
Then write 3-4 sentences describing Omnithrive's engineers at this same level - referencing the same technical areas pulled from the JD.

SECTION 5 - COMPARISON BULLETS (introduce with: "Here is how a partnership with Omnithrive compares to a direct senior hire:"):
Write exactly 4 bullet points:
- Cost: A fraction of what a comparable market hire would command - with zero benefits overhead and no equity dilution. Do NOT invent any salary figure.
- Speed: A vetted engineer integrated within 2 weeks, not the months a senior search takes.
- Scalability: Tie to their industry ({industry}) and how on-demand capacity suits their business model.
- Quality assurance: A team behind every engineer - peer review, architectural oversight, delivery continuity.

SECTION 6 - INDUSTRY/CONTEXT PARAGRAPH (3-4 sentences):
Acknowledge their business context ({industry}, {description}). Draw a parallel between how they measure success and how Omnithrive is built.

SECTION 7 - SOFT CTA:
Start with: "I am not asking for a long conversation. Just 20 minutes."
List 3 call agenda items: engineer profiles matching requirements, integration approach, confidentiality/security/IP.
End with: "Would you be open to a brief call this week or next?"

SECTION 8 - CLOSING:
Best regards,
Shivakumar C
Founder & CEO, Omnithrive Technologies
www.omnithrivetech.com

---

HARD RULES:
- ADDRESS: Start with "Dear {company} Team," on the very first line. Never "Dear Hiring Manager."
- TONE: Formal, authoritative, peer-to-peer. Not salesy. No filler phrases.
- SPECIFICITY: Every technical reference must come from the actual JD excerpt. Do not invent requirements.
- PUNCTUATION: No em-dashes or en-dashes. Use plain hyphens (-). Straight quotes only.
- LENGTH: 450 to 520 words for the email body. Count carefully.

SUBJECT LINE RULES:
- Under 60 characters. Curiosity-driven, not salesy.
- Good examples: "A thought on {company}'s AI build" | "{company}'s AI hiring - a perspective" | "Re: your {job_title} search"
- NEVER use: free, guaranteed, limited time, act now, offer, deal, click, earn, discount, prize, winner, congratulations, urgent, no cost, 100%, !!!, $$$

Respond ONLY in this exact format:
SUBJECT: <subject line>
EMAIL:
<email body>"""


def sanitize_text(text: str) -> str:
    """Replace AI-telltale punctuation with plain equivalents."""
    text = text.replace("\u2014", "-")   # em-dash
    text = text.replace("\u2013", "-")   # en-dash
    text = text.replace("\u2018", "'").replace("\u2019", "'")   # left/right single
    text = text.replace("\u201c", '"').replace("\u201d", '"')   # left/right double
    text = text.replace("\u2026", "...")
    return text


def get_salary_pitch(salary_raw):
    """
    Returns (budget_str, tenth_str, has_salary).
    has_salary is False if no usable salary figure was found — callers should
    then use a no-salary prompt variant and omit specific figures entirely.
    """
    if salary_raw:
        normalised = re.sub(r'(\d+)\s*[kK]\b', lambda m: str(int(m.group(1)) * 1000), salary_raw)
        nums = re.findall(r'\d[\d,]*', normalised)
        for n in nums:
            try:
                val = int(n.replace(",", ""))
                if 30000 <= val <= 1000000:  # plausible annual salary
                    tenth = val // 10
                    return "${:,}".format(val), "${:,}".format(tenth), True
            except ValueError:
                continue
    return None, None, False


def generate_email(client, lead):
    company = lead.get("company_name", "")
    dm_name = (lead.get("decision_maker_name") or "").strip()
    dm_title = (lead.get("decision_maker_title") or "").strip()
    description = (lead.get("company_description") or "").strip()
    industry = (lead.get("company_industry") or "").strip()
    job_title = (lead.get("job_title") or "").strip()
    keywords = (lead.get("tech_keywords") or "").strip()
    job_desc = (lead.get("job_description") or "").strip()
    salary_budget, salary_tenth, has_salary = get_salary_pitch(lead.get("salary", ""))

    jd_excerpt = job_desc[:800] if job_desc else "(No job description available - use company info and industry context to personalise.)"

    # Select the right prompt variant based on DM availability and salary presence
    if dm_name and has_salary:
        prompt = PROMPT_WITH_DM_WITH_SALARY.format(
            omnithrive=OMNITHRIVE_CONTEXT,
            dm_name=dm_name,
            dm_title=dm_title or "Decision Maker",
            company=company,
            industry=industry or "Technology",
            description=description or "an enterprise company",
            job_title=job_title,
            keywords=keywords[:300] if keywords else "AI/ML",
            salary_budget=salary_budget,
            salary_tenth=salary_tenth,
            job_description=jd_excerpt,
        )
    elif dm_name and not has_salary:
        prompt = PROMPT_WITH_DM_NO_SALARY.format(
            omnithrive=OMNITHRIVE_CONTEXT,
            dm_name=dm_name,
            dm_title=dm_title or "Decision Maker",
            company=company,
            industry=industry or "Technology",
            description=description or "an enterprise company",
            job_title=job_title,
            keywords=keywords[:300] if keywords else "AI/ML",
            job_description=jd_excerpt,
        )
    elif not dm_name and has_salary:
        prompt = PROMPT_WITHOUT_DM_WITH_SALARY.format(
            omnithrive=OMNITHRIVE_CONTEXT,
            company=company,
            industry=industry or "Technology",
            description=description or "an enterprise company",
            job_title=job_title,
            keywords=keywords[:300] if keywords else "AI/ML",
            salary_budget=salary_budget,
            salary_tenth=salary_tenth,
            job_description=jd_excerpt,
        )
    else:
        prompt = PROMPT_WITHOUT_DM_NO_SALARY.format(
            omnithrive=OMNITHRIVE_CONTEXT,
            company=company,
            industry=industry or "Technology",
            description=description or "an enterprise company",
            job_title=job_title,
            keywords=keywords[:300] if keywords else "AI/ML",
            job_description=jd_excerpt,
        )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,  # increased to accommodate longer email format (~500 words)
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    subject, email_body = "", ""

    lines = raw.split("\n")
    body_lines = []
    in_body = False

    for line in lines:
        if line.startswith("SUBJECT:"):
            subject = line.replace("SUBJECT:", "").strip()
        elif line.startswith("EMAIL:"):
            in_body = True
        elif in_body:
            body_lines.append(line)

    email_body = "\n".join(body_lines).strip()
    return sanitize_text(subject), sanitize_text(email_body)


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
           AND (draft_email IS NULL OR draft_email = '')
           AND company_name NOT IN (
               SELECT DISTINCT company_name FROM leads
               WHERE draft_email IS NOT NULL AND draft_email != ''
           )
           ORDER BY company_name"""
    ).fetchall()

    # Pick best row per company: score = DM name (3) + has JD (2) + has desc (1)
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

    if not rows:
        print("All leads already have draft emails. Nothing to do.")
        conn.close()
        return

    total = len(rows)
    print("Drafting emails for " + str(total) + " leads using Claude Haiku...\n")

    done = 0
    failed = 0

    for i, lead in enumerate(rows):
        company = lead["company_name"]
        dm_name = (lead.get("decision_maker_name") or "").strip()
        _, _, has_salary = get_salary_pitch(lead.get("salary", ""))
        prefix = "[" + str(i + 1) + "/" + str(total) + "] " + company

        try:
            subject, body = generate_email(client, lead)
            if subject and body:
                conn.execute(
                    "UPDATE leads SET draft_subject = ?, draft_email = ?, "
                    "status = 'drafted' WHERE id = ?",
                    (subject, body, lead["id"])
                )
                conn.commit()
                done += 1
                dm_label = " -> " + dm_name if dm_name else " -> (no DM)"
                salary_label = " [salary known]" if has_salary else " [no salary]"
                print(prefix + dm_label + salary_label)
            else:
                failed += 1
                print(prefix + " FAILED (empty response)")
        except Exception as e:
            failed += 1
            print(prefix + " ERROR: " + str(e)[:60])

        time.sleep(0.5)

    conn.close()
    print("\nDone. Drafted: " + str(done) + " | Failed: " + str(failed))

    if done > 0:
        print("\nRe-exporting Excel with draft emails...")
        from export_xlsx import export
        export()


if __name__ == "__main__":
    run()