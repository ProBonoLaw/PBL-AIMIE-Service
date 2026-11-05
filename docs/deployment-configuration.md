# Deployment configuration

Public CI uses synthetic values. Set real GitHub **variables** only in the original
private repository. Variables are configuration, not encrypted or automatically
masked secrets: public workflow logs, generated manifests and artifacts can reveal
their values. Private resources and the private synchronization destination must
remain on the private side. API keys, access tokens, signed URLs and passwords
belong in GitHub **secrets** or Key Vault, not variables.

Set `ENABLE_PRIVATE_DEPLOYMENTS=true` as a private **repository variable** after
configuring environment approvals and credentials. Job admission checks repository
visibility as well as this flag; environment-scoped flags are not available at
that stage. Public deployments stay disabled even if the flag is accidentally set.

## Workflow variables

| Environment | Variables | Purpose |
| --- | --- | --- |
| `aks-test` | `AZURE_CLIENT_ID`, `AKS_DEPLOY_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | OIDC login; CI and deploy identities may be distinct |
| `aks-test` | `TEST_AZURE_SUBSCRIPTION_ID` | Expected Test subscription; must match login subscription |
| `aks-test` | `AZURE_WORKLOAD_IDENTITY_CLIENT_ID` | Application workload identity |
| `aks-test` | `AKS_CLUSTER_RESOURCE_GROUP`, `AKS_CLUSTER_NAME` | Test cluster |
| `aks-test` | `TEST_ACR_NAME`, `TEST_ACR_LOGIN_SERVER` | Test registry resource and hostname |
| `aks-test` | `TEST_STORAGE_ACCOUNT` | Configuration and Durable storage account |
| `aks-test` | `TEST_KEYVAULT_NAME`, `TEST_TLS_CERT_NAME`, `TEST_INGRESS_HOST` | Test ingress and appsettings |
| `aks-production` | `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_WORKLOAD_IDENTITY_CLIENT_ID` | Production OIDC and workload identities |
| `aks-production` | `PROD_AZURE_SUBSCRIPTION_ID`, `TEST_AZURE_SUBSCRIPTION_ID` | Expected Production subscription and source Test subscription |
| `aks-production` | `PROD_ACR_NAME`, `TEST_ACR_NAME`, `TEST_ACR_LOGIN_SERVER` | Image promotion targets |
| `aks-production` | `PROD_STORAGE_ACCOUNT` | Production configuration and Durable storage account |
| `aks-production` | `PROD_AKS_RESOURCE_GROUP`, `PROD_AKS_CLUSTER_NAME` | Production cluster |
| `aks-production` | `PROD_KEYVAULT_NAME`, `TEST_KEYVAULT_NAME`, `PROD_TLS_CERT_NAME`, `PROD_INGRESS_HOST` | Production ingress and separation from Test |

The production workflow derives `PROD_ACR_LOGIN_SERVER` from Azure. Set it yourself
for local rendering. Local scripts read environment variables; GitHub variables
are mapped into those variables by the workflows. GitHub variables are not
automatically available to the deployed application. Application settings continue
to come from the private Key Vault appsettings secret.

## SharePoint example

All previously committed document links were removed together with their sensitive
source text. There are no hardcoded tenant names, site IDs or library paths.
`test.py` uses a wholly synthetic document and accepts the optional
`SHAREPOINT_EXAMPLE_DOCUMENT_URL` environment variable. Without it, the example
uses a reserved `example.invalid` URL and requires no private data.

For private validation, create the `private-integration` environment variable
`SHAREPOINT_EXAMPLE_DOCUMENT_URL` containing the complete unsigned HTTPS document
URL. Set the private repository variable `ENABLE_PRIVATE_INTEGRATION_TESTS=true`
and manually run `Validate private source configuration`. The workflow maps:

```yaml
env:
  SHAREPOINT_EXAMPLE_DOCUMENT_URL: ${{ vars.SHAREPOINT_EXAMPLE_DOCUMENT_URL }}
```

The example validates serialization without downloading the document or printing
the configured URL. It rejects URLs containing credentials, query strings or
fragments. Any future authenticated document fetching must use secrets for
credentials. This variable configures the example; production source URLs remain
data supplied by the search index, not hardcoded application settings.

## Administrative scripts

Supply the workflow variables above as local environment variables, plus these
only for the administrative operations that need them:

| Variables | Used by |
| --- | --- |
| `DEPLOYMENT_REPOSITORY` (`owner/repository`), optional `GITHUB_OIDC_SUBJECT` | GitHub OIDC bootstrap; use the private deployment repository |
| `TEST_IDENTITY_RESOURCE_GROUP` | Test workload and CI identity bootstrap |
| `TEST_WORKLOAD_IDENTITY_NAME`, `TEST_CI_IDENTITY_NAME` | Test identity resource names |
| `PROD_WORKLOAD_IDENTITY_NAME`, `PROD_CI_IDENTITY_NAME` | Production identity resource names |
| `TEST_STORAGE_RESOURCE_GROUP`, `PROD_STORAGE_RESOURCE_GROUP` | Storage role bootstrap |
| `TEST_FUNCTION_RESOURCE_GROUP`, `TEST_FUNCTION_APP_NAME` | Test settings export and role bootstrap |
| `PROD_FUNCTION_RESOURCE_GROUP`, `PROD_FUNCTION_APP_NAME` | Production settings export and role bootstrap |
| `PROD_ROUTING_IDENTITY_NAME` | Production ingress identity bootstrap |
| `TEST_CA_VAULT_NAME`, `TEST_CA_CERT_NAME` | Test certificate signing and import |

Store local configuration under ignored `.local/` or `.env` files. Before enabling
deployment, migrate the former hardcoded values into these private variables.
Missing configuration intentionally fails instead of using old infrastructure.
