#!/usr/bin/env python3
"""
Diagnostic script to see what event_type values exist in the database
and identify potential Re-Air events.
"""
import argparse
import sqlite3
from collections import Counter

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to sqlite database")
    args = ap.parse_args()
    
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    
    # Check if event_type column exists
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(events)")
    cols = {row[1] for row in cursor.fetchall()}
    
    if "event_type" not in cols:
        print("❌ event_type column doesn't exist in events table")
        print("   Run the migration script or re-ingest data")
        return
    
    print("✅ event_type column exists\n")
    
    # Get all event_type values with counts
    cursor.execute("""
        SELECT event_type, COUNT(*) as count
        FROM events
        GROUP BY event_type
        ORDER BY count DESC
    """)
    
    print("Event Type Distribution:")
    print("-" * 50)
    type_counts = {}
    for row in cursor.fetchall():
        event_type = row[0] or "(NULL)"
        count = row[1]
        type_counts[event_type] = count
        print(f"  {event_type:30s} {count:6d} events")
    
    print("\n" + "=" * 50)
    print("Sample events by type:\n")
    
    # Show sample events for each type
    for event_type in type_counts.keys():
        if event_type == "(NULL)":
            cursor.execute("""
                SELECT title, network, start_utc, airing_id
                FROM events
                WHERE event_type IS NULL
                LIMIT 3
            """)
        else:
            cursor.execute("""
                SELECT title, network, start_utc, airing_id
                FROM events
                WHERE event_type = ?
                LIMIT 3
            """, (event_type,))
        
        print(f"\n{event_type}:")
        for row in cursor.fetchall():
            print(f"  • {row[0]}")
            print(f"    Network: {row[1]}, Start: {row[2]}")
    
    # Look for potential Re-Air indicators in titles
    print("\n" + "=" * 50)
    print("Events with 'Re-Air' or 'Replay' in title:\n")
    cursor.execute("""
        SELECT title, event_type, network, start_utc
        FROM events
        WHERE title LIKE '%Re-Air%' OR title LIKE '%Replay%' OR title LIKE '%replay%'
        LIMIT 10
    """)
    
    found_reair = False
    for row in cursor.fetchall():
        found_reair = True
        print(f"  • {row[0]}")
        print(f"    Type: {row[1]}, Network: {row[2]}")
    
    if not found_reair:
        print("  (No events found with Re-Air/Replay in title)")
    
    conn.close()

if __name__ == "__main__":
    main()
