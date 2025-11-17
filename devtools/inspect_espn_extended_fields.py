#!/usr/bin/env python3
"""
Fetch ESPN API data and examine the links field for deeplink clues
"""
import json
import requests

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

# Query with additional fields that might help
QUERY = """
query TestFields {
  airings(
    countryCode: "US"
    deviceType: DESKTOP
    tz: "America/New_York"
    day: "2025-11-13"
    limit: 10
  ) {
    id
    airingId
    simulcastAiringId
    name
    type
    network { id name shortName }
    sport { name }
    league { name }
    image { url }
    feedName
    feedType
    externalId
    eventId
    gameId
    authTypes
    source { id name }
    tier
    links {
      web {
        href
        short {
          href
        }
      }
      self {
        href
      }
    }
  }
}
"""

params = {"apiKey": API_KEY, "features": FEATURES}
payload = {"query": QUERY}

print("=== Fetching ESPN API data with extended fields ===\n")

try:
    r = requests.post(API_BASE, params=params, headers=HEADERS, json=payload, timeout=10)
    r.raise_for_status()
    data = r.json()
    
    if "errors" in data:
        print("GraphQL Errors:")
        for error in data["errors"]:
            print(f"  - {error.get('message')}")
        print("\nPartial data may still be available...\n")
    
    airings = data.get("data", {}).get("airings", [])
    
    if not airings:
        print("No airings returned!")
        exit(1)
    
    print(f"Found {len(airings)} airings\n")
    print("=" * 80)
    
    for i, airing in enumerate(airings, 1):
        network = airing.get("network", {})
        network_name = network.get("name", "Unknown")
        network_id = network.get("id", "")
        
        print(f"\n{i}. {airing.get('name', 'Untitled')}")
        print(f"   Network: {network_name} (ID: {network_id})")
        print(f"   Type: {airing.get('type')}")
        print(f"   ID: {airing.get('id')}")
        print(f"   AiringID: {airing.get('airingId')}")
        print(f"   SimulcastAiringID: {airing.get('simulcastAiringId')}")
        
        # Check for additional fields
        if airing.get('feedName'):
            print(f"   FeedName: {airing['feedName']}")
        if airing.get('feedType'):
            print(f"   FeedType: {airing['feedType']}")
        if airing.get('externalId'):
            print(f"   ExternalID: {airing['externalId']}")
        if airing.get('eventId'):
            print(f"   EventID: {airing['eventId']}")
        if airing.get('gameId'):
            print(f"   GameID: {airing['gameId']}")
        if airing.get('authTypes'):
            print(f"   AuthTypes: {airing['authTypes']}")
        if airing.get('source'):
            print(f"   Source: {airing['source']}")
        if airing.get('tier'):
            print(f"   Tier: {airing['tier']}")
        
        # The important one - links!
        links = airing.get('links')
        if links:
            print(f"   Links: {json.dumps(links, indent=6)}")
        
        print("   " + "-" * 76)
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY - Fields by Network")
    print("=" * 80)
    
    networks = {}
    for airing in airings:
        net = airing.get("network", {}).get("name", "Unknown")
        if net not in networks:
            networks[net] = {
                "has_links": 0,
                "has_auth_types": 0,
                "has_external_id": 0,
                "has_event_id": 0,
                "total": 0
            }
        
        networks[net]["total"] += 1
        if airing.get("links"):
            networks[net]["has_links"] += 1
        if airing.get("authTypes"):
            networks[net]["has_auth_types"] += 1
        if airing.get("externalId"):
            networks[net]["has_external_id"] += 1
        if airing.get("eventId"):
            networks[net]["has_event_id"] += 1
    
    for net, stats in networks.items():
        print(f"\n{net}:")
        print(f"  Total: {stats['total']}")
        print(f"  Has Links: {stats['has_links']}")
        print(f"  Has AuthTypes: {stats['has_auth_types']}")
        print(f"  Has ExternalID: {stats['has_external_id']}")
        print(f"  Has EventID: {stats['has_event_id']}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
