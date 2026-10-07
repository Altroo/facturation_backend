#!/usr/bin/env bash
set -euo pipefail
# Execute on the server; prepare by default. Apps run sequentially.
phase="${1:-prepare}"
case "$phase" in prepare|apply|rollback) ;; *) echo "Usage: $0 [prepare|apply|rollback] [journal-directory]" >&2; exit 2;; esac
report_dir="${2:-/var/lib/ebh-ai-corrections}"
mkdir -p "$report_dir"
chmod 700 "$report_dir"
# All five application images run as appuser (UID/GID 1000).
chown 1000:1000 "$report_dir"
for app in management_projet facturation contracts reservation gestion_magasin; do
  printf '\n%s : %s\n' "$app" "$phase"
  phase_args=()
  if [ "$phase" != prepare ]; then phase_args+=("--$phase"); fi
  docker compose --project-directory "/var/www/${app}_backend" run --rm --no-deps \
    -v "$report_dir:/ai-corrections" web \
    python manage.py ai_correct_texts --journal "/ai-corrections/$app.jsonl" "${phase_args[@]}"
done
