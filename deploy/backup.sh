#!/usr/bin/env bash
# Back up a running Mizan shop: database, uploaded files and the site's keys.
#
#   deploy/backup.sh shop      [ENV_FILE]     (ENV_FILE defaults to deploy/.env)
#   deploy/backup.sh shop-web  [ENV_FILE]
#
# The backup lands in deploy/backups/<date-time>/ on this computer. Copy that
# folder somewhere safe (USB disk, another computer, cloud drive). It contains
# all your business data and the site's secret key: keep it private.
set -euo pipefail
EDITION="${1:?usage: $0 shop|shop-web [ENV_FILE]}"
DEPLOY="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${2:-$DEPLOY/.env}"
COMPOSE_FILE="$DEPLOY/editions/$EDITION.yaml"
[ -f "$COMPOSE_FILE" ] || { echo "Unknown edition '$EDITION'" >&2; exit 2; }
SITE="$(grep -E '^SITE_NAME=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
DC=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")
[ -n "${COMPOSE_PROJECT_NAME:-}" ] && DC+=(-p "$COMPOSE_PROJECT_NAME")

STAMP="$(date +%Y%m%d-%H%M%S)"
TMP="/tmp/mizan-backup-$STAMP"
DEST="$DEPLOY/backups/$STAMP"

"${DC[@]}" exec -T backend bench --site "$SITE" backup --with-files --backup-path "$TMP"
mkdir -p "$DEST"; chmod 700 "$DEST"
"${DC[@]}" cp "backend:$TMP/." "$DEST/"
"${DC[@]}" exec -T backend rm -rf "$TMP"
echo
echo "Backup saved in: $DEST"
ls -l "$DEST"
