#!/usr/bin/env python3
"""
ESPN Watch API - Airing Kind Probe

Dev tool to fetch a sample of ESPN Watch airings and classify them structurally as:
  - sports_event  (has competition or gameId)
  - sports_show   (has league/sport but no competition/gameId)
  - other         (everything else)

This is intended for debugging and refining how we tag items as "Sports event"
vs. studio shows like SportsCenter, docu-series, etc.
"""

import argparse
import datetime as _dt
import json
import sys
from typing import Any, Dict, List

import requests

# ESPN Watch API details (same as espn_api_inspector.py)
API_BASE = "https://watch.graph.api.espn.com/api"
API_KEY = "0dbf88e8-cc6d-41da-aa83-18b5c630bc5c"
FEATURES = "pbov7"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Origin": "https://www.espn.com",
    "Referer": "https://www.espn.com/",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# GraphQL query for sampling airings with structural fields we care about
AIRINGS_QUERY = """
query SampleAirings($day: String!, $limit: Int!) {
  airings(
    countryCode: "US"
    deviceType: DESKTOP
    tz: "America/New_York"
    day: $day
    limit: $limit
  ) {
    id
    name
    shortName
    type
    startDateTime
    endDateTime
    airingId
    simulcastAiringId
    gameId
    league {
      id
      name
    }
    sport {
      id
      name
    }
    competition {
      __typename
    }
    network {
      id
      name
      shortName
    }
  }
}
"""


def classify_airing(airing: Dict[str, Any]) -> str:
    """
    Classify an Airing structurally based on the Watch API fields.

    Returns one of:
      - "sports_event"
      - "sports_show"
      - "other"
    """
    has_competition = airing.get("competition") is not None
    has_game_id = airing.get("gameId") is not None
    has_league_or_sport = bool(airing.get("league") or airing.get("sport"))

    if has_competition or has_game_id:
        return "sports_event"

    if has_league_or_sport:
        return "sports_show"

    return "other"


def fetch_airings(day: str, limit: int) -> List[Dict[str, Any]]:
    """Fetch a batch of airings for a given day."""
    params = {
        "apiKey": API_KEY,
        "features": FEATURES,
    }
    payload = {
        "query": AIRINGS_QUERY,
        "variables": {
            "day": day,
            "limit": limit,
        },
    }

    resp = requests.post(
        API_BASE,
        params=params,
        headers=HEADERS,
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if "errors" in data:
        # Bubble up GraphQL errors in a readable way
        raise SystemExit(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}")

    airings = data.get("data", {}).get("airings") or []
    return airings


def summarize_airing(airing: Dict[str, Any]) -> str:
    """Create a compact one-line summary of an airing."""
    league = airing.get("league") or {}
    sport = airing.get("sport") or {}
    network = airing.get("network") or {}

    league_name = league.get("name") or "-"
    sport_name = sport.get("name") or "-"
    network_name = network.get("shortName") or network.get("name") or "-"

    start = airing.get("startDateTime") or "-"
    a_type = airing.get("type") or "-"
    name = airing.get("name") or "-"
    short = airing.get("shortName") or "-"
    airing_id = airing.get("airingId") or airing.get("id")

    has_comp = "Y" if airing.get("competition") is not None else "N"
    has_game = "Y" if airing.get("gameId") is not None else "N"

    kind = classify_airing(airing)

    return (
        f"[{kind:12}] {start}  {network_name:8} "
        f"(comp={has_comp}, gameId={has_game})  "
        f"{league_name} / {sport_name}  "
        f"name='{name}'  short='{short}'  id={airing_id}"
    )


def pick_example_cases(airings: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Pick a few example airings per kind to use as eyeball test cases.
    """
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "sports_event": [],
        "sports_show": [],
        "other": [],
    }
    for a in airings:
        kind = classify_airing(a)
        if len(buckets[kind]) < 3:
            buckets[kind].append(a)
    return buckets


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe ESPN Watch airings and classify them as sports_event / sports_show / other."
    )
    parser.add_argument(
        "--day",
        help="Day to sample in YYYY-MM-DD (default: today in America/New_York)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of airings to fetch (default: 50)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Dump raw JSON for the fetched airings (in addition to the summary).",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> None:
    args = parse_args(argv)

    if args.day:
        day = args.day
    else:
        # Use today's date in ISO format; Watch API expects YYYY-MM-DD
        day = _dt.date.today().isoformat()

    print("=" * 80)
    print(f"ESPN WATCH API - AIRING KIND PROBE  (day={day}, limit={args.limit})")
    print("=" * 80)
    print()

    try:
        airings = fetch_airings(day=day, limit=args.limit)
    except Exception as e:  # noqa: BLE001 - this is a dev tool, show everything
        print(f"❌ Error fetching airings: {e}")
        sys.exit(1)

    if not airings:
        print("No airings returned.")
        return

    # Per-airing summaries
    print("Per-airing structural classification:")
    print("-" * 80)
    for airing in airings:
        print(summarize_airing(airing))
    print()

    # Aggregate counts
    counts = {"sports_event": 0, "sports_show": 0, "other": 0}
    for a in airings:
        counts[classify_airing(a)] += 1

    print("Aggregate counts:")
    for kind, count in counts.items():
        print(f"  {kind:12}: {count}")
    print()

    # Suggested example test cases
    examples = pick_example_cases(airings)
    print("Suggested eyeball test cases (one per kind):")
    print("-" * 80)
    for kind, items in examples.items():
        if not items:
            continue
        print(f"{kind}:")
        for a in items:
            print("  " + summarize_airing(a))
        print()

    if args.json:
        print()
        print("=" * 80)
        print("Raw JSON (airings):")
        print("=" * 80)
        print(json.dumps(airings, indent=2, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
