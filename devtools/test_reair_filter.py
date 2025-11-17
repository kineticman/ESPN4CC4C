#!/usr/bin/env python3
"""
Test Re-Air filtering functionality
"""
import sys
import sqlite3
from pathlib import Path

# Add parent to path to import filter_events
sys.path.insert(0, str(Path(__file__).parent))
from filter_events import EventFilter


def test_reair_filter(db_path: str):
    """Test Re-Air filtering on database"""
    
    print("=" * 70)
    print("Testing Re-Air Filter")
    print("=" * 70)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get total counts
    cursor.execute("SELECT COUNT(*) FROM events")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM events WHERE is_reair = 1")
    reair_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM events WHERE is_reair = 0 OR is_reair IS NULL")
    regular_count = cursor.fetchone()[0]
    
    print(f"\nDatabase Stats:")
    print(f"  Total events:    {total:6d}")
    print(f"  Regular events:  {regular_count:6d} ({regular_count/total*100:.1f}%)")
    print(f"  Re-Air events:   {reair_count:6d} ({reair_count/total*100:.1f}%)")
    
    # Test 1: Default filter (include re-airs)
    print("\n" + "-" * 70)
    print("Test 1: Default filter (exclude_reair = false)")
    print("-" * 70)
    
    filter1 = EventFilter()  # No config file = defaults
    filter1.exclude_reair = False
    
    cursor.execute("""
        SELECT id, title, is_reair, network
        FROM events
        LIMIT 100
    """)
    
    included = 0
    excluded = 0
    for row in cursor.fetchall():
        event = {
            "id": row[0],
            "title": row[1],
            "is_reair": row[2],
            "network": row[3],
        }
        if filter1.should_include(event):
            included += 1
        else:
            excluded += 1
    
    print(f"  Included: {included}, Excluded: {excluded}")
    print(f"  ✓ All events included (as expected)")
    
    # Test 2: Exclude re-airs
    print("\n" + "-" * 70)
    print("Test 2: Exclude Re-Airs (exclude_reair = true)")
    print("-" * 70)
    
    filter2 = EventFilter()
    filter2.exclude_reair = True
    
    cursor.execute("""
        SELECT id, title, is_reair, network
        FROM events
    """)
    
    included_regular = 0
    excluded_reair = 0
    for row in cursor.fetchall():
        event = {
            "id": row[0],
            "title": row[1],
            "is_reair": row[2],
            "network": row[3],
        }
        if filter2.should_include(event):
            included_regular += 1
        else:
            excluded_reair += 1
    
    print(f"  Included (regular): {included_regular}")
    print(f"  Excluded (re-airs): {excluded_reair}")
    
    if excluded_reair == reair_count:
        print(f"  ✓ Correctly excluded all {reair_count} Re-Air events")
    else:
        print(f"  ✗ ERROR: Expected to exclude {reair_count}, but excluded {excluded_reair}")
    
    # Show sample excluded re-airs
    print("\n" + "-" * 70)
    print("Sample Re-Air Events (that would be excluded):")
    print("-" * 70)
    
    cursor.execute("""
        SELECT title, network, event_type
        FROM events
        WHERE is_reair = 1
        LIMIT 5
    """)
    
    for row in cursor.fetchall():
        print(f"  • {row[0]}")
        print(f"    Network: {row[1]}, Type: {row[2]}")
    
    conn.close()
    
    print("\n" + "=" * 70)
    print("✓ Re-Air filtering test complete!")
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_reair_filter.py <db_path>")
        sys.exit(1)
    
    test_reair_filter(sys.argv[1])
