"""
main.py — Orchestrates the daily PIB news digest:
  1. Scrape today's press releases from pib.gov.in
  2. Summarize each one locally (no API calls)
  3. Build an HTML digest email
  4. Send it via SMTP

Run manually with:  python main.py
Run without sending (just print to console):  python main.py --dry-run
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timezone, timedelta
from html import escape

from scraper import fetch_todays_releases
from summarizer import summarize
from emailer import send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Load .env file if it exists (written from PIB_ENV secret by the workflow).
if os.path.exists(".env"):
    with open(".env", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()


IST = timezone(timedelta(hours=5, minutes=30))
SUMMARY_SENTENCES_STR = os.environ.get("SUMMARY_SENTENCES", "").strip()
SUMMARY_SENTENCES = int(SUMMARY_SENTENCES_STR) if SUMMARY_SENTENCES_STR else 3

MAX_ITEMS_STR = os.environ.get("MAX_ITEMS", "").strip()
MAX_ITEMS = int(MAX_ITEMS_STR) if MAX_ITEMS_STR else 60




def build_html(releases, date_str):
    if not releases:
        items_html = "<p>No press releases were found for today.</p>"
    else:
        rows = []
        for r in releases:
            title = escape(r["title"])
            summary = escape(r["summary"])
            url = escape(r["url"])
            rows.append(f"""
            <tr>
              <td style="padding:16px 0;border-bottom:1px solid #e5e5e5;">
                <div style="font-size:16px;font-weight:600;color:#111;margin-bottom:6px;">
                  {title}
                </div>
                <div style="font-size:14px;color:#333;line-height:1.5;margin-bottom:8px;">
                  {summary}
                </div>
                <a href="{url}" style="font-size:13px;color:#1a5fb4;text-decoration:none;">
                  Read full release &rarr;
                </a>
              </td>
            </tr>
            """)
        items_html = f'<table style="width:100%;border-collapse:collapse;">{"".join(rows)}</table>'

    return f"""
    <html>
    <body style="font-family:Arial,Helvetica,sans-serif;max-width:640px;margin:0 auto;padding:20px;color:#111;">
      <h2 style="margin-bottom:4px;">PIB News Digest — {date_str}</h2>
      <p style="color:#666;font-size:13px;margin-top:0;">
        {len(releases)} press release(s) from pib.gov.in, summarized automatically.
      </p>
      {items_html}
      <p style="color:#999;font-size:11px;margin-top:24px;">
        Source: Press Information Bureau, Government of India (pib.gov.in).
        Summaries are auto-generated and may miss nuance — click through for the full text.
      </p>
    </body>
    </html>
    """


def build_plain(releases, date_str):
    lines = [f"PIB News Digest — {date_str}", ""]
    for r in releases:
        lines.append(f"- {r['title']}")
        lines.append(f"  {r['summary']}")
        lines.append(f"  {r['url']}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print digest instead of emailing it")
    parser.add_argument("--include-all-dates", action="store_true", help="Don't filter to just today's releases (useful for testing)")
    args = parser.parse_args()

    date_str = datetime.now(IST).strftime("%d %B %Y")
    logger.info("Fetching releases for %s ...", date_str)

    raw_releases = fetch_todays_releases(
        only_today=not args.include_all_dates,
        max_items=MAX_ITEMS,
    )

    if not raw_releases:
        logger.warning("No releases found. Exiting without sending an email.")
        # Still exit cleanly — an empty news day isn't a pipeline failure.
        sys.exit(0)

    releases = []
    for r in raw_releases:
        try:
            r["summary"] = summarize(r["body"], num_sentences=SUMMARY_SENTENCES)
        except Exception as e:
            logger.warning("Summarization failed for %s: %s", r["url"], e)
            r["summary"] = r["body"][:280] + "..."
        releases.append(r)

    html_body = build_html(releases, date_str)
    plain_body = build_plain(releases, date_str)

    if args.dry_run:
        sys.stdout.buffer.write(plain_body.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
        return

    subject = f"PIB News Digest — {date_str} ({len(releases)} releases)"
    send_email(subject, html_body, plain_body)
    logger.info("Done. Sent digest with %d releases.", len(releases))


if __name__ == "__main__":
    main()
