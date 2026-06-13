"""
Daily Job Alert — Siddharth Singh
Fetches top backend/Kafka/distributed systems roles from target companies
using Google Gemini (FREE) + Google Search Grounding, then sends via Gmail SMTP.

Required GitHub Actions secrets:
  GEMINI_API_KEY      — free from aistudio.google.com (no credit card)
  GMAIL_ADDRESS       — your Gmail address
  GMAIL_APP_PASSWORD  — 16-char Gmail App Password (Google Account → Security)
  RECIPIENT_EMAIL     — where to send the digest
"""

import os
import json
import smtplib
import datetime
import urllib.request
import urllib.error
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Configuration ──────────────────────────────────────────────────────────────

COMPANIES = [
    {"name": "Google",      "url": "https://careers.google.com/jobs/results/?q=backend+engineer&location=India"},
    {"name": "Microsoft",   "url": "https://jobs.careers.microsoft.com/global/en/search?q=backend+engineer&l=India"},
    {"name": "Amazon",      "url": "https://www.amazon.jobs/en/search?base_query=backend+engineer&loc_query=India"},
    {"name": "Uber",        "url": "https://www.uber.com/global/en/careers/list/?query=backend+india"},
    {"name": "Flipkart",    "url": "https://www.flipkartcareers.com/#!/joblist"},
    {"name": "PhonePe",     "url": "https://careers.phonepe.com/?q=backend"},
    {"name": "Razorpay",    "url": "https://razorpay.com/jobs/#openings"},
    {"name": "CRED",        "url": "https://careers.cred.club/"},
    {"name": "Swiggy",      "url": "https://careers.swiggy.com/#careers"},
    {"name": "Confluent",   "url": "https://careers.confluent.io/?search=india"},
    {"name": "Databricks",  "url": "https://www.databricks.com/company/careers/open-positions?location=India"},
    {"name": "Zepto",       "url": "https://www.zepto.co.in/careers"},
]

CANDIDATE_PROFILE = """
Name: Siddharth Singh
Title: Backend Engineer | Distributed Systems
Experience: 3+ years at Thales (Fortune 500 defense-tech)
Core stack: Java, Apache Kafka, Apache Cassandra (LWT, bucketing, quorum),
            Apache Spark, Spring Boot, Kubernetes, Docker, Keycloak, OAuth2
Key wins: 90% race-condition elimination, 85% downtime prevention,
          40% latency reduction, Employee Recognition Award
Target: SDE-2 / Senior Backend Engineer roles paying 20+ LPA in India
"""

GEMINI_MODEL = "gemini-2.0-flash"   # free tier, fast, has Google Search grounding

# ── Fetch jobs via Gemini + Google Search grounding ───────────────────────────

def call_gemini(prompt: str, retries: int = 4) -> str:
    """Call Gemini REST API with exponential backoff on 429 rate-limit errors."""
    api_key = os.environ["GEMINI_API_KEY"]
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
        }
    }).encode("utf-8")

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)

        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 15 * (2 ** attempt)   # 15s, 30s, 60s, 120s
                print(f"Rate limited (429). Waiting {wait}s before retry {attempt+1}/{retries}...")
                time.sleep(wait)
            else:
                print(f"HTTP error {e.code}: {e.reason}")
                raise
        except (KeyError, IndexError) as e:
            print("Unexpected Gemini response structure")
            raise RuntimeError("Failed to parse Gemini response") from e

    raise RuntimeError("Gemini API still rate-limiting after all retries. Try again later.")


def fetch_jobs() -> list[dict]:
    """Fetch jobs in two batches to reduce prompt size and avoid rate limits."""
    all_jobs: list[dict] = []

    # Split companies into 2 batches of 6 — smaller prompts = less likely to hit limits
    batches = [COMPANIES[:6], COMPANIES[6:]]

    for batch_num, batch in enumerate(batches, 1):
        company_list = "\n".join(f"- {c['name']}: {c['url']}" for c in batch)

        prompt = f"""You are a job board aggregator helping a backend engineer in India find top roles.

Candidate profile:
{CANDIDATE_PROFILE}

Search the web to find currently open job listings at these companies for a Backend Engineer
with Java, Kafka, Cassandra, Spark, Spring Boot, Kubernetes skills. India roles, 20+ LPA.

Companies:
{company_list}

Return ONLY a valid JSON array — no markdown, no preamble, nothing else.
Each object: company, title, location, url, salary_range, match_reason
Max 2 listings per company. Prefer Kafka/Cassandra/Spark/distributed systems roles.

Example:
[{{"company":"Uber","title":"Senior Software Engineer - Backend","location":"Bangalore, India","url":"https://uber.com/careers/...","salary_range":"30-50 LPA","match_reason":"Distributed systems, Kafka event streaming focus"}}]
"""

        print(f"Batch {batch_num}/2: querying {len(batch)} companies...")
        try:
            raw = call_gemini(prompt)
        except RuntimeError as e:
            print(f"Batch {batch_num} failed: {e}")
            continue

        # Parse JSON
        raw = raw.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            print(f"Batch {batch_num}: no JSON array found. Raw: {raw[:300]}")
            continue

        try:
            jobs = json.loads(raw[start:end])
            all_jobs.extend(jobs)
            print(f"Batch {batch_num}: got {len(jobs)} listings")
        except json.JSONDecodeError as e:
            print(f"Batch {batch_num}: JSON parse error — {e}")

        # Small pause between batches to be polite to the API
        if batch_num < len(batches):
            time.sleep(5)

    print(f"Total: {len(all_jobs)} listings across {len({j.get('company') for j in all_jobs})} companies")
    return all_jobs


