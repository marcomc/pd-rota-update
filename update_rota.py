#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
update_rota.py — Sync a CSV rota to PagerDuty schedule layers.

The schedule must have one layer per weekday (Mon–Sun), each with a single
day-of-week restriction.  The script identifies those seven layers, replaces
their user rotation with the assignments from the CSV, and sets the rotation
start date to the first occurrence of that weekday in the CSV.

A "fill" layer (e.g. daytime Mon–Fri with multiple restrictions) and expired
layers (those with an end date) are left untouched.

CSV format (one row per weekday):
  Col 1: start date in DD/MM/YYYY format (first occurrence of that weekday)
  Col 2: day name (Mon–Sun) — informational, not parsed
  Col 3+: on-call person name for week 1, week 2, … (blank = no coverage)

By default the script runs in dry-run mode and prints the planned changes
without touching PagerDuty.  Pass --apply to write the changes.

Usage:
  python update_rota.py rota.csv --schedule "My On-Call Schedule"
  python update_rota.py rota.csv --schedule PXXXXXXX
  python update_rota.py rota.csv --schedule PXXXXXXX --apply
"""

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

__version__ = "0.1.0"

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------------------------------------------------------------------------
# pd CLI wrappers
# ---------------------------------------------------------------------------


def _run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"\nERROR running: {' '.join(cmd)}", file=sys.stderr)
        print(r.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    return r.stdout.strip()


def pd_json(*args):
    out = _run(["pd"] + list(args))
    return json.loads(out) if out else {}


def pd_cmd(*args, check=True):
    return _run(["pd"] + list(args), check=check)


# ---------------------------------------------------------------------------
# User resolution
# ---------------------------------------------------------------------------


def build_user_index():
    """Return {lowercase_name: {"id": ..., "email": ..., "name": ...}}."""
    users = pd_json("user", "list", "--json")
    if not isinstance(users, list):
        sys.exit("ERROR: unexpected response from 'pd user list'")
    index = {}
    for u in users:
        full = u["name"]
        first = full.split()[0]
        entry = {"id": u["id"], "email": u["email"], "name": full}
        index[full.lower()] = entry
        if first.lower() not in index:  # full name takes precedence
            index[first.lower()] = entry
    return index


def resolve(name, index):
    """Resolve a CSV name to a user dict. Exits with a clear error if missing."""
    key = name.strip().lower()
    if key not in index:
        print(f"\nERROR: No PagerDuty user matches '{name}'", file=sys.stderr)
        known = {u["id"]: u for u in index.values()}
        print("Known users:", file=sys.stderr)
        for u in known.values():
            print(f"  {u['name']}  ({u['email']})", file=sys.stderr)
        sys.exit(1)
    return index[key]


# ---------------------------------------------------------------------------
# Schedule resolution and fetching
# ---------------------------------------------------------------------------


def resolve_schedule_id(ref):
    """Accept a PagerDuty schedule ID or a name substring."""
    if len(ref) == 7 and ref[0].upper() == "P":
        return ref.upper()
    schedules = pd_json("schedule", "list", "--json")
    if not isinstance(schedules, list):
        sys.exit("ERROR: unexpected response from 'pd schedule list'")
    matches = [s for s in schedules if ref.lower() in s["name"].lower()]
    if not matches:
        print(f"ERROR: No schedule matching '{ref}'", file=sys.stderr)
        for s in schedules:
            print(f"  {s['id']}  {s['name']}", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"WARNING: {len(matches)} schedules match '{ref}', using first:", file=sys.stderr)
        for s in matches:
            print(f"  {s['id']}  {s['name']}", file=sys.stderr)
    return matches[0]["id"]


def fetch_schedule(schedule_id):
    """Return the schedule dict from GET /schedules/{id}."""
    data = pd_json("rest", "get", "-e", f"/schedules/{schedule_id}")
    return data["schedule"]


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def _parse_date(date_str):
    """Parse a DD/MM/YYYY (or DD/MM) date string into a datetime.date."""
    parts = date_str.strip().split("/")
    if len(parts) == 3:
        day, month, year = map(int, parts)
        return datetime(year, month, day).date()
    if len(parts) == 2:
        day, month = map(int, parts)
        today = datetime.today().date()
        for year in (today.year, today.year + 1):
            d = datetime(year, month, day).date()
            if (d - today).days >= -7:
                return d
        return datetime(today.year + 1, month, day).date()
    sys.exit(f"ERROR: invalid date '{date_str}' — expected DD/MM/YYYY or DD/MM")


def parse_rota(path):
    """Return {weekday (0=Mon): {'date': first_date, 'names': [name, ...]}}."""
    rota = {}
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            date_str = row[0].strip()
            if not date_str:
                continue
            first_date = _parse_date(date_str)
            weekday = first_date.weekday()  # 0=Mon … 6=Sun
            names = [c.strip() for c in row[2:] if c.strip()]
            if names:
                rota[weekday] = {"date": first_date, "names": names}
    return rota


# ---------------------------------------------------------------------------
# Layer manipulation
# ---------------------------------------------------------------------------

_LAYER_FIELDS = {
    "id",
    "name",
    "start",
    "end",
    "users",
    "restrictions",
    "rotation_turn_length_seconds",
    "rotation_virtual_start",
}


def clean_layer(layer):
    """Strip computed/read-only fields before sending to the API."""
    return {k: v for k, v in layer.items() if k in _LAYER_FIELDS}


def make_virtual_start(first_date, existing_vstart, tz_name):
    """Return ISO-8601 string with first_date as the date and the existing Handoff Time preserved.

    The time-of-day portion of rotation_virtual_start (the "Handoff Time" shown in the
    PagerDuty UI) is kept exactly as configured in the layer.  Only the date is advanced
    to align with the first CSV occurrence of that weekday.
    """
    tz = ZoneInfo(tz_name)
    existing_dt = datetime.fromisoformat(existing_vstart).astimezone(tz)
    dt = datetime(
        first_date.year,
        first_date.month,
        first_date.day,
        existing_dt.hour,
        existing_dt.minute,
        existing_dt.second,
        tzinfo=tz,
    )
    return dt.isoformat()


def build_updated_layer(layer, names, user_index, first_date, tz_name):
    """Return a copy of the layer with the new user rotation, start date, and virtual start."""
    users = [
        {"user": {"id": resolve(n, user_index)["id"], "type": "user_reference"}} for n in names
    ]
    tz = ZoneInfo(tz_name)
    updated = dict(layer)
    updated["users"] = users
    updated["start"] = datetime(
        first_date.year, first_date.month, first_date.day, tzinfo=tz
    ).isoformat()
    updated["rotation_virtual_start"] = make_virtual_start(
        first_date, layer["rotation_virtual_start"], tz_name
    )
    return updated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(
        description="Sync a CSV rota to PagerDuty schedule layers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("csv", help="Path to rota CSV file")
    ap.add_argument(
        "--schedule", "-s", required=True, help="Schedule ID (e.g. PXXXXXXX) or name substring"
    )
    ap.add_argument(
        "--apply", action="store_true", help="Write changes to PagerDuty (default: dry-run only)"
    )
    args = ap.parse_args()

    # --- Mode banner ---------------------------------------------------------
    if args.apply:
        print("*** APPLY MODE — changes will be written to PagerDuty ***")
    else:
        print("*** DRY-RUN MODE — no changes will be written (pass --apply to apply) ***")
    print()

    # --- Parse CSV -----------------------------------------------------------
    print(f"Parsing {args.csv}...")
    rota = parse_rota(args.csv)
    if not rota:
        sys.exit("ERROR: No assignments found in CSV.")
    print(f"  Weekdays  : {', '.join(DAY_NAMES[wd] for wd in sorted(rota))}")
    for wd in sorted(rota):
        entry = rota[wd]
        print(f"  {DAY_NAMES[wd]:3s} ({entry['date']})  {entry['names']}")

    # --- Resolve schedule ----------------------------------------------------
    print("\nResolving schedule...")
    schedule_id = resolve_schedule_id(args.schedule)
    print(f"  Schedule ID: {schedule_id}")

    # --- Fetch schedule ------------------------------------------------------
    print("\nFetching schedule details...")
    schedule = fetch_schedule(schedule_id)
    tz_name = schedule["time_zone"]
    print(f"  Name       : {schedule['name']}")
    print(f"  Time zone  : {tz_name}")
    print(f"  Layers     : {len(schedule['schedule_layers'])}")

    # --- Fetch users ---------------------------------------------------------
    print("\nFetching PagerDuty users...")
    user_index = build_user_index()
    print(f"  Found {len({u['id'] for u in user_index.values()})} user(s).")

    # --- Categorise layers ---------------------------------------------------
    # Target layers: single restriction, not expired → will be updated.
    # Pass-through: fill layers (multi-restriction) or expired → left unchanged.
    target_ids = set()
    for layer in schedule["schedule_layers"]:
        is_expired = bool(layer.get("end"))
        is_single = len(layer.get("restrictions", [])) == 1
        if not is_expired and is_single:
            target_ids.add(layer["id"])

    # --- Build updated layer map ---------------------------------------------
    updates = {}  # layer_id → updated_layer dict
    warnings = []

    for layer in schedule["schedule_layers"]:
        if layer["id"] not in target_ids:
            continue
        pd_day = layer["restrictions"][0]["start_day_of_week"]
        weekday = pd_day - 1  # PD 1–7  →  Python 0–6
        day_name = DAY_NAMES[weekday]

        if weekday not in rota:
            warnings.append(
                f"  WARNING: No CSV data for {day_name} ('{layer['name']}') — left unchanged"
            )
            continue

        entry = rota[weekday]
        updates[layer["id"]] = build_updated_layer(
            layer, entry["names"], user_index, entry["date"], tz_name
        )

    # --- Print plan ----------------------------------------------------------
    print(f"\nPlan ({len(target_ids)} target layer(s), {len(updates)} to change):")
    for layer in schedule["schedule_layers"]:
        if layer["id"] not in updates:
            continue
        pd_day = layer["restrictions"][0]["start_day_of_week"]
        weekday = pd_day - 1
        day_name = DAY_NAMES[weekday]
        updated = updates[layer["id"]]

        old_names = [u["user"].get("summary", u["user"]["id"]) for u in layer["users"]]
        new_names = rota[weekday]["names"]
        old_start = layer["start"][:10]
        new_start = updated["start"][:10]
        old_vstart = layer["rotation_virtual_start"][:19]
        new_vstart = updated["rotation_virtual_start"][:19]
        old_turn = layer["rotation_turn_length_seconds"]
        new_turn = updated["rotation_turn_length_seconds"]

        print(f"\n  {day_name}  '{layer['name']}' ({layer['id']}):")
        print(f"    users      : {old_names}  →  {new_names}")
        if old_start != new_start:
            print(f"    start      : {old_start}  →  {new_start}")
        if old_vstart != new_vstart:
            print(f"    virt_start : {old_vstart}  →  {new_vstart}")
        if old_turn != new_turn:
            print(f"    turn_secs  : {old_turn}  →  {new_turn}")

    for w in warnings:
        print(w)

    # --- Apply or exit -------------------------------------------------------
    if not args.apply:
        print("\n[dry-run] No changes applied. Re-run with --apply to write to PagerDuty.")
        return

    confirm = input("\nApply these changes to PagerDuty? [y/N] ")
    confirm = "".join(c for c in confirm if c.isalpha()).lower()
    if confirm != "y":
        print("Aborted.")
        return

    # Build full schedule payload preserving original layer order
    all_layers = []
    for layer in schedule["schedule_layers"]:
        all_layers.append(clean_layer(updates.get(layer["id"], layer)))

    schedule_payload = {
        "schedule": {
            "name": schedule["name"],
            "time_zone": schedule["time_zone"],
            "description": schedule.get("description"),
            "schedule_layers": all_layers,
        }
    }

    print("\nUpdating schedule layers...")
    pd_cmd(
        "rest",
        "put",
        "-e",
        f"/schedules/{schedule_id}",
        "-d",
        json.dumps(schedule_payload),
    )
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)
