#!/usr/bin/env python3
"""
clear_sticky.py - Clear sticky lane assignments

This script clears the event_lane table which tracks "sticky" lane assignments.
Use this when you've changed filters and want to completely reset channel planning.

When to use this:
- After changing filters.ini and filters aren't applying immediately
- When you want to completely reorganize channel assignments
- As a "nuclear option" to start fresh

Note: After running this, the next build_plan will assign events to channels
from scratch without considering previous assignments.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone


def clear_sticky_lanes(db_path: str, dry_run: bool = False) -> dict:
    """
    Clear the event_lane table to reset sticky lane assignments.
    
    Args:
        db_path: Path to SQLite database
        dry_run: If True, show what would be deleted without actually deleting
        
    Returns:
        Dictionary with operation results
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "db_path": db_path,
        "dry_run": dry_run,
        "success": False,
        "error": None,
    }
    
    try:
        # Check if event_lane table exists
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='event_lane'
        """)
        
        if not cursor.fetchone():
            result["error"] = "event_lane table does not exist"
            result["lanes_cleared"] = 0
            result["success"] = True  # Not an error, just nothing to do
            return result
        
        # Count current sticky assignments
        cursor.execute("SELECT COUNT(*) FROM event_lane")
        count_before = cursor.fetchone()[0]
        result["lanes_before"] = count_before
        
        if count_before == 0:
            result["message"] = "event_lane table is already empty"
            result["lanes_cleared"] = 0
            result["success"] = True
            return result
        
        # Show some sample assignments before clearing (for dry run)
        cursor.execute("""
            SELECT event_id, channel_id 
            FROM event_lane 
            LIMIT 10
        """)
        result["sample_assignments"] = [
            {"event_id": row[0], "channel_id": row[1]} 
            for row in cursor.fetchall()
        ]
        
        if dry_run:
            result["message"] = f"Would clear {count_before} sticky lane assignments"
            result["lanes_cleared"] = 0
            result["success"] = True
        else:
            # Actually clear the table
            conn.execute("DELETE FROM event_lane")
            conn.commit()
            
            # Verify
            cursor.execute("SELECT COUNT(*) FROM event_lane")
            count_after = cursor.fetchone()[0]
            
            result["lanes_cleared"] = count_before - count_after
            result["lanes_after"] = count_after
            result["message"] = f"Cleared {result['lanes_cleared']} sticky lane assignments"
            result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
        result["success"] = False
    finally:
        conn.close()
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Clear sticky lane assignments from event_lane table",
        epilog="""
Examples:
  # Preview what would be cleared
  python3 clear_sticky.py --db data/db.sqlite3 --dry-run
  
  # Actually clear sticky assignments
  python3 clear_sticky.py --db data/db.sqlite3
  
  # Then rebuild plan to apply filters
  python3 build_plan.py --db data/db.sqlite3 --valid-hours 72
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--db",
        required=True,
        help="Path to SQLite database file",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    
    args = parser.parse_args()
    
    # Run the clear operation
    result = clear_sticky_lanes(args.db, dry_run=args.dry_run)
    
    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=" * 70)
        print("ESPN4CC4C - Clear Sticky Lane Assignments")
        print("=" * 70)
        print()
        
        if args.dry_run:
            print("🔍 DRY RUN MODE (no changes will be made)")
            print()
        
        if result["success"]:
            if "lanes_before" in result:
                print(f"Sticky assignments before: {result['lanes_before']}")
            
            if "sample_assignments" in result and result["sample_assignments"]:
                print("\nSample assignments:")
                for assign in result["sample_assignments"][:5]:
                    print(f"  • Event {assign['event_id']} → Channel {assign['channel_id']}")
                if result['lanes_before'] > 5:
                    print(f"  ... and {result['lanes_before'] - 5} more")
            
            print()
            print(f"✅ {result['message']}")
            
            if not args.dry_run and result.get("lanes_cleared", 0) > 0:
                print()
                print("Next steps:")
                print("  1. Run build_plan.py to create a fresh plan")
                print("  2. Your filters will now be fully applied")
                print()
                print("  Example:")
                print(f"    python3 build_plan.py --db {args.db} --valid-hours 72")
        else:
            print(f"❌ Error: {result['error']}")
            return 1
        
        print()
        print("=" * 70)
    
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
