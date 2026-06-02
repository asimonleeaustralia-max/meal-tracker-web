# Deploying MealTracker to Azure

This guide walks through deploying the MealTracker microservices to **Azure Container Apps** (Consumption plan). Follow the steps in order — each one is copy-pasteable.

## Why these choices

| Concern | Choice | Why |
|---|---|---|
| Compute | **Azure Container Apps**, Consumption plan | Per-second billing, **scales to zero**, free monthly grant of 180k vCPU-seconds + 360k GiB-seconds + 2M requests. A near-idle hobby workload typically lives inside the free tier; a moderate workload runs for low single-digit dollars/month. |
| Database | **Azure Database for PostgreSQL Flexible Server, Burstable B1ms** | Cheapest credible managed Postgres on Azure (~US$12/month + storage). Speaks vanilla Postgres so you can later move to **Neon** (serverless, free dev tier) or **Supabase** if you prefer. |
| Photo storage | **Azure Blob Storage, Standard LRS** | A few cents per GB/month. Clients upload directly via SAS URLs so the API process never sees the bytes. |
| Container registry | **ACR Basic SKU** | ~US$5/month for the registry. Cheaper alternative: Docker Hub or GHCR (just edit `registries` in the Bicep). |
| Logs | **Log Analytics workspace** | Built into the Container Apps environment. First 5 GB/month free. |
| Inference | **RunPod Serverless** (already chosen) | GPU only spins up on request. Per-second billing. |

**Rough idle-time budget:** ~$15–20/month for Postgres + ACR + storage. Compute and request charges stay inside Azure's free tier as long as traffic is light. The vision-service cold-call cost is dominated by RunPod, not Azure.

---

## Prerequisites (one-time)

