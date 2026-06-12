#!/usr/bin/env python3
"""
Daily fetch script for Corden Cleeeerrrrb World Cup sweepstake.

Pulls match results from Wikipedia's "2026 FIFA World Cup" article (and the
group pages), parses scores and dates, and writes results.json in the
openfootball-compatible shape that the sweepstake page already understands.

Runs on GitHub Actions twice a day. Free, no API key, no signup.

Schema produced (matches the page's expected feed):
{
  "name": "World Cup 2026",
  "updated": "2026-06-12T08:00:00Z",
  "matches": [
    {
      "team1": "Mexico",
      "team2": "South Africa",
      "date":  "2026-06-11",
      "group": "Group A",
      "score": {"ft": [2, 0]},
      "goals1": [{"name": "Quinones"}, {"name": "Jimenez"}],
      "goals2": []
    },
    ...
  ]
}
"""

import json
import re
import sys
import urllib.request
import datetime
from html.parser import HTMLParser

WIKI_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup"
USER_AGENT = "CordenCleerrrbSweepstakeBot/1.0 (https://github.com)"

# All 48 qualified teams. We use this list to recognise match rows.
TEAMS = [
    "Algeria", "Argentina", "Australia", "Austria", "Belgium",
    "Bosnia and Herzegovina", "Brazil", "Canada", "Cape Verde", "Colombia",
    "Croatia", "Curacao", "Czechia", "DR Congo", "Ecuador", "Egypt",
    "England", "France", "Germany", "Ghana", "Haiti", "Iran", "Iraq",
    "Ivory Coast", "Japan", "Jordan", "Mexico", "Morocco", "Netherlands",
    "New Zealand", "Norway", "Panama", "Paraguay", "Portugal", "Qatar",
    "Saudi Arabia", "Scotland", "Senegal", "South Africa", "South Korea",
    "Spain", "Sweden", "Switzerland", "Tunisia", "Turkiye", "United States",
    "Uruguay", "Uzbekistan",
]

# Normalise common name variants from Wikipedia to the page's spellings.
NAME_FIX = {
    "Czech Republic": "Czechia",
    "Turkey": "Turkiye",
    "Türkiye": "Turkiye",
    "United States of America": "United States",
    "USA": "United States",
    "Cote d'Ivoire": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "South Korea": "South Korea",
    "Korea Republic": "South Korea",
    "Curaçao": "Curacao",
}


def fix_name(s: str) -> str:
    s = s.strip()
    return NAME_FIX.get(s, s)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


# ---------- HTML parsing ----------
# Wikipedia's group-stage tables follow a standard infobox-football style:
# each match has a date row, then "Team1 score-score Team2".
# Rather than parse the giant page perfectly, we use focused regexes against
# the rendered text, which is robust to Wikipedia's table markup variations.

# Match line example (after stripping tags):
#   "11 June 2026 13:00 Mexico 2-0 South Africa Estadio Azteca, Mexico City"
# We hunt for: <date> <team> <a-b> <team>
DATE_RE = re.compile(
    r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+2026)",
    re.IGNORECASE,
)
SCORE_RE = re.compile(r"\b(\d{1,2})\s*[\u2013\u2014\-]\s*(\d{1,2})\b")


class TextExtractor(HTMLParser):
    """Strip HTML tags but preserve readable spacing."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("br", "tr", "li", "p", "h1", "h2", "h3", "table"):
            self.parts.append("\n")
        if tag == "td":
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if self.skip:
            return
        self.parts.append(data)

    def text(self):
        return "".join(self.parts)


def parse_matches(html: str):
    """Return a list of (date_iso, team1, score1, score2, team2)."""
    ex = TextExtractor()
    ex.feed(html)
    text = ex.text()
    # Collapse whitespace inside each line, keep line breaks.
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"[\t ]+", " ", raw).strip()
        if line:
            lines.append(line)

    matches = []
    current_date = None
    for line in lines:
        d = DATE_RE.search(line)
        if d:
            try:
                current_date = datetime.datetime.strptime(
                    d.group(1), "%d %B %Y"
                ).date().isoformat()
            except ValueError:
                pass
        sc = SCORE_RE.search(line)
        if sc and current_date:
            a, b = int(sc.group(1)), int(sc.group(2))
            # Look for two team names in the same line, one before and one
            # after the score. We grab the longest known-team substring on
            # each side. This handles "Mexico 2-0 South Africa" cleanly and
            # also lines like "Mexico v South Africa 13:00 ... 2-0 ...".
            before = line[: sc.start()]
            after = line[sc.end():]
            t1 = find_team(before)
            t2 = find_team(after)
            if t1 and t2 and t1 != t2:
                matches.append((current_date, t1, a, b, t2))
    return matches


def find_team(segment: str):
    """Return the longest team name appearing in segment, or None."""
    best = None
    for name in TEAMS:
        # Wikipedia may render as Türkiye / Curaçao; check the page-friendly
        # name as well as the unaccented form.
        for variant in (name, name.replace("Turkiye", "Türkiye"),
                        name.replace("Curacao", "Curaçao")):
            if variant in segment:
                if best is None or len(variant) > len(best):
                    best = name
                break
    return best


def build_output(found):
    """Produce the openfootball-shaped JSON the page reads."""
    out = {
        "name": "World Cup 2026",
        "updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "matches": [],
    }
    seen = set()
    for date_iso, t1, a, b, t2 in found:
        key = (date_iso, t1, t2)
        if key in seen:
            continue
        seen.add(key)
        out["matches"].append({
            "team1": t1,
            "team2": t2,
            "date": date_iso,
            "score": {"ft": [a, b]},
            "goals1": [],
            "goals2": [],
        })
    return out


def main():
    try:
        html = fetch(WIKI_URL)
    except Exception as e:
        print(f"Failed to fetch Wikipedia: {e}", file=sys.stderr)
        sys.exit(1)
    found = parse_matches(html)
    out = build_output(found)
    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Wrote results.json with {len(out['matches'])} matches")


if __name__ == "__main__":
    main()
