#!/usr/bin/env python3
"""
Test which ESPN API fields are available by trying them incrementally
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
}

# Test individual fields to see what works
TEST_FIELDS = [
    ("feedName", "feedName"),
    ("feedType", "feedType"),
    ("externalId", "externalId"),
    ("eventId", "eventId"),  
    ("gameId", "gameId"),
    ("authTypes", "authTypes"),
    ("description", "description"),
]

params = {"apiKey": API_KEY, "features": FEATURES}

print("=== Testing ESPN API Fields ===\n")

working_fields = ["id", "name", "airingId", "simulcastAiringId", "type", "network { id name }", "sport { name }", "league { name }"]

for field_name, field_query in TEST_FIELDS:
    test_query = f"""
    query Test_{field_name.replace(' ', '_')} {{
      airings(countryCode: "US", deviceType: DESKTOP, tz: "America/New_York", day: "2025-11-13", limit: 3) {{
        id
        name
        network {{ name }}
        {field_query}
      }}
    }}
    """
    
    payload = {"query": test_query}
    
    try:
        r = requests.post(API_BASE, params=params, headers=HEADERS, json=payload, timeout=10)
        
        if r.status_code >= 400:
            print(f"❌ {field_name}: HTTP {r.status_code}")
            continue
        
        data = r.json()
        
        if "errors" in data:
            print(f"❌ {field_name}: {data['errors'][0].get('message', 'Error')[:80]}")
            continue
        
        airings = data.get("data", {}).get("airings", [])
        if not airings:
            print(f"⚠️  {field_name}: No airings (might still be valid field)")
            working_fields.append(field_query)
            continue
        
        # Check if field has data
        has_data = any(airing.get(field_name) for airing in airings)
        
        if has_data:
            print(f"✅ {field_name}: WORKS and HAS DATA")
            sample = next(a.get(field_name) for a in airings if a.get(field_name))
            print(f"   Sample: {sample}")
            working_fields.append(field_query)
        else:
            print(f"✅ {field_name}: Field exists but no data in these airings")
            working_fields.append(field_query)
            
    except Exception as e:
        print(f"❌ {field_name}: {str(e)[:80]}")

print("\n" + "=" * 60)
print("Building comprehensive query with working fields...")
print("=" * 60)

# Now build a comprehensive query with all working fields
final_query = f"""
query Comprehensive {{
  airings(countryCode: "US", deviceType: DESKTOP, tz: "America/New_York", day: "2025-11-13", limit: 10) {{
    {chr(10).join('    ' + f for f in working_fields)}
  }}
}}
"""

print("\nFinal query:")
print(final_query)

payload = {"query": final_query}
r = requests.post(API_BASE, params=params, headers=HEADERS, json=payload, timeout=10)
data = r.json()

if "errors" not in data:
    airings = data.get("data", {}).get("airings", [])
    print(f"\n✅ Got {len(airings)} airings with full data!")
    
    # Group by network
    by_network = {}
    for airing in airings:
        net = airing.get("network", {}).get("name", "Unknown")
        if net not in by_network:
            by_network[net] = []
        by_network[net].append(airing)
    
    print("\nData by Network:")
    for net, items in by_network.items():
        print(f"\n{net} ({len(items)} airings):")
        for item in items[:2]:  # Show first 2 from each network
            print(f"  - {item.get('name')}")
            for field_name, _ in TEST_FIELDS:
                val = item.get(field_name)
                if val:
                    print(f"      {field_name}: {val}")
else:
    print(f"\n❌ Final query failed: {data['errors']}")