1. **An Azure account.** [Free tier](https://azure.microsoft.com/free/) is enough to start; you get $200 credit for 30 days.
2. **Azure CLI** installed. macOS: `brew install azure-cli`. [Other platforms.](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
3. **Docker** with `buildx` (already installed if you have Docker Desktop).
4. The repo cloned locally.

Verify:
```bash
az --version
docker --version
```

Log in:
```bash
az login
az account set --subscription "<your-subscription-name-or-id>"
```

---

## Step 1 — Pick names and store them as shell vars

These names appear in URLs and DNS, so pick them once and reuse:

```bash
# Edit these three values, the rest derive automatically
export RG="mealtracker-rg"          # resource group name
export LOC="australiaeast"          # any region — pick the one closest to your users
export PREFIX="mealtracker"         # 3–12 chars, lowercase letters/digits/dashes
                                    # (this is the "namePrefix" Bicep param)

# Derived
export ACR_NAME="${PREFIX}acr"
export ENV_NAME="${PREFIX}-env"
export PG_NAME="${PREFIX}-pg"
export STG_NAME="${PREFIX}stg"
```

> **Region tip:** Container Apps Consumption plan is available in most regions. `australiaeast`, `eastus`, `westeurope`, `northeurope`, `southeastasia` are safe choices. Run `az provider show -n Microsoft.App --query "resourceTypes[?resourceType=='managedEnvironments'].locations" -o tsv` for a current list.

---

## Step 2 — Register the required resource providers

First time only on a subscription:

```bash
az provider register --namespace Microsoft.App         --wait
az provider register --namespace Microsoft.OperationalInsights --wait
az provider register --namespace Microsoft.DBforPostgreSQL    --wait
az provider register --namespace Microsoft.Storage            --wait
az provider register --namespace Microsoft.ContainerRegistry  --wait
```

---

## Step 3 — Create the resource group

```bash
az group create --name "${RG}" --location "${LOC}"
```

---

## Step 4 — Generate secrets

You need two secrets and a Postgres admin password. Generate strong ones now and keep them somewhere safe (password manager, Key Vault).

```bash
# Linux/macOS
JWT_SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(64))")
PG_PASSWORD=$(python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(28)))")

echo "JWT_SECRET=${JWT_SECRET}"
echo "PG_PASSWORD=${PG_PASSWORD}"
```

> **Production note:** Once everything is working, move these into **Azure Key Vault** and replace the parameter values with Key Vault references (`@Microsoft.KeyVault(SecretUri=…)`). The Bicep template is structured to make this swap easy.

---

## Step 5 — (Optional) Set up OAuth providers

Skip this for the first run; you can add OAuth after the core is up.

### Google
1. Go to <https://console.cloud.google.com>, create a project, enable the *Google Identity* API.
2. **APIs & Services → Credentials → Create credentials → OAuth client ID → Web application**.
3. Add the authorized redirect URI (you'll know the final hostname after Step 8; until then add a placeholder and update later):
   `https://<gateway-fqdn>/api/auth/oauth/google/callback`
4. Copy the Client ID and Client Secret.

### Apple Sign-In
1. <https://developer.apple.com/account> → **Certificates, IDs & Profiles**.
2. Register a **Services ID** (e.g. `com.example.mealtracker.web`) and enable Sign in with Apple.
3. Configure the return URL: `https://<gateway-fqdn>/api/auth/oauth/apple/callback`.
4. Create a **Sign in with Apple Key**, download the `.p8` file.
5. Note the Services ID, Team ID, Key ID, and the contents of the `.p8` (PEM format).

### Facebook
1. <https://developers.facebook.com/apps/> → Create app → "Consumer" → enable **Facebook Login**.
2. Add redirect URI: `https://<gateway-fqdn>/api/auth/oauth/facebook/callback`.
3. Copy the App ID and App Secret.

> The OAuth callback URLs need the *final* gateway FQDN, which you'll have after Step 8. Just put a placeholder in for now and revisit.

---

## Step 6 — (Optional) Set up the RunPod vision endpoint

Skip and the vision-service will run in "stub mode" (returns canned predictions) so you can ship the rest. Come back here once the API is up.

1. **Build the worker image** (defined in `services/vision-service/runpod-worker/`):
   ```bash
   cd services/vision-service/runpod-worker
   docker build -t <yourdockerhub>/mealtracker-vision-worker:latest .
   docker push <yourdockerhub>/mealtracker-vision-worker:latest
   cd -
   ```
   Edit `handler.py` first to plug in whichever vision model you want — the file ships with a stub that returns fixed predictions.

2. **Create the RunPod Serverless Endpoint:**
   - <https://www.runpod.io/console/serverless>
   - Click **New Endpoint**
   - Point it at the image you just pushed
   - Choose a GPU type that fits your model. A `RTX A4000` or `L4` is fine for most 7–13B vision-language models.
   - Set **Max Workers** to a low number (1–2) initially.
   - Set **Idle Timeout** to ~30 seconds so the worker scales to zero quickly.

3. Copy the endpoint **URL** (looks like `https://api.runpod.ai/v2/<endpoint-id>/runsync`) and **API Key** from the RunPod settings page.

---

## Step 7 — Fill in `parameters.json`

```bash
cp infra/azure/parameters.example.json infra/azure/parameters.json
```

Edit `infra/azure/parameters.json`:

- `namePrefix` — same as `$PREFIX` above
- `pgAdminPassword` — the `PG_PASSWORD` you generated
- `jwtSecret` — the `JWT_SECRET` you generated
- `googleClientId` / `googleClientSecret` — from Step 5 (leave empty if skipping)
- `appleClientId` / `applePrivateKey` — from Step 5
- `facebookClientId` / `facebookClientSecret` — from Step 5
- `runpodEndpointUrl` / `runpodApiKey` — from Step 6
- `imageTag` — leave as `"v1"` for now

---

## Step 8 — Provision the infrastructure

This single command creates the ACR, Postgres, storage, environment, and *empty* Container Apps:

```bash
az deployment group create \
  --resource-group "${RG}" \
  --template-file infra/azure/main.bicep \
  --parameters @infra/azure/parameters.json
```

Take ~5–10 minutes. When it finishes, capture the outputs:

```bash
az deployment group show \
  -g "${RG}" -n main \
  --query properties.outputs
```

You'll see something like:
```
"gatewayFqdn":   { "value": "mealtracker-gateway.brave-rock-1234.australiaeast.azurecontainerapps.io" }
"webFqdn":       { "value": "mealtracker-web.brave-rock-1234.australiaeast.azurecontainerapps.io" }
"acrLoginServer":{ "value": "mealtrackeracr.azurecr.io" }
"postgresHost":  { "value": "mealtracker-pg.postgres.database.azure.com" }
```

Save the gateway FQDN — that's where the iOS app and any external clients will connect.

> The Container Apps are now created but **failing to start** because the images don't exist yet. That's expected — they'll come up after Step 10.

---

## Step 9 — Update OAuth callback URLs (if Step 5 was done)

Now that you know the real gateway FQDN, go back to each provider's console and update the redirect URI:

- Google: `https://<gatewayFqdn>/api/auth/oauth/google/callback`
- Apple:  `https://<gatewayFqdn>/api/auth/oauth/apple/callback`
- Facebook: `https://<gatewayFqdn>/api/auth/oauth/facebook/callback`

---

## Step 10 — Build and push the images

```bash
./scripts/build-and-push.sh "${ACR_NAME}" v1
```

This builds all six service images for `linux/amd64` and pushes them to your ACR. Takes ~5–10 minutes on a typical laptop.

> If you're on an Apple Silicon Mac, the `--platform linux/amd64` flag in the script ensures the images run on Azure's Intel-based Container Apps hosts. Without it, you'll get exec-format errors on startup.

---

## Step 11 — Roll the Container Apps onto the new images

The first deployment already pointed each app at `:v1`. Now that those tags exist, force a fresh revision so each app pulls and starts:

```bash
for app in gateway auth meal nutrition vision web; do
  az containerapp revision restart \
    --resource-group "${RG}" \
    --name "${PREFIX}-${app}" || true
done
```

Or, if you bumped the tag (e.g. to `v2`):

```bash
az deployment group create \
  --resource-group "${RG}" \
  --template-file infra/azure/main.bicep \
  --parameters @infra/azure/parameters.json \
  --parameters imageTag=v2
```

Watch them come up:
```bash
az containerapp list -g "${RG}" -o table
```

You're looking for `Running` in the `RunningStatus` column for all six.

---

## Step 12 — Run database migrations

The dev mode auto-creates tables. In production, run Alembic explicitly.

**Easiest path: a one-off Container Apps Job.** For each schema-owning service:

```bash
for svc in auth meal nutrition; do
  az containerapp job create \
    --resource-group "${RG}" \
    --name "${PREFIX}-${svc}-migrate" \
    --environment "${ENV_NAME}" \
    --image "${ACR_NAME}.azurecr.io/mealtracker/${svc}-service:v1" \
    --trigger-type Manual \
    --replica-timeout 600 \
    --registry-server "${ACR_NAME}.azurecr.io" \
    --registry-identity system \
    --command "alembic" --args "upgrade head" \
    --env-vars \
      "ENVIRONMENT=production" \
      "DATABASE_URL=secretref:database-url" \
      "DB_SCHEMA=${svc}" \
    --secrets "database-url=postgresql+psycopg://mealadmin:${PG_PASSWORD}@${PG_NAME}.postgres.database.azure.com:5432/mealtracker?sslmode=require"
done

# Run each one
for svc in auth meal nutrition; do
  az containerapp job start --resource-group "${RG}" --name "${PREFIX}-${svc}-migrate"
done
```

> Note: alembic uses `psycopg` (sync), so the URL prefix is `postgresql+psycopg` here, not `postgresql+asyncpg`. Both connect to the same database.

For the nutrition service, also seed the food reference data (one-off):
```bash
# Easiest: shell into a running revision
az containerapp exec \
  --resource-group "${RG}" \
  --name "${PREFIX}-nutrition" \
  --command "python -c 'import asyncio; from app.main import lifespan; print(\"seeded\")'"
```
…or write a tiny `python -m app.seed` entry point and trigger it as a Container Apps Job the same way as the migrations.

---

## Step 13 — Smoke-test

```bash
GATEWAY="https://$(az containerapp show -g ${RG} -n ${PREFIX}-gateway --query properties.configuration.ingress.fqdn -o tsv)"
echo "Gateway: ${GATEWAY}"

# Health
curl -fsS "${GATEWAY}/healthz" | jq .

# Signup
curl -fsS "${GATEWAY}/api/auth/signup" \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"hunter2hunter2"}' | jq .
# → { "access_token":"...", "refresh_token":"...", ... }

# Use that access_token
TOKEN="<paste access_token>"
curl -fsS "${GATEWAY}/api/auth/me" -H "Authorization: Bearer ${TOKEN}" | jq .
```

Visit the web frontend in your browser:
```bash
echo "Web: https://$(az containerapp show -g ${RG} -n ${PREFIX}-web --query properties.configuration.ingress.fqdn -o tsv)"
```

---

## Step 14 — Point the iOS app at the production gateway

In the Swift app, change the base URL from the dev/local one to the gateway FQDN. The codable mapping is set up such that the iOS-side `Meal`/`Person`/`MealPhoto` structs serialise directly to the API (see `docs/ios-sync-mapping.md`). Use the OAuth `/token-exchange` endpoint with Apple's native Sign-in flow:

```swift
// After Sign in with Apple returns an ASAuthorizationAppleIDCredential
let idToken = String(data: credential.identityToken!, encoding: .utf8)!

var req = URLRequest(url: URL(string: "\(baseURL)/api/auth/oauth/apple/token-exchange")!)
req.httpMethod = "POST"
req.setValue("application/json", forHTTPHeaderField: "Content-Type")
req.httpBody = try JSONEncoder().encode(["id_token": idToken])
let (data, _) = try await URLSession.shared.data(for: req)
let pair = try JSONDecoder().decode(TokenPair.self, from: data)
// Store pair.accessToken in Keychain; pass on every subsequent request.
```

---

## Step 15 — Point your GoDaddy domain at the web app

This step wires `macrossimple.com` (registered at GoDaddy) at the **web-frontend** container app, and `api.macrossimple.com` at the **api-gateway**. Splitting them keeps the browser using same-origin `/api/*` calls (you'll just update the frontend's `API_GATEWAY_URL` env var to the new API hostname).

> **Heads-up: you can choose ONE of two patterns.**
>
> **Pattern A — split:** `macrossimple.com` → web frontend, `api.macrossimple.com` → gateway. Cleanest. Two custom domains to set up. This is what's shown below.
>
> **Pattern B — single:** `macrossimple.com` → web frontend only. Browser keeps calling `/api/*` (the frontend's nginx proxies internally to the gateway over the Container Apps environment's private DNS). The gateway stays on its `*.azurecontainerapps.io` hostname. Simpler DNS, but the gateway's FQDN leaks if anyone inspects network calls. Skip Step 15.4 to go this route.

### 15.1 — Decide which hostnames you want

```bash
export ROOT_DOMAIN="macrossimple.com"           # apex/root
export WEB_HOSTNAME="${ROOT_DOMAIN}"            # → web-frontend Container App
export WWW_HOSTNAME="www.${ROOT_DOMAIN}"        # also → web-frontend (recommended)
export API_HOSTNAME="api.${ROOT_DOMAIN}"        # → api-gateway Container App
```

### 15.2 — Gather what you need from Azure

```bash
# Static IP of the Container Apps environment (needed for the apex A record)
ENV_IP=$(az containerapp env show -g "${RG}" -n "${ENV_NAME}" \
  --query "properties.staticIp" -o tsv)
echo "Container Apps env static IP: ${ENV_IP}"

# The auto-generated FQDN of each app (the CNAME target for subdomains)
WEB_FQDN=$(az containerapp show -g "${RG}" -n "${PREFIX}-web" \
  --query "properties.configuration.ingress.fqdn" -o tsv)
GATEWAY_FQDN=$(az containerapp show -g "${RG}" -n "${PREFIX}-gateway" \
  --query "properties.configuration.ingress.fqdn" -o tsv)
echo "Web FQDN:     ${WEB_FQDN}"
echo "Gateway FQDN: ${GATEWAY_FQDN}"

# The domain-ownership verification IDs (one per app)
WEB_VERIFY=$(az containerapp show -g "${RG}" -n "${PREFIX}-web" \
  --query "properties.customDomainVerificationId" -o tsv)
GATEWAY_VERIFY=$(az containerapp show -g "${RG}" -n "${PREFIX}-gateway" \
  --query "properties.customDomainVerificationId" -o tsv)
echo "Web verify ID:     ${WEB_VERIFY}"
echo "Gateway verify ID: ${GATEWAY_VERIFY}"
```

Keep these values open — you'll paste them into GoDaddy in 15.3.

### 15.3 — Add the DNS records in GoDaddy

1. Sign in at <https://dcc.godaddy.com/control/portfolio>.
2. Find **macrossimple.com** in your list, click the **⋮** (or **DNS**) button, choose **Manage DNS**.
3. **Delete the default GoDaddy parking records** that conflict:
   - Any existing **A record** on `@` (the default points at GoDaddy's parking page).
   - Any existing **CNAME** on `www` if you want the `www` subdomain.
4. Add these records (use GoDaddy's **Add New Record** button, one at a time):

| Type  | Name | Value | TTL |
|-------|------|-------|-----|
| **A**     | `@`              | `<ENV_IP>` (from 15.2)                              | 600 sec / 1 hour |
| **TXT**   | `asuid`          | `<WEB_VERIFY>` (from 15.2)                          | 1 hour |
| **CNAME** | `www`            | `<WEB_FQDN>` (from 15.2, no `https://`, no trailing dot) | 1 hour |
| **TXT**   | `asuid.www`      | `<WEB_VERIFY>` (same as the apex)                   | 1 hour |
| **CNAME** | `api`            | `<GATEWAY_FQDN>` (from 15.2)                        | 1 hour |
| **TXT**   | `asuid.api`      | `<GATEWAY_VERIFY>`                                  | 1 hour |

> Notes for GoDaddy specifically:
> - GoDaddy's "Name" field uses `@` for the apex (root) domain. Just type `@`.
> - For the CNAMEs, **don't** include `https://` or a trailing dot. GoDaddy will reject either.
> - GoDaddy's UI sometimes auto-appends your domain to the Name field (showing `www.macrossimple.com` after you type `www`). That's fine — it's display-only.
> - DNS propagation usually completes within 5–15 minutes for GoDaddy, but the docs say allow up to 48 hours. You can check with `dig`:
>   ```bash
>   dig +short A    macrossimple.com
>   dig +short CNAME api.macrossimple.com
>   dig +short TXT  asuid.macrossimple.com
>   ```
>   Each should return the value you set.

### 15.4 — Bind the hostnames in Azure

Once DNS resolves (verify with the `dig` commands above before continuing — binding will fail otherwise), bind each hostname and request a managed certificate. **The order matters: `add` first, then `bind`.**

```bash
# Apex domain → web-frontend (uses A record validation = HTTP method)
az containerapp hostname add \
  -g "${RG}" -n "${PREFIX}-web" \
  --hostname "${WEB_HOSTNAME}"

az containerapp hostname bind \
  -g "${RG}" -n "${PREFIX}-web" \
  --environment "${ENV_NAME}" \
  --hostname "${WEB_HOSTNAME}" \
  --validation-method HTTP

# www subdomain → web-frontend (uses CNAME validation)
az containerapp hostname add \
  -g "${RG}" -n "${PREFIX}-web" \
  --hostname "${WWW_HOSTNAME}"

az containerapp hostname bind \
  -g "${RG}" -n "${PREFIX}-web" \
  --environment "${ENV_NAME}" \
  --hostname "${WWW_HOSTNAME}" \
  --validation-method CNAME

# api subdomain → api-gateway (uses CNAME validation)
az containerapp hostname add \
  -g "${RG}" -n "${PREFIX}-gateway" \
  --hostname "${API_HOSTNAME}"

az containerapp hostname bind \
  -g "${RG}" -n "${PREFIX}-gateway" \
  --environment "${ENV_NAME}" \
  --hostname "${API_HOSTNAME}" \
  --validation-method CNAME
```

Each `bind` takes 2–5 minutes — it provisions a free managed TLS certificate from DigiCert. The cert auto-renews; nothing further to do.

### 15.5 — Re-point the frontend at the new API hostname

The frontend container reads `API_GATEWAY_URL` at startup and substitutes it into nginx. Update it to the custom domain so the browser stops calling the `*.azurecontainerapps.io` address:

```bash
az containerapp update \
  -g "${RG}" -n "${PREFIX}-web" \
  --set-env-vars "API_GATEWAY_URL=https://${API_HOSTNAME}"
```

Also update the gateway's CORS whitelist to allow the new origins:

```bash
az containerapp update \
  -g "${RG}" -n "${PREFIX}-gateway" \
  --set-env-vars "CORS_ORIGINS=[\"https://${WEB_HOSTNAME}\",\"https://${WWW_HOSTNAME}\"]"
```

### 15.6 — Update OAuth provider callback URLs

The redirect URIs you set in **Step 5** still point at the old `*.azurecontainerapps.io` gateway hostname. Update each provider:

- **Google:** APIs & Services → Credentials → your OAuth client → Authorized redirect URIs → add `https://api.macrossimple.com/api/auth/oauth/google/callback` (and remove the old one).
- **Apple:** Identifiers → your Services ID → Sign in with Apple → Configure → Return URLs → add `https://api.macrossimple.com/api/auth/oauth/apple/callback`.
- **Facebook:** App → Facebook Login → Settings → Valid OAuth Redirect URIs → add `https://api.macrossimple.com/api/auth/oauth/facebook/callback`.

Then update the auth-service env vars so it sends the right redirect URI in the outgoing OAuth requests:

```bash
az containerapp update \
  -g "${RG}" -n "${PREFIX}-auth" \
  --set-env-vars \
    "GOOGLE_REDIRECT_URI=https://${API_HOSTNAME}/api/auth/oauth/google/callback" \
    "APPLE_REDIRECT_URI=https://${API_HOSTNAME}/api/auth/oauth/apple/callback" \
    "FACEBOOK_REDIRECT_URI=https://${API_HOSTNAME}/api/auth/oauth/facebook/callback" \
    "OAUTH_SUCCESS_REDIRECT=https://${WEB_HOSTNAME}/auth/success" \
    "OAUTH_FAILURE_REDIRECT=https://${WEB_HOSTNAME}/auth/failure"
```

### 15.7 — Test

```bash
curl -fsS "https://${API_HOSTNAME}/healthz" | jq .
# { "status": "ok", "service": "api-gateway" }

open "https://${WEB_HOSTNAME}"   # macOS; Linux: xdg-open
```

You should see the login screen served at `https://macrossimple.com` over a valid TLS cert, and OAuth sign-ins should work end-to-end.

### Troubleshooting

**`The custom domain has not been verified`** when running `hostname bind` — DNS hasn't propagated yet, or the `asuid.<subdomain>` TXT record is wrong. Re-check with `dig +short TXT asuid.macrossimple.com`; if empty, give DNS another 10 minutes.

**`Validation failed for hostname`** — for an apex domain you must use `--validation-method HTTP`; for any CNAME subdomain you must use `--validation-method CNAME`. Mixing them up gives this error.

**Browser shows "Not secure"** for the first minute or two after `bind` succeeds — the managed cert isn't installed yet. Wait 2–3 more minutes and reload.

**OAuth redirects break after the cutover** — you missed a redirect URI somewhere. Check the network tab; the URL the provider is trying to reach should match exactly what's in `GOOGLE_REDIRECT_URI` (etc.) on the auth-service AND in the provider's allowed-callback list.

**The browser hits `https://macrossimple.com/api/auth/login` and gets a 502** — this happens if you chose Pattern A but forgot Step 15.5. The frontend's nginx is still proxying `/api` to the old `*.azurecontainerapps.io` gateway. Rerun the `az containerapp update --set-env-vars "API_GATEWAY_URL=..."` from 15.5 and restart the revision.

---

## Day-2 operations

### View logs
```bash
az containerapp logs show -g "${RG}" -n "${PREFIX}-gateway" --follow
```
Or query Log Analytics for cross-service searches:
```bash
az monitor log-analytics query \
  --workspace $(az monitor log-analytics workspace show -g "${RG}" -n "${PREFIX}-logs" --query customerId -o tsv) \
  --analytics-query "ContainerAppConsoleLogs_CL | where ContainerAppName_s startswith '${PREFIX}' | order by TimeGenerated desc | take 50"
```

### Scale individual services
```bash
az containerapp update -g "${RG}" -n "${PREFIX}-gateway" \
  --min-replicas 1 --max-replicas 20
```

### Deploy a new image version
```bash
./scripts/build-and-push.sh "${ACR_NAME}" v2

for svc in api-gateway auth meal nutrition vision web; do
  az containerapp update -g "${RG}" -n "${PREFIX}-${svc/api-/}" \
    --image "${ACR_NAME}.azurecr.io/mealtracker/${svc}:v2"
done
```

### Rotate the JWT secret
Update the value in your parameter file, redeploy with `imageTag` unchanged. All in-flight access tokens will be invalidated on next call; clients will retry via `/auth/refresh` and get fresh ones — *but only if the refresh token's signature is still valid*. To rotate without forcing every user to re-login, do a two-phase rotation: accept both old and new secrets for one access-token lifetime, then drop the old one. (Not built in yet — add it before rotating.)

### Switch the database to Neon (cheaper for development/hobby)
Neon offers a free-tier serverless Postgres that scales to zero. To switch:

1. Create a project at <https://console.neon.tech>.
2. Copy the connection string (looks like `postgresql://user:pwd@ep-xxxx.region.aws.neon.tech/db?sslmode=require`).
3. Convert it for asyncpg: replace `postgresql://` with `postgresql+asyncpg://`.
4. In each Container App, update the `DATABASE_URL` secret:
   ```bash
   az containerapp secret set -g "${RG}" -n "${PREFIX}-auth" \
     --secrets "database-url=postgresql+asyncpg://user:pwd@ep-xxxx.region.aws.neon.tech/db?ssl=require"
   az containerapp revision restart -g "${RG}" -n "${PREFIX}-auth"
   ```
5. Repeat for `meal` and `nutrition`.
6. Decommission the Azure Postgres: `az postgres flexible-server delete -g "${RG}" -n "${PG_NAME}"`.

No code changes required.

### Cost monitoring
```bash
az consumption usage list --start-date $(date -v-30d +%Y-%m-%d) --end-date $(date +%Y-%m-%d) -o table
```
Or set a budget alert in the Cost Management blade of the Azure portal.

---

## Troubleshooting

**Container App stuck `Provisioning`:** check `az containerapp revision list -g "${RG}" -n "${PREFIX}-gateway" -o table` and look at the latest revision's `ProvisioningState`. Then `az containerapp logs show ... --follow` for the actual error. Most common: image-pull failure (forgot to push), missing env var, or wrong port number.

**Postgres connection refused from Container App:** ensure the firewall rule `AllowAllAzureIPs` exists on the Postgres server (`az postgres flexible-server firewall-rule list -g "${RG}" -n "${PG_NAME}"`).

**OAuth callback returns "redirect_uri_mismatch":** the URL configured at the provider must match exactly. Trailing slashes count.

**JWT verification fails everywhere after redeploy:** the `JWT_SECRET` env var is per-service. If you changed it in one service but not others, the gateway will reject tokens issued by auth. Set it as a Container Apps Environment-level secret next time, or just keep both `parameters.json` and the deploy command as the single source of truth.

**Vision calls time out:** RunPod cold-start can take 30–60s on the first request after idle. Increase `request_timeout_seconds` on the gateway and `runpod_timeout_seconds` on vision-service, or switch the worker to `/run` + polling (`runpod_async=true`) which doesn't tie up a TCP connection.

**Costs higher than expected:** the most likely culprits are (1) ACR Standard or Premium SKU when Basic was enough, (2) Postgres set above B1ms, (3) Container Apps `minReplicas > 0` on services that don't need to be warm. Check `az consumption usage list` to confirm.

---

## What's not yet automated

These are deliberate "do later when needed" gaps so the first deploy stays simple:

- **Custom domains + TLS.** Container Apps gives you a free `*.azurecontainerapps.io` cert; for a custom domain, add a DNS CNAME and run `az containerapp hostname add` + `az containerapp ssl upload`.
- **VNet integration.** The Postgres flexible server is currently public-with-firewall. For higher security, move it into a VNet and put the Container Apps environment in the same VNet (this requires the workload-profiles environment type, which the Bicep already uses, plus a `/27` subnet).
- **Managed identity for ACR pulls.** Currently uses admin-user credentials. Switch by giving each Container App a system-assigned identity and granting it `AcrPull` on the registry.
- **Backup automation for blob photos.** Geo-replication is off (LRS) for cost. Enable RA-GRS if photos are mission-critical.
- **CI/CD.** Wire `scripts/build-and-push.sh` into GitHub Actions with a service principal that has `Contributor` on the resource group; trigger on tag push.
