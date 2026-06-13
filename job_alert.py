"""
Daily Job Alert — Siddharth Singh
Scrapes fresh job listings directly from LinkedIn Jobs public search
(no login required), filters for relevance and recency (≤3 days),
sends a styled digest via Gmail SMTP.

Required GitHub Actions secrets:
  GMAIL_ADDRESS       — your Gmail address
  GMAIL_APP_PASSWORD  — 16-char Gmail App Password
  RECIPIENT_EMAIL     — where to deliver the digest

NO external API keys needed.
"""

import os
import json
import smtplib
import datetime
import urllib.request
import urllib.parse
import urllib.error
import time
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html.parser import HTMLParser

# ── Configuration ──────────────────────────────────────────────────────────────

CANDIDATE_PROFILE = {
    "name":  "Siddharth Singh",
    "stack": "Java · Kafka · Cassandra · Spark · Spring Boot · Kubernetes",
}

# LinkedIn job search queries — each maps to one search URL
# f=TPR_1&f_TPR=r259200  → posted in last 3 days (259200 seconds)
# f_E=4  → Associate + Mid-Senior level
# f_JT=F → Full-time only

LINKEDIN_SEARCHES = [
    {
        "label": "Backend Engineer India",
        "url": (
            "https://www.linkedin.com/jobs/search/?keywords=backend+engineer+java+kafka"
            "&location=India&f_TPR=r259200&f_JT=F&f_E=4&sortBy=DD"
        ),
    },
    {
        "label": "Distributed Systems India",
        "url": (
            "https://www.linkedin.com/jobs/search/?keywords=distributed+systems+engineer+java"
            "&location=India&f_TPR=r259200&f_JT=F&f_E=4&sortBy=DD"
        ),
    },
    {
        "label": "Senior SWE Kafka India",
        "url": (
            "https://www.linkedin.com/jobs/search/?keywords=senior+software+engineer+kafka+java"
            "&location=India&f_TPR=r259200&f_JT=F&f_E=4&sortBy=DD"
        ),
    },
    {
        "label": "Platform Engineer Kafka India",
        "url": (
            "https://www.linkedin.com/jobs/search/?keywords=platform+engineer+kafka+kubernetes"
            "&location=India&f_TPR=r259200&f_JT=F&sortBy=DD"
        ),
    },
    {
        "label": "Java Spring Boot Senior India",
        "url": (
            "https://www.linkedin.com/jobs/search/?keywords=senior+java+developer+spring+boot"
            "&location=India&f_TPR=r259200&f_JT=F&f_E=4&sortBy=DD"
        ),
    },
]

TARGET_COMPANIES = [
    "google", "microsoft", "amazon", "aws", "uber", "flipkart", "phonepe",
    "razorpay", "cred", "swiggy", "confluent", "databricks", "zepto",
    "meesho", "zomato", "atlassian", "adobe", "salesforce", "goldman sachs",
    "jp morgan", "morgan stanley", "deutsche bank", "paypal", "linkedin",
    "meta", "apple", "netflix", "airbnb", "stripe", "walmart", "visa",
    "mastercard", "barclays", "hsbc", "thoughtworks", "oracle", "sap",
    "bytedance", "groww", "slice", "navi", "smallcase", "browserstack",
    "postman", "freshworks", "zoho", "chargebee", "clevertap", "lenskart",
]

EXCLUDE_COMPANY_KEYWORDS = [
    "consultancy", "consulting", "recruiter", "staffing", "solutions pvt",
    "manpower", "hiring", "placement", "talent", "ventures pvt", "infotech",
    "technologies pvt", "softwares", "it services",
]

MAX_JOBS_IN_EMAIL = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── LinkedIn Scraper ───────────────────────────────────────────────────────────

