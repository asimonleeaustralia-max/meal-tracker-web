#!/usr/bin/env bash
# Meal + people sync smoke test — PUT upsert by client UUID, incremental pull.
#
# Prerequisites: docker compose up (gateway on :8080).
#
# Usage:
#   ./scripts/smoke-test-meal-sync.sh
#   BASE_URL=http://192.168.1.42:8080 ./scripts/smoke-test-meal-sync.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
EMAIL="meal-sync-$(date +%s)-$RANDOM@example.com"
PASS="TestPass123!"
PERSON_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
MEAL_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"

fail() { echo "FAIL: $*" >&2; exit 1; }

echo "==> signup + login"
SIGNUP=$(curl -sf -X POST "${BASE_URL}/api/auth/signup" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASS}\",\"client\":\"ios\"}") \
  || fail "POST /api/auth/signup failed"
AT=$(echo "$SIGNUP" | jq -r '.access_token // empty')
[[ -n "$AT" ]] || fail "signup response missing access_token"

NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SINCE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "==> PUT new person (client UUID ${PERSON_ID})"
CREATE_PERSON=$(curl -sf -X PUT "${BASE_URL}/api/people/${PERSON_ID}" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${AT}" \
  -d "{\"name\":\"Smoke person\",\"is_default\":true,\"is_removed\":false}") \
  || fail "PUT /api/people (create) failed"
echo "$CREATE_PERSON" | jq -e --arg id "$PERSON_ID" '.id == $id' >/dev/null \
  || fail "person id mismatch"
echo "$CREATE_PERSON" | jq -e '.updated_at != null' >/dev/null \
  || fail "create person response missing updated_at"
PERSON_UPDATED=$(echo "$CREATE_PERSON" | jq -r '.updated_at')
echo "OK: person updated_at=${PERSON_UPDATED}"

echo "==> PUT new meal linked to person (client UUID ${MEAL_ID})"
CREATE=$(curl -sf -X PUT "${BASE_URL}/api/meals/${MEAL_ID}" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${AT}" \
  -d "{\"title\":\"Smoke meal\",\"date\":\"${NOW}\",\"person_id\":\"${PERSON_ID}\",\"calories\":500,\"protein\":30}") \
  || fail "PUT /api/meals (create) failed"
SYNC_GUID=$(echo "$CREATE" | jq -r '.last_sync_guid // empty')
[[ -n "$SYNC_GUID" ]] || fail "create response missing last_sync_guid"
echo "$CREATE" | jq -e --arg pid "$PERSON_ID" '.person_id == $pid' >/dev/null \
  || fail "meal person_id mismatch"
echo "$CREATE" | jq -e '.calories == 500' >/dev/null \
  || fail "expected calories 500, got $(echo "$CREATE" | jq -r '.calories')"
echo "OK: last_sync_guid=${SYNC_GUID}"

echo "==> PUT update meal (calories 600)"
UPDATE=$(curl -sf -X PUT "${BASE_URL}/api/meals/${MEAL_ID}" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${AT}" \
  -d "{\"title\":\"Smoke meal\",\"date\":\"${NOW}\",\"person_id\":\"${PERSON_ID}\",\"calories\":600,\"protein\":30}") \
  || fail "PUT /api/meals (update) failed"
NEW_GUID=$(echo "$UPDATE" | jq -r '.last_sync_guid // empty')
[[ -n "$NEW_GUID" && "$NEW_GUID" != "$SYNC_GUID" ]] \
  || fail "update should return a new last_sync_guid"
echo "$UPDATE" | jq -e '.calories == 600' >/dev/null \
  || fail "expected calories 600, got $(echo "$UPDATE" | jq -r '.calories')"

echo "==> GET /api/people?since=${SINCE}"
PULL_PEOPLE=$(curl -sf "${BASE_URL}/api/people?since=${SINCE}" \
  -H "Authorization: Bearer ${AT}") \
  || fail "GET /api/people?since= failed"
FOUND_PERSON=$(echo "$PULL_PEOPLE" | jq --arg id "$PERSON_ID" '[.[] | select(.id == $id)] | length')
[[ "$FOUND_PERSON" -ge 1 ]] || fail "person not in incremental people pull"
echo "$PULL_PEOPLE" | jq -e --arg id "$PERSON_ID" '[.[] | select(.id == $id)] | .[0].name == "Smoke person"' >/dev/null \
  || fail "pulled person name expected 'Smoke person'"

echo "==> GET /api/meals?since=${SINCE}"
PULL=$(curl -sf "${BASE_URL}/api/meals?since=${SINCE}" \
  -H "Authorization: Bearer ${AT}") \
  || fail "GET /api/meals?since= failed"
FOUND=$(echo "$PULL" | jq --arg id "$MEAL_ID" '[.[] | select(.id == $id)] | length')
[[ "$FOUND" -ge 1 ]] || fail "updated meal not in incremental pull"
echo "$PULL" | jq -e --arg id "$MEAL_ID" '[.[] | select(.id == $id)] | .[0].calories == 600' >/dev/null \
  || fail "pulled meal calories expected 600"
echo "$PULL" | jq -e --arg pid "$PERSON_ID" --arg id "$MEAL_ID" \
  '[.[] | select(.id == $id)] | .[0].person_id == $pid' >/dev/null \
  || fail "pulled meal person_id mismatch"

echo "==> POST /api/photos/upload-url (SAS upload flow)"
UPLOAD=$(curl -sf -X POST "${BASE_URL}/api/photos/upload-url" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${AT}" \
  -d "{\"meal_id\":\"${MEAL_ID}\",\"width\":1080,\"height\":1080,\"byte_size_upload\":12345,\"sha256\":\"abc123\"}") \
  || fail "POST /api/photos/upload-url failed"
PHOTO_ID=$(echo "$UPLOAD" | jq -r '.photo_id // empty')
[[ -n "$PHOTO_ID" ]] || fail "upload-url response missing photo_id"
echo "$UPLOAD" | jq -e '.upload_url != null and .blob_name != null' >/dev/null \
  || fail "upload-url response missing upload_url or blob_name"
echo "OK: photo_id=${PHOTO_ID}"

echo "==> PATCH /api/photos/${PHOTO_ID} (upload_confirmed)"
PATCH_PHOTO=$(curl -sf -X PATCH "${BASE_URL}/api/photos/${PHOTO_ID}" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${AT}" \
  -d '{"upload_confirmed":true}') \
  || fail "PATCH /api/photos (confirm) failed"
echo "$PATCH_PHOTO" | jq -e '.updated_at != null' >/dev/null \
  || fail "patch photo response missing updated_at"
echo "$PATCH_PHOTO" | jq -e '.image_data_b64 == null' >/dev/null \
  || fail "patch photo response should omit image_data_b64"

echo "==> GET /api/photos?since=${SINCE}"
PULL_PHOTOS=$(curl -sf "${BASE_URL}/api/photos?since=${SINCE}" \
  -H "Authorization: Bearer ${AT}") \
  || fail "GET /api/photos?since= failed"
FOUND_PHOTO=$(echo "$PULL_PHOTOS" | jq --arg id "$PHOTO_ID" '[.[] | select(.id == $id)] | length')
[[ "$FOUND_PHOTO" -ge 1 ]] || fail "confirmed photo not in incremental photos pull"
echo "$PULL_PHOTOS" | jq -e --arg id "$PHOTO_ID" \
  '[.[] | select(.id == $id)] | .[0].blob_name != null' >/dev/null \
  || fail "pulled photo missing blob_name"
echo "$PULL_PHOTOS" | jq -e --arg id "$PHOTO_ID" \
  '[.[] | select(.id == $id)] | .[0].image_data_b64 == null' >/dev/null \
  || fail "photos pull should omit image_data_b64"

echo "==> GET /api/photos/${PHOTO_ID}/download-url"
DOWNLOAD=$(curl -sf "${BASE_URL}/api/photos/${PHOTO_ID}/download-url" \
  -H "Authorization: Bearer ${AT}") \
  || fail "GET /api/photos/download-url failed"
echo "$DOWNLOAD" | jq -e '.download_url != null and .expires_at != null' >/dev/null \
  || fail "download-url response missing download_url or expires_at"

echo "PASS"
