# AIMIE Service on AKS Test

This deployment retains the Python Azure Functions host, Durable Functions,
generation code, API paths and Cosmos checkpoints. `/api/healthz` confirms that the
host has indexed the application; it does not check every external dependency.

Configure the variables in [deployment configuration](deployment-configuration.md).
No script contains a default subscription, cluster, storage account, private
hostname or vault. The shared namespace is `aimie-operations`; this repository owns
only its `aimie-service` resources. Provision the namespace, ingress controller,
registry, storage, Key Vault CSI driver, OIDC and workload identity first.

## Settings and identities

`python scripts/configure-aks-test.py export` exports allowlisted settings from the
configured Function App to ignored `.local/appsettings.aks-test.json`, without
printing values. The export consolidates configuration and Durable storage onto
`TEST_STORAGE_ACCOUNT`. `validate`, `consolidate-storage`, and `publish` operate on
that private file. Publication writes `aimie-service-appsettings` to
`TEST_KEYVAULT_NAME`; restart the service to load updated environment settings.

Run `scripts/bootstrap-aks-test.sh` for workload identity and
`scripts/bootstrap-github-oidc-test.sh` for CI identity after setting their variables.
These scripts change Azure resources. The workload identity needs Key Vault secret
read access, appropriate Search and Cosmos roles, and Storage Blob Data Owner,
Storage Queue Data Contributor and Storage Table Data Contributor on the shared
account. The CI identity needs registry push and AKS deployment permissions. Keep
OIDC federation scoped to the private repository and `aks-test` environment.

## Certificates and ingress

Set `TEST_INGRESS_HOST`, `TEST_CA_VAULT_NAME`, `TEST_CA_CERT_NAME`,
`TEST_KEYVAULT_NAME`, and `TEST_TLS_CERT_NAME`. The prepare, sign, and import
certificate scripts create their private files under `.local/`. The signer uses a
Key Vault CA key without exporting it. Supply a signed leaf certificate to
`scripts/import-aks-test-certificate.sh --cert <path> --dry-run` to validate the key,
hostname, validity and CA chain before importing. Private DNS must route the
configured ingress hostname to the internal ingress load balancer; clients must
trust the issuing CA. Keep certificates, private keys, DNS details and case data
out of Git.

## Deployment and validation

With private deployments enabled, a push to `main` builds, tests and publishes a
commit-tagged image, uploads agent configurations through the existing AIMIE pod,
then applies manifests. First deployment needs an initial configuration upload
from a network that can reach storage. The pod uses workload identity and private
networking for subsequent uploads. There is no fallback to a developer's active
subscription or a hardcoded cluster.

For local review, set the rendering variables and an immutable `IMAGE_TAG`, then:

```bash
DRY_RUN=1 bash scripts/deploy-aks-test.sh
python scripts/validate-aks-manifests.py .local/aimie-service-rendered.yaml
```

The deployment uses the `AimieServiceAksTest` task hub and `aimie-service-aks-test`
host ID. Before changing storage on a running service, pause new work, drain
orchestrations, preserve previous settings, copy and verify agent configurations,
and verify host keys and Durable state after restart. Settings changes do not copy
orchestration history. Keep the original Function App and its storage available
until existing orchestration status URLs are no longer needed.
