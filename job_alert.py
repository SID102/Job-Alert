"""
Daily Job Alert — Siddharth Singh
Fetches jobs DIRECTLY from top MNC career portals using their
public ATS APIs (Greenhouse, Lever, custom) — no scraping, no auth needed.

Companies covered:
  Greenhouse ATS : Uber, Confluent, Databricks, Atlassian, Razorpay,
                   Swiggy, Meesho, BrowserStack, Postman, Freshworks
  Lever ATS      : Razorpay (backup), CoinBase, Stripe
  Custom APIs    : Google, Microsoft, Amazon

Required GitHub Actions secrets (same as before):
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
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Configuration ──────────────────────────────────────────────────────────────

CANDIDATE_PROFILE = {
    "name":  "Siddharth Singh",
    "stack": "Java · Kafka · Cassandra · Spark · Spring Boot · Kubernetes",
}

MAX_AGE_DAYS   = 7
MAX_JOBS_EMAIL = 30

RELEVANT_KEYWORDS = [
    "backend", "software engineer", "sde", "swe", "platform",
    "distributed", "java", "kafka", "spark", "cassandra",
    "data engineer", "infrastructure", "microservice", "kubernetes",
    "streaming", "scala", "spring", "senior engineer", "staff engineer",
]

EXCLUDE_KEYWORDS = [
    "intern", "frontend", "react", "ios", "android", "mobile",
    "designer", "sales", "marketing", "recruiter", "hr", "legal",
    "finance", "accounting", "junior", "manual qa", "test engineer",
]

# ── Company Configs ────────────────────────────────────────────────────────────

# Greenhouse public API: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
GREENHOUSE_COMPANIES = [
    {"name": "Uber",          "slug": "uber",              "color": "#000000"},
    {"name": "Confluent",     "slug": "confluent",         "color": "#E31837"},
    {"name": "Databricks",    "slug": "databricks",        "color": "#FF3621"},
    {"name": "Atlassian",     "slug": "atlassian",         "color": "#0052CC"},
    {"name": "Swiggy",        "slug": "swiggy",            "color": "#FC8019"},
    {"name": "BrowserStack",  "slug": "browserstack",      "color": "#FF6C37"},
    {"name": "Postman",       "slug": "postman",           "color": "#FF6C37"},
    {"name": "Freshworks",    "slug": "freshworks",        "color": "#25C16F"},
    {"name": "Meesho",        "slug": "meesho",            "color": "#9B3DE8"},
    {"name": "Razorpay",      "slug": "razorpay",          "color": "#3395FF"},
    {"name": "CRED",          "slug": "dreamplug",         "color": "#1A1A1A"},
    {"name": "Groww",         "slug": "groww",             "color": "#00D09C"},
    {"name": "Zomato",        "slug": "zomato",            "color": "#E23744"},
    {"name": "PhonePe",       "slug": "phonepe",           "color": "#5F259F"},
    {"name": "Zepto",         "slug": "zepto",             "color": "#8B1A1A"},
    {"name": "Stripe",        "slug": "stripe",            "color": "#635BFF"},
    {"name": "Cloudflare",    "slug": "cloudflare",        "color": "#F48120"},
    {"name": "HashiCorp",     "slug": "hashicorp",         "color": "#7B42BC"},
    {"name": "Datadog",       "slug": "datadog",           "color": "#632CA6"},
    {"name": "Figma",         "slug": "figma",             "color": "#1ABCFE"},
]

# Lever public API: https://api.lever.co/v0/postings/{slug}?mode=json
LEVER_COMPANIES = [
    {"name": "Coinbase",      "slug": "coinbase",          "color": "#0052FF"},
    {"name": "Gojek",         "slug": "gojek",             "color": "#00AA13"},
    {"name": "Chargebee",     "slug": "chargebee",         "color": "#F5A623"},
    {"name": "CleverTap",     "slug": "clevertap",         "color": "#FF6B35"},
    {"name": "Smallcase",     "slug": "smallcase",         "color": "#19A68A"},
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch_url(url: str, timeout: int = 20) -> str | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 JobAlertBot/3.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"    Error [{url[:70]}]: {e}")
        return None


def parse_date(s: str) -> datetime.date | None:
    if not s:
        return None
    # Handle Unix timestamps (milliseconds)
    if isinstance(s, (int, float)) or (isinstance(s, str) and s.isdigit()):
        try:
            ts = int(s)
            if ts > 1e10:
                ts //= 1000
            return datetime.date.fromtimestamp(ts)
        except Exception:
            return None
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def days_ago(dt: datetime.date | None) -> int | None:
    if dt is None:
        return None
    return (datetime.date.today() - dt).days


def is_relevant(title: str, dept: str = "", location: str = "") -> bool:
    text = (title + " " + dept + " " + location).lower()
    if any(k in text for k in EXCLUDE_KEYWORDS):
        return False
    return any(k in text for k in RELEVANT_KEYWORDS)


def is_india_or_remote(location: str) -> bool:
    loc = location.lower()
    return any(k in loc for k in [
        "india", "bangalore", "bengaluru", "mumbai", "delhi",
        "hyderabad", "pune", "chennai", "noida", "gurgaon",
        "remote", "worldwide", "global", "anywhere",
    ])

# ── Greenhouse Fetcher ─────────────────────────────────────────────────────────

def fetch_greenhouse(company: dict) -> list[dict]:
    slug = company["slug"]
    name = company["name"]
    url  = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

    raw = fetch_url(url)
    if not raw:
        return []

    try:
        data = json.loads(raw)
        jobs_raw = data.get("jobs", [])
    except Exception as e:
        print(f"    {name}: parse error — {e}")
        return []

    results = []
    for r in jobs_raw:
        title    = r.get("title", "")
        dept     = r.get("departments", [{}])[0].get("name", "") if r.get("departments") else ""
        loc_list = r.get("offices", []) or r.get("location", {})
        if isinstance(loc_list, list):
            location = ", ".join(o.get("name", "") for o in loc_list if o.get("name"))
        elif isinstance(loc_list, dict):
            location = loc_list.get("name", "")
        else:
            location = ""

        if not location:
            location = "Remote"

        # Greenhouse jobs without location filter — keep India + Remote
        if not is_india_or_remote(location):
            continue

        if not is_relevant(title, dept, location):
            continue

        link     = r.get("absolute_url", "#")
        pub_raw  = r.get("updated_at", "") or r.get("created_at", "")
        pub_date = parse_date(pub_raw)
        age      = days_ago(pub_date)

        if age is not None and age > MAX_AGE_DAYS:
            continue

        results.append({
            "company":  name,
            "title":    title.strip(),
            "location": location.strip(),
            "dept":     dept,
            "url":      link,
            "age":      age,
            "source":   "Greenhouse",
            "color":    company["color"],
        })

    print(f"    {name}: {len(results)} matching jobs")
    return results

# ── Lever Fetcher ──────────────────────────────────────────────────────────────

def fetch_lever(company: dict) -> list[dict]:
    slug = company["slug"]
    name = company["name"]
    url  = f"https://api.lever.co/v0/postings/{slug}?mode=json"

    raw = fetch_url(url)
    if not raw:
        return []

    try:
        jobs_raw = json.loads(raw)
        if not isinstance(jobs_raw, list):
            jobs_raw = jobs_raw.get("data", [])
    except Exception as e:
        print(f"    {name}: parse error — {e}")
        return []

    results = []
    for r in jobs_raw:
        title    = r.get("text", "")
        dept     = r.get("categories", {}).get("team", "")
        location = r.get("categories", {}).get("location", "") or r.get("workplaceType", "Remote")
        link     = r.get("hostedUrl", r.get("applyUrl", "#"))
        pub_ts   = r.get("createdAt", 0)
        pub_date = parse_date(str(pub_ts)) if pub_ts else None
        age      = days_ago(pub_date)

        if not is_india_or_remote(location):
            continue
        if not is_relevant(title, dept, location):
            continue
        if age is not None and age > MAX_AGE_DAYS:
            continue

        results.append({
            "company":  name,
            "title":    title.strip(),
            "location": location.strip(),
            "dept":     dept,
            "url":      link,
            "age":      age,
            "source":   "Lever",
            "color":    company["color"],
        })

    print(f"    {name}: {len(results)} matching jobs")
    return results

# ── Google Careers API ─────────────────────────────────────────────────────────

def fetch_google() -> list[dict]:
    results = []
    queries = [
        "backend engineer india",
        "software engineer kafka india",
        "platform engineer india",
        "distributed systems india",
    ]
    for q in queries:
        params = urllib.parse.urlencode({
            "q": q,
            "hl": "en",
            "jlo": "en_IN",
            "location": "India",
        })
        url = f"https://careers.google.com/api/jobs/jobs-v1/search/?{params}"
        raw = fetch_url(url)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            for r in data.get("jobs", []):
                title    = r.get("title", "")
                location = ", ".join(r.get("locations", ["India"]))
                link     = "https://careers.google.com/jobs/results/" + str(r.get("id", ""))
                pub_raw  = r.get("publish_date", "") or r.get("modified_date", "")
                pub_date = parse_date(pub_raw)
                age      = days_ago(pub_date)

                if not is_india_or_remote(location):
                    continue
                if not is_relevant(title, "", location):
                    continue
                if age is not None and age > MAX_AGE_DAYS:
                    continue

                results.append({
                    "company":  "Google",
                    "title":    title.strip(),
                    "location": location.strip(),
                    "dept":     "",
                    "url":      link,
                    "age":      age,
                    "source":   "Google Careers",
                    "color":    "#4285F4",
                })
        except Exception as e:
            print(f"    Google query '{q}': {e}")
        time.sleep(1)

    # Deduplicate Google jobs by title+location
    seen = set()
    deduped = []
    for j in results:
        k = j["title"].lower()[:40]
        if k not in seen:
            seen.add(k)
            deduped.append(j)

    print(f"    Google: {len(deduped)} matching jobs")
    return deduped

# ── Microsoft Careers API ──────────────────────────────────────────────────────

def fetch_microsoft() -> list[dict]:
    results = []
    searches = [
        "backend engineer",
        "software engineer java",
        "platform engineer",
        "distributed systems",
    ]
    for q in searches:
        params = urllib.parse.urlencode({
            "q": q,
            "l": "India",
            "pg": 1,
            "pgSz": 20,
            "o": "Recent",
            "flt": True,
        })
        url = f"https://gcsservices.careers.microsoft.com/search/api/v1/search?{params}"
        raw = fetch_url(url)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            jobs_raw = data.get("operationResult", {}).get("result", {}).get("jobs", [])
            for r in jobs_raw:
                title    = r.get("title", "")
                location = r.get("primaryLocation", "India")
                link     = f"https://jobs.careers.microsoft.com/global/en/job/{r.get('jobId', '')}"
                pub_raw  = r.get("postingDate", "")
                pub_date = parse_date(pub_raw)
                age      = days_ago(pub_date)

                if not is_india_or_remote(location):
                    continue
                if not is_relevant(title, "", ""):
                    continue
                if age is not None and age > MAX_AGE_DAYS:
                    continue

                results.append({
                    "company":  "Microsoft",
                    "title":    title.strip(),
                    "location": location.strip(),
                    "dept":     "",
                    "url":      link,
                    "age":      age,
                    "source":   "Microsoft Careers",
                    "color":    "#00A4EF",
                })
        except Exception as e:
            print(f"    Microsoft query '{q}': {e}")
        time.sleep(1)

    seen = set()
    deduped = []
    for j in results:
        k = j["title"].lower()[:40]
        if k not in seen:
            seen.add(k)
            deduped.append(j)

    print(f"    Microsoft: {len(deduped)} matching jobs")
    return deduped

# ── Aggregate all sources ──────────────────────────────────────────────────────

def fetch_jobs() -> list[dict]:
    all_jobs: list[dict] = []

    print("→ Greenhouse companies...")
    for company in GREENHOUSE_COMPANIES:
        all_jobs += fetch_greenhouse(company)
        time.sleep(0.5)

    print("→ Lever companies...")
    for company in LEVER_COMPANIES:
        all_jobs += fetch_lever(company)
        time.sleep(0.5)

    print("→ Google Careers...")
    all_jobs += fetch_google()

    print("→ Microsoft Careers...")
    all_jobs += fetch_microsoft()

    # Global dedup by company+title
    seen: set[str] = set()
    deduped = []
    for j in all_jobs:
        key = f"{j['company'].lower()}|{j['title'].lower()[:50]}"
        if key not in seen:
            seen.add(key)
            deduped.append(j)

    # Sort: by recency (most recent first)
    deduped.sort(key=lambda j: j["age"] if j["age"] is not None else 999)

    result = deduped[:MAX_JOBS_EMAIL]
    print(f"\nTotal: {len(result)} jobs (from {len(all_jobs)} raw, {len(deduped)} after dedup)")
    return result

# ── HTML Email ─────────────────────────────────────────────────────────────────

def age_badge(age) -> str:
    if age is None:   label, bg, col = "recently",  "#f0f0ec", "#666"
    elif age == 0:    label, bg, col = "today",     "#EAF3DE", "#3B6D11"
    elif age == 1:    label, bg, col = "yesterday", "#E6F1FB", "#185FA5"
    elif age <= 3:    label, bg, col = f"{age}d ago","#FFF8E6","#9A6B00"
    else:             label, bg, col = f"{age}d ago","#f5f0ec","#888"
    return (f'<span style="background:{bg};color:{col};font-size:11px;'
            f'padding:1px 7px;border-radius:4px;font-weight:600;">🕐 {label}</span>')


def job_card_html(j: dict) -> str:
    color = j.get("color", "#185FA5")
    dept_html = (
        f'<span style="font-size:11px;color:#888;">· {j["dept"]}</span>'
        if j.get("dept") else ""
    )
    return f"""
