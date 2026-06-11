#!/usr/bin/env bash
# Bind custom domains to Container Apps with Azure-managed TLS certificates.
# Idempotent: skips hostnames that are already bound with SniEnabled.
#
# Usage:
#   RG=mealtracker-rg PREFIX=mealtracker476a ./scripts/bind-custom-domains.sh
#
# Optional overrides:
#   WEB_HOSTNAME=macrossimple.com
#   WWW_HOSTNAME=www.macrossimple.com
#   API_HOSTNAME=api.macrossimple.com

set -euo pipefail

RG="${RG:?Set RG (resource group name)}"
PREFIX="${PREFIX:?Set PREFIX (namePrefix from Bicep)}"
ENV_NAME="${ENV_NAME:-${PREFIX}-env}"
WEB_HOSTNAME="${WEB_HOSTNAME:-macrossimple.com}"
WWW_HOSTNAME="${WWW_HOSTNAME:-www.${WEB_HOSTNAME}}"
API_HOSTNAME="${API_HOSTNAME:-api.${WEB_HOSTNAME}}"

is_bound() {
  local app="$1" host="$2"
  az containerapp hostname list -g "${RG}" -n "${app}" -o json \
    | python3 -c "
import json, sys
host = sys.argv[1]
for row in json.load(sys.stdin):
    if row.get('name') == host and row.get('bindingType') == 'SniEnabled':
        sys.exit(0)
sys.exit(1)
" "${host}"
}

bind_hostname() {
  local app="$1" host="$2" method="$3"
  if is_bound "${app}" "${host}"; then
    echo "==> ${host} already bound on ${app} (managed TLS)"
    return 0
  fi
  echo "==> Adding ${host} to ${app}"
  az containerapp hostname add -g "${RG}" -n "${app}" --hostname "${host}" 2>/dev/null || true
  echo "==> Binding ${host} on ${app} (validation=${method}, managed certificate)"
  az containerapp hostname bind \
    -g "${RG}" -n "${app}" \
    --environment "${ENV_NAME}" \
    --hostname "${host}" \
    --validation-method "${method}"
}

echo "Binding web hostnames on ${PREFIX}-web"
bind_hostname "${PREFIX}-web" "${WEB_HOSTNAME}" HTTP
bind_hostname "${PREFIX}-web" "${WWW_HOSTNAME}" CNAME

echo "Binding API hostname on ${PREFIX}-gateway"
bind_hostname "${PREFIX}-gateway" "${API_HOSTNAME}" CNAME

echo "Done. Managed certificates auto-renew."
