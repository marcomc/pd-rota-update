# Agent instructions — pd-rota-update

This file teaches AI agents (Claude, Codex, etc.) how to work with this project.

---

## Project overview

`pd-rota-update` reads a CSV rota file and syncs it to a PagerDuty schedule as
layer updates. The main script is `update_rota.py`; the active rota is `rota.csv`
(git-ignored); the committed structural reference is `rota_template.csv`.

---

## Installation

### Prerequisites

- Python ≥ 3.9
- Node.js + `pagerduty-cli` authenticated with your PagerDuty account

```bash
npm install -g pagerduty-cli
pd auth web          # browser OAuth flow (or: pd auth add --token <TOKEN>)
```

### Option A — install as a system command (recommended)

```bash
make install         # copies update_rota.py to ~/.local/bin/pd-rota-update
```

Ensure `~/.local/bin` is on your `PATH`, then invoke from anywhere:

```bash
pd-rota-update rota.csv --schedule "My On-Call Schedule"
```

### Option B — run directly from the project directory

```bash
python update_rota.py rota.csv --schedule "My On-Call Schedule"
# or via make:
make preview SCHEDULE="My On-Call Schedule"
make apply   SCHEDULE="My On-Call Schedule"
```

### Verify the installation

```bash
pd-rota-update --version
```

---

## Invocation reference

```text
pd-rota-update <csv> --schedule <id-or-name> [--apply]

positional:
  csv              Path to rota CSV file

required:
  -s, --schedule   Schedule ID (e.g. PXXXXXXX) or name substring

options:
  --apply          Write changes to PagerDuty (default: dry-run only)
  --version        Print version and exit
  -h, --help       Show help
```

**Typical workflow:**

```bash
# 1. Preview — prints the plan, nothing is written
pd-rota-update rota.csv --schedule "My On-Call Schedule"

# 2. Apply — prompts for confirmation, then writes to PagerDuty
pd-rota-update rota.csv --schedule "My On-Call Schedule" --apply
```

---

## User-facing prompt (copy-paste to start a session)

When a user wants to convert a rota image and apply it to PagerDuty, they
should paste the following into a Claude Code session alongside the image:

```text
I'm attaching a screenshot of our on-call rota.
Please convert it to rota.csv following the instructions in AGENTS.md,
do a dry-run so I can review the changes, and — after my confirmation —
apply them to PagerDuty.

PagerDuty schedule name: <YOUR SCHEDULE NAME>
```

The agent will then execute the full end-to-end workflow described below.

---

## End-to-end workflow (for agents)

When triggered by the user prompt above, execute these steps in order:

1. **Determine today's date** — read the `currentDate` value from the system
   context (available in Claude Code sessions). If it is not available, run
   `date +%d/%m/%Y` in the shell. Use this date for all year-inference logic.

2. **Convert the image to CSV** — follow the detailed instructions in the
   section below. Write the result to `rota.csv` in the project directory.

3. **Preview** — run the script (dry-run by default) and show the output to the
   user:

   ```bash
   python update_rota.py rota.csv --schedule "<schedule>"
   ```

4. **Wait for confirmation** — do not apply until the user explicitly approves
   the preview output.

5. **Apply** — once confirmed, run:

   ```bash
   python update_rota.py rota.csv --schedule "<schedule>" --apply
   ```

---

## How to convert a rota table image to CSV

### Step 0 — Identify the image layout

Rota spreadsheets come in two orientations. Identify which one you have before
extracting data.

**Layout A — rows are weekdays** (this is already the target CSV format):

| date DD/MM/YYYY | day | W1      | W2      | W3      | … |
|-----------------|-----|---------|---------|---------|---|
| 09/03/2026      | Mon | Person1 | Person2 | Person3 | … |
| 10/03/2026      | Tue | Person2 | Person3 | Person1 | … |

**Layout B — columns are weekdays** (requires transposing to Layout A):

|        | Mon     | Tue     | Wed     | … |
|--------|---------|---------|---------|---|
| 09/03  | Person1 | Person2 | Person3 | … |
| 16/03  | Person2 | Person3 | Person1 | … |

Row 1 of Layout B contains the date of the first occurrence of each weekday.
Row 2 contains the day name. Subsequent rows are weekly assignments.

**The CSV output is always Layout A, regardless of the image orientation.**
If the image is Layout B, transpose it: each column becomes a row, with the
column's date in col 1 and the column's day name in col 2.

### Step 1 — Read the target CSV structure

One row per weekday:

| col 1        | col 2    | col 3 | col 4 | col 5 | col 6 | … |
|--------------|----------|-------|-------|-------|-------|---|
| DD/MM/YYYY   | day name | W1    | W2    | W3    | W4    | … |

- **Column 1**: the calendar date of the first occurrence of that weekday,
  written as `DD/MM/YYYY` (e.g. `09/03/2026`).
- **Column 2**: the day name (`Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`, `Sun`).
- **Columns 3 onwards**: the person on call for week 1, week 2, week 3, …
  A blank cell means no override for that slot.

### Step 2 — Apply date and year rules

