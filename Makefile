.PHONY: help install uninstall preview apply lint fmt check check-prereqs

SCRIPT   := update_rota.py
TARGET   := $(HOME)/.local/bin/pd-rota-update
ROTA     ?= rota.csv
SCHEDULE ?= $(error SCHEDULE is required — e.g.: make preview SCHEDULE="My Schedule")

# ── Help (default) ────────────────────────────────────────────────────────────

.DEFAULT_GOAL := help

help:
	@echo "pd-rota-update — sync a CSV rota to PagerDuty schedule layers"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "  check-prereqs  Verify Python 3.9+ and pd CLI are available"
	@echo "  install    Copy $(SCRIPT) to $(TARGET)"
	@echo "  uninstall  Remove $(TARGET)"
	@echo "  preview    Preview changes without applying (requires SCHEDULE=)"
	@echo "  apply      Apply changes to PagerDuty (requires SCHEDULE=)"
	@echo "  lint       Run ruff check (report issues)"
	@echo "  fmt        Run ruff format (fix formatting in place)"
	@echo "  check      Run lint + format check without modifying files (CI)"
	@echo ""
	@echo "Examples:"
	@echo "  make preview SCHEDULE=\"My On-Call Schedule\""
	@echo "  make apply   SCHEDULE=PXXXXXXX ROTA=rota.csv"
	@echo ""

# ── Prerequisites check ───────────────────────────────────────────────────────

check-prereqs:
	@python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null || \
		{ echo "ERROR: Python 3.9+ is required. Found: $$(python3 --version 2>&1 || echo 'not installed')"; exit 1; }
	@command -v pd >/dev/null 2>&1 || \
		{ echo "ERROR: 'pd' (pagerduty-cli) is not installed."; \
		  echo "       Fix: npm install -g pagerduty-cli"; exit 1; }
	@echo "Prerequisites OK (python3=$$(python3 --version), pd=$$(pd --version 2>/dev/null || echo 'ok'))"

# ── Installation ─────────────────────────────────────────────────────────────

install: check-prereqs
	@mkdir -p $(dir $(TARGET))
	install -m 755 $(SCRIPT) $(TARGET)
	@echo "Installed → $(TARGET)"

uninstall:
	rm -f $(TARGET)
	@echo "Removed $(TARGET)"

# ── Run ───────────────────────────────────────────────────────────────────────

preview:
	python3 $(SCRIPT) $(ROTA) --schedule "$(SCHEDULE)"

apply:
	python3 $(SCRIPT) $(ROTA) --schedule "$(SCHEDULE)" --apply

# ── Linting / formatting ─────────────────────────────────────────────────────

lint:
	ruff check $(SCRIPT)

fmt:
	ruff format $(SCRIPT)

# CI-safe: check lint and formatting without modifying files
check:
	ruff check $(SCRIPT)
	ruff format --check $(SCRIPT)
