# AIMIE Service on AKS Production

Production uses a separate subscription, cluster, registry, Key Vault, identities,
certificate, task hub and Functions host ID. All resource identifiers are supplied
through [private environment configuration](deployment-configuration.md).

The manual `Promote and deploy AKS Production` workflow is restricted to `main`, a
private repository, and `ENABLE_PRIVATE_DEPLOYMENTS=true`. Configure approval rules
on the `aks-production` GitHub environment before enabling it.

## Preparation

Provision AKS with OIDC, workload identity, Key Vault CSI and internal ingress. The
kubelet identity needs registry pull access. The application workload identity
needs secret read access, Search and Cosmos roles, and Storage Blob Data Owner,
Storage Queue Data Contributor and Storage Table Data Contributor on
`PROD_STORAGE_ACCOUNT`. The CI identity needs pull access to Test ACR, push access
to Production ACR, and deployment permissions on the Production cluster.
`scripts/bootstrap-aks-production.sh` prepares the identities and roles using the
configured targets. Keep its OIDC subject scoped to the private repository and
`aks-production` environment.

Export allowlisted settings using `python scripts/configure-aks-production.py export`.
Review the ignored `.local/appsettings.aks-production.json`, validate it, then use
`publish --vault-name "$PROD_KEYVAULT_NAME"`. The preparation uses
`PROD_STORAGE_ACCOUNT` for configurations and identity-based Durable storage.
`consolidate-storage` updates an earlier export; `configure-agents` changes only
the configuration endpoint. These operations do not move existing blobs or
orchestration history. The publisher rejects the configured Test vault.

Configure private DNS and a certificate for `PROD_INGRESS_HOST`, and establish CA
trust in clients before cutover. Keep infrastructure details in the private
deployment environment rather than in this repository.

## Promotion

The workflow accepts `latest` or a tested `sha-<40-character commit>` tag from Test
ACR. It resolves the tag to a digest and a commit on `main`, verifies separate Test
and Production resources, and copies those image bytes into Production ACR.
`latest` identifies the latest tested/published image; it does not attest that the
Test rollout succeeded. A fresh public initial commit changes commit IDs, so build
new images after establishing the public-to-private history relationship.

Agent configurations come from the checked-out `main`, even when selecting an
older image. They are uploaded before deployment through the running Production
pod with workload identity; first deployment needs an initial upload from a
network with storage access. Blob uploads are not atomic. A failure stops the
deployment, and unchanged blob names are preserved.

For a local render, set the variables documented in the configuration guide and:

```bash
DRY_RUN=1 bash scripts/deploy-aks-production.sh
python scripts/validate-aks-manifests.py .local/aimie-service-production-rendered.yaml production
```

The renderer verifies `AZURE_SUBSCRIPTION_ID` against `PROD_AZURE_SUBSCRIPTION_ID`.
Manifest validation requires `TEST_ACR_LOGIN_SERVER` and `TEST_KEYVAULT_NAME` to
check separation. The deployment uses `AimieServiceAksProduction` and
`aimie-service-aks-production` for Durable and host-key isolation.

## Cutover and rollback

Before changing a running deployment's storage, pause new requests, drain active
work, preserve previous settings and copy and verify configuration blobs. Retain
old storage and host keys for outstanding orchestration status URLs. Restart and
verify scheduling, polling, state persistence and host-key stability before
restoring traffic. Switch callers only after the new endpoint is healthy. Keep
the original Function App running until its workflows complete.
