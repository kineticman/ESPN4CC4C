#!/usr/bin/env python3
import argparse
import json
import sys
import time
from datetime import date

import requests

API_HOST = "watch.graph.api.espn.com"
API_PATH = "/api"
API_KEY = "0dbf88e8-cc6d-41da-aa83-18b5c630bc5c"  # public per you

GQL_QUERY = """
query Airings(
  $countryCode: String!, $deviceType: DeviceType!, $tz: String!,
  $day: String!, $limit: Int
) {
  airings(
    countryCode: $countryCode, deviceType: $deviceType, tz: $tz,
    day: $day, limit: $limit
  ) {
    id airingId simulcastAiringId name shortName type
    startDateTime endDateTime
    network { id name shortName }
    league { id name abbreviation }
    sport { id name abbreviation }
    packages { name }
    description
    images { url width height alt }
    links { href url rel type }
  }
}
""".strip()

UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
UA_CHROME = "Mozilla/5.0 AppleWebKit/537.36 Chrome/127 Safari/537.36"


def attempt(day_iso: str, tz: str, *, features: str | None, device: str, ua: str):
    url = f"https://{API_HOST}{API_PATH}"
    params = {"apiKey": API_KEY}
    if features is not None:
        params["features"] = features

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.espn.com",
        "Referer": "https://www.espn.com/",
        "User-Agent": ua,
    }

    payload = {
        "query": GQL_QUERY,
        "variables": {
            "countryCode": "US",
            "deviceType": device,  # DESKTOP (PS), try MOBILE/TV if needed
            "tz": tz,
            "day": day_iso,  # PS used YYYY-MM-DD
            "limit": 2000,
        },
        "operationName": "Airings",
    }

    s = requests.Session()
    for i in range(1, 4):
        try:
            r = s.post(url, params=params, headers=headers, json=payload, timeout=20)
            ok = 200 <= r.status_code < 300
            print(
                f"[{i}] features={features!r} device={device} ua={'DESKTOP' if ua == UA_DESKTOP else 'CHROME'} -> {r.status_code}"  # noqa: E501
            )
            if not ok:
                body = r.text
                print("  resp-ct:", r.headers.get("content-type"))
                print(
                    "  body-snippet:",
                    body[:500].replace("\n", " ") if body else "<empty>",
                )
                time.sleep(0.5 * i)
                continue

            data = r.json()
            air = (data or {}).get("data", {}).get("airings") or []
            print(f"  ✓ {len(air)} airings")
            return air
        except Exception as e:
            print(f"  EX: {e!r}")
            time.sleep(0.5 * i)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--tz", default="America/New_York")
    ap.add_argument("--save", help="Save raw airings JSON to file")
    args = ap.parse_args()

    day_iso = args.day or date.today().strftime("%Y-%m-%d")

    # Try a small matrix of "likely good" shapes:
    tries = [
        {"features": "pbov7", "device": "DESKTOP", "ua": UA_DESKTOP},  # exact PS shape
        {"features": None, "device": "DESKTOP", "ua": UA_DESKTOP},  # omit features
        {"features": "pbov7", "device": "MOBILE", "ua": UA_CHROME},  # alt device
        {"features": "pbov7", "device": "TV", "ua": UA_CHROME},  # alt device
        {"features": "", "device": "DESKTOP", "ua": UA_CHROME},  # empty features param
    ]

    air = None
    for t in tries:
        air = attempt(day_iso, args.tz, **t)
        if air is not None:
            break

    if air is None:
        print("All attempts returned errors. See diagnostics above.", file=sys.stderr)
        sys.exit(2)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump({"airings": air}, f, indent=2)
        print(f"Saved raw -> {args.save}")

    # Print a short summary
    print(
        json.dumps(
            {
                "total_airings": len(air),
                "first_fields": sorted(list(air[0].keys())) if air else [],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
