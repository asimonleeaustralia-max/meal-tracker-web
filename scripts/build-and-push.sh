#!/usr/bin/env bash
# Build all service images and push them to your Azure Container Registry.
#
# Usage:
#   ./scripts/build-and-push.sh <acr-name> <tag>
#
# Run from the repo root.

set -euo pipefail

ACR="${1:?Usage: $0 <acr-name> <tag>}"
TAG="${2:?Usage: $0 <acr-name> <tag>}"
REGISTRY="${ACR}.azurecr.io"

echo "==> Logging in to ${REGISTRY}"
az acr login --name "${ACR}"

services=(api-gateway auth-service meal-service nutrition-service vision-service web-frontend)
for svc in "${services[@]}"; do
  image="${REGISTRY}/mealtracker/${svc}:${TAG}"
  echo "==> Building ${image}"
  build_args=(--platform linux/amd64)
  if [[ "${svc}" == "web-frontend" ]]; then
    build_args+=(--build-arg "BUILD_VERSION=${TAG}")
  fi
  docker build \
    -f "services/${svc}/Dockerfile" \
    -t "${image}" \
    "${build_args[@]}" \
    .
  echo "==> Pushing  ${image}"
  docker push "${image}"
done

echo "Done. Set imageTag=${TAG} in parameters.json and redeploy the Bicep."
