# iOS auth via API gateway

All requests go through the gateway at `http://localhost:8080` (or your deployed
gateway URL). Pass `"client": "ios"` on signup/login so admin sessions show the
correct client.

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
