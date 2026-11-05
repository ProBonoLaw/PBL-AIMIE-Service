#!/usr/bin/env bash
# Provision this repository's publishing/deployment identity. Does not deploy the application.
set -euo pipefail
for name in TEST_ACR_NAME TEST_STORAGE_RESOURCE_GROUP TEST_STORAGE_ACCOUNT; do
  [[ -n "${!name:-}" ]] || { echo "Set $name before provisioning resources" >&2; exit 1; }
done
subscription=${TEST_AZURE_SUBSCRIPTION_ID:?Set TEST_AZURE_SUBSCRIPTION_ID}
group=${TEST_IDENTITY_RESOURCE_GROUP:?Set TEST_IDENTITY_RESOURCE_GROUP}
cluster_group=${AKS_CLUSTER_RESOURCE_GROUP:?Set AKS_CLUSTER_RESOURCE_GROUP}
cluster_name=${AKS_CLUSTER_NAME:?Set AKS_CLUSTER_NAME}
identity=${TEST_CI_IDENTITY_NAME:?Set TEST_CI_IDENTITY_NAME}
repository=${DEPLOYMENT_REPOSITORY:?Set DEPLOYMENT_REPOSITORY}
az_test() { az "$@" --subscription "$subscription" --only-show-errors; }

# Match Operations' discovery of the organization's OIDC subject prefix.
# An explicit override supports installations where gh is not authenticated locally.
subject=${GITHUB_OIDC_SUBJECT:-}
if [[ -z "$subject" ]]; then
  prefix=$(gh api "repos/$repository/actions/oidc/customization/sub" | python3 -c 'import json,sys
config=json.load(sys.stdin)
print(config.get("sub_claim_prefix") or ("repo:"+sys.argv[1] if config.get("use_default") else ""))' "$repository")
  [[ -n "$prefix" && "$prefix" != null ]] || {
    echo 'Set GITHUB_OIDC_SUBJECT to this repository aks-test environment token subject' >&2
    exit 1
  }
  subject="${prefix}:environment:aks-test"
fi
if ! az_test identity show -g "$group" -n "$identity" -o none 2>/dev/null; then
  az_test identity create -g "$group" -n "$identity" -o none
fi
client_id=$(az_test identity show -g "$group" -n "$identity" --query clientId -o tsv)
principal_id=$(az_test identity show -g "$group" -n "$identity" --query principalId -o tsv)
if ! az_test identity federated-credential show -g "$group" --identity-name "$identity" \
  -n aimie-service-aks-test -o none 2>/dev/null; then
  az_test identity federated-credential create -g "$group" --identity-name "$identity" \
    -n aimie-service-aks-test --issuer https://token.actions.githubusercontent.com \
    --subject "$subject" --audiences api://AzureADTokenExchange -o none
fi

assign_role() {
  local role="$1" scope="$2" count
  count=$(az_test role assignment list --assignee-object-id "$principal_id" \
    --scope "$scope" --role "$role" --query 'length(@)' -o tsv)
  if [[ "$count" == 0 ]]; then
    az_test role assignment create --assignee-object-id "$principal_id" \
      --assignee-principal-type ServicePrincipal --role "$role" --scope "$scope" -o none
  fi
}
acr_id=$(az_test acr show -g "$group" -n "${TEST_ACR_NAME:?Set TEST_ACR_NAME}" --query id -o tsv)
aks_id=$(az_test aks show -g "$cluster_group" -n "$cluster_name" --query id -o tsv)
assign_role AcrPush "$acr_id"
assign_role Reader "$acr_id"
assign_role 'Azure Kubernetes Service Contributor Role' "$aks_id"
# Same CI permissions as Operations; this identity is distinct from the workload identity.
assign_role 'Azure Kubernetes Service RBAC Cluster Admin' "$aks_id"
storage_id=$(az_test storage account show -g "${TEST_STORAGE_RESOURCE_GROUP:?Set storage resource group}" -n "${TEST_STORAGE_ACCOUNT:?Set TEST_STORAGE_ACCOUNT}" --query id -o tsv)
assign_role 'Storage Blob Data Contributor' "$storage_id/blobServices/default/containers/agents"
printf 'Set aks-test AZURE_CLIENT_ID and AKS_DEPLOY_CLIENT_ID to %s\n' "$client_id"
printf 'Set aks-test AZURE_SUBSCRIPTION_ID=%s\n' "$subscription"
az_test account show --query tenantId -o tsv
