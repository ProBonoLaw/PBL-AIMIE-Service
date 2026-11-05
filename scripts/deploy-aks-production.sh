#!/usr/bin/env bash
# Render or manually deploy AIMIE Service into the separate production AKS cluster.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${AZURE_SUBSCRIPTION_ID:?Set the production subscription ID}"
: "${AZURE_TENANT_ID:?Set AZURE_TENANT_ID}"
: "${AZURE_WORKLOAD_IDENTITY_CLIENT_ID:?Set the production workload identity client ID}"
: "${IMAGE_TAG:?Set IMAGE_TAG to a tested sha-<commit> tag}"
: "${PROD_ACR_LOGIN_SERVER:?Set the production ACR login server}"
: "${PROD_KEYVAULT_NAME:?Set the production Key Vault name}"
: "${PROD_TLS_CERT_NAME:?Set the production ingress certificate name}"
: "${PROD_INGRESS_HOST:?Set the production private ingress hostname}"
: "${PROD_AKS_RESOURCE_GROUP:?Set the production AKS resource group}"
: "${PROD_AKS_CLUSTER_NAME:?Set the production AKS cluster name}"

production_subscription=${PROD_AZURE_SUBSCRIPTION_ID:?Set PROD_AZURE_SUBSCRIPTION_ID}
[[ "$AZURE_SUBSCRIPTION_ID" == "$production_subscription" ]] || {
  echo 'Refusing to deploy production resources outside the production subscription' >&2
  exit 1
}
guid_pattern='^[[:xdigit:]]{8}(-[[:xdigit:]]{4}){3}-[[:xdigit:]]{12}$'
[[ "$AZURE_TENANT_ID" =~ $guid_pattern && "$AZURE_WORKLOAD_IDENTITY_CLIENT_ID" =~ $guid_pattern ]] || {
  echo 'Azure tenant and workload identity client IDs must be GUIDs' >&2
  exit 1
}
[[ "$IMAGE_TAG" =~ ^sha-[[:xdigit:]]{40}$ ]] || {
  echo 'IMAGE_TAG must be sha- followed by a 40-character commit SHA' >&2
  exit 1
}
[[ "$PROD_ACR_LOGIN_SERVER" =~ ^[a-z0-9-]+\.azurecr\.io$ ]] || {
  echo 'PROD_ACR_LOGIN_SERVER must be an Azure Container Registry hostname' >&2
  exit 1
}
[[ "$PROD_KEYVAULT_NAME" =~ ^[a-z0-9-]{3,24}$ && "$PROD_TLS_CERT_NAME" =~ ^[A-Za-z0-9-]+$ ]] || {
  echo 'Invalid production Key Vault or certificate name' >&2
  exit 1
}
[[ "$PROD_INGRESS_HOST" =~ ^[a-z0-9.-]+\.[a-z]{2,}$ ]] || {
  echo 'PROD_INGRESS_HOST must be a DNS hostname' >&2
  exit 1
}
[[ "$PROD_AKS_RESOURCE_GROUP" =~ ^[A-Za-z0-9._-]+$ && "$PROD_AKS_CLUSTER_NAME" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo 'Invalid production AKS resource group or cluster name' >&2
  exit 1
}

scratch=$(mktemp -d)
trap 'rm -r -- "$scratch"' EXIT
bundle="$scratch/aimie-service-production.yaml"
first=true
for name in service-account appsettings-secretproviderclass aimie-service ingress; do
  if [[ "$first" == false ]]; then printf '\n---\n' >> "$bundle"; fi
  sed \
    -e "s@<workload-identity-client-id>@${AZURE_WORKLOAD_IDENTITY_CLIENT_ID}@g" \
    -e "s@<azure-tenant-id>@${AZURE_TENANT_ID}@g" \
    -e "s@<acr-login-server>@${PROD_ACR_LOGIN_SERVER}@g" \
    -e "s@<key-vault-name>@${PROD_KEYVAULT_NAME}@g" \
    -e "s@<tls-cert-name>@${PROD_TLS_CERT_NAME}@g" \
    -e "s@<ingress-host>@${PROD_INGRESS_HOST}@g" \
    -e "s@aimie-service:latest@aimie-service:${IMAGE_TAG}@g" \
    "k8s/aimie-operations/production/${name}.yaml" >> "$bundle"
  first=false
done
if grep -qE '<[a-z-]+>|:latest' "$bundle"; then
  echo 'An unresolved production placeholder remains' >&2
  exit 1
fi

if [[ "${DRY_RUN:-0}" == 1 ]]; then
  output=${RENDER_OUTPUT:-.local/aimie-service-production-rendered.yaml}
  mkdir -p "$(dirname "$output")"
  cp "$bundle" "$output"
  printf 'Rendered production manifests to %s without applying them\n' "$output"
  exit 0
fi

current_subscription=$(az account show --query id --output tsv)
[[ "$current_subscription" == "$production_subscription" ]] || {
  echo 'Azure CLI must be logged into the production subscription' >&2
  exit 1
}

# Create the shared namespace only on a cluster where it is absent.
AKS_CLUSTER_RESOURCE_GROUP="$PROD_AKS_RESOURCE_GROUP" AKS_CLUSTER_NAME="$PROD_AKS_CLUSTER_NAME" \
  bash scripts/aks-run-command.sh "$bundle" \
  'if ! kubectl get namespace aimie-operations >/dev/null 2>&1; then kubectl create namespace aimie-operations; fi; kubectl apply -f aimie-service-production.yaml && kubectl rollout status deployment/aimie-service -n aimie-operations --timeout=15m'
