#!/usr/bin/env python3
"""
Investigate the relationship between packages and networks
to understand ESPN+ vs linear network requirements
"""
import json
import sqlite3
import sys
from collections import defaultdict


def analyze_packages_networks(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all events with their network and package info
    cursor.execute(
        """
        SELECT network, network_short, packages, COUNT(*) as cnt
        FROM events
        WHERE network IS NOT NULL
        GROUP BY network, network_short, packages
        ORDER BY network, cnt DESC
    """
    )

    rows = cursor.fetchall()

    # Organize by network
    by_network = defaultdict(lambda: {"total": 0, "packages": defaultdict(int)})

    for network, network_short, packages_json, count in rows:
        by_network[network]["total"] += count

        # Parse packages
        if packages_json and packages_json != "[]":
            try:
                packages = json.loads(packages_json)
                pkg_key = ", ".join(sorted(packages)) if packages else "No package"
            except Exception:
                pkg_key = "Invalid JSON"
        else:
            pkg_key = "No package"

        by_network[network]["packages"][pkg_key] += count

    print("=" * 100)
    print("NETWORK vs PACKAGE ANALYSIS")
    print("=" * 100)
    print()

    # Categorize networks
    espn_plus_networks = []
    linear_networks = []
    mixed_networks = []

    for network in sorted(by_network.keys()):
        data = by_network[network]
        total = data["total"]
        packages = data["packages"]

        has_espn_plus = any("ESPN_PLUS" in pkg for pkg in packages.keys())
        has_no_package = "No package" in packages

        print(f"📺 {network:<30} ({total} events)")
        print("-" * 100)

        for pkg, cnt in sorted(packages.items(), key=lambda x: -x[1]):
            pct = cnt / total * 100
            print(f"   {pkg:<60} {cnt:>4} events ({pct:>5.1f}%)")
        print()

        # Categorize
        if has_espn_plus and not has_no_package:
            espn_plus_networks.append(network)
        elif not has_espn_plus and has_no_package:
            linear_networks.append(network)
        else:
            mixed_networks.append(network)

    print("=" * 100)
    print("CREDENTIAL REQUIREMENTS SUMMARY")
    print("=" * 100)
    print()

    print("🔑 ESPN+ SUBSCRIPTION REQUIRED:")
    print("-" * 100)
    for net in espn_plus_networks:
        print(f"  • {net:<30} ({by_network[net]['total']} events)")
    print()

    print("📺 LINEAR TV PROVIDER REQUIRED (Cable/Satellite/Streaming TV):")
    print("-" * 100)
    for net in linear_networks:
        print(f"  • {net:<30} ({by_network[net]['total']} events)")
    print()

    if mixed_networks:
        print("⚠️  MIXED/UNCLEAR:")
        print("-" * 100)
        for net in mixed_networks:
            print(f"  • {net:<30} ({by_network[net]['total']} events)")
        print()

    # Check for events that appear on both ESPN+ and linear
    print("=" * 100)
    print("SIMULCAST ANALYSIS (same event on multiple networks)")
    print("=" * 100)
    print()

    cursor.execute(
        """
        SELECT e1.title, e1.network, e2.network, e1.packages, e2.packages
        FROM events e1
        JOIN events e2 ON e1.title = e2.title
            AND e1.start_utc = e2.start_utc
            AND e1.network != e2.network
        WHERE e1.network < e2.network
        LIMIT 20
    """
    )

    simulcasts = cursor.fetchall()
    if simulcasts:
        print("Sample simulcast events (same event on multiple networks):")
        print()
        for title, net1, net2, pkg1, pkg2 in simulcasts[:10]:
            print(f"  '{title}'")
            print(f"    → {net1:<20} {pkg1 or 'No package'}")
            print(f"    → {net2:<20} {pkg2 or 'No package'}")
            print()
    else:
        print("No simulcast events detected in database.")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python investigate_packages.py <db_path>")
        sys.exit(1)

    analyze_packages_networks(sys.argv[1])
