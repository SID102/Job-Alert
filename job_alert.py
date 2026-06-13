"""
Daily Job Alert — Siddharth Singh
Fetches backend/distributed-systems roles via Adzuna API (free, 250 req/day),
filters by target companies, sends a styled digest via Gmail SMTP.

Required GitHub Actions secrets:
  ADZUNA_APP_ID       — from developer.adzuna.com (free registration)
  ADZUNA_APP_KEY      — from developer.adzuna.com (free registration)
  GMAIL_ADDRESS       — your Gmail address
  GMAIL_APP_PASSWORD  — 16-char Gmail App Password
  RECIPIENT_EMAIL     — where to deliver the digest
"""

import os
import json
import smtplib
import datetime
import urllib.request
import urllib.parse
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Configuration ──────────────────────────────────────────────────────────────

CANDIDATE_PROFILE = {
    "name": "Siddharth Singh",
    "title": "Backend Engineer | Distributed Systems",
    "stack": "Java · Kafka · Cassandra · Spark · Spring Boot · Kubernetes",
    "target": "SDE-2 / Senior Backend · 20+ LPA · India",
}

# Keywords to search — Adzuna will match these against job titles + descriptions
SEARCH_QUERIES = [
    "backend engineer java kafka",
    "distributed systems java kafka cassandra",
    "software engineer kafka cassandra spark",
    "senior backend engineer java spring boot",
    "platform engineer kafka kubernetes india",
]

# Target companies — jobs from these get a highlight badge in the email
TARGET_COMPANIES = [
    "google", "microsoft", "amazon", "uber", "flipkart", "phonepe",
    "razorpay", "cred", "swiggy", "confluent", "databricks", "zepto",
    "meesho", "zomato", "paytm", "atlassian", "adobe", "salesforce",
    "goldman sachs", "jp morgan", "morgan stanley",
]

ADZUNA_COUNTRY = "in"          # India
ADZUNA_RESULTS_PER_QUERY = 10  # fetch top 10 per query, deduplicate after
MIN_SALARY_INR = 2_000_000     # ~20 LPA (Adzuna uses annual INR)

# ── Fetch jobs from Adzuna API ─────────────────────────────────────────────────

