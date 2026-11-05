#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

: "${AZURE_TENANT_ID:?Set AZURE_TENANT_ID}"
: "${AZURE_WORKLOAD_IDENTITY_CLIENT_ID:?Set the aimie-service workload identity client ID}"
: "${IMAGE_TAG:?Set IMAGE_TAG}"
guid_pattern='^[[:xdigit:]]{8}(-[[:xdigit:]]{4}){3}-[[:xdigit:]]{12}$'
if [[ ! "$AZURE_TENANT_ID" =~ $guid_pattern || ! "$AZURE_WORKLOAD_IDENTITY_CLIENT_ID" =~ $guid_pattern ]]; then
  echo 'Azure tenant and workload identity client IDs must be GUIDs' >&2
  exit 1
fi
if [[ ! "$IMAGE_TAG" =~ ^sha-[[:xdigit:]]{40}$ ]]; then
  echo 'IMAGE_TAG must be sha- followed by a 40-character main commit SHA' >&2
  exit 1
fi

: "${TEST_ACR_LOGIN_SERVER:?Set TEST_ACR_LOGIN_SERVER}"
: "${TEST_KEYVAULT_NAME:?Set TEST_KEYVAULT_NAME}"
: "${TEST_TLS_CERT_NAME:?Set TEST_TLS_CERT_NAME}"
: "${TEST_INGRESS_HOST:?Set TEST_INGRESS_HOST}"
[[ "$TEST_ACR_LOGIN_SERVER" =~ ^[a-z0-9-]+\.azurecr\.io$ ]] || { echo 'Invalid Test ACR hostname' >&2; exit 1; }
[[ "$TEST_KEYVAULT_NAME" =~ ^[a-z0-9-]{3,24}$ && "$TEST_TLS_CERT_NAME" =~ ^[A-Za-z0-9-]+$ ]] || { echo 'Invalid Test vault or certificate name' >&2; exit 1; }
[[ "$TEST_INGRESS_HOST" =~ ^[a-z0-9.-]+\.[a-z]{2,}$ ]] || { echo 'Invalid Test ingress hostname' >&2; exit 1; }

scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
bundle="$scratch/aimie-service.yaml"
first=true
for name in service-account appsettings-secretproviderclass aimie-service ingress.aks-test; do
  if [[ "$first" == false ]]; then printf '\n---\n' >> "$bundle"; fi
  sed \
    -e "s@<workload-identity-client-id>@${AZURE_WORKLOAD_IDENTITY_CLIENT_ID}@g" \
    -e "s@<azure-tenant-id>@${AZURE_TENANT_ID}@g" \
    -e "s@<acr-login-server>@${TEST_ACR_LOGIN_SERVER}@g" \
    -e "s@<key-vault-name>@${TEST_KEYVAULT_NAME}@g" \
    -e "s@<tls-cert-name>@${TEST_TLS_CERT_NAME}@g" \
    -e "s@<ingress-host>@${TEST_INGRESS_HOST}@g" \
    -e "s@aimie-service:latest@aimie-service:${IMAGE_TAG}@g" \
    "k8s/aimie-operations/${name}.yaml" >> "$bundle"
  first=false
done
if grep -qE '<[a-z-]+>|:latest' "$bundle"; then
  echo 'An unresolved deployment placeholder remains' >&2
  exit 1
fi
if [[ "${DRY_RUN:-0}" == 1 ]]; then
  output="${RENDER_OUTPUT:-.local/aimie-service-rendered.yaml}"
  mkdir -p "$(dirname "$output")"
  cp "$bundle" "$output"
  printf 'Rendered test manifests to %s without applying them\n' "$output"
  exit 0
fi

# The Operations repository owns the shared namespace and ingress controller.
bash scripts/aks-run-command.sh "$bundle" \
  'kubectl get namespace aimie-operations >/dev/null && kubectl apply -f aimie-service.yaml && kubectl rollout status deployment/aimie-service -n aimie-operations --timeout=15m'
