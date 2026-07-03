"""
scraper.py — Fetches today's press releases from pib.gov.in

PIB's site is an ASP.NET WebForms app. Its RSS feed blocks non-browser
requests (returns an empty <channel>), so instead we scrape the public
"All Releases" listing page, which lists the day's releases grouped by
ministry, and then fetch each release's detail page for the full text.

Two things make this reasonably robust without depending on exact CSS
classes (which PIB changes periodically):
  - Titles are pulled from the <meta property="og:title"> tag, which is
    stable across redesigns.
  - Article body text is extracted by finding the line containing
    "Posted On:" (start marker) and "(Release ID:" (end marker), since
    every PIB release follows this exact template.
"""

import re
import time
import logging
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE = "https://www.pib.gov.in"
LISTING_URL = f"{BASE}/allRel.aspx"
DETAIL_URL = f"{BASE}/PressReleasePage.aspx"

# A realistic browser User-Agent avoids some basic bot-blocking.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

IST = timezone(timedelta(hours=5, minutes=30))


def _today_ist_str():
    """Return today's date in IST as it appears in PIB's 'Posted On' line, e.g. '03 JUL 2026'."""
    return datetime.now(IST).strftime("%d %b %Y").upper()


def get_release_links(lang=1, reg=3, session=None, max_items=60):
    """
    Fetch the 'All Releases' listing page and return a de-duplicated list
    of {"prid": ..., "url": ...} dicts for every press release linked on it.

    lang=1 -> English, reg=3 -> National (PIB Delhi) region.
    """
    session = session or requests.Session()
    params = {"lang": lang, "reg": reg}
    resp = session.get(LISTING_URL, headers=HEADERS, params=params, timeout=25)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    seen = set()
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"PRID=(\d+)", href)
        if not m or "PressReleasePage" not in href:
            continue
        prid = m.group(1)
        if prid in seen:
            continue
        seen.add(prid)
        links.append({
            "prid": prid,
            "url": f"{DETAIL_URL}?PRID={prid}&lang={lang}&reg={reg}",
        })
        if len(links) >= max_items:
            break

    logger.info("Found %d release links on listing page", len(links))
    return links


def get_release_detail(url, session=None):
    """
    Fetch a single press release page and return
    {"title": str, "body": str, "posted_on": str|None, "url": url}
    or None if the page couldn't be parsed.
    """
    session = session or requests.Session()
    resp = session.get(url, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    # Title: prefer og:title meta tag (stable), fall back to <h2>.
    title = None
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    if not title:
        h2 = soup.find("h2")
        title = h2.get_text(strip=True) if h2 else None
    if not title:
        return None

    # Strip non-content elements before extracting text.
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()

    text = soup.get_text("\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    start_idx = None
    end_idx = None
    posted_on = None
    for i, line in enumerate(lines):
        if start_idx is None and ("Posted On" in line or "posted on" in line.lower()):
            start_idx = i
            # The date is often on this same line or the next one.
            m = re.search(r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})", line)
            if m:
                posted_on = m.group(1).upper()
            elif i + 1 < len(lines):
                m2 = re.search(r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})", lines[i + 1])
                if m2:
                    posted_on = m2.group(1).upper()
        is_signoff_marker = line.strip("*").strip() == "" and "*" in line
        if start_idx is not None and ("Release ID" in line or is_signoff_marker):
            end_idx = i
            break

    if start_idx is not None:
        body_lines = lines[start_idx + 1 : end_idx] if end_idx else lines[start_idx + 1 : start_idx + 60]
    else:
        # Fallback: just take the first chunk of text, skipping the nav/menu noise.
        body_lines = lines[:40]

    body = " ".join(body_lines).strip()
    return {"title": title, "body": body, "posted_on": posted_on, "url": url}


def fetch_todays_releases(lang=1, reg=3, delay=1.0, only_today=True, max_items=60):
    """
    Full pipeline: get today's listing, fetch each detail page, filter to
    today's date (IST) if only_today=True, and return a list of release dicts.
    """
    session = requests.Session()
    links = get_release_links(lang=lang, reg=reg, session=session, max_items=max_items)
    today_str = _today_ist_str()

    releases = []
    for link in links:
        try:
            detail = get_release_detail(link["url"], session=session)
        except requests.RequestException as e:
            logger.warning("Failed to fetch %s: %s", link["url"], e)
            continue
        if not detail or not detail["body"]:
            continue
        if only_today and detail["posted_on"] and detail["posted_on"] != today_str:
            continue
        releases.append(detail)
        time.sleep(delay)  # be polite to the server

    logger.info("Collected %d releases for %s", len(releases), today_str)
    return releases


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for r in fetch_todays_releases(only_today=False, max_items=10):
        print("-", r["title"], "|", r["posted_on"], "|", r["url"])