<div style="background:#fff;border:1px solid #e8e8e4;border-radius:8px;
            padding:14px 18px;margin-bottom:10px;border-left:3px solid {color};">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;
              gap:8px;flex-wrap:wrap;margin-bottom:5px;">
    <div style="font-size:14px;font-weight:600;color:#1a1a1a;">{j['title']}</div>
    <span style="background:#f5f5f5;color:#333;font-size:11px;
                 padding:2px 8px;border-radius:4px;font-weight:700;
                 border-left:3px solid {color};white-space:nowrap;">
      {j['company']}
    </span>
  </div>
  <div style="font-size:12px;color:#666;margin-bottom:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
    <span>📍 {j['location']}</span>
    {age_badge(j['age'])}
    {dept_html}
  </div>
  <a href="{j['url']}" style="font-size:12px;color:{color};text-decoration:none;font-weight:600;">
    Apply on {j['company']} →
  </a>
</div>"""


def build_email_html(jobs: list[dict], date_str: str) -> str:
    total       = len(jobs)
    today_count = sum(1 for j in jobs if j["age"] == 0)
    companies   = len({j["company"] for j in jobs})
    body = "".join(job_card_html(j) for j in jobs) if jobs else (
        "<p style='color:#888;padding:20px 0;'>No fresh listings today. Will retry tomorrow.</p>"
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f4f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:620px;margin:32px auto;padding:0 16px 40px;">

    <div style="background:#1a1a1a;border-radius:10px;padding:24px 28px;margin-bottom:14px;">
      <div style="font-size:11px;color:#888;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;">Direct from MNC Portals</div>
      <div style="font-size:22px;font-weight:700;color:#fff;margin-bottom:4px;">🔔 Backend Engineer Roles</div>
      <div style="font-size:13px;color:#aaa;">
        {date_str} &nbsp;·&nbsp; {total} listings &nbsp;·&nbsp; {today_count} posted today &nbsp;·&nbsp; {companies} companies
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
      Each card links directly to the company's own careers portal · Sorted by most recent
    </div>

    {body}

    <div style="margin-top:20px;padding-top:14px;border-top:1px solid #e8e8e4;font-size:11px;color:#aaa;text-align:center;">
      Sources: Greenhouse ATS · Lever ATS · Google Careers · Microsoft Careers<br>
      Uber · Confluent · Databricks · Atlassian · Razorpay · Swiggy · Coinbase · Google · Microsoft + more
    </div>
  </div>
</body>
</html>"""


def send_email(html_body: str, date_str: str):
    sender    = os.environ["GMAIL_ADDRESS"]
    password  = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 MNC Job Digest — Backend Roles · {date_str}"
    msg["From"]    = f"Job Alert <{sender}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
    print(f"Email sent → {recipient}")


def main():
    date_str = datetime.date.today().strftime("%d %B %Y")
    print(f"=== Job Alert — {date_str} ===")
    jobs = fetch_jobs()
    html = build_email_html(jobs, date_str)
    send_email(html, date_str)
    print("Done ✓")

if __name__ == "__main__":
    main()
