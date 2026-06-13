# Daily Job Alert — Siddharth Singh

Automated daily digest of Backend Engineer / SDE-2 roles fetched from
**Adzuna Jobs API** (free), filtered for Java · Kafka · Cassandra · Spark
skills, delivered to Gmail every morning at 7 AM IST via GitHub Actions.

**Zero cost. No credit card. Pure Python stdlib — no pip installs.**

---

## Setup (5 minutes)

### Step 1 — Get a free Adzuna API key

1. Go to **https://developer.adzuna.com**
2. Click **"Register"** — sign up with email (free, no credit card)
3. Go to **Dashboard** → you'll see your **App ID** and **App Key**
4. Copy both values

Free tier: 250 requests/day. The script uses ~5 requests per run. More than enough.

---

### Step 2 — Get a Gmail App Password

1. Go to **https://myaccount.google.com/security**
2. Make sure **2-Step Verification** is ON
3. Search **"App passwords"** → create one → name it "Job Alert"
4. Copy the **16-character password**

---

### Step 3 — Push to GitHub

```bash
cd job-alert
git init
git add .
git commit -m "init job alert"
gh repo create job-alert --private --push
```

---

### Step 4 — Add 5 secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret               | Value                              |
|----------------------|------------------------------------|
| `ADZUNA_APP_ID`      | Your App ID from developer.adzuna.com |
| `ADZUNA_APP_KEY`     | Your App Key from developer.adzuna.com |
| `GMAIL_ADDRESS`      | `siddharthsingh002018@gmail.com`   |
| `GMAIL_APP_PASSWORD` | 16-char App Password               |
| `RECIPIENT_EMAIL`    | `siddharthsingh002018@gmail.com`   |

---

### Step 5 — Test it

Repo → **Actions** → **"Daily Job Alert"** → **"Run workflow"**

Runs in ~30 seconds. Check your inbox.

---

## Customise

**Add search terms** — edit `SEARCH_QUERIES` in `job_alert.py`

**Add target companies** — edit `TARGET_COMPANIES` list (blue-highlighted in email)

**Change salary floor** — edit `MIN_SALARY_INR = 2_000_000` (2M INR = 20 LPA)

**Change schedule** — edit `.github/workflows/daily_job_alert.yml` cron line