def fetch_adzuna(query: str, app_id: str, app_key: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": ADZUNA_RESULTS_PER_QUERY,
        "what": query,
        "where": "India",
        "salary_min": MIN_SALARY_INR,
        "sort_by": "relevance",
        "content-type": "application/json",
    })

    url = (
        f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1?{params}"
    )

    req = urllib.request.Request(url, headers={"User-Agent": "JobAlertBot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("results", [])
    except urllib.error.HTTPError as e:
        print(f"  Adzuna HTTP {e.code} for query '{query}': {e.reason}")
        return []
    except Exception as e:
        print(f"  Adzuna error for query '{query}': {e}")
        return []


def is_target_company(company_name: str) -> bool:
    name_lower = company_name.lower()
    return any(t in name_lower for t in TARGET_COMPANIES)


def fetch_jobs() -> list[dict]:
    app_id  = os.environ["ADZUNA_APP_ID"]
    app_key = os.environ["ADZUNA_APP_KEY"]

    seen_ids: set[str] = set()
    all_jobs: list[dict] = []

    for query in SEARCH_QUERIES:
        print(f"  Searching: '{query}'...")
        results = fetch_adzuna(query, app_id, app_key)

        for r in results:
            job_id = r.get("id", "")
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            company  = r.get("company", {}).get("display_name", "Unknown")
            title    = r.get("title", "")
            location = r.get("location", {}).get("display_name", "India")
            url      = r.get("redirect_url", "#")
            salary_min = r.get("salary_min") or 0
            salary_max = r.get("salary_max") or 0
            description = r.get("description", "")[:200]

            # Compute salary label
            if salary_min and salary_max:
                lpa_min = round(salary_min / 100_000)
                lpa_max = round(salary_max / 100_000)
                salary_label = f"{lpa_min}–{lpa_max} LPA"
            elif salary_min:
                lpa_min = round(salary_min / 100_000)
                salary_label = f"{lpa_min}+ LPA"
            else:
                salary_label = "Competitive"

            all_jobs.append({
                "id":          job_id,
                "company":     company,
                "title":       title,
                "location":    location,
                "url":         url,
                "salary":      salary_label,
                "description": description,
                "highlight":   is_target_company(company),
            })

    # Sort: target companies first, then rest
    all_jobs.sort(key=lambda j: (not j["highlight"], j["company"].lower()))

    print(f"Total: {len(all_jobs)} unique listings")
    return all_jobs


# ── Build HTML email ───────────────────────────────────────────────────────────

def job_card_html(j: dict) -> str:
    highlight_style = (
        "border-left: 3px solid #185FA5;" if j["highlight"] else ""
    )
    company_badge_bg  = "#E6F1FB" if j["highlight"] else "#f0f0ec"
    company_badge_col = "#185FA5" if j["highlight"] else "#555"

    return f"""
<div style="background:#fff;border:1px solid #e8e8e4;border-radius:8px;
            padding:14px 18px;margin-bottom:10px;{highlight_style}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;
              gap:8px;flex-wrap:wrap;margin-bottom:5px;">
    <div style="font-size:15px;font-weight:600;color:#1a1a1a;">{j['title']}</div>
    <span style="background:{company_badge_bg};color:{company_badge_col};font-size:11px;
                 padding:2px 8px;border-radius:4px;font-weight:600;white-space:nowrap;">
      {j['company']}
    </span>
  </div>
  <div style="font-size:12px;color:#666;margin-bottom:5px;">
    📍 {j['location']} &nbsp;·&nbsp;
    <span style="background:#EAF3DE;color:#3B6D11;font-size:11px;
                 padding:2px 7px;border-radius:4px;font-weight:600;">{j['salary']}</span>
  </div>
  <div style="font-size:12px;color:#777;margin-bottom:8px;line-height:1.5;">
    {j['description']}{'…' if j['description'] else ''}
  </div>
  <a href="{j['url']}"
     style="font-size:12px;color:#185FA5;text-decoration:none;font-weight:500;">
    View job →
  </a>
</div>"""


def build_email_html(jobs: list[dict], date_str: str) -> str:
    total      = len(jobs)
    highlights = sum(1 for j in jobs if j["highlight"])
    companies  = len({j["company"] for j in jobs})

    if not jobs:
        body = "<p style='color:#888;padding:20px 0;'>No matching listings found today. Will retry tomorrow.</p>"
    else:
        body = "".join(job_card_html(j) for j in jobs)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f4f0;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:620px;margin:32px auto;padding:0 16px 40px;">

    <!-- Header -->
    <div style="background:#1a1a1a;border-radius:10px;padding:24px 28px;margin-bottom:14px;">
      <div style="font-size:11px;color:#888;letter-spacing:0.08em;
                  text-transform:uppercase;margin-bottom:4px;">Daily Job Digest</div>
      <div style="font-size:22px;font-weight:700;color:#fff;margin-bottom:4px;">
        🔔 Backend Engineer Roles
      </div>
      <div style="font-size:13px;color:#aaa;">
        {date_str} &nbsp;·&nbsp; {total} listings &nbsp;·&nbsp;
        {highlights} target companies &nbsp;·&nbsp; {companies} total companies
      </div>
    </div>

    <!-- Profile -->
    <div style="background:#fff;border:1px solid #e8e8e4;border-radius:8px;
                padding:12px 18px;margin-bottom:14px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <div style="width:38px;height:38px;border-radius:50%;background:#E6F1FB;
                    display:flex;align-items:center;justify-content:center;
                    font-weight:700;font-size:13px;color:#185FA5;flex-shrink:0;">SS</div>
        <div>
          <div style="font-size:13px;font-weight:600;color:#1a1a1a;">Siddharth Singh</div>
          <div style="font-size:11px;color:#888;">{CANDIDATE_PROFILE['stack']}</div>
        </div>
      </div>
    </div>

    <!-- Listings -->
    {body}

    <!-- Footer -->
    <div style="margin-top:20px;padding-top:14px;border-top:1px solid #e8e8e4;
                font-size:11px;color:#aaa;text-align:center;">
      Automated · GitHub Actions · Adzuna Jobs API · Runs daily at 7 AM IST
    </div>
  </div>
</body>
</html>"""


# ── Send via Gmail SMTP ────────────────────────────────────────────────────────

def send_email(html_body: str, date_str: str):
    sender    = os.environ["GMAIL_ADDRESS"]
    password  = os.environ["GMAIL_APP_PASSWORD"]
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
    print("Fetching jobs from Adzuna...")
    jobs = fetch_jobs()
    print("Building email...")
    html = build_email_html(jobs, date_str)
    print("Sending email...")
    send_email(html, date_str)
    print("Done ✓")

if __name__ == "__main__":
    main()