# ── Build HTML email ───────────────────────────────────────────────────────────

def build_email_html(jobs: list[dict], date_str: str) -> str:
    if not jobs:
        body_content = "<p style='color:#888;padding:20px 0;'>No listings found today. Will retry tomorrow.</p>"
    else:
        by_company: dict[str, list] = {}
        for j in jobs:
            by_company.setdefault(j.get("company", "Other"), []).append(j)

        cards = ""
        for company, listings in by_company.items():
            for j in listings:
                salary = j.get("salary_range", "")
                salary_badge = (
                    f'<span style="background:#EAF3DE;color:#3B6D11;font-size:11px;'
                    f'padding:2px 8px;border-radius:4px;font-weight:600;">{salary}</span>'
                ) if salary else ""

                cards += f"""
                <div style="background:#fff;border:1px solid #e8e8e4;border-radius:8px;
                            padding:14px 18px;margin-bottom:10px;">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;
                              gap:8px;flex-wrap:wrap;margin-bottom:6px;">
                    <div style="font-size:15px;font-weight:600;color:#1a1a1a;">{j.get('title','Role')}</div>
                    <span style="background:#E6F1FB;color:#185FA5;font-size:11px;
                                 padding:2px 8px;border-radius:4px;font-weight:600;">{company}</span>
                  </div>
                  <div style="font-size:12px;color:#666;margin-bottom:6px;">
                    📍 {j.get('location','India')} &nbsp;·&nbsp; {salary_badge}
                  </div>
                  <div style="font-size:12px;color:#555;margin-bottom:8px;font-style:italic;">
                    {j.get('match_reason','')}
                  </div>
                  <a href="{j.get('url','#')}"
                     style="font-size:12px;color:#185FA5;text-decoration:none;font-weight:500;">
                    View on portal →
                  </a>
                </div>"""
        body_content = cards

    total = len(jobs)
    companies_hit = len({j.get("company") for j in jobs})

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f4f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:600px;margin:32px auto;background:#f5f4f0;padding:0 16px 32px;">
    <div style="background:#1a1a1a;border-radius:10px;padding:24px 28px;margin-bottom:16px;">
      <div style="font-size:11px;color:#888;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;">Daily Job Digest</div>
      <div style="font-size:22px;font-weight:600;color:#fff;margin-bottom:4px;">🔔 Backend Engineer Roles</div>
      <div style="font-size:13px;color:#aaa;">{date_str} · {total} listings · {companies_hit} companies</div>
    </div>
    <div style="background:#fff;border:1px solid #e8e8e4;border-radius:8px;padding:12px 18px;margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <div style="width:36px;height:36px;border-radius:50%;background:#E6F1FB;display:flex;align-items:center;
                    justify-content:center;font-weight:600;font-size:13px;color:#185FA5;flex-shrink:0;">SS</div>
        <div>
          <div style="font-size:13px;font-weight:600;color:#1a1a1a;">Siddharth Singh</div>
          <div style="font-size:11px;color:#888;">Java · Kafka · Cassandra · Spark · SDE-2 · 20+ LPA</div>
        </div>
      </div>
    </div>
    {body_content}
    <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e8e8e4;font-size:11px;color:#aaa;text-align:center;">
      Automated · GitHub Actions · Powered by Google Gemini (free)
    </div>
  </div>
</body>
</html>"""


# ── Send via Gmail SMTP ────────────────────────────────────────────────────────

def send_email(html_body: str, date_str: str):
    sender   = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 Daily Job Digest — Backend Engineer Roles ({date_str})"
    msg["From"]    = f"Job Alert <{sender}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())

    print(f"Email sent → {recipient}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    date_str = datetime.date.today().strftime("%d %B %Y")
    print(f"=== Job Alert — {date_str} ===")
    jobs = fetch_jobs()
    html = build_email_html(jobs, date_str)
    send_email(html, date_str)
    print("Done ✓")

if __name__ == "__main__":
    main()
