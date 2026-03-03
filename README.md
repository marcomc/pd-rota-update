# pd-rota-update

Sync a weekly on-call rota from a CSV file to a PagerDuty schedule as layer
updates.

## How it works

The script reads the CSV and updates the **rotation layers** of the target
PagerDuty schedule directly. It expects the schedule to have one layer per
weekday (Mon–Sun), each restricted to a single day of the week. For each of
those seven layers the script:

1. Identifies the layer by its single-day restriction.
2. Replaces the `users` list with the ordered assignments from the CSV.
3. Advances the **date** part of `rotation_virtual_start` to the first
   occurrence of that weekday in the CSV, while **preserving the time-of-day**
   (the "Handoff Time" shown in the PagerDuty UI) exactly as configured in the
   layer. This keeps the moment of handoff unchanged.
4. Leaves `rotation_turn_length_seconds` (the cadence at which the rotation
   advances) completely unchanged. If it needs to be adjusted it should be done
   from the PagerDuty web UI.

The "fill" layer (the one that covers Mon–Fri daytime with multiple restrictions)
and any expired layers are left completely untouched. Running the script twice
with the same CSV is safe and idempotent.

## Requirements

- Python ≥ 3.9 (no extra packages — stdlib only)
- Node.js (for `pagerduty-cli`)

```bash
npm install -g pagerduty-cli
```

## PagerDuty authentication

The `pd` CLI must be authenticated before running this script.
Two methods are available.

### Option A — Browser login (recommended)

Opens a PagerDuty OAuth flow in your browser. Tokens are managed
automatically.

```bash
pd auth web      # opens browser, saves token
pd auth list     # verify — shows subdomain, email, type
```

### Option B — API token

Use this when a browser is not available (CI, servers, shared accounts).

**Get a token in the PagerDuty web UI:**

1. Log in to your PagerDuty account.
2. Click your avatar (top right) → **My Profile**.
3. Go to the **User Settings** tab.
4. Under **API Access**, click **Create New API User Token**.
5. Give it a description (e.g. `pd-rota-update`) and copy the token
   — it is shown only once.

> If you need an account-level token (admin), go to
> **Configuration → API Access Keys** instead.

**Register the token with the CLI:**

```bash
pd auth add --token YOUR_TOKEN --alias myaccount
pd auth list     # verify — shows subdomain, email, type
```

To switch between saved accounts at any time:

```bash
pd auth list                    # show all saved accounts
pd auth use --alias myaccount   # activate one
```

## Installation

```bash
make install        # copies pd-rota-update to ~/.local/bin
```

Afterwards you can call it from anywhere:

```bash
pd-rota-update rota.csv --schedule "My On-Call Schedule"
```

## CSV format

One row per weekday, exported directly from your spreadsheet:

| col 1            | col 2 | col 3   | col 4   | col 5   | col 6   | …  |
|------------------|-------|---------|---------|---------|---------|----|
| `09/03/2026`     | Mon   | Person1 | Person2 | Person2 | Person3 | …  |
| `10/03/2026`     | Tue   | Person3 | Person1 | Person3 | Person1 | …  |
| …                | …     | …       | …       | …       | …       | …  |

- **Col 1** — date (`DD/MM/YYYY`) of the first occurrence of that weekday
- **Col 2** — day name (`Mon`–`Sun`), informational only, not parsed
- **Col 3 onwards** — person name for week 1, week 2, … (blank = no override)

Person names are matched against your PagerDuty account by first or full name
(case-insensitive). No names are hardcoded.

The default year is the current calendar year. When a rota spans
December → January, December keeps the current year and January becomes
next year automatically.

See [`rota_template.csv`](rota_template.csv) for the column layout reference.

## Usage

```text
pd-rota-update <csv> --schedule <id-or-name> [options]

positional:
  csv                     Path to rota CSV file

required:
  -s, --schedule          Schedule ID (e.g. PXXXXXXX) or name substring

options:
  --apply                 Write changes to PagerDuty (default: dry-run only)
  -h, --help              Show help
```

### Examples

```bash
# Preview changes (default — nothing is written to PagerDuty)
pd-rota-update rota.csv --schedule "Engineering On-Call"

# Apply after reviewing the preview
pd-rota-update rota.csv --schedule "Engineering On-Call" --apply

# Use schedule ID directly
pd-rota-update rota.csv --schedule PXXXXXXX --apply
```

## Generating the CSV from a spreadsheet image

If you have a screenshot of the rota table, you can use Claude (or another
multimodal AI) to extract it directly. See [`AGENTS.md`](AGENTS.md) for the
exact prompt to use.

## Finding your schedule name or ID

Before running the script you need to know the name or ID of the PagerDuty
schedule to update. List all available schedules with:

```bash
pd schedule list
```

The output shows each schedule's ID and name, for example:

```text
 ID      Name
 ─────── ────────────────────
 PXXXXXXX  My On-Call Schedule
 PYYYYYYY  Second Line Support
```

Pass either value to `--schedule`:

```bash
pd-rota-update rota.csv --schedule "My On-Call Schedule"
pd-rota-update rota.csv --schedule PXXXXXXX
```

> **Note:** `pd schedule list` output contains real schedule names and IDs.
> Do not paste it into committed files — see [`AGENTS.md`](AGENTS.md) for
> the privacy rules.

## Testing without affecting live schedules

### Level 1 — preview (safest, no PagerDuty changes)

Running the script without `--apply` always performs a dry-run: it resolves
users, computes all layer changes, and prints the full plan without writing
anything to PagerDuty:

```bash
pd-rota-update rota.csv --schedule "My On-Call Schedule"
```

Use this to verify the CSV is parsed correctly and names are matched before
committing to any changes.

### Level 2 — test against a throwaway schedule copy

If you want to exercise the actual PagerDuty API calls end-to-end, clone
a real schedule first:

```bash
pd schedule copy --name "My On-Call Schedule" --destination "TEST - My On-Call Schedule"
```

Then run the script against the copy:

```bash
pd-rota-update rota.csv --schedule "TEST - My On-Call Schedule" --apply
```

Inspect the result in the PagerDuty web UI. When done, delete the test
schedule manually via **Configuration → Schedules → (schedule) → Delete**.

> **Note:** The cloned schedule has the same layer structure as the original,
> so it is a faithful test target. Changes to the clone do not affect the
> original schedule or its users.

## Development

```bash
make lint       # ruff check
make fmt        # ruff format
make check      # lint + format check (CI-safe)
```
