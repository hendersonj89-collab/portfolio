#!/usr/bin/env python3
"""Fetch fresh remote-in-Canada job postings from structured sources.

Sources (no API keys needed):
  1. LinkedIn guest job search (remote filter, last N hours)
  2. CPA Ontario Career Centre RSS (Madgex board)
  3. Job Bank Canada search, sorted by date

Usage: python3 jobs_digest.py [--hours 48] [--json out.json]
Prints a markdown list of new postings; writes JSON if --json given.
Stdlib only, so it runs anywhere with python3.
"""
import argparse, html, json, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "en-CA,en;q=0.9"}

LINKEDIN_KEYWORDS = [
    "CPA senior accountant", "CPA controller", "accounting manager CPA",
    "financial reporting manager", "corporate tax CPA", "tax manager",
    "financial analyst CPA", "FP&A analyst", "financial data analyst",
    "accounting manager remote", "senior accountant remote",
]
CPAO_KEYWORDS = ["remote"]
JOBBANK_KEYWORDS = ["accountant CPA remote", "controller remote", "financial analyst remote", "tax remote"]

EXCLUDE_TITLE = re.compile(
    r"\b(bookkeeper|clerk|intern|co-op|receptionist|payroll administrator|junior|board member|tenure|faculty|"
    r"apprenticeship|graduate program|programme)\b", re.I)
# French-language postings (Quebec) are skipped; bilingual titles usually repeat the English after a slash.
FRENCH_TITLE = re.compile(
    r"(contr\u00f4leur|comptable|analyste|conseill|sp\u00e9cialiste|chef\.fe|directeur|directrice|financi\u00e8re|"
    r"gestionnaire|adjoint|responsable|v\u00e9rificat)", re.I)


def get(url, timeout=20, retries=3):
    """GET with browser headers; backs off and retries on HTTP 429."""
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == retries:
                raise
            time.sleep(8 * (attempt + 1))


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def linkedin(hours, log):
    out = []
    for kw in LINKEDIN_KEYWORDS:
        q = urllib.parse.urlencode({"keywords": kw, "location": "Canada", "f_WT": "2",
                                    "f_TPR": f"r{hours*3600}", "start": 0})
        url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?" + q
        try:
            body = get(url)
        except Exception as e:
            log.append(f"linkedin[{kw}]: {e}")
            continue
        for card in re.findall(r"<li>(.*?)</li>", body, re.S):
            m_link = re.search(r'href="([^"]+)"', card)
            m_title = re.search(r'class="base-search-card__title"[^>]*>(.*?)</h3>', card, re.S)
            m_co = re.search(r'class="base-search-card__subtitle"[^>]*>(.*?)</h4>', card, re.S)
            m_loc = re.search(r'class="job-search-card__location"[^>]*>(.*?)</span>', card, re.S)
            m_date = re.search(r'datetime="([^"]+)"', card)
            if not (m_link and m_title):
                continue
            out.append({"source": "linkedin", "title": clean(m_title.group(1)),
                        "company": clean(m_co.group(1)) if m_co else "",
                        "location": clean(m_loc.group(1)) if m_loc else "Canada (remote)",
                        "posted": m_date.group(1) if m_date else "",
                        "url": m_link.group(1).split("?")[0], "query": kw})
        time.sleep(1)
    return out


def cpa_ontario(hours, log):
    out = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    for kw in CPAO_KEYWORDS:
        url = "https://mycareer.cpaontario.ca/jobsrss/?" + urllib.parse.urlencode({"keywords": kw})
        try:
            root = ET.fromstring(get(url))
        except Exception as e:
            log.append(f"cpaontario[{kw}]: {e}")
            continue
        for item in root.iter("item"):
            title = clean(item.findtext("title"))
            link = (item.findtext("link") or "").strip()
            pub = item.findtext("pubDate") or ""
            desc = clean(item.findtext("description"))
            try:
                dt = datetime.strptime(pub[:25].strip(), "%a, %d %b %Y %H:%M:%S").replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
            except ValueError:
                pass
            company, _, role = title.partition(": ")
            out.append({"source": "cpaontario", "title": role or title,
                        "company": company if role else "", "location": desc[:120],
                        "posted": pub, "url": link, "query": kw})
    return out


