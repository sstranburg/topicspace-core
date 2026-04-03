#!/bin/bash
# Daily crypto event fetch — run via cron at 7:00 AM.
# Fetches yesterday's CryptoPanic news + Reddit formation signals
# and appends (with dedup) to crypto_ecosystem.jsonl.
#
# Cron entry (add with: crontab -e):
#   0 7 * * * /Users/sue/Documents/git/storm/scripts/cron_crypto_daily.sh

set -e

STORM_DIR="/Users/sue/Documents/git/storm"
PYTHON="$STORM_DIR/venv/bin/python"
LOG_DIR="$STORM_DIR/logs"
LOG_FILE="$LOG_DIR/crypto_fetch_$(date +%Y-%m-%d).log"

mkdir -p "$LOG_DIR"

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) crypto fetch ===" >> "$LOG_FILE"

"$PYTHON" "$STORM_DIR/scripts/fetch_crypto.py" >> "$LOG_FILE" 2>&1

echo "Done." >> "$LOG_FILE"
