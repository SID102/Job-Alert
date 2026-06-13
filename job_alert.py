"""
Daily Job Alert — Siddharth Singh
Fetches backend/distributed-systems roles via Adzuna API (free tier),
sorted by date (most recent first), sends a styled digest via Gmail SMTP.

Required GitHub Actions secrets:
  ADZUNA_APP_ID       — from developer.adzuna.com
  ADZUNA_APP_KEY      — from developer.adzuna.com
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
    "name":  "Siddharth Singh",
    "stack": "Java · Kafka · Cassandra · Spark · Spring Boot · Kubernetes",
}

# Broad queries → more results. Adzuna free = 250 req/day, we use ~8
SEARCH_QUERIES = [
    "backend engineer",
    "software engineer java",
    "senior software engineer",
    "distributed systems engineer",
    "java developer kafka",
    "platform engineer java",
    "software engineer kafka cassandra",
    "senior backend developer",
]

# Keywords that must appear in title or description to be included
RELEVANT_KEYWORDS = [
    "java", "kafka", "cassandra", "spark", "backend", "distributed",
    "spring", "microservice", "kubernetes", "scala", "streaming",
    "platform engineer", "software engineer", "sde", "swe",
]

# These company names get a blue highlight badge in the email
TARGET_COMPANIES = [
    "google", "microsoft", "amazon", "aws", "uber", "flipkart", "phonepe",
    "razorpay", "cred", "swiggy", "confluent", "databricks", "zepto",
    "meesho", "zomato", "atlassian", "adobe", "salesforce", "goldman sachs",
    "jp morgan", "morgan stanley", "deutsche bank", "paypal", "linkedin",
    "meta", "apple", "netflix", "airbnb", "stripe", "coinbase", "walmart",
    "target", "visa", "mastercard", "barclays", "hsbc", "thoughtworks",
    "infosys", "tcs", "wipro", "accenture", "oracle", "sap", "ibm",
]

ADZUNA_COUNTRY   = "in"
RESULTS_PER_PAGE = 20          # max per Adzuna call
MIN_SALARY_INR   = 1_500_000   # 15 LPA floor (cast wider, filter later)
MAX_JOBS_IN_EMAIL = 20         # cap email length

# ── Fetch from Adzuna ─────────────────────────────────────────────────────────

def fetch_adzuna(query: str, app_id: str, app_key: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "app_id":          app_id,
        "app_key":         app_key,
        "results_per_page": RESULTS_PER_PAGE,
        "what":            query,
        "where":           "India",
        "salary_min":      MIN_SALARY_INR,
        "sort_by":         "date",          # ← most recent first
        "content-type":    "application/json",
    })
    url = f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "JobAlertBot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("results", [])
    except urllib.error.HTTPError as e:
        print(f"  Adzuna HTTP {e.code} for '{query}': {e.reason}")
        return []
    except Exception as e:
        print(f"  Adzuna error for '{query}': {e}")
        return []


def is_relevant(title: str, desc: str) -> bool:
    text = (title + " " + desc).lower()
    return any(kw in text for kw in RELEVANT_KEYWORDS)


def is_target_company(name: str) -> bool:
    return any(t in name.lower() for t in TARGET_COMPANIES)


def parse_salary(r: dict) -> str:
    sal_min = r.get("salary_min") or 0
    sal_max = r.get("salary_max") or 0
    if sal_min and sal_max:
        return f"{round(sal_min/100_000)}–{round(sal_max/100_000)} LPA"
    if sal_min:
        return f"{round(sal_min/100_000)}+ LPA"
    return "Competitive"


def fetch_jobs() -> list[dict]:
    app_id  = os.environ["ADZUNA_APP_ID"]
    app_key = os.environ["ADZUNA_APP_KEY"]

    seen: set[str] = set()
    all_jobs: list[dict] = []

    for query in SEARCH_QUERIES:
        print(f"  Searching: '{query}'...")
        results = fetch_adzuna(query, app_id, app_key)
        added = 0
        for r in results:
            job_id = r.get("id", "")
            if not job_id or job_id in seen:
                continue

            title   = r.get("title", "")
            desc    = (r.get("description") or "")
            company = r.get("company", {}).get("display_name", "Unknown")

            if not is_relevant(title, desc):
                continue

            seen.add(job_id)
            added += 1

            location_parts = r.get("location", {}).get("area", [])
            location = ", ".join(location_parts[-2:]) if location_parts else "India"

            created = r.get("created", "")[:10]   # YYYY-MM-DD
            redirect_url = r.get("redirect_url", "#")

            all_jobs.append({
                "id":        job_id,
                "company":   company,
                "title":     title,
                "location":  location,
                "url":       redirect_url,
                "salary":    parse_salary(r),
                "desc":      desc[:250].replace("\n", " ").strip(),
                "highlight": is_target_company(company),
                "posted":    created,
            })
        print(f"    → {added} relevant out of {len(results)} results")

    # Sort: target companies first, then by most recent posting date
    all_jobs.sort(key=lambda j: (not j["highlight"], j["posted"]), reverse=False)
    all_jobs.sort(key=lambda j: not j["highlight"])   # keep highlights at top

    # Deduplicate by (company + title) to avoid near-duplicates
    seen_titles: set[str] = set()
    deduped: list[dict] = []
    for j in all_jobs:
        key = f"{j['company'].lower()}|{j['title'].lower()[:40]}"
        if key not in seen_titles:
            seen_titles.add(key)
            deduped.append(j)

    result = deduped[:MAX_JOBS_IN_EMAIL]
    print(f"Total: {len(result)} jobs (from {len(all_jobs)} before dedup/cap)")
    return result


# ── Build HTML email ───────────────────────────────────────────────────────────

def job_card_html(j: dict) -> str:
    border  = "border-left:3px solid #185FA5;" if j["highlight"] else ""
    co_bg   = "#E6F1FB" if j["highlight"] else "#f0f0ec"
    co_col  = "#185FA5" if j["highlight"] else "#555"

    # Format posted date nicely
    posted_label = ""
    if j["posted"]:
        try:
            dt = datetime.date.fromisoformat(j["posted"])
            delta = (datetime.date.today() - dt).days
            if delta == 0:
                posted_label = "today"
            elif delta == 1:
                posted_label = "yesterday"
            else:
                posted_label = f"{delta}d ago"
        except Exception:
            posted_label = j["posted"]

    posted_html = (
        f'<span style="background:#FFF8E6;color:#9A6B00;font-size:11px;'
        f'padding:1px 7px;border-radius:4px;font-weight:600;">🕐 {posted_label}</span>'
        if posted_label else ""
    )

    return f"""