def jobbank(hours, log):
    out = []
    for kw in JOBBANK_KEYWORDS:
        q = urllib.parse.urlencode({"searchstring": kw, "sort": "D", "fage": "2" if hours <= 48 else "7"})
        url = "https://www.jobbank.gc.ca/jobsearch/jobsearch?" + q
        try:
            body = get(url)
        except Exception as e:
            log.append(f"jobbank[{kw}]: {e}")
            continue
        for art in re.findall(r"<article[^>]*>(.*?)</article>", body, re.S):
            m_link = re.search(r'href="(/jobsearch/jobposting/[^"]+)"', art)
            m_title = re.search(r'class="noctitle[^"]*"[^>]*>(.*?)</span>', art, re.S)
            m_co = re.search(r'class="business"[^>]*>(.*?)</li>', art, re.S)
            m_loc = re.search(r'class="location"[^>]*>(.*?)</li>', art, re.S)
            m_date = re.search(r'class="date"[^>]*>(.*?)</li>', art, re.S)
            if not (m_link and m_title):
                continue
            out.append({"source": "jobbank", "title": clean(m_title.group(1)),
                        "company": clean(m_co.group(1)) if m_co else "",
                        "location": clean(m_loc.group(1)) if m_loc else "",
                        "posted": clean(m_date.group(1)) if m_date else "",
                        "url": "https://www.jobbank.gc.ca" + re.sub(r";jsessionid=[^?]*", "", m_link.group(1)).split("?")[0], "query": kw})
        time.sleep(1)
    return out


FLAG_RE = re.compile(r"\b(fully remote|remote-?first|100% remote|remote work|work remotely|remote \((?:[A-Za-z, ]{1,30})\)|"
                     r"remote position|remote role|remote opportunity|work from home|anywhere in canada|"
                     r"hybrid|on-site|onsite|in-office|in office|temporary|contract|maternity)\b", re.I)
SALARY_RE = re.compile(r"\$\s?\d{2,3},?\d{3}(?:\s?(?:-|to|\u2013)\s?\$?\s?\d{2,3},?\d{3})?", re.I)


def enrich_linkedin(jobs, limit, log):
    """Fetch each LinkedIn posting via the guest API and add remote/hybrid/salary flags."""
    n = 0
    for j in jobs:
        if j["source"] != "linkedin" or n >= limit:
            continue
        m = re.search(r"-(\d{6,})$", j["url"])
        if not m:
            continue
        n += 1
        try:
            body = get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}")
        except Exception as e:
            log.append(f"detail[{m.group(1)}]: {e}")
            continue
        desc = re.search(r'class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', body, re.S)
        text = clean(desc.group(1)) if desc else ""
        flags = sorted({f.lower() for f in FLAG_RE.findall(text)})
        sal = SALARY_RE.findall(text)
        j["flags"] = ", ".join(flags)
        j["salary"] = " / ".join(dict.fromkeys(sal)) if sal else ""
        j["cpa"] = "CPA required" if re.search(r"CPA (designation|designated)? ?(is )?(required|mandatory)|must (be|have|hold) (a )?CPA", text, re.I) \
            else ("CPA mentioned" if "CPA" in text else "")
        time.sleep(1.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--json")
    ap.add_argument("--details", type=int, default=100, help="fetch flags/salary for up to N LinkedIn rows (0 = skip)")
    a = ap.parse_args()
    log, jobs = [], []
    for fn in (linkedin, cpa_ontario, jobbank):
        jobs += fn(a.hours, log)
    seen, uniq = set(), []
    for j in jobs:
        if EXCLUDE_TITLE.search(j["title"]):
            continue
        if FRENCH_TITLE.search(j["title"]) and "/" not in j["title"]:
            continue
        if "/" in j["title"] and FRENCH_TITLE.search(j["title"]):
            # keep the English half of a bilingual title
            halves = [h.strip() for h in j["title"].split("/")]
            j["title"] = next((h for h in halves if not FRENCH_TITLE.search(h)), j["title"])
        key = (j["title"].lower(), j["company"].lower())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(j)
    if a.details:
        enrich_linkedin(uniq, a.details, log)
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"fetched_at": datetime.now(timezone.utc).isoformat(), "jobs": uniq, "errors": log}, f, indent=1)
    print(f"# {len(uniq)} postings (last {a.hours}h), {len(jobs)-len(uniq)} dupes/excluded dropped\n")
    for j in uniq:
        extra = " | ".join(x for x in (j.get("flags"), j.get("salary"), j.get("cpa")) if x)
        print(f"- [{j['source']}] {j['title']} — {j['company']} — {j['location']} — {j['posted'][:10]}"
              + (f"\n  {extra}" if extra else "") + f"\n  {j['url']}")
    if log:
        print("\n# errors\n" + "\n".join(log), file=sys.stderr)


if __name__ == "__main__":
    main()
