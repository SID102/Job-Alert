# Daily Job Alert — Siddharth Singh

Automated daily digest of top Backend Engineer / SDE-2 roles across 12 companies,
fetched via **Google Gemini (free)** + Google Search, delivered to Gmail at 7 AM IST.

**Zero cost. No credit card. Uses only free APIs.**

---

## Setup (5 minutes)

### Step 1 — Get your FREE Gemini API key

1. Go to **https://aistudio.google.com**
2. Sign in with your Google account
3. Click **"Get API key"** → **"Create API key"**
4. Copy the key (starts with `AIza...`)

That's it — free tier gives 1,500 requests/day. More than enough.

---

### Step 2 — Get a Gmail App Password

> Google blocks plain password login for scripts. App Password is the fix.

1. Go to **https://myaccount.google.com/security**
2. Make sure **2-Step Verification** is ON
3. Search for **"App passwords"** at the top
4. Create one → App: Mail → Device: Other → name it "Job Alert"
5. Copy the **16-character password** (ignore spaces)

---

### Step 3 — Push to GitHub

```bash
# unzip the downloaded file first, then:
cd job-alert
git init
git add .
git commit -m "init job alert"
gh repo create job-alert --private --push
# (or create repo manually on github.com and push)
```

---

### Step 4 — Add 4 secrets to GitHub

Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret name          | Value                                   |
|----------------------|-----------------------------------------|
| `GEMINI_API_KEY`     | The `AIza...` key from Step 1           |
| `GMAIL_ADDRESS`      | `siddharthsingh002018@gmail.com`        |
| `GMAIL_APP_PASSWORD` | The 16-char password from Step 2        |
| `RECIPIENT_EMAIL`    | `siddharthsingh002018@gmail.com`        |

---

### Step 5 — Test it now

Repo → **Actions tab** → **"Daily Job Alert"** → **"Run workflow"** → **"Run workflow"**

Watch the logs. If it goes green, check your inbox. Done.

After that it fires automatically every day at **7:00 AM IST** — no maintenance needed.

---

## Customise

**Add a company** — edit `COMPANIES` list in `job_alert.py`:
```python
{"name": "Coinbase", "url": "https://www.coinbase.com/careers/positions?department=Engineering"},
```

**Change schedule** — edit `.github/workflows/daily_job_alert.yml`:
```yaml
- cron: "30 1 * * *"   # 1:30 AM UTC = 7:00 AM IST
- cron: "0 2 * * *"    # 2:00 AM UTC = 7:30 AM IST
```
Use https://crontab.guru to build expressions.

---

## Files

```
job-alert/
├── job_alert.py                       # main script (pure stdlib + Gemini REST)
├── requirements.txt                   # empty — no pip installs needed
├── README.md
└── .github/
    └── workflows/
        └── daily_job_alert.yml        # GitHub Actions cron schedule
```