- **Always write dates as `DD/MM/YYYY`** — never omit the year.
- **Default year is the current calendar year** (determined in Step 0) unless
  the image or the user specifies otherwise.
- **December → January crossings**: if the rota spans the year boundary,
  December dates use the *current* year and January dates use *next* year.
  Each date is evaluated independently, so this happens automatically.

Example: a rota running from 29/12 to 05/01 (current year = 2026):

```csv
29/12/2026,Mon,…
30/12/2026,Tue,…
31/12/2026,Wed,…
01/01/2027,Thu,…
```

### Step 3 — Output rules

- Write the CSV to `rota.csv` in the project directory.
- Include **no header row**.
- Use the **name exactly as it appears in the image**. Full names are preferred
  over first names as they are unambiguous when two people share a first name.
  First names alone are also accepted by the script.
- Preserve the exact column count: if the longest row has 7 values, all rows
  must have 7 values (pad with trailing commas for shorter rows).
- Use Unix line endings (`\n`).
- Use `rota_template.csv` as the structural reference for column layout.

### Step 4 — Example (Layout B image → Layout A CSV)

Given a Layout B image (current year = 2026):

```text
|       | Mon     | Tue     | Wed     | Thu     | Fri     | Sat     | Sun     |
| 09/03 | Person1 | Person3 | Person1 | Person3 | Person1 | Person3 | Person1 |
| 16/03 | Person2 | Person1 | Person2 | Person1 | Person2 | Person2 | Person1 |
| 23/03 | Person2 | Person3 | Person2 | Person3 | Person2 | Person3 | Person2 |
| 30/03 | Person3 | Person1 | Person3 | Person1 | Person3 | Person1 | Person3 |
| 06/04 | Person1 | Person2 | Person1 |         |         |         |         |
```

Each column becomes a row; the column header date goes into col 1:

```csv
09/03/2026,Mon,Person1,Person2,Person2,Person3,Person1
10/03/2026,Tue,Person3,Person1,Person3,Person1,Person2
11/03/2026,Wed,Person1,Person2,Person2,Person3,Person1
12/03/2026,Thu,Person3,Person1,Person3,Person1,
13/03/2026,Fri,Person1,Person2,Person2,Person3,
14/03/2026,Sat,Person3,Person2,Person3,Person1,
15/03/2026,Sun,Person1,Person1,Person2,Person3,
```

### Step 5 — Common pitfalls

- **Identify the layout first.** Do not assume the image is already Layout A.
- **Always transpose Layout B to Layout A** before writing the CSV.
- **Do not invent data** for blank cells. Use an empty field (trailing comma).
- **Always include the year** — `DD/MM/YYYY`, not `DD/MM`.
- **Do not hardcode a year** — always derive it from today's date (Step 0).
- Cell background colours are decorative and should be ignored.

---

## Keeping personal information out of version control

This project is designed so that no personal or organisational data is ever
committed to the repository.

| What                             | How it is kept private              |
|----------------------------------|-------------------------------------|
| Real names in the rota           | `rota.csv` is git-ignored (`*.csv`) |
| Schedule IDs and account details | Never appear in committed files     |
| API tokens / OAuth credentials   | Stored by `pd` CLI, not in the repo |

**Rules for agents to follow:**

- **Never write `rota.csv` content into committed files.** It contains
  real team members' names.
- **Never add real names, emails, schedule IDs, or subdomain names**
  to `README.md`, `AGENTS.md`, or any other tracked file. Use
  `Person1` / `Person2` / `PXXXXXXX` as stand-ins in all examples.
- **Never expose API tokens.** The `pd` CLI stores credentials in its
  own config. Do not echo or log token values.
- **Treat command output with care.** Commands like `pd schedule list`
  and `pd user list` return real names and IDs. Never paste that
  output into committed files or chat history that may be logged.

The `.gitignore` enforces the CSV rule automatically. All other rules
above are conventions that agents must follow manually.

---

## Key files

| File                | Purpose                                          |
|---------------------|--------------------------------------------------|
| `update_rota.py`    | Main script — parses CSV, updates PagerDuty      |
| `rota.csv`          | Active rota (git-ignored, regenerate from image) |
| `rota_template.csv` | Committed template with placeholder names        |
| `Makefile`          | `make install` / `make lint` / `make fmt`        |
| `pyproject.toml`    | Ruff linting config                              |
| `README.md`         | Full usage docs                                  |

---

## CSV format reference (for parsing `rota.csv`)

```python
parse_rota(path) -> dict[int, dict]
# Returns: {weekday (0=Mon … 6=Sun): {"date": first_date, "names": [name, ...]}}
```

- Row structure: `DD/MM/YYYY, DayName, PersonWeek1, PersonWeek2, …`
- `date` is a `datetime.date` parsed from the `DD/MM/YYYY` field; it is the
  first occurrence of that weekday (used to set the layer's
  `rotation_virtual_start`).
- `names` is the ordered list of on-call persons across the weeks.
- Each `name` is matched against PagerDuty users by first or full name
  (case-insensitive) inside `build_user_index()`.
- `DD/MM` (without year) is also accepted for backward compatibility; the year
  is then inferred using the same current-year-default rules described above.
