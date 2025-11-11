#!/usr/bin/env python3
"""
Generate filter options from current database contents.
Run this to see what's actually available to filter on.
"""
import sqlite3
import sys


def get_filter_options(db_path: str) -> dict:
    """Extract all unique filter values from database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    options = {}

    # Networks
    cursor.execute(
        """
        SELECT DISTINCT network, COUNT(*) as cnt
        FROM events
        WHERE network IS NOT NULL AND network != ''
        GROUP BY network
        ORDER BY cnt DESC, network
    """
    )
    options["networks"] = cursor.fetchall()

    # Sports
    cursor.execute(
        """
        SELECT DISTINCT sport, COUNT(*) as cnt
        FROM events
        WHERE sport IS NOT NULL AND sport != ''
        GROUP BY sport
        ORDER BY cnt DESC, sport
    """
    )
    options["sports"] = cursor.fetchall()

    # Leagues
    cursor.execute(
        """
        SELECT DISTINCT league_name, COUNT(*) as cnt
        FROM events
        WHERE league_name IS NOT NULL AND league_name != ''
        GROUP BY league_name
        ORDER BY cnt DESC, league_name
    """
    )
    options["leagues"] = cursor.fetchall()

    # Event types
    cursor.execute(
        """
        SELECT DISTINCT event_type, COUNT(*) as cnt
        FROM events
        WHERE event_type IS NOT NULL AND event_type != ''
        GROUP BY event_type
        ORDER BY cnt DESC
    """
    )
    options["event_types"] = cursor.fetchall()

    # Package analysis
    cursor.execute(
        """
        SELECT packages, COUNT(*) as cnt
        FROM events
        WHERE packages IS NOT NULL AND packages != '' AND packages != '[]'
        GROUP BY packages
        ORDER BY cnt DESC
        LIMIT 20
    """
    )
    options["packages"] = cursor.fetchall()

    conn.close()
    return options


def print_options(options: dict):
    """Pretty print filter options"""
    print("=" * 80)
    print("AVAILABLE FILTER OPTIONS (from your current database)")
    print("=" * 80)

    print("\n📺 NETWORKS (by event count):")
    print("-" * 80)
    for network, count in options["networks"]:
        print(f"  {network:<30} ({count:>4} events)")

    print("\n⚽ SPORTS (by event count):")
    print("-" * 80)
    for sport, count in options["sports"]:
        print(f"  {sport:<30} ({count:>4} events)")

    print("\n🏆 LEAGUES (by event count):")
    print("-" * 80)
    for league, count in options["leagues"]:
        print(f"  {league:<30} ({count:>4} events)")

    print("\n📡 EVENT TYPES:")
    print("-" * 80)
    for etype, count in options["event_types"]:
        print(f"  {etype:<30} ({count:>4} events)")

    print("\n💰 PACKAGES (top 20):")
    print("-" * 80)
    for pkg, count in options["packages"]:
        # Parse and show cleaner
        pkg_clean = pkg.replace('["', "").replace('"]', "").replace('", "', ", ")
        print(f"  {pkg_clean:<50} ({count:>4} events)")

    print("\n" + "=" * 80)
    print("💡 TIP: Use these exact names in your filters.ini file")
    print("=" * 80)


def generate_example_config(options: dict) -> str:
    """Generate an example filters.ini with current options commented out"""
    config = """# ESPN4CC4C Filtering Configuration
# Generated from your current database contents
#
# Use "*" or "all" to include everything (no filtering)
# Use comma-separated values to whitelist specific items
# Uncomment and modify lines below to activate filters

[filters]
# ============================================================================
# NETWORK FILTERING
# ============================================================================
# Currently available networks:
"""
    for network, count in options["networks"][:10]:
        config += f"#   {network} ({count} events)\n"
    if len(options["networks"]) > 10:
        config += f"#   ... and {len(options['networks']) - 10} more\n"

    config += """#
# Examples:
#   enabled_networks = ESPN,ESPN2,ESPN+
#   exclude_networks = ESPN Deportes
enabled_networks = *
exclude_networks =

# ============================================================================
# SPORT FILTERING
# ============================================================================
# Currently available sports:
"""
    for sport, count in options["sports"]:
        config += f"#   {sport} ({count} events)\n"

    config += """#
# Examples:
#   enabled_sports = Football,Basketball,Soccer
#   exclude_sports = Dogs,Jai Alai
enabled_sports = *
exclude_sports =

# ============================================================================
# LEAGUE FILTERING
# ============================================================================
# Currently available leagues:
"""
    for league, count in options["leagues"][:15]:
        config += f"#   {league} ({count} events)\n"
    if len(options["leagues"]) > 15:
        config += f"#   ... and {len(options['leagues']) - 15} more\n"

    config += """#
# Examples:
#   enabled_leagues = NFL,NBA,NHL
#   exclude_leagues = College
#   enabled_leagues = NCAA  # Matches any league with "NCAA" in name
enabled_leagues = *
exclude_leagues =

# ============================================================================
# PACKAGE FILTERING (ESPN+ subscription requirements)
# ============================================================================
# Examples:
#   require_espn_plus = true        # Only show ESPN+ content
#   require_espn_plus = false       # Exclude ESPN+ content
#   exclude_ppv = true              # Exclude PPV events
require_espn_plus =
exclude_ppv = false

# ============================================================================
# EVENT TYPE FILTERING
# ============================================================================
# Currently available types:
"""
    for etype, count in options["event_types"]:
        config += f"#   {etype} ({count} events)\n"

    config += """#
# Examples:
#   enabled_event_types = LIVE,UPCOMING    # No replays
#   exclude_event_types = OVER             # Same as above
enabled_event_types = *
exclude_event_types =

# ============================================================================
# ADVANCED OPTIONS
# ============================================================================
case_insensitive = true
partial_league_match = true
"""
    return config


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_filter_options.py <db_path> [--generate-config]")
        print("\nExamples:")
        print("  python generate_filter_options.py ./data/eplus_vc.sqlite3")
        print(
            "  python generate_filter_options.py ./data/eplus_vc.sqlite3 --generate-config > filters.ini"  # noqa: E501
        )
        sys.exit(1)

    db_path = sys.argv[1]
    generate_config = "--generate-config" in sys.argv

    options = get_filter_options(db_path)

    if generate_config:
        print(generate_example_config(options))
    else:
        print_options(options)
