"""
Daily Job Alert — Siddharth Singh
Sources:
  1. Remotive API       — free, no key, tech jobs globally (many India/remote)
  2. Himalayas API      — free, no key, great for senior tech roles
  3. The Muse API       — free, no key, good MNC coverage
  4. Arbeitnow RSS      — free, no key, fresh listings daily

All sources are public APIs — no scraping, no auth, works from GitHub Actions.

Required GitHub Actions secrets:
  GMAIL_ADDRESS       — your Gmail
  GMAIL_APP_PASSWORD  — 16-char App Password
  RECIPIENT_EMAIL     — delivery address
"""

import os
import json
import smtplib
import datetime
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Configuration ──────────────────────────────────────────────────────────────

CANDIDATE_PROFILE = {
    "name":  "Siddharth Singh",
    "stack": "Java · Kafka · Cassandra · Spark · Spring Boot · Kubernetes",
}

RELEVANT_KEYWORDS = [
    "java", "kafka", "cassandra", "spark", "backend", "distributed",
    "spring boot", "spring", "microservice", "kubernetes", "k8s",
    "streaming", "platform engineer", "software engineer", "sde", "swe",
    "data engineer", "scala", "flink", "data platform",
]

# Skip these — too junior or irrelevant
EXCLUDE_TITLE_KEYWORDS = [
    "intern", "trainee", "junior", "fresher", "frontend", "react",
    "angular", "vue", "ios", "android", "mobile", "designer", "qa ",
    "test engineer", "manual", "sales", "marketing", "hr ",
]

TARGET_COMPANIES = [
    "google", "microsoft", "amazon", "aws", "uber", "flipkart", "phonepe",
    "razorpay", "cred", "swiggy", "confluent", "databricks", "zepto",
    "meesho", "zomato", "atlassian", "adobe", "salesforce", "goldman sachs",
    "jp morgan", "morgan stanley", "paypal", "linkedin", "meta", "apple",
    "netflix", "airbnb", "stripe", "walmart", "visa", "mastercard",
    "barclays", "hsbc", "thoughtworks", "oracle", "sap", "bytedance",
    "groww", "slice", "smallcase", "browserstack", "postman", "freshworks",
    "zoho", "chargebee", "clevertap", "lenskart", "twilio", "cloudflare",
    "hashicorp", "datadog", "elastic", "mongodb", "redis", "cockroachdb",
]

MAX_AGE_DAYS = 7       # jobs older than this are skipped
MAX_JOBS_EMAIL = 25

# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch_url(url: str, timeout: int = 20) -> str | None:
    headers = {
        "User-Agent": "JobAlertBot/2.0 (personal job digest)",
        "Accept": "application/json, text/html, application/rss+xml",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  Fetch error [{url[:60]}]: {e}")
        return None


def parse_date(date_str: str) -> datetime.date | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            return datetime.datetime.strptime(date_str[:25], fmt[:len(date_str[:25])]).date()
        except Exception:
            pass
    try:
        return datetime.date.fromisoformat(date_str[:10])
    except Exception:
        return None


def days_ago(dt: datetime.date | None) -> int | None:
    if dt is None:
        return None
    return (datetime.date.today() - dt).days


def is_relevant(title: str, desc: str = "") -> bool:
    text = (title + " " + desc).lower()
    if any(k in text for k in EXCLUDE_TITLE_KEYWORDS):
        return False
    return any(k in text for k in RELEVANT_KEYWORDS)


def is_target(company: str) -> bool:
    return any(t in company.lower() for t in TARGET_COMPANIES)


def make_job(title, company, location, url, posted_date, source, desc="") -> dict:
    age = days_ago(posted_date)
    return {
        "title":     title.strip(),
        "company":   company.strip(),
        "location":  location.strip() if location else "Remote / India",
        "url":       url.strip(),
        "source":    source,
        "age":       age,
        "desc":      desc[:200].replace("\n", " ").strip(),
        "highlight": is_target(company),
    }

# ── Source 1: Remotive API ─────────────────────────────────────────────────────

def fetch_remotive() -> list[dict]:
    jobs = []
    for tag in ["software-dev", "backend", "devops-sysadmin", "data"]:
        url = f"https://remotive.com/api/remote-jobs?category={tag}&limit=50"
        raw = fetch_url(url)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            for r in data.get("jobs", []):
                title   = r.get("title", "")
                company = r.get("company_name", "")
                loc     = r.get("candidate_required_location", "Worldwide")
                link    = r.get("url", "#")
                pub     = parse_date(r.get("publication_date", ""))
                desc    = r.get("description", "")[:300]

                if not is_relevant(title, desc):
                    continue
                age = days_ago(pub)
                if age is not None and age > MAX_AGE_DAYS:
                    continue

                jobs.append(make_job(title, company, loc, link, pub, "Remotive", desc))
        except Exception as e:
            print(f"  Remotive parse error: {e}")

    print(f"  Remotive: {len(jobs)} relevant jobs")
    return jobs

# ── Source 2: Himalayas API ────────────────────────────────────────────────────

def fetch_himalayas() -> list[dict]:
    jobs = []
    queries = ["java backend", "kafka engineer", "distributed systems", "platform engineer java"]
    for q in queries:
        url = f"https://himalayas.app/jobs/api?q={urllib.parse.quote(q)}&limit=20"
        raw = fetch_url(url)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            for r in data.get("jobs", []):
                title   = r.get("title", "")
                company = r.get("companyName", "") or r.get("company", {}).get("name", "")
                loc     = r.get("location", "Remote")
                link    = r.get("applicationLink", "") or r.get("url", "#")
                pub     = parse_date(r.get("createdAt", "") or r.get("publishedAt", ""))
                desc    = r.get("description", "")[:300]

                if not is_relevant(title, desc):
                    continue
                age = days_ago(pub)
                if age is not None and age > MAX_AGE_DAYS:
                    continue

                jobs.append(make_job(title, company, loc, link, pub, "Himalayas", desc))
        except Exception as e:
            print(f"  Himalayas parse error ({q}): {e}")

    print(f"  Himalayas: {len(jobs)} relevant jobs")
    return jobs

# ── Source 3: Arbeitnow RSS (fresh, daily updated) ────────────────────────────

def fetch_arbeitnow() -> list[dict]:
    jobs = []
    url = "https://www.arbeitnow.com/api/job-board-api"
    raw = fetch_url(url)
    if not raw:
        return jobs
    try:
        data = json.loads(raw)
        for r in data.get("data", []):
            title   = r.get("title", "")
            company = r.get("company_name", "")
            loc     = r.get("location", "Remote")
            link    = r.get("url", "#")
            pub     = parse_date(r.get("created_at", ""))
            desc    = r.get("description", "")[:300]
            tags    = " ".join(r.get("tags", []))

            if not is_relevant(title, desc + " " + tags):
                continue
            age = days_ago(pub)
            if age is not None and age > MAX_AGE_DAYS:
                continue

            jobs.append(make_job(title, company, loc, link, pub, "Arbeitnow", desc))
    except Exception as e:
        print(f"  Arbeitnow parse error: {e}")

    print(f"  Arbeitnow: {len(jobs)} relevant jobs")
    return jobs

# ── Source 4: The Muse API (MNC heavy) ────────────────────────────────────────

def fetch_themuse() -> list[dict]:
    jobs = []
    for page in [1, 2]:
        url = (
            f"https://www.themuse.com/api/public/jobs"
            f"?category=Software+Engineer&category=Data+Science&level=Senior+Level"
            f"&level=Mid+Level&page={page}&api_key=public"
        )
        raw = fetch_url(url)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            for r in data.get("results", []):
                title   = r.get("name", "")
                company = r.get("company", {}).get("name", "")
                locs    = r.get("locations", [{}])
                loc     = locs[0].get("name", "Remote") if locs else "Remote"
                link    = r.get("refs", {}).get("landing_page", "#")
                pub     = parse_date(r.get("publication_date", ""))
                desc    = r.get("contents", "")[:300]

                if not is_relevant(title, desc):
                    continue
                age = days_ago(pub)
                if age is not None and age > MAX_AGE_DAYS:
                    continue

                jobs.append(make_job(title, company, loc, link, pub, "The Muse", desc))
        except Exception as e:
            print(f"  TheMuse parse error: {e}")

    print(f"  The Muse: {len(jobs)} relevant jobs")
    return jobs

# ── Aggregate & deduplicate ────────────────────────────────────────────────────

def fetch_jobs() -> list[dict]:
    print("Fetching from all sources...")
    all_jobs: list[dict] = []
    all_jobs += fetch_remotive()
    all_jobs += fetch_himalayas()
    all_jobs += fetch_arbeitnow()
    all_jobs += fetch_themuse()

    # Deduplicate by (company + title)
    seen: set[str] = set()
    deduped = []
    for j in all_jobs:
        key = f"{j['company'].lower()}|{j['title'].lower()[:50]}"
        if key not in seen:
            seen.add(key)
            deduped.append(j)

    # Sort: MNCs first, then by recency
    deduped.sort(key=lambda j: (
        not j["highlight"],
        j["age"] if j["age"] is not None else 999
    ))

    result = deduped[:MAX_JOBS_EMAIL]
    print(f"Total: {len(result)} jobs after dedup (from {len(all_jobs)} raw)")
    return result

# ── HTML email ─────────────────────────────────────────────────────────────────

def age_badge(age) -> str:
    if age is None:
        label, bg, col = "recently", "#f0f0ec", "#666"
    elif age == 0:
        label, bg, col = "today",     "#EAF3DE", "#3B6D11"
    elif age == 1:
        label, bg, col = "yesterday", "#E6F1FB", "#185FA5"
    elif age <= 3:
        label, bg, col = f"{age}d ago","#FFF8E6", "#9A6B00"
    else:
        label, bg, col = f"{age}d ago","#f0f0ec", "#666"

    return (
        f'<span style="background:{bg};color:{col};font-size:11px;'
        f'padding:1px 7px;border-radius:4px;font-weight:600;">🕐 {label}</span>'
    )


def source_badge(source: str) -> str:
    colors = {
        "Remotive":  ("#f5f0ff", "#6B21A8"),
        "Himalayas": ("#FFF0F0", "#9A1818"),
        "Arbeitnow": ("#F0FFF4", "#166534"),
        "The Muse":  ("#FFF8E6", "#9A6B00"),
    }
    bg, col = colors.get(source, ("#f0f0ec", "#555"))
    return (
        f'<span style="background:{bg};color:{col};font-size:10px;'
        f'padding:1px 6px;border-radius:4px;font-weight:500;">{source}</span>'
    )


def job_card_html(j: dict) -> str:
    border = "border-left:3px solid #185FA5;" if j["highlight"] else ""
    co_bg  = "#E6F1FB" if j["highlight"] else "#f0f0ec"
    co_col = "#185FA5" if j["highlight"] else "#555"
    desc_html = f'<div style="font-size:12px;color:#777;margin-bottom:8px;line-height:1.5;">{j["desc"]}{"…" if j["desc"] else ""}</div>' if j["desc"] else ""

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
    {age_badge(j['age'])}
    {source_badge(j['source'])}
  </div>
  {desc_html}
  <a href="{j['url']}" style="font-size:12px;color:#185FA5;text-decoration:none;font-weight:500;">
    View &amp; Apply →
  </a>
</div>"""


def build_email_html(jobs: list[dict], date_str: str) -> str:
    total      = len(jobs)
    highlights = sum(1 for j in jobs if j["highlight"])
    today_count = sum(1 for j in jobs if j["age"] == 0)
    body = "".join(job_card_html(j) for j in jobs) if jobs else (
        "<p style='color:#888;padding:20px 0;'>No matching fresh listings found today. Will retry tomorrow.</p>"
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f4f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:620px;margin:32px auto;padding:0 16px 40px;">

    <div style="background:#1a1a1a;border-radius:10px;padding:24px 28px;margin-bottom:14px;">
      <div style="font-size:11px;color:#888;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;">Daily Job Digest</div>
      <div style="font-size:22px;font-weight:700;color:#fff;margin-bottom:4px;">🔔 Backend Engineer Roles</div>
      <div style="font-size:13px;color:#aaa;">
        {date_str} &nbsp;·&nbsp; {total} listings &nbsp;·&nbsp; {today_count} posted today &nbsp;·&nbsp; {highlights} MNC
      </div>
    </div>

    <div style="background:#fff;border:1px solid #e8e8e4;border-radius:8px;padding:12px 18px;margin-bottom:14px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <div style="width:38px;height:38px;border-radius:50%;background:#E6F1FB;display:flex;align-items:center;
                    justify-content:center;font-weight:700;font-size:13px;color:#185FA5;flex-shrink:0;">SS</div>
        <div>
          <div style="font-size:13px;font-weight:600;color:#1a1a1a;">Siddharth Singh</div>
          <div style="font-size:11px;color:#888;">{CANDIDATE_PROFILE['stack']}</div>
        </div>
      </div>
    </div>

    <div style="font-size:11px;color:#888;margin-bottom:12px;">
      🔵 Blue border = MNC &nbsp;·&nbsp; 🟢 Green = today &nbsp;·&nbsp; 🔵 Blue = yesterday &nbsp;·&nbsp; 🟡 Yellow = 2–7d
    </div>

    {body}

    <div style="margin-top:20px;padding-top:14px;border-top:1px solid #e8e8e4;font-size:11px;color:#aaa;text-align:center;">
      Sources: Remotive · Himalayas · Arbeitnow · The Muse &nbsp;·&nbsp; MNCs first · ≤7 days old · 7 AM IST daily
    </div>
  </div>
</body>
</html>"""


# ── Gmail send ─────────────────────────────────────────────────────────────────

def send_email(html_body: str, date_str: str):
    sender    = os.environ["GMAIL_ADDRESS"]
    password  = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 Job Digest — Backend Roles · {date_str}"
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
