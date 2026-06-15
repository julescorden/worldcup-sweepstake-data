#!/usr/bin/env python3
"""
Fetches finished World Cup 2026 match results and writes a compact results.json
that the Squarespace page (wc-draw.html) reads.

Strategy:
  1. Try openfootball/worldcup.json on GitHub first.  It's a public JSON
     file maintained by hand by an active maintainer, updates within hours
     of each match finishing, and needs no scraping or API key.
  2. If openfootball returns no usable data, fall back to scraping the
     Yahoo Sports schedule article (the original source).
  3. Never overwrite a good results.json with an empty parse.  If both
     sources fail or come back empty, the existing file is left alone.
"""

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

OPENFOOTBALL_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
YAHOO_URL = "https://sports.yahoo.com/soccer/article/2026-world-cup-schedule-qualified-teams-groups-match-dates-fixtures-how-to-watch-050724214.html"

USER_AGENT = "Mozilla/5.0 (compatible; CordenCleerrrbBot/1.0; +https://github.com/julescorden/worldcup-sweepstake-data)"

TEAM_NAME_MAP = {
    "Czech Republic": "Czechia",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Turkey": "Türkiye",
    "USA": "United States",
    "Korea Republic": "South Korea",
    "Cape Verde Islands": "Cape Verde",
    "Cabo Verde": "Cape Verde",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Curacao": "Curaçao",
}


def normalise(name):
    n = (name or "").strip()
    return TEAM_NAME_MAP.get(n, n)


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_openfootball():
    try:
        raw = fetch(OPENFOOTBALL_URL)
        data = json.loads(raw)
    except Exception as e:
        print("openfootball fetch/parse failed: " + str(e), file=sys.stderr)
        return []
    out = []
    for m in data.get("matches", []):
        score = (m.get("score") or {}).get("ft")
        if not score or len(score) != 2:
            continue
        try:
            s1, s2 = int(score[0]), int(score[1])
        except (TypeError, ValueError):
            continue
        out.append({
            "team1": normalise(m.get("team1", "")),
            "team2": normalise(m.get("team2", "")),
            "date": m.get("date", ""),
            "score": {"ft": [s1, s2]},
            "goals1": [],
            "goals2": [],
        })
    return out


YAHOO_RESULT_RE = re.compile(
    r"\b([A-Z][A-Za-zA-\u017f' .\-]+?)\s+(\d+)\s*,\s+([A-Z][A-Za-zA-\u017f' .\-]+?)\s+(\d+)\b"
)


def parse_yahoo():
    try:
        html = fetch(YAHOO_URL)
    except Exception as e:
        print("Yahoo fetch failed: " + str(e), file=sys.stderr)
        return []
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    out = []
    seen = set()
    for m in YAHOO_RESULT_RE.finditer(text):
        t1, s1, t2, s2 = m.group(1).strip(), m.group(2), m.group(3).strip(), m.group(4)
        if len(t1) < 3 or len(t2) < 3:
            continue
        if any(c.isdigit() for c in t1 + t2):
            continue
        key = (t1, t2)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "team1": normalise(t1),
            "team2": normalise(t2),
            "date": "",
            "score": {"ft": [int(s1), int(s2)]},
            "goals1": [],
            "goals2": [],
        })
    return out


def build_output(matches, source):
    return {
        "name": "World Cup 2026",
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "matches": matches,
    }


def main():
    matches = parse_openfootball()
    source = "openfootball"
    if not matches:
        print("openfootball returned no matches; trying Yahoo fallback", file=sys.stderr)
        matches = parse_yahoo()
        source = "yahoo"
    if not matches:
        print("Both sources returned empty - leaving existing results.json untouched.")
        return
    out = build_output(matches, source)
    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("Wrote results.json with " + str(len(matches)) + " matches from " + source)


if __name__ == "__main__":
    main()
