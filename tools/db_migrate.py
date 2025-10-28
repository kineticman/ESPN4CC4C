#!/usr/bin/env python3
import argparse, os, sys, subprocess

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--lanes", type=int, default=40)
    ap.add_argument("--seed-channels-if-empty", action="store_true")
    ap.add_argument("--drop-unique-plan-run", action="store_true")
    args = ap.parse_args()

    # Prefer the repo version of rebuildDB.py (mounted at /app/tools inside container)
    here = os.path.dirname(os.path.abspath(__file__))
    rebuild = os.path.join(here, "rebuildDB.py")
    if not os.path.exists(rebuild):
        print("rebuildDB.py not found next to db_migrate.py", file=sys.stderr)
        sys.exit(0)  # non-fatal; update_schedule.sh continues

    cmd = [
        sys.executable, rebuild,
        "--db", args.db,
        "--lanes", str(args.lanes),
    ]

    # rebuildDB.py already seeds channels if empty, so this flag is advisory
    if args.seed_channels_if_empty:
        # no-op; included for API symmetry
        pass

    if args.drop_unique_plan_run:
        cmd.append("--drop-unique-plan-run")

    # DO NOT pass --wipe-plans here; migrations should be non-destructive.
    subprocess.run(cmd, check=False)

if __name__ == "__main__":
    main()
