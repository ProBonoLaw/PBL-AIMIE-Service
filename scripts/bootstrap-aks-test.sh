#!/usr/bin/env bash
# Provision the service's identity and data access. This script writes Azure resources when run.
set -euo pipefail
for name in TEST_KEYVAULT_NAME TEST_FUNCTION_RESOURCE_GROUP TEST_FUNCTION_APP_NAME TEST_STORAGE_RESOURCE_GROUP TEST_STORAGE_ACCOUNT; do
  [[ -n "${!name:-}" ]] || { echo "Set $name before provisioning resources" >&2; exit 1; }
done
cd "$(dirname "$0")/.."
subscription=${TEST_AZURE_SUBSCRIPTION_ID:?Set TEST_AZURE_SUBSCRIPTION_ID}
group=${TEST_IDENTITY_RESOURCE_GROUP:?Set TEST_IDENTITY_RESOURCE_GROUP}
cluster_group=${AKS_CLUSTER_RESOURCE_GROUP:?Set AKS_CLUSTER_RESOURCE_GROUP}
cluster_name=${AKS_CLUSTER_NAME:?Set AKS_CLUSTER_NAME}
identity=${TEST_WORKLOAD_IDENTITY_NAME:?Set TEST_WORKLOAD_IDENTITY_NAME}
settings=${APPSETTINGS_FILE:-.local/appsettings.aks-test.json}
python3 scripts/configure-aks-test.py validate --file "$settings"
az_test() { az "$@" --subscription "$subscription" --only-show-errors; }

if ! az_test identity show -g "$group" -n "$identity" -o none 2>/dev/null; then
  az_test identity create -g "$group" -n "$identity" -o none
fi
client_id=$(az_test identity show -g "$group" -n "$identity" --query clientId -o tsv)
principal_id=$(az_test identity show -g "$group" -n "$identity" --query principalId -o tsv)
issuer=$(az_test aks show -g "$cluster_group" -n "$cluster_name" --query oidcIssuerProfile.issuerUrl -o tsv)
[[ "$issuer" == https://* ]] || { echo 'AKS OIDC issuer is not enabled' >&2; exit 1; }
if ! az_test identity federated-credential show -g "$group" --identity-name "$identity" \
  -n aks-aimie-service-test -o none 2>/dev/null; then
  az_test identity federated-credential create -g "$group" --identity-name "$identity" \
    -n aks-aimie-service-test --issuer "$issuer" \
    --subject system:serviceaccount:aimie-operations:aimie-service \
    --audiences api://AzureADTokenExchange -o none
fi

assign_role() {
  local role="$1" scope="$2" count
  [[ "$scope" == /subscriptions/* ]] || { echo 'Invalid role assignment scope' >&2; exit 1; }
  count=$(az_test role assignment list --assignee-object-id "$principal_id" \
    --scope "$scope" --role "$role" --query 'length(@)' -o tsv)
  if [[ "$count" == 0 ]]; then
    az_test role assignment create --assignee-object-id "$principal_id" \
      --assignee-principal-type ServicePrincipal --role "$role" --scope "$scope" -o none
  fi
}
vault_id=$(az_test keyvault show -n "${TEST_KEYVAULT_NAME:?Set TEST_KEYVAULT_NAME}" --query id -o tsv)
assign_role 'Key Vault Secrets User' "$vault_id/secrets/aimie-service-appsettings"

# Copy only the existing app's Search roles, at their existing scopes.
source_principal=$(az_test functionapp identity show -g "${TEST_FUNCTION_RESOURCE_GROUP:?Set TEST_FUNCTION_RESOURCE_GROUP}" -n "${TEST_FUNCTION_APP_NAME:?Set TEST_FUNCTION_APP_NAME}" \
  --query principalId -o tsv)
[[ -n "$source_principal" && "$source_principal" != null ]] || { echo 'Source Function identity is missing' >&2; exit 1; }
role_rows=$(az_test role assignment list --assignee-object-id "$source_principal" --all -o json | \
  python3 -c 'import json,sys
for row in json.load(sys.stdin):
    if row["roleDefinitionName"] in {"Search Index Data Reader", "Search Service Contributor"}:
        print(row["roleDefinitionName"] + "\t" + row["scope"])')
while IFS=$'\t' read -r role scope; do
  [[ -z "$role" ]] || assign_role "$role" "$scope"
done <<< "$role_rows"

# Functions host keys and Durable state use workload identity on the shared account.
storage_id=$(az_test storage account show -g "${TEST_STORAGE_RESOURCE_GROUP:?Set storage resource group}" -n "${TEST_STORAGE_ACCOUNT:?Set TEST_STORAGE_ACCOUNT}" --query id -o tsv)
assign_role 'Storage Blob Data Owner' "$storage_id"
assign_role 'Storage Queue Data Contributor' "$storage_id"
assign_role 'Storage Table Data Contributor' "$storage_id"

# Cosmos SQL data-plane permissions are separate from Azure RBAC assignments.
cosmos_accounts=$(python3 - "$settings" <<'PY'
import json,sys
from urllib.parse import urlsplit
settings=json.load(open(sys.argv[1]))
for account in sorted({urlsplit(settings[key]).hostname.split('.')[0] for key in
                       ('ACCOUNT_COSMOS_ENDPOINT','COSMOS_MESSAGE_HISTORY_ENDPOINT')}):
    print(account)
PY
)
while IFS= read -r account; do
  cosmos_group=$(az_test cosmosdb list --query "[?name=='${account}'].resourceGroup | [0]" -o tsv)
  [[ -n "$cosmos_group" ]] || { echo "Cannot find configured Cosmos account $account" >&2; exit 1; }
  cosmos_id=$(az_test cosmosdb show -g "$cosmos_group" -n "$account" --query id -o tsv)
  count=$(az_test cosmosdb sql role assignment list -g "$cosmos_group" -a "$account" -o json | \
    python3 -c 'import json,sys
print(sum(row["principalId"] == sys.argv[1] and row["scope"].rstrip("/").lower() in {"", sys.argv[2].lower()} and
          row["roleDefinitionId"].endswith("/00000000-0000-0000-0000-000000000002")
          for row in json.load(sys.stdin)))' "$principal_id" "$cosmos_id")
  if [[ "$count" == 0 ]]; then
    az_test cosmosdb sql role assignment create -g "$cosmos_group" -a "$account" \
      --role-definition-id 00000000-0000-0000-0000-000000000002 \
      --principal-id "$principal_id" --scope / -o none
  fi
done <<< "$cosmos_accounts"
printf 'Set aks-test environment AZURE_WORKLOAD_IDENTITY_CLIENT_ID=%s\n' "$client_id"
printf 'Durable storage and host keys use workload identity with Blob, Queue and Table data roles.\n'
