#!/usr/bin/env python3
"""
Check Re-Air events in the database after ingesting with isReAir field.
"""
import argparse
import sqlite3

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to sqlite database")
    args = ap.parse_args()
    
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check if is_reair column exists
    cursor.execute("PRAGMA table_info(events)")
    cols = {row[1] for row in cursor.fetchall()}
    
    if "is_reair" not in cols:
        print("❌ is_reair column doesn't exist yet")
        print("   Run the updated ingestion script to add this field")
        return
    
    print("✅ is_reair column exists\n")
    
    # Count Re-Air vs regular events
    cursor.execute("SELECT COUNT(*) FROM events WHERE is_reair = 1")
    reair_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM events WHERE is_reair = 0 OR is_reair IS NULL")
    regular_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM events")
    total_count = cursor.fetchone()[0]
    
    print("Event Distribution:")
    print("=" * 60)
    print(f"  Regular events:  {regular_count:6d} ({regular_count/total_count*100:.1f}%)")
    print(f"  Re-Air events:   {reair_count:6d} ({reair_count/total_count*100:.1f}%)")
    print(f"  Total events:    {total_count:6d}")
    
    # Show sample Re-Air events
    if reair_count > 0:
        print("\n" + "=" * 60)
        print("Sample Re-Air Events:")
        print("=" * 60)
        cursor.execute("""
            SELECT title, network, event_type, start_utc
            FROM events
            WHERE is_reair = 1
            ORDER BY start_utc
            LIMIT 10
        """)
        
        for row in cursor.fetchall():
            print(f"\n  • {row[0]}")
            print(f"    Network: {row[1]}, Type: {row[2]}")
            print(f"    Start: {row[3]}")
    
    # Show event_type distribution for Re-Air events
    print("\n" + "=" * 60)
    print("Re-Air Events by Type:")
    print("=" * 60)
    cursor.execute("""
        SELECT event_type, COUNT(*) as count
        FROM events
        WHERE is_reair = 1
        GROUP BY event_type
        ORDER BY count DESC
    """)
    
    for row in cursor.fetchall():
        event_type = row[0] or "(NULL)"
        count = row[1]
        print(f"  {event_type:20s} {count:6d} events")
    
    # Show network distribution for Re-Air events
    print("\n" + "=" * 60)
    print("Top Networks for Re-Air Events:")
    print("=" * 60)
    cursor.execute("""
        SELECT network, COUNT(*) as count
        FROM events
        WHERE is_reair = 1
        GROUP BY network
        ORDER BY count DESC
        LIMIT 10
    """)
    
    for row in cursor.fetchall():
        network = row[0] or "(NULL)"
        count = row[1]
        print(f"  {network:20s} {count:6d} events")
    
    conn.close()

if __name__ == "__main__":
    main()
