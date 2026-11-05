#!/usr/bin/env bash
# Provision Production workload and GitHub deployment identities and scoped access.
set -euo pipefail
for name in PROD_AKS_CLUSTER_NAME PROD_KEYVAULT_NAME PROD_ACR_NAME TEST_ACR_NAME PROD_ROUTING_IDENTITY_NAME PROD_STORAGE_RESOURCE_GROUP PROD_STORAGE_ACCOUNT PROD_FUNCTION_RESOURCE_GROUP PROD_FUNCTION_APP_NAME PROD_WORKLOAD_IDENTITY_NAME PROD_CI_IDENTITY_NAME; do
  [[ -n "${!name:-}" ]] || { echo "Set $name before provisioning resources" >&2; exit 1; }
done
cd "$(dirname "$0")/.."
subscription=${PROD_AZURE_SUBSCRIPTION_ID:?Set PROD_AZURE_SUBSCRIPTION_ID}
test_subscription=${TEST_AZURE_SUBSCRIPTION_ID:?Set TEST_AZURE_SUBSCRIPTION_ID}
group=${PROD_AKS_RESOURCE_GROUP:?Set PROD_AKS_RESOURCE_GROUP}
repository=${DEPLOYMENT_REPOSITORY:?Set DEPLOYMENT_REPOSITORY}
settings=${APPSETTINGS_FILE:-.local/appsettings.aks-production.json}
python3 scripts/configure-aks-production.py validate --file "$settings"
az_prod() { az "$@" --subscription "$subscription" --only-show-errors; }
az_test() { az "$@" --subscription "$test_subscription" --only-show-errors; }

ensure_identity() {
  if ! az_prod identity show -g "$group" -n "$1" -o none 2>/dev/null; then
    az_prod identity create -g "$group" -n "$1" -o none
  fi
}
ensure_federation() {
  local identity="$1" name="$2" issuer="$3" subject="$4"
  if ! az_prod identity federated-credential show -g "$group" --identity-name "$identity" -n "$name" -o none 2>/dev/null; then
    az_prod identity federated-credential create -g "$group" --identity-name "$identity" -n "$name" \
      --issuer "$issuer" --subject "$subject" --audiences api://AzureADTokenExchange -o none
  fi
}
assign_role() {
  local principal="$1" role="$2" scope="$3" count
  count=$(az_prod role assignment list --assignee-object-id "$principal" --scope "$scope" \
    --role "$role" --query 'length(@)' -o tsv)
  if [[ "$count" == 0 ]]; then
    az_prod role assignment create --assignee-object-id "$principal" \
      --assignee-principal-type ServicePrincipal --role "$role" --scope "$scope" -o none
  fi
}

