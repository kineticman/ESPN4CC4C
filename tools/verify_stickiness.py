#!/usr/bin/env python3
import argparse, sqlite3, sys
from textwrap import shorten

def get_prev_curr(conn, prev, curr):
    if prev is not None and curr is not None:
        return prev, curr
    c = conn.execute("SELECT id FROM plan_run ORDER BY id DESC LIMIT 2").fetchall()
    if len(c) < 2:
        print("Not enough plans to compare.", file=sys.stderr)
        sys.exit(1)
    return (prev or c[1][0], curr or c[0][0])

def load_slots(conn, pid):
    return conn.execute("""
        SELECT channel_id, event_id FROM plan_slot
        WHERE plan_id=? AND kind='event'
    """, (pid,)).fetchall()

def main():
    ap = argparse.ArgumentParser(description="Compare lane stickiness between two plans.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--prev", type=int, help="previous plan_id (optional)")
    ap.add_argument("--curr", type=int, help="current  plan_id (optional)")
    ap.add_argument("--limit", type=int, default=120, help="how many moved rows to print")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    prev_id, curr_id = get_prev_curr(conn, args.prev, args.curr)

    prev = load_slots(conn, prev_id)
    curr = load_slots(conn, curr_id)

    prev_map = {}
    for ch, evt in prev:
        prev_map.setdefault(evt, ch)

    common = 0
    unchanged = 0
    moved = []

    for ch, evt in curr:
        pl = prev_map.get(evt)
        if pl is None:
            continue
        common += 1
        if pl == ch:
            unchanged += 1
        else:
            moved.append((evt, pl, ch))

    print(f"=== Stickiness check ===")
    print(f"DB: {args.db}")
    print(f"Comparing plans: newest={curr_id} vs prev={prev_id}")
    print(f"Common events: {common}")
    print(f"Unchanged lanes: {unchanged}")
    print(f"Moved lanes: {len(moved)}\n")
    if moved:
        print(f"{'event_id':<66}  {'prev_lane':<10}  {'new_lane':<10}")
        print(f"{'-'*66}  {'-'*10}  {'-'*10}")
        for evt, pl, nl in moved[:args.limit]:
            print(f"{shorten(evt, width=66, placeholder='…'):<66}  {pl:<10}  {nl:<10}")

if __name__ == "__main__":
    main()
