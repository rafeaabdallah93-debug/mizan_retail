#!/usr/bin/env bash
# Restore a backup made by deploy/backup.sh into a running Mizan shop.
# WARNING: this REPLACES everything currently in the shop with the backup.
#
#   deploy/restore.sh shop      deploy/backups/<date-time> [ENV_FILE]
#   deploy/restore.sh shop-web  deploy/backups/<date-time> [ENV_FILE]
#
# The shop must be started first (docker compose ... up -d) and use the same
# edition as the backup (a shop-web backup needs the shop-web edition).
set -euo pipefail
EDITION="${1:?usage: $0 shop|shop-web BACKUP_FOLDER [ENV_FILE]}"
SRC="${2:?usage: $0 shop|shop-web BACKUP_FOLDER [ENV_FILE]}"
DEPLOY="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${3:-$DEPLOY/.env}"
COMPOSE_FILE="$DEPLOY/editions/$EDITION.yaml"
[ -f "$COMPOSE_FILE" ] || { echo "Unknown edition '$EDITION'" >&2; exit 2; }
getenv() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }
SITE="$(getenv SITE_NAME)"
DC=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")
[ -n "${COMPOSE_PROJECT_NAME:-}" ] && DC+=(-p "$COMPOSE_PROJECT_NAME")

# First file in the backup folder matching a pattern ($1 is a glob on purpose).
# shellcheck disable=SC2086
one() { local f; for f in "$SRC"/$1; do if [ -f "$f" ]; then basename "$f"; return 0; fi; done; return 1; }
DB_FILE="$(one '*-database.sql.gz')" || { echo "No *-database.sql.gz in $SRC" >&2; exit 1; }
PUB="$(one '*-files.tar' || true)"
PRIV="$(one '*-private-files.tar' || true)"
CONF="$(one '*-site_config_backup.json' || true)"

read -r -p "This replaces ALL data of $SITE with the backup in $SRC. Type YES to continue: " ok
[ "$ok" = "YES" ] || { echo "Cancelled."; exit 1; }

TMP="/tmp/mizan-restore-$$"
"${DC[@]}" exec -T backend mkdir -p "$TMP"
"${DC[@]}" cp "$SRC/." "backend:$TMP/"
# Backup files are private (mode 600, owned by you); let the bench user read the copies.
"${DC[@]}" exec -T -u root backend chown -R frappe "$TMP"
args=(--db-root-username root --db-root-password "$(getenv DB_ROOT_PASSWORD)" --force)
[ -n "$PUB" ] && args+=(--with-public-files "$TMP/$PUB")
[ -n "$PRIV" ] && args+=(--with-private-files "$TMP/$PRIV")
"${DC[@]}" exec -T backend bench --site "$SITE" restore "$TMP/$DB_FILE" "${args[@]}"
# Saved passwords (e.g. the WooCommerce API secret) are encrypted with the
# site's key: bring back the key that was in use when the backup was made.
if [ -n "$CONF" ]; then
  KEY="$("${DC[@]}" exec -T backend jq -r '.encryption_key // empty' "$TMP/$CONF")"
  [ -n "$KEY" ] && "${DC[@]}" exec -T backend bench --site "$SITE" set-config encryption_key "$KEY"
fi
"${DC[@]}" exec -T backend bench --site "$SITE" migrate
"${DC[@]}" exec -T backend bench --site "$SITE" enable-scheduler
"${DC[@]}" exec -T backend rm -rf "$TMP"
"${DC[@]}" restart backend websocket queue-short queue-long scheduler frontend
echo "Restored $SITE from $SRC"
