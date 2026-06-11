#!/usr/bin/env bash
# Build images, deploy Bicep, and ensure custom domains use managed TLS.
#
# Usage (from repo root):
#   RG=mealtracker-rg PREFIX=mealtracker476a ./scripts/deploy-azure.sh [tag]
#
# Reads secrets from infra/azure/parameters.json (gitignored).
# Override tag: ./scripts/deploy-azure.sh v60

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

RG="${RG:-mealtracker-rg}"
TAG="${1:-}"
PARAMS="${ROOT}/infra/azure/parameters.json"

if [[ -z "${TAG}" ]]; then
  TAG="$(python3 -c "import json; p=json.load(open('${PARAMS}')); print(p['parameters']['imageTag']['value'])")"
  # Bump patch-style vNN tags automatically
  if [[ "${TAG}" =~ ^v([0-9]+)$ ]]; then
    TAG="v$(( ${BASH_REMATCH[1]} + 1 ))"
  else
    TAG="v$(date +%Y%m%d%H%M)"
  fi
fi

PREFIX="$(python3 -c "import json; p=json.load(open('${PARAMS}')); print(p['parameters']['namePrefix']['value'])")"
ACR="$(python3 -c "import re; print(re.sub(r'[^a-z0-9]', '', '${PREFIX}'.lower()) + 'acr')")"
ENV_NAME="${PREFIX}-env"

echo "==> Deploy tag: ${TAG}"
echo "==> Resource group: ${RG}, prefix: ${PREFIX}, ACR: ${ACR}"

echo "==> Building and pushing images"
"${ROOT}/scripts/build-and-push.sh" "${ACR}" "${TAG}"

echo "==> Deploying Bicep (imageTag=${TAG})"
az deployment group create \
  --resource-group "${RG}" \
  --name "deploy-${TAG}" \
  --template-file "${ROOT}/infra/azure/main.bicep" \
  --parameters @"${PARAMS}" \
  --parameters "imageTag=${TAG}"

echo "==> Ensuring custom domains + managed TLS"
RG="${RG}" PREFIX="${PREFIX}" ENV_NAME="${ENV_NAME}" \
  "${ROOT}/scripts/bind-custom-domains.sh"

echo "==> Smoke test"
API_HOST="${API_HOSTNAME:-api.macrossimple.com}"
WEB_HOST="${WEB_HOSTNAME:-macrossimple.com}"
curl -fsS "https://${API_HOST}/healthz" | python3 -m json.tool
echo "Web: https://${WEB_HOST}"
echo "API: https://${API_HOST}"
echo "Deploy complete (${TAG})."
