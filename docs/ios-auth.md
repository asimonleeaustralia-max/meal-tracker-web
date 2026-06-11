# iOS auth via API gateway

## Base URL

| Environment | Base URL |
|-------------|----------|
| Local simulator | `http://localhost:8080` |
| Physical device on LAN | `http://<LAN-IP>:8080` (your Mac's IP; gateway must bind `0.0.0.0:8080` via docker compose) |
| Production | `https://<gateway-fqdn>` (Bicep output `gatewayFqdn`, e.g. `https://mealtracker-gateway.xxx.azurecontainerapps.io` or your custom API domain) |

Native iOS apps do **not** use browser CORS — only the web frontend does. No gateway CORS change is required for the simulator or a device build.

All requests below use the gateway base URL. Pass `"client": "ios"` on signup/login so admin sessions show the correct client.

## Signup

```bash
curl -s -X POST http://localhost:8080/api/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{"email":"ios-test@example.com","password":"TestPass123!","client":"ios"}' | jq
```

Returns `201` with `access_token`, `refresh_token`, `expires_in`, and `session_id`.

## Login

```bash
curl -s -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ios-test@example.com","password":"TestPass123!","client":"ios"}' | jq
```

Returns `200` with a fresh token pair. Save both tokens for the calls below.

## Me

```bash
AT="<access_token from login>"
curl -s http://localhost:8080/api/auth/me \
  -H "Authorization: Bearer $AT" | jq
```

Returns `200` with the authenticated user's public profile.

## Refresh

```bash
RT="<refresh_token from login>"
curl -s -X POST http://localhost:8080/api/auth/refresh \
  -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"$RT\"}" | jq
```

Returns `200` with a rotated token pair (old refresh token is revoked).

## Sign in with Apple (native iOS)

Use the **Sign in with Apple** SDK on device/simulator to obtain an Apple-issued `id_token`, then exchange it for MealTracker JWTs:

```bash
curl -s -X POST http://localhost:8080/api/auth/oauth/apple/token-exchange \
  -H 'Content-Type: application/json' \
  -d '{"id_token":"<apple_id_token>","email":"user@privaterelay.appleid.com","display_name":"Simon"}' | jq
```

`email` and `display_name` are optional when Apple includes them in the ID token (first sign-in only for name).

Returns `200` with the same `TokenPair` shape as login (`access_token`, `refresh_token`, `expires_in`, `session_id`). The gateway route is public (no bearer token required for the exchange itself).

### Required env vars (auth-service)

| Variable | Purpose |
|----------|---------|
| `APPLE_CLIENT_ID` | **Services ID** for web OAuth (e.g. `com.example.macrossimple.web`). |
| `APPLE_IOS_CLIENT_ID` | **iOS bundle ID** (e.g. `com.example.MacrosSimple`). Used as the `aud` claim when verifying native Apple ID tokens. |
| `APPLE_TEAM_ID` | Apple Developer Team ID (10-char). Required for the **browser** OAuth flow only; not needed for native `token-exchange`. |
| `APPLE_KEY_ID` | Sign in with Apple key ID (browser flow). |
| `APPLE_PRIVATE_KEY` | `.p8` private key contents (browser flow). |
| `APPLE_REDIRECT_URI` | Callback URL for web OAuth (e.g. `https://api.example.com/api/auth/oauth/apple/callback`). |

For native iOS sign-in, only **`APPLE_IOS_CLIENT_ID`** must be set correctly.
For web **Continue with Apple**, also set `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`,
`APPLE_KEY_ID`, and `APPLE_PRIVATE_KEY`. See `docs/ios-apple-registration.md`
for the full iOS settings toggle and web deep-link flow.

Local `docker-compose.yml` already wires `APPLE_CLIENT_ID` from the host environment:

```bash
export APPLE_IOS_CLIENT_ID="com.yourcompany.MacrosSimple"
export APPLE_CLIENT_ID="com.yourcompany.macrossimple.web"   # web OAuth only
docker compose up --build
```

Verification uses Apple's JWKS (`https://appleid.apple.com/auth/keys`) — no client secret is needed for `token-exchange`.

## Incremental sync (single call)

After auth, pull all entity changes since a cursor in one request:

```bash
curl -s "http://localhost:8080/api/sync/changes?since=2026-01-01T00:00:00Z" \
  -H "Authorization: Bearer $AT" | jq '{meal_count:(.meals|length), people_count:(.people|length), photo_count:(.photos|length), server_time}'
```

See `docs/ios-sync-mapping.md` for field mapping and per-entity push flows.

## Full smoke test

```bash
./scripts/test_full_sync.sh
# or against a device on your LAN:
BASE_URL=http://192.168.1.42:8080 ./scripts/test_full_sync.sh
```
