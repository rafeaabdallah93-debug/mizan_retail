#!/usr/bin/env bash
# Check a running edition after `up -d`:
#
#   deploy/verify.sh shop     deploy/.env [COMPOSE_PROJECT]
#   deploy/verify.sh shop-web deploy/.env [COMPOSE_PROJECT]
#
# Prints each check and ends with "ALL CHECKS PASSED" (exit 0) or the list of
# failed checks (exit 1). It creates one test branch and deletes it again; it
# changes nothing else. Run it from the mizan_retail folder.
set -u

EDITION="${1:-}"; ENV_FILE="${2:-}"; PROJECT="${3:-}"
case "$EDITION" in shop|shop-web) ;; *) echo "usage: $0 shop|shop-web ENV_FILE [COMPOSE_PROJECT]" >&2; exit 2 ;; esac
[ -f "$ENV_FILE" ] || { echo "env file not found: $ENV_FILE" >&2; exit 2; }

DEPLOY="$(cd "$(dirname "$0")" && pwd)"
env_value() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }
SITE="$(env_value SITE_NAME)"; COMPANY="$(env_value COMPANY)"
PORT="$(env_value HTTP_PORT)"; [ -n "$PORT" ] || { [ "$EDITION" = shop ] && PORT=8081 || PORT=8082; }

DC=(docker compose -f "$DEPLOY/editions/$EDITION.yaml" --env-file "$ENV_FILE")
[ -n "$PROJECT" ] && DC+=(-p "$PROJECT")
bench() { "${DC[@]}" exec -T backend bench --site "$SITE" "$@" 2>/dev/null | tail -1; }

FAILED=()
check() { # check <name> <expected> <actual>
  if [ "$2" = "$3" ]; then echo "ok    $1: $3"; else echo "FAIL  $1: expected '$2', got '$3'"; FAILED+=("$1"); fi
}

echo "== services"; "${DC[@]}" ps -a --format '{{.Service}}: {{.State}} {{.Status}}'
for _ in $(seq 1 30); do  # gunicorn may still be booting right after `up -d`
  ping="$(curl -s "http://localhost:$PORT/api/method/ping")"; [ "$ping" = '{"message":"pong"}' ] && break; sleep 2
done
check "ping" '{"message":"pong"}' "$ping"
check "login page" 200 "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/login")"
check "Mizan logo asset" 200 "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/assets/mizan_core/images/logo.svg")"
echo "== apps"; "${DC[@]}" exec -T backend bench --site "$SITE" list-apps 2>/dev/null
check "setup complete" true "$(bench execute frappe.is_setup_complete)"
check "exactly one company" 1 "$(bench execute frappe.db.count --args '["Company"]')"
check "company from env file" "$COMPANY" "$(bench execute frappe.db.exists --args "[\"Company\", \"$COMPANY\"]")"

# Mizan edition checks
check "System Settings app_name" Mizan "$(bench execute frappe.db.get_single_value --args '["System Settings", "app_name"]')"
check "Egypt VAT sales template" 1 "$(bench execute frappe.db.count --args '["Sales Taxes and Charges Template", {"title": "Egypt VAT", "is_default": 1, "disabled": 0}]')"
check "Egypt VAT purchase template" 1 "$(bench execute frappe.db.count --args '["Purchase Taxes and Charges Template", {"title": "Egypt VAT"}]')"
check "no GST account" 0 "$(bench execute frappe.db.count --args '["Account", {"account_name": ["like", "%GST%"]}]')"
check "no ERPNext Tax template" 0 "$(bench execute frappe.db.count --args '["Sales Taxes and Charges Template", {"title": "Egypt Tax"}]')"

branch="Verify Branch $(date +%s)"
args="{\"company\": \"$COMPANY\", \"branch_name\": \"$branch\"}"
created="$("${DC[@]}" exec -T backend bench --site "$SITE" execute mizan_retail.branches.create_branch --kwargs "$args" 2>&1 | tail -1)"
echo "create_branch -> $created"
case "$created" in *'"pos_profile"'*) created=ok ;; esac
check "create_branch" ok "$created"
if [ "$created" = ok ]; then
  pos="$(bench execute frappe.db.get_value --args "[\"POS Profile\", {\"warehouse\": [\"like\", \"$branch - %\"]}, \"taxes_and_charges\"]")"
  case "$pos" in *"Egypt VAT"*) pos=ok ;; esac
  check "branch till charges Egypt VAT" ok "$pos"
  bench execute mizan_retail.branches.delete_branch --kwargs "$args" >/dev/null
  check "test branch deleted" 0 "$(bench execute frappe.db.count --args "[\"Warehouse\", {\"warehouse_name\": \"$branch\"}]")"
fi

if [ "${#FAILED[@]}" -eq 0 ]; then echo "ALL CHECKS PASSED"; exit 0; fi
echo "FAILED: ${FAILED[*]}"; exit 1
