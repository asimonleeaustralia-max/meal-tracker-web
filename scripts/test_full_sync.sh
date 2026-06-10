#!/usr/bin/env bash
# End-to-end iOS sync smoke test (Stages 1–5).
#
# Prerequisites: docker compose up (gateway on :8080).
#
# Usage:
#   ./scripts/test_full_sync.sh
#   BASE_URL=http://192.168.1.42:8080 ./scripts/test_full_sync.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
EMAIL="${TEST_EMAIL:-sync-test-$(date +%s)@example.com}"
PASS="${TEST_PASSWORD:-TestPass123!}"
SINCE="${SINCE_CURSOR:-2026-01-01T00:00:00Z}"

MEAL_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
PERSON_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
PHOTO_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "OK: $*"; }

echo "==> Base URL: ${BASE_URL}"

# --- Stage 1: Auth ---
echo ""
echo "==> Stage 1: signup + login"
SIGNUP=$(curl -sf -X POST "${BASE_URL}/api/auth/signup" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASS}\",\"client\":\"ios\"}") \
  || fail "signup failed"
AT=$(echo "$SIGNUP" | jq -r '.access_token // empty')
[[ -n "$AT" ]] || fail "no access_token from signup"
ME=$(curl -sf "${BASE_URL}/api/auth/me" -H "Authorization: Bearer ${AT}") \
  || fail "/api/auth/me failed"
echo "$ME" | jq -e '.id' >/dev/null || fail "me response missing id"
ok "Stage 1 — authenticated as ${EMAIL}"

# --- Stage 2: People ---
echo ""
echo "==> Stage 2: people bootstrap + PUT"
PEOPLE=$(curl -sf "${BASE_URL}/api/people" -H "Authorization: Bearer ${AT}") \
  || fail "GET /api/people failed"
DEFAULT_PERSON=$(echo "$PEOPLE" | jq -r '.[0].id // empty')
[[ -n "$DEFAULT_PERSON" ]] || fail "no default person from bootstrap"
curl -sf -X PUT "${BASE_URL}/api/people/${PERSON_ID}" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${AT}" \
  -d '{"name":"Sync Test","is_default":false,"is_removed":false}' >/dev/null \
  || fail "PUT /api/people failed"
ok "Stage 2 — default person ${DEFAULT_PERSON}, created ${PERSON_ID}"

# --- Stage 3: Meals ---
echo ""
echo "==> Stage 3: meal PUT"
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
curl -sf -X PUT "${BASE_URL}/api/meals/${MEAL_ID}" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${AT}" \
  -d "{\"title\":\"Sync smoke meal\",\"date\":\"${NOW}\",\"person_id\":\"${DEFAULT_PERSON}\",\"calories\":100}" \
  >/dev/null || fail "PUT /api/meals failed"
ok "Stage 3 — meal ${MEAL_ID}"

# --- Stage 4: Photos (metadata PUT) ---
echo ""
echo "==> Stage 4: photo metadata PUT"
curl -sf -X PUT "${BASE_URL}/api/photos/${PHOTO_ID}" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${AT}" \
  -d "{\"meal_id\":\"${MEAL_ID}\",\"width\":100,\"height\":100,\"display_order\":0}" \
  >/dev/null || fail "PUT /api/photos failed"
ok "Stage 4 — photo ${PHOTO_ID}"

# --- Stage 5: Unified incremental pull ---
echo ""
echo "==> Stage 5: GET /api/sync/changes?since=${SINCE}"
SYNC=$(curl -sf "${BASE_URL}/api/sync/changes?since=${SINCE}" \
  -H "Authorization: Bearer ${AT}") || fail "GET /api/sync/changes failed"
SUMMARY=$(echo "$SYNC" | jq '{meal_count:(.meals|length), people_count:(.people|length), photo_count:(.photos|length), server_time}')
echo "$SUMMARY"
MEAL_COUNT=$(echo "$SUMMARY" | jq -r '.meal_count')
PEOPLE_COUNT=$(echo "$SUMMARY" | jq -r '.people_count')
PHOTO_COUNT=$(echo "$SUMMARY" | jq -r '.photo_count')
SERVER_TIME=$(echo "$SUMMARY" | jq -r '.server_time')
[[ "$MEAL_COUNT" -ge 1 ]] || fail "expected meals in sync response"
[[ "$PEOPLE_COUNT" -ge 1 ]] || fail "expected people in sync response"
[[ "$PHOTO_COUNT" -ge 1 ]] || fail "expected photos in sync response"
[[ "$SERVER_TIME" != "null" && -n "$SERVER_TIME" ]] || fail "missing server_time"
ok "Stage 5 — single endpoint returned all entity types (meals=${MEAL_COUNT}, people=${PEOPLE_COUNT}, photos=${PHOTO_COUNT})"

echo ""
echo "All stages passed."
