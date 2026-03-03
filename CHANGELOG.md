# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] — 2026-03-04

### Fixed

- `resolve_schedule_id`: replaced the fragile length+first-char heuristic with
  a strict `re.fullmatch(r"P[A-Z0-9]{6}", ...)` check, preventing 7-character
  schedule names starting with "P" from being misidentified as IDs.
- `_parse_date`: `ValueError` from `datetime()` (e.g. `32/13/2026`) is now
  caught and reported as a clean `sys.exit` error instead of a Python traceback.
- `parse_rota`: duplicate weekday rows in the CSV (same weekday appearing twice)
  now exit immediately with a clear error naming both conflicting dates, instead
  of silently overwriting the first row with the second.
- `fetch_schedule`: added a guard on the `"schedule"` key before accessing the
  API response, preventing an unhandled `KeyError` on unexpected responses.
- `parse_rota`: CSV files are now opened with `encoding="utf-8-sig"`, correctly
  handling UTF-8 BOM headers produced by Excel and similar tools.
- `pd_json`: `json.JSONDecodeError` is now caught; the error message includes
  the raw CLI output (first 200 chars) to aid diagnosis.
- `build_user_index`: service accounts and bot users with an empty or missing
  `name` field are now skipped instead of causing an `IndexError` or `KeyError`.
- `make_virtual_start`: the `fold` attribute of the existing handoff datetime is
  now preserved when constructing the new `rotation_virtual_start`, ensuring the
  correct UTC offset is chosen for dates that fall during a DST transition.

## [0.1.0] — 2026-03-03

### Added

- CSV rota parser supporting `DD/MM/YYYY` and `DD/MM` date formats, with
  automatic year inference and December → January year-boundary handling.
- PagerDuty schedule layer sync: identifies weekday layers by single-day
  restriction and replaces their user rotation from the CSV.
- Fill layer and expired layer detection: layers with multiple day restrictions
  or an `end` date are left completely untouched.
- User resolution by first name or full name (case-insensitive) against the
  PagerDuty account.
- Schedule lookup by name substring or direct schedule ID (`PXXXXXXX`).
- `rotation_virtual_start` date advancement: only the date portion is updated;
  the Handoff Time (time-of-day) configured in the PagerDuty UI is preserved.
- `rotation_turn_length_seconds` preserved unchanged (managed via PagerDuty UI).
- Dry-run mode by default: resolves users and prints the full plan without
  writing anything to PagerDuty.
- `--apply` flag to write changes; prompts for explicit confirmation before
  making any API call.
- Runtime mode banner clearly indicating dry-run or apply mode.
- Clean Ctrl-C handling: prints `Aborted.` and exits with code 1.
- `--version` flag reporting the current version.
- Makefile targets: `install`, `uninstall`, `preview`, `apply`, `lint`, `fmt`,
  `check`, `check-prereqs`.
- `make check-prereqs` verifies Python 3.9+ and the `pd` CLI are available,
  printing a clear error and the fix command if either is missing.
- `make install` runs `check-prereqs` first and aborts if any prerequisite is
  absent, preventing a broken installation.
- `rota_template.csv` as a committed structural reference with placeholder names.
- `.gitignore` rule excluding all `*.csv` files except `rota_template.csv`,
  keeping live rota data out of version control.
- MIT licence.
