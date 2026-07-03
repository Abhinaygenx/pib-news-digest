# PIB News Digest

Automatically scrapes today's press releases from [pib.gov.in](https://www.pib.gov.in),
summarizes each one locally (no paid API), and emails you a digest — once a day,
completely hands-off, via GitHub Actions.

## How it works

1. **`scraper.py`** fetches PIB's "All Releases" listing page and each release's
   detail page, extracting the title and body text.
   (PIB's official RSS feed blocks non-browser requests, so this scrapes the
   public listing page instead — it's the same info, just via HTML.)
2. **`summarizer.py`** does simple frequency-based extractive summarization —
   entirely local, no API key, no cost, no rate limits.
3. **`emailer.py`** sends the digest as an HTML email over SMTP.
4. **`main.py`** ties it all together.
5. **`.github/workflows/daily-digest.yml`** runs `main.py` automatically every
   day at 7:30 AM IST using GitHub Actions (free for public repos, and free for
   private repos up to a generous monthly minutes quota).

## Setup (10 minutes)

### 1. Create a repo
Create a new GitHub repository and push these files to it (or upload them
via the GitHub web UI).

### 2. Get an email account to send from
Easiest option: a Gmail account.
1. Turn on 2-Step Verification: https://myaccount.google.com/security
2. Create an **App Password**: https://myaccount.google.com/apppasswords
   (choose "Mail" as the app) — this gives you a 16-character password.
   You cannot use your normal Gmail password for SMTP; it will be rejected.

Any other SMTP provider (Outlook, Zoho, a work email, SendGrid, etc.) works too —
just adjust the host/port below.

### 3. Add GitHub Secrets
In your repo: **Settings → Secrets and variables → Actions → New repository secret**.

You can set up your configuration in one of two ways:

#### Option A: Single Combined Secret (Easiest)
Create a single repository secret named **`PIB_ENV`** and paste the entire block of configuration variables into the **Value** field:
```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=abhinaykumar5432@gmail.com
SMTP_PASS=your_16_char_app_password
EMAIL_FROM=abhinaykumar5432@gmail.com
```

#### Option B: Individual Secrets
Alternatively, you can add these secrets one-by-one:

| Secret name   | Example value              |
|---------------|-----------------------------|
| `SMTP_HOST`   | `smtp.gmail.com`            |
| `SMTP_PORT`   | `587`                       |
| `SMTP_USER`   | `youraddress@gmail.com`     |
| `SMTP_PASS`   | *(the 16-char App Password)*|
| `EMAIL_FROM`  | `youraddress@gmail.com`     |
| `EMAIL_TO`    | `abhinaykumar5432@gmail.com` (Optional; defaults to `abhinaykumar5432@gmail.com`) |

### 4. Test it
Go to the **Actions** tab in your repo → **Daily PIB News Digest** →
**Run workflow** (this is the `workflow_dispatch` trigger, so you don't have
to wait for the schedule). Check the logs, then check your inbox.

### 5. Let it run
That's it — it will now run automatically every day at 7:30 AM IST. To change
the time, edit the `cron` line in `.github/workflows/daily-digest.yml`
(cron times are in UTC; IST = UTC + 5:30).

## Running locally (for testing/tweaking)

```bash
pip install -r requirements.txt

# Print the digest to your terminal instead of emailing it:
python main.py --dry-run

# Test against all recent releases, not just today's (useful outside IST business hours):
python main.py --dry-run --include-all-dates

# Actually send an email (requires env vars set locally, e.g. via a .env
# file + `export $(cat .env | xargs)`, or just export them in your shell):
export SMTP_HOST=smtp.gmail.com SMTP_PORT=587 \
       SMTP_USER=you@gmail.com SMTP_PASS=xxxxxxxxxxxxxxxx \
       EMAIL_FROM=you@gmail.com EMAIL_TO=abhinaykumar5432@gmail.com
python main.py
```

## Known limitations & things worth improving

- **Summary quality**: the summarizer is a lightweight, free, local algorithm
  (word-frequency extractive scoring) — decent for structured government
  press releases, but not as fluent as an LLM. If you later want higher
  quality, swap `summarizer.py` to call the Claude API instead (a few lines
  of change) — this project deliberately avoided that to keep it free.
- **HTML structure changes**: government sites occasionally redesign. The
  scraper uses fairly resilient anchors (the `og:title` meta tag, the literal
  strings "Posted On" / "Release ID"), but if PIB changes its page template,
  the scraper may need small tweaks.
- **Region/language**: currently pulls English, National (Delhi) releases
  (`lang=1&reg=3`). You can fetch other regional PIB offices by changing
  those params in `scraper.py`.
- **Duplicates**: releases are filtered to today's date using each page's
  "Posted On" field, which should prevent most repeats across days, but
  there's no persistent dedupe store across runs. If you want that, you'd
  add a small file (or GitHub Gist / database) tracking sent PRIDs.
- **Rate limiting**: the scraper waits 1 second between requests to avoid
  hammering PIB's servers — please don't remove this.
