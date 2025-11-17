#!/usr/bin/env python3
"""
ESPN Watch API Schema Inspector
Discovers all available fields in the airings query using GraphQL introspection
"""
import json
import sys

import requests

# ESPN Watch API details
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

# GraphQL Introspection Query - discovers the schema
INTROSPECTION_QUERY = """
{
  __type(name: "Airing") {
    name
    kind
    fields {
      name
      type {
        name
        kind
        ofType {
          name
          kind
        }
      }
      description
    }
  }
}
"""

# Test query to get a real airing and see what fields actually come back
TEST_QUERY = """
query TestAiring {
  airings(
    countryCode: "US"
    deviceType: DESKTOP
    tz: "America/New_York"
    day: "2025-11-11"
    limit: 1
  ) {
    id
    name
    shortName
    type
    startDateTime
    endDateTime
    airingId
    simulcastAiringId
    network {
      id
      name
      shortName
    }
    league {
      id
      name
      abbreviation
    }
    sport {
      id
      name
      abbreviation
    }
    packages {
      name
    }
  }
}
"""


def introspect_schema():
    """Use GraphQL introspection to discover available fields"""
    print("=" * 80)
    print("ESPN WATCH API - SCHEMA INTROSPECTION")
    print("=" * 80)
    print()

    params = {"apiKey": API_KEY, "features": FEATURES}
    payload = {"query": INTROSPECTION_QUERY}

    try:
        r = requests.post(
            API_BASE, params=params, headers=HEADERS, json=payload, timeout=10
        )
        r.raise_for_status()
        data = r.json()

        airing_type = data.get("data", {}).get("__type")
        if not airing_type:
            print("❌ Could not introspect Airing type")
            print(f"Response: {json.dumps(data, indent=2)}")
            return

        print(f"Type: {airing_type['name']}")
        print(f"Kind: {airing_type['kind']}")
        print()
        print("Available Fields:")
        print("-" * 80)

        fields = airing_type.get("fields", [])
        for field in sorted(fields, key=lambda x: x["name"]):
            name = field["name"]
            type_info = field["type"]
            type_name = type_info.get("name") or (
                type_info.get("ofType", {}).get("name") or "Unknown"
            )
            type_kind = type_info.get("kind")
            desc = field.get("description", "")

            # Build type string
            if type_kind == "LIST":
                type_str = f"[{type_name}]"
            elif type_kind == "NON_NULL":
                inner = type_info.get("ofType", {})
                inner_name = inner.get("name", "Unknown")
                type_str = f"{inner_name}!"
            else:
                type_str = type_name

            print(f"  {name:30s} {type_str:20s} {desc}")

        print()
        print(f"Total fields available: {len(fields)}")

    except Exception as e:
        print(f"❌ Introspection failed: {e}")
        import traceback

        traceback.print_exc()


def test_real_data():
    """Fetch actual data to see what's really returned"""
    print()
    print("=" * 80)
    print("REAL DATA TEST - Fetching 1 actual airing")
    print("=" * 80)
    print()

    params = {"apiKey": API_KEY, "features": FEATURES}
    payload = {"query": TEST_QUERY, "operationName": "TestAiring"}

    try:
        r = requests.post(
            API_BASE, params=params, headers=HEADERS, json=payload, timeout=10
        )
        r.raise_for_status()
        data = r.json()

        airings = data.get("data", {}).get("airings", [])
        if not airings:
            print("❌ No airings returned")
            return

        airing = airings[0]
        print("Sample Airing Data:")
        print("-" * 80)
        print(json.dumps(airing, indent=2))
        print()
        print("Fields present in response:")
        print("-" * 80)
        for key in sorted(airing.keys()):
            value = airing[key]
            value_type = type(value).__name__
            print(f"  {key:30s} {value_type:15s} {str(value)[:50]}")

    except Exception as e:
        print(f"❌ Real data test failed: {e}")
        import traceback

        traceback.print_exc()


def test_extended_fields():
    """Try querying additional fields that might exist but aren't documented"""
    print()
    print("=" * 80)
    print("EXTENDED FIELDS TEST - Trying potentially available fields")
    print("=" * 80)
    print()

    # Fields that might exist based on common GraphQL patterns
    test_fields = [
        "thumbnail",
        "image",
        "imageUrl",
        "thumbnailUrl",
        "poster",
        "posterUrl",
        "logo",
        "logoUrl",
        "images",
        "media",
        "description",
        "summary",
        "longDescription",
        "venue",
        "competitors",
        "teams",
        "category",
        "categories",
    ]

    # Build a query with all test fields
    fields_str = "\n    ".join(test_fields)
    extended_query = f"""
    query ExtendedTest {{
      airings(
        countryCode: "US"
        deviceType: DESKTOP
        tz: "America/New_York"
        day: "2025-11-11"
        limit: 1
      ) {{
        id
        name
        {fields_str}
      }}
    }}
    """

    params = {"apiKey": API_KEY, "features": FEATURES}
    payload = {"query": extended_query}

    try:
        r = requests.post(
            API_BASE, params=params, headers=HEADERS, json=payload, timeout=10
        )

        # Note: This might return errors for invalid fields, which is fine
        data = r.json()

        if "errors" in data:
            print("Testing fields resulted in errors (expected):")
            print("-" * 80)
            for error in data["errors"]:
                msg = error.get("message", "")
                print(f"  {msg}")

            # Parse out which fields failed
            print()
            print("Fields that FAILED (don't exist):")
            print("-" * 80)
            for field in test_fields:
                if any(field in str(e) for e in data["errors"]):
                    print(f"  ❌ {field}")

            print()
            print("Fields that might exist (no explicit error):")
            print("-" * 80)
            for field in test_fields:
                if not any(field in str(e) for e in data["errors"]):
                    print(f"  ✅ {field} (might exist, try individual query)")

        else:
            print("✅ Query succeeded! Here's what came back:")
            airings = data.get("data", {}).get("airings", [])
            if airings:
                print(json.dumps(airings[0], indent=2))

    except Exception as e:
        print(f"❌ Extended test failed: {e}")


def main():
    print()
    print("ESPN WATCH API FIELD DISCOVERY")
    print("Discovering what fields are available in the airings query...")
    print()

    # Run all tests
    introspect_schema()
    test_real_data()
    test_extended_fields()

    print()
    print("=" * 80)
    print("DONE!")
    print("=" * 80)


if __name__ == "__main__":
    main()