class JobCardParser(HTMLParser):
    """Parse LinkedIn job search results page to extract job cards."""

    def __init__(self):
        super().__init__()
        self.jobs: list[dict] = []
        self._current: dict = {}
        self._capture_field: str | None = None
        self._depth = 0
        self._in_card = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "")

        # Detect job card containers
        if tag == "li" and "base-card" in classes:
            self._current = {}
            self._in_card = True

        if not self._in_card:
            return

        # Job title link
        if tag == "a" and "base-card__full-link" in classes:
            href = attrs_dict.get("href", "")
            if href:
                self._current["url"] = href.split("?")[0]

        if tag == "h3" and "base-search-card__title" in classes:
            self._capture_field = "title"

        if tag == "h4" and "base-search-card__subtitle" in classes:
            self._capture_field = "company"

        if tag == "span" and "job-search-card__location" in classes:
            self._capture_field = "location"

        if tag == "time":
            self._current["posted_raw"] = attrs_dict.get("datetime", "")
            self._capture_field = "posted_label"

    def handle_data(self, data):
        if self._capture_field:
            existing = self._current.get(self._capture_field, "")
            self._current[self._capture_field] = (existing + data).strip()

    def handle_endtag(self, tag):
        if tag in ("h3", "h4", "span", "time"):
            self._capture_field = None

        if tag == "li" and self._in_card and self._current.get("title"):
            self.jobs.append(dict(self._current))
            self._current = {}
            self._in_card = False