workload=${PROD_WORKLOAD_IDENTITY_NAME:?Set PROD_WORKLOAD_IDENTITY_NAME}
ci=${PROD_CI_IDENTITY_NAME:?Set PROD_CI_IDENTITY_NAME}
ensure_identity "$workload"
ensure_identity "$ci"
workload_client=$(az_prod identity show -g "$group" -n "$workload" --query clientId -o tsv)
workload_principal=$(az_prod identity show -g "$group" -n "$workload" --query principalId -o tsv)
ci_client=$(az_prod identity show -g "$group" -n "$ci" --query clientId -o tsv)
ci_principal=$(az_prod identity show -g "$group" -n "$ci" --query principalId -o tsv)
issuer=$(az_prod aks show -g "$group" -n "${PROD_AKS_CLUSTER_NAME:?Set PROD_AKS_CLUSTER_NAME}" --query oidcIssuerProfile.issuerUrl -o tsv)
[[ "$issuer" == https://* ]] || { echo 'Production AKS OIDC issuer is disabled' >&2; exit 1; }
ensure_federation "$workload" aks-aimie-service-prod "$issuer" \
  system:serviceaccount:aimie-operations:aimie-service
ensure_federation "$ci" github-aimie-service-prod https://token.actions.githubusercontent.com \
  "${GITHUB_OIDC_SUBJECT:-repo:${repository}:environment:aks-production}"

vault_id=$(az_prod keyvault show -n "${PROD_KEYVAULT_NAME:?Set PROD_KEYVAULT_NAME}" --query id -o tsv)
prod_acr_id=$(az_prod acr show -n "${PROD_ACR_NAME:?Set PROD_ACR_NAME}" --query id -o tsv)
test_acr_id=$(az_test acr show -n "${TEST_ACR_NAME:?Set TEST_ACR_NAME}" --query id -o tsv)
aks_id=$(az_prod aks show -g "$group" -n "${PROD_AKS_CLUSTER_NAME:?Set PROD_AKS_CLUSTER_NAME}" --query id -o tsv)
kubelet_principal=$(az_prod aks show -g "$group" -n "${PROD_AKS_CLUSTER_NAME:?Set PROD_AKS_CLUSTER_NAME}" --query identityProfile.kubeletidentity.objectId -o tsv)
routing_principal=$(az_prod identity list --query "[?name=='${PROD_ROUTING_IDENTITY_NAME:?Set PROD_ROUTING_IDENTITY_NAME}'].principalId | [0]" -o tsv)
assign_role "$workload_principal" 'Key Vault Secrets User' "$vault_id/secrets/aimie-service-appsettings"
assign_role "$routing_principal" 'Key Vault Secrets User' "$vault_id"
assign_role "$kubelet_principal" AcrPull "$prod_acr_id"
assign_role "$ci_principal" Reader "$test_acr_id"
assign_role "$ci_principal" AcrPull "$test_acr_id"
assign_role "$ci_principal" Reader "$prod_acr_id"
assign_role "$ci_principal" AcrPush "$prod_acr_id"
assign_role "$ci_principal" 'Azure Kubernetes Service Contributor Role' "$aks_id"
assign_role "$ci_principal" 'Azure Kubernetes Service RBAC Cluster Admin' "$aks_id"

storage_id=$(az_prod storage account show -g "${PROD_STORAGE_RESOURCE_GROUP:?Set storage resource group}" -n "${PROD_STORAGE_ACCOUNT:?Set PROD_STORAGE_ACCOUNT}" --query id -o tsv)
agents_scope="$storage_id/blobServices/default/containers/agents"
assign_role "$ci_principal" 'Storage Blob Data Contributor' "$agents_scope"
assign_role "$workload_principal" 'Storage Blob Data Owner' "$storage_id"
assign_role "$workload_principal" 'Storage Queue Data Contributor' "$storage_id"
assign_role "$workload_principal" 'Storage Table Data Contributor' "$storage_id"

source_principal=$(az_prod functionapp identity show -g "${PROD_FUNCTION_RESOURCE_GROUP:?Set PROD_FUNCTION_RESOURCE_GROUP}" -n "${PROD_FUNCTION_APP_NAME:?Set PROD_FUNCTION_APP_NAME}" --query principalId -o tsv)
[[ -n "$source_principal" && "$source_principal" != null ]] || { echo 'Production Function identity is missing' >&2; exit 1; }
role_rows=$(az_prod role assignment list --assignee-object-id "$source_principal" --all -o json | \
  python3 -c 'import json,sys
for row in json.load(sys.stdin):
    if row["roleDefinitionName"] in {"Search Index Data Reader", "Search Index Data Contributor", "Search Service Contributor"}:
        print(row["roleDefinitionName"] + "\t" + row["scope"])')
while IFS=$'\t' read -r role scope; do
  [[ -z "$role" ]] || assign_role "$workload_principal" "$role" "$scope"
done <<< "$role_rows"

account=$(python3 - "$settings" <<'PY'
import json,sys
from urllib.parse import urlsplit
settings=json.load(open(sys.argv[1]))
accounts={urlsplit(settings[key]).hostname.split('.')[0] for key in
          ('ACCOUNT_COSMOS_ENDPOINT','COSMOS_MESSAGE_HISTORY_ENDPOINT')}
if len(accounts) != 1: raise SystemExit('Expected one production Cosmos account')
print(accounts.pop())
PY
)
cosmos_group=$(az_prod cosmosdb list --query "[?name=='${account}'].resourceGroup | [0]" -o tsv)
[[ -n "$cosmos_group" ]] || { echo 'Production Cosmos account is missing' >&2; exit 1; }
count=$(az_prod cosmosdb sql role assignment list -g "$cosmos_group" -a "$account" -o json | \
  python3 -c 'import json,sys
print(sum(row["principalId"] == sys.argv[1] and row["roleDefinitionId"].endswith("/00000000-0000-0000-0000-000000000002") for row in json.load(sys.stdin)))' "$workload_principal")
if [[ "$count" == 0 ]]; then
  az_prod cosmosdb sql role assignment create -g "$cosmos_group" -a "$account" \
    --role-definition-id 00000000-0000-0000-0000-000000000002 \
    --principal-id "$workload_principal" --scope / -o none
fi
printf 'AZURE_CLIENT_ID=%s\nAZURE_WORKLOAD_IDENTITY_CLIENT_ID=%s\n' "$ci_client" "$workload_client"
