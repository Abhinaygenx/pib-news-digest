"""
scraper.py — Fetches today's press releases from pib.gov.in

PIB's site is an ASP.NET WebForms app. We use two strategies to get release links:

Primary: Scrape the "All Releases" listing page (allRel.aspx), which lists the
  day's releases grouped by ministry.

Fallback: Use the PIB press-release search page (allrelNew.aspx) which lists
  releases with English titles directly, as a fallback if the primary page
  returns 0 links (common when running from CI/cloud IPs that PIB's server
  treats with less trust).

In both cases, each release's detail page is then fetched for the full body.
Article body text is extracted by finding the line containing "Posted On:"
(start marker) and "(Release ID:" (end marker), since every PIB release
follows this exact template.

Session warming: We always visit the PIB homepage first to establish a session
cookie, which greatly improves the reliability of subsequent scraping requests.
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
FALLBACK_LISTING_URL = f"{BASE}/allrelNew.aspx"
DETAIL_URL = f"{BASE}/PressReleasePage.aspx"

# A realistic browser User-Agent avoids some basic bot-blocking.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

IST = timezone(timedelta(hours=5, minutes=30))


def _today_ist_str():
    """Return today's date in IST as it appears in PIB's 'Posted On' line, e.g. '03 JUL 2026'."""
    return datetime.now(IST).strftime("%d %b %Y").upper()


def _warm_session(session):
    """Visit the PIB homepage to establish a session cookie before scraping."""
    try:
        session.get(f"{BASE}/", headers=HEADERS, timeout=20)
        time.sleep(0.5)
    except Exception as e:
        logger.warning("Session warm-up failed (non-fatal): %s", e)


def _extract_prid_links(soup, lang=1, reg=3, max_items=60):
    """Extract PRID links from a BeautifulSoup-parsed page."""
    seen = set()
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"PRID=(\d+)", href, re.IGNORECASE)
        if not m:
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
    return links


def get_release_links(lang=1, reg=3, session=None, max_items=60):
    """
    Fetch the 'All Releases' listing page and return a de-duplicated list
    of {"prid": ..., "url": ...} dicts for every press release linked on it.

    Falls back to an alternate listing page if the primary page returns 0 results.
    lang=1 -> English, reg=3 -> National (PIB Delhi) region.
    """
    session = session or requests.Session()
    params = {"lang": lang, "reg": reg}

    # --- Primary listing page ---
    try:
        resp = session.get(LISTING_URL, headers=HEADERS, params=params, timeout=25)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        links = _extract_prid_links(soup, lang=lang, reg=reg, max_items=max_items)
        logger.info("Primary listing: found %d release links", len(links))
        if links:
            return links
    except Exception as e:
        logger.warning("Primary listing page failed: %s", e)

    # --- Fallback listing page ---
    logger.info("Trying fallback listing page: %s", FALLBACK_LISTING_URL)
    try:
        resp2 = session.get(FALLBACK_LISTING_URL, headers=HEADERS, params=params, timeout=25)
        resp2.raise_for_status()
        soup2 = BeautifulSoup(resp2.text, "lxml")
        links2 = _extract_prid_links(soup2, lang=lang, reg=reg, max_items=max_items)
        logger.info("Fallback listing: found %d release links", len(links2))
        if links2:
            return links2
    except Exception as e:
        logger.warning("Fallback listing page also failed: %s", e)

    # --- Second fallback: search page with today's date ---
    from datetime import datetime
    today = datetime.now(IST)
    date_param = today.strftime("%d/%m/%Y")
    search_url = f"{BASE}/allrel.aspx"
    search_params = {"lang": lang, "reg": reg, "fromdate": date_param, "todate": date_param}
    logger.info("Trying date-filtered search fallback for %s", date_param)
    try:
        resp3 = session.get(search_url, headers=HEADERS, params=search_params, timeout=25)
        resp3.raise_for_status()
        soup3 = BeautifulSoup(resp3.text, "lxml")
        links3 = _extract_prid_links(soup3, lang=lang, reg=reg, max_items=max_items)
        logger.info("Date-filtered search: found %d release links", len(links3))
        return links3
    except Exception as e:
        logger.warning("Date-filtered search also failed: %s", e)

    return []


def get_release_detail(url, session=None, retries=2):
    """
    Fetch a single press release page and return
    {"title": str, "body": str, "posted_on": str|None, "url": url}
    or None if the page couldn't be parsed.

    Retries up to `retries` times on transient network errors.
    """
    session = session or requests.Session()
    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=25)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries:
                wait = 2 ** attempt
                logger.warning("Attempt %d failed for %s: %s — retrying in %ds", attempt + 1, url, e, wait)
                time.sleep(wait)
    else:
        raise last_exc

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
    Full pipeline: warm session, get today's listing, fetch each detail page,
    filter to today's date (IST) if only_today=True, and return a list of
    release dicts.
    """
    session = requests.Session()

    # Warm the session with a homepage visit before scraping
    _warm_session(session)

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
