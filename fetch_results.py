#!/usr/bin/env python3
"""
Daily fetch script for Corden Cleeeerrrrb World Cup sweepstake.

Pulls match results from Yahoo Sports' 2026 World Cup schedule article, which
keeps a consistent format for every group ("Thursday, June 11: Mexico 2,
South Africa 0") and is updated throughout the tournament.

Runs on GitHub Actions twice a day. Free, no API key.
"""

import datetime
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser

YAHOO_URL = (
    "https://sports.yahoo.com/soccer/article/"
    "2026-world-cup-schedule-teams-group-stage-match-dates-fixtures-"
    "how-to-watch-050724300.html"
)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36 CordenCleerrrbBot/1.0"
)

NAME_FIX = {
    "Korea Republic": "South Korea",
    "Cabo Verde": "Cape Verde",
    "Cote d'Ivoire": "Ivory Coast",
    "Czech Republic": "Czechia",
    "Turkey": "Türkiye",
    "USA": "United States",
}

TEAMS = {
    "Algeria", "Argentina", "Australia", "Austria", "Belgium",
    "Bosnia and Herzegovina", "Brazil", "Canada", "Cape Verde", "Colombia",
    "Croatia", "Curaçao", "Czechia", "DR Congo", "Ecuador", "Egypt",
    "England", "France", "Germany", "Ghana", "Haiti", "Iran", "Iraq",
    "Ivory Coast", "Japan", "Jordan", "Mexico", "Morocco", "Netherlands",
    "New Zealand", "Norway", "Panama", "Paraguay", "Portugal", "Qatar",
    "Saudi Arabia", "Scotland", "Senegal", "South Africa", "South Korea",
    "Spain", "Sweden", "Switzerland", "Tunisia", "Türkiye", "United States",
    "Uruguay", "Uzbekistan",
}


def fix_name(s: str) -> str:
    s = s.strip()
    return NAME_FIX.get(s, s)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


class TextExtractor(HTMLParser):
    BLOCK_TAGS = {"br", "p", "li", "div", "tr", "h1", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        self.parts.append(data)

    def text(self):
        return "".join(self.parts)


SORTED_TEAMS = sorted(TEAMS | set(NAME_FIX), key=len, reverse=True)
TEAM_ALTERNATION = "|".join(re.escape(t) for t in SORTED_TEAMS)
RESULT_RE = re.compile(
    r"(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
    r",\s+(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
    r"\s+(?P<day>\d{1,2})"
    r"[^:\n]*:\s*"  # tolerate ", time (channel)" or similar between date and colon
    r"(?P<t1>" + TEAM_ALTERNATION + r")"
    r"\s+(?P<s1>\d{1,2})\s*,\s+"
    r"(?P<t2>" + TEAM_ALTERNATION + r")"
    r"\s+(?P<s2>\d{1,2})",
    re.IGNORECASE,
)


def parse_matches(html: str):
    ex = TextExtractor()
    ex.feed(html)
    text = ex.text()
    flat = re.sub(r"\s+", " ", text)

    matches = []
    seen = set()
    for m in RESULT_RE.finditer(flat):
        t1 = fix_name(m.group("t1"))
        t2 = fix_name(m.group("t2"))
        if t1 not in TEAMS or t2 not in TEAMS or t1 == t2:
            continue
        try:
            date = datetime.datetime.strptime(
                f"{m.group('day')} {m.group('month')} 2026", "%d %B %Y"
            ).date().isoformat()
        except ValueError:
            continue
        key = (date, t1, t2)
        if key in seen:
            continue
        seen.add(key)
        matches.append({
            "team1": t1,
            "team2": t2,
            "date": date,
            "score": {"ft": [int(m.group("s1")), int(m.group("s2"))]},
            "goals1": [],
            "goals2": [],
        })
    return matches


def build_output(found):
    return {
        "name": "World Cup 2026",
        "updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "matches": found,
    }


def main():
    try:
        html = fetch(YAHOO_URL)
    except Exception as e:
        print(f"Failed to fetch Yahoo: {e}", file=sys.stderr)
        sys.exit(1)
    found = parse_matches(html)
    if not found:
        # Don't overwrite a good file with an empty one. Exit successfully
        # with a clear message so the workflow doesn't commit nothing.
        print("Parsed 0 matches - leaving existing results.json untouched.")
        return
    out = build_output(found)
    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Wrote results.json with {len(found)} matches")
    for m in found:
        print(f"  {m['date']}  {m['team1']} {m['score']['ft'][0]}-{m['score']['ft'][1]} {m['team2']}")


if __name__ == "__main__":
    main()
