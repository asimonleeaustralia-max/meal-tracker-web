#!/usr/bin/env bash
# Auth smoke test — signup, login, me, refresh against the API gateway.
#
# Prerequisites: docker compose up (gateway on :8080).
#
# Usage:
#   ./scripts/smoke-test-auth.sh
#   BASE_URL=http://192.168.1.42:8080 ./scripts/smoke-test-auth.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
EMAIL="smoke-$(date +%s)-$RANDOM@example.com"
PASS="TestPass123!"

fail() { echo "FAIL: $*" >&2; exit 1; }

SIGNUP=$(curl -sf -X POST "${BASE_URL}/api/auth/signup" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASS}\",\"client\":\"ios\"}") \
  || fail "POST /api/auth/signup failed"
echo "$SIGNUP" | jq -e '.access_token' >/dev/null || fail "signup response missing access_token"

LOGIN=$(curl -sf -X POST "${BASE_URL}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASS}\",\"client\":\"ios\"}") \
  || fail "POST /api/auth/login failed"
AT=$(echo "$LOGIN" | jq -r '.access_token // empty')
RT=$(echo "$LOGIN" | jq -r '.refresh_token // empty')
[[ -n "$AT" && -n "$RT" ]] || fail "login response missing tokens"

ME=$(curl -sf "${BASE_URL}/api/auth/me" -H "Authorization: Bearer ${AT}") \
  || fail "GET /api/auth/me failed"
echo "$ME" | jq -e '.id' >/dev/null || fail "me response missing id"

REFRESH=$(curl -sf -X POST "${BASE_URL}/api/auth/refresh" \
  -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"${RT}\"}") \
  || fail "POST /api/auth/refresh failed"
echo "$REFRESH" | jq -e '.access_token' >/dev/null || fail "refresh response missing access_token"

echo "PASS"