<div style="background:#fff;border:1px solid #e8e8e4;border-radius:8px;
            padding:14px 18px;margin-bottom:10px;{border}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;
              gap:8px;flex-wrap:wrap;margin-bottom:5px;">
    <div style="font-size:14px;font-weight:600;color:#1a1a1a;">{j['title']}</div>
    <span style="background:{co_bg};color:{co_col};font-size:11px;
                 padding:2px 8px;border-radius:4px;font-weight:600;white-space:nowrap;">
      {j['company']}
    </span>
  </div>
  <div style="font-size:12px;color:#666;margin-bottom:6px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
    <span>📍 {j['location']}</span>
    <span style="background:#EAF3DE;color:#3B6D11;padding:1px 7px;
                 border-radius:4px;font-weight:600;">{j['salary']}</span>
    {posted_html}
  </div>
  <div style="font-size:12px;color:#777;margin-bottom:8px;line-height:1.5;">
    {j['desc']}{'…' if j['desc'] else ''}
  </div>
  <a href="{j['url']}" style="font-size:12px;color:#185FA5;text-decoration:none;font-weight:500;">
    Apply →
  </a>
</div>"""


def build_email_html(jobs: list[dict], date_str: str) -> str:
    total      = len(jobs)
    highlights = sum(1 for j in jobs if j["highlight"])
    companies  = len({j["company"] for j in jobs})

    body = "".join(job_card_html(j) for j in jobs) if jobs else (
        "<p style='color:#888;padding:20px 0;'>No matching listings found today. Will retry tomorrow.</p>"
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f4f0;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:620px;margin:32px auto;padding:0 16px 40px;">

    <div style="background:#1a1a1a;border-radius:10px;padding:24px 28px;margin-bottom:14px;">
      <div style="font-size:11px;color:#888;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;">
        Daily Job Digest
      </div>
      <div style="font-size:22px;font-weight:700;color:#fff;margin-bottom:4px;">
        🔔 Backend Engineer Roles
      </div>
      <div style="font-size:13px;color:#aaa;">
        {date_str} &nbsp;·&nbsp; {total} listings &nbsp;·&nbsp;
        {highlights} MNC/target &nbsp;·&nbsp; {companies} companies
      </div>
    </div>

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

    <!-- Legend -->
    <div style="font-size:11px;color:#888;margin-bottom:10px;display:flex;gap:14px;flex-wrap:wrap;">
      <span>🔵 Blue border = MNC / target company</span>
      <span>🕐 Yellow badge = how recently posted</span>
    </div>

    {body}

    <div style="margin-top:20px;padding-top:14px;border-top:1px solid #e8e8e4;
                font-size:11px;color:#aaa;text-align:center;">
      Automated · GitHub Actions · Adzuna API · Sorted by most recent · 7 AM IST daily
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