def scrape_linkedin(search_url: str, label: str) -> list[dict]:
    """Fetch and parse a LinkedIn jobs search page."""
    req = urllib.request.Request(search_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for '{label}'")
        return []
    except Exception as e:
        print(f"  Error for '{label}': {e}")
        return []

    parser = JobCardParser()
    parser.feed(html)

    if not parser.jobs:
        # Fallback: extract from embedded JSON (LinkedIn sometimes renders this way)
        jobs = extract_from_json_ld(html)
        print(f"  '{label}': {len(jobs)} jobs (via JSON fallback)")
        return jobs

    print(f"  '{label}': {len(parser.jobs)} jobs parsed")
    return parser.jobs


def extract_from_json_ld(html: str) -> list[dict]:
    """Try to extract jobs from JSON-LD embedded in the page."""
    jobs = []
    matches = re.findall(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL)
    for match in matches:
        try:
            data = json.loads(match)
            if isinstance(data, dict) and data.get("@type") == "JobPosting":
                jobs.append({
                    "title":       data.get("title", ""),
                    "company":     data.get("hiringOrganization", {}).get("name", ""),
                    "location":    data.get("jobLocation", {}).get("address", {}).get("addressLocality", "India"),
                    "url":         data.get("url", "#"),
                    "posted_raw":  data.get("datePosted", ""),
                    "posted_label": "",
                })
        except Exception:
            pass
    return jobs


# ── Filtering & Processing ─────────────────────────────────────────────────────

def is_consultancy(company: str) -> bool:
    c = company.lower()
    return any(kw in c for kw in EXCLUDE_COMPANY_KEYWORDS)


def is_target_company(company: str) -> bool:
    return any(t in company.lower() for t in TARGET_COMPANIES)


def days_ago(posted_raw: str) -> int | None:
    """Return how many days ago the job was posted, or None if unknown."""
    if not posted_raw:
        return None
    try:
        dt = datetime.date.fromisoformat(posted_raw[:10])
        return (datetime.date.today() - dt).days
    except Exception:
        return None


def days_label(d: int | None) -> str:
    if d is None:
        return "recently"
    if d == 0:
        return "today"
    if d == 1:
        return "yesterday"
    return f"{d}d ago"


def fetch_jobs() -> list[dict]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    all_jobs: list[dict] = []

    for search in LINKEDIN_SEARCHES:
        print(f"  Scraping: {search['label']}...")
        raw = scrape_linkedin(search["url"], search["label"])
        time.sleep(2)  # polite delay between requests

        for r in raw:
            title   = r.get("title", "").strip()
            company = r.get("company", "").strip()
            url     = r.get("url", "#")
            location = r.get("location", "India").strip()
            posted_raw = r.get("posted_raw", "")

            if not title or not company:
                continue

            # Dedup by URL or title+company
            dedup_key = url if url != "#" else f"{company.lower()}|{title.lower()[:40]}"
            if dedup_key in seen_urls:
                continue
            seen_urls.add(dedup_key)

            # Skip consultancies/staffing firms
            if is_consultancy(company):
                continue

            # Skip jobs older than 3 days
            age = days_ago(posted_raw)
            if age is not None and age > 3:
                continue

            all_jobs.append({
                "title":     title,
                "company":   company,
                "location":  location,
                "url":       url,
                "salary":    "Competitive",   # LinkedIn rarely shows salary publicly
                "age":       age,
                "age_label": days_label(age),
                "highlight": is_target_company(company),
            })

    # Sort: target companies first, then by recency
    all_jobs.sort(key=lambda j: (
        not j["highlight"],
        j["age"] if j["age"] is not None else 999
    ))

    result = all_jobs[:MAX_JOBS_IN_EMAIL]
    print(f"Total after filter: {len(result)} jobs")
    return result


# ── Build HTML email ───────────────────────────────────────────────────────────

def age_badge(label: str, age) -> str:
    if age == 0:
        bg, col = "#EAF3DE", "#3B6D11"   # green = today
    elif age == 1:
        bg, col = "#E6F1FB", "#185FA5"   # blue = yesterday
    else:
        bg, col = "#FFF8E6", "#9A6B00"   # yellow = 2-3 days

    return (
        f'<span style="background:{bg};color:{col};font-size:11px;'
        f'padding:1px 7px;border-radius:4px;font-weight:600;">🕐 {label}</span>'
    )


def job_card_html(j: dict) -> str:
    border = "border-left:3px solid #185FA5;" if j["highlight"] else ""
    co_bg  = "#E6F1FB" if j["highlight"] else "#f0f0ec"
    co_col = "#185FA5" if j["highlight"] else "#555"

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
  <div style="font-size:12px;color:#666;margin-bottom:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
    <span>📍 {j['location']}</span>
    {age_badge(j['age_label'], j['age'])}
  </div>
  <a href="{j['url']}" style="font-size:12px;color:#185FA5;text-decoration:none;font-weight:500;">
    View on LinkedIn →
  </a>
</div>"""


def build_email_html(jobs: list[dict], date_str: str) -> str:
    total      = len(jobs)
    highlights = sum(1 for j in jobs if j["highlight"])
    companies  = len({j["company"] for j in jobs})
    today_count = sum(1 for j in jobs if j["age"] == 0)

    body = "".join(job_card_html(j) for j in jobs) if jobs else (
        "<p style='color:#888;padding:20px 0;'>No fresh listings found today (≤3 days old). Will retry tomorrow.</p>"
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
        {date_str} &nbsp;·&nbsp; {total} fresh listings &nbsp;·&nbsp;
        {today_count} posted today &nbsp;·&nbsp; {highlights} MNC
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

    <div style="font-size:11px;color:#888;margin-bottom:12px;display:flex;gap:14px;flex-wrap:wrap;">
      <span>🔵 Blue border = MNC / target company</span>
      <span>🟢 Green badge = posted today &nbsp; 🔵 Blue = yesterday &nbsp; 🟡 Yellow = 2–3 days</span>
    </div>

    {body}

    <div style="margin-top:20px;padding-top:14px;border-top:1px solid #e8e8e4;
                font-size:11px;color:#aaa;text-align:center;">
      Source: LinkedIn Jobs · Only listings ≤3 days old · MNCs highlighted · 7 AM IST daily
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
    msg["Subject"] = f"🔔 Job Digest — Fresh Backend Roles (≤3 days) · {date_str}"
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
    print("Scraping LinkedIn Jobs (last 3 days only)...")
    jobs = fetch_jobs()
    print("Building email...")
    html = build_email_html(jobs, date_str)
    print("Sending email...")
    send_email(html, date_str)
    print("Done ✓")

if __name__ == "__main__":
    main()
