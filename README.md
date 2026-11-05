# AI Moderator and Intuitive Engagement Service
## aka AIMIE Service

### Objective
This service is used to drive communications between various services and our LLMs.

### Requirements
* Visual Studio Code installed.
* Understanding of Azure Functions, especially with Durable Function SDK.
* You have all of the endpoint and API keys.
* Install Azure CLI
* Install Azure Functions Core Tools via npm: `npm i -g azure-functions-core-tools@4 --unsafe-perm true`

### Configuration
1. Ensure you create a `local.settings.json` file in your base folder.
2. In the `local.settings.json` file, you will need two first level properties: `IsEncrypted` and `Values`.
    * `IsEncrypted` can be set to `false`, as you're instance should be protected in a Dev Containter.
    * `Values` will have be an property bag object.
3. For `Values` you will need the following properties configured:

| Property Name | Description | Default Value | Notes |
|---|---|---|---|
| `AzureWebJobsStorage__accountName` | Storage account for Durable state and Functions host keys, authenticated with Azure RBAC | Your storage account name | Use `az login` locally; AKS uses its projected workload identity. Remove `AzureWebJobsStorage` when using this setting. |
| `AzureWebJobsStorage` | Connection string alternative for Durable storage | Omitted for Test | May be used for Azurite locally or environments still using an account key; do not combine with identity-based storage settings. |
| `FUNCTIONS_WORKER_RUNTIME` | The name of the languge/platform used by Azure Functions | `python` | Do not change, unless there is a significant change to the service model.|
| `FUNCTIONS_EXTENSION_VERSION` | The version of Azure Functions developed | `~2` | Do not change, unless there is a significant change to the service model.|
| `OPENAI_API_VERSION` | The version of Azure OpenAI API used. | `2024-08-01-preview` | |
| `SEMANTIC_CONFIGURATION_NAME` | The Azure Search config name for Semantic lookups | `Primary` | Do not change unless it is necessary |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint for LLM. | Set `AZURE_OPENAI_ENDPOINT` | This is used in Development.  This may change in the future. |
| `AZURE_OPENAI_API_KEY` | Azure Open AI Key for access to LLM. | **Cannot be empty** | Set through your private secret store |
| `ACCOUNT_COSMOS_ENDPOINT` | The data repository for sessional chat history for each account. | Your Cosmos DB account URL | This is used for development.  Production endpoint TBD. |
| `COSMOS_MESSAGE_HISTORY_DATABASE` | The name of the CosmosDb database | Set for your deployment | This is used in Development.  This may change in the future. |
| `COSMOS_MESSAGE_HISTORY_CONTAINER` | The name of the CosmosDb container | Set for your deployment | This is used in Development.  This may change in the future. |
| `COSMOS_MESSAGE_HISTORY_ENDPOINT` | The data repository for basic account information. | Your Cosmos DB account URL | This is used for development.  Production endpoint TBD. |
| `ACCOUNT_COSMOS_DATABASE` | The name of the CosmosDb database that contains account information | Set for your deployment | This is used in Development.  This may change in the future. |
| `ACCOUNT_COSMOS_CONTAINER` | The name of the CosmosDb container that contains account information | `accounts` | This is used in Development.  This may change in the future. |
| `ANTHROPIC_API_KEY` | Anthropic API Key for backup LLMs | **Cannot be empty** | Set through your private secret store |
| `ANTHROPIC_FOUNDRY_API_KEY` or `AZURE_ANTHROPIC_API_KEY` | API key for an Azure AI Foundry Anthropic deployment | Required when an agent is configured with `llmType: azureAnthropic` | Either setting is accepted. |
| `ANTHROPIC_FOUNDRY_BASE_URL` | Azure AI Foundry Anthropic base URL | Optional | Use this directly when available. |
| `AZURE_ANTHROPIC_ENDPOINT` | Azure AI Foundry Anthropic endpoint | Optional | Used when `ANTHROPIC_FOUNDRY_BASE_URL` is not set; the service adds `/anthropic` if needed. |
| `ANTHROPIC_FOUNDRY_RESOURCE` | Azure AI Foundry resource name | Optional | Used when neither Anthropic base URL nor endpoint is set. |
| `AZURE_COGNITIVE_SERVICE_ENDPOINT` | Miscellaneous Azure AI services.  This is used to extract (via NER) information from requests. | Your Azure AI services endpoint | This is the development instance.  Production endpoint TBD. |
| `AZURE_COGNITIVE_SERVICE_KEY` | Service key for Azure AI services. |**Cannot be empty** |Set through your private secret store |
| `GOOGLE_API_KEY` | Service Key for Google LLM services | **Cannot be empty** | Set through your private secret store |
| `OPENAI_API_KEY` | Service Key for OpenAI LLM services | **Cannot be empty** | Set through your private secret store |
| `CONFIG_STORAGE_ACCOUNT` | The Blob Storage URL containing agent configurations | **Cannot be empty** | Your configuration storage account URL |
| `CONFIG_STORAGE_ACCOUNT_CONTAINER` | Container containing agent configuration JSON files | `agents` | Test uses the shared data storage account for both configurations and Durable state. |

_Note: For local development, you will need to ensure that your account principal has read/write access to COSMOS DB instance:_

```bash
az cosmosdb sql role assignment create --account-name "$COSMOS_ACCOUNT_NAME" --resource-group "$COSMOS_RESOURCE_GROUP" --role-definition-id 00000000-0000-0000-0000-000000000002 --scope "/" --principal-id "$PRINCIPAL_ID"
```

_Note: Whenever you create a new Azure Function instance or if you're testing locally, you will need to ensure you or the managed identity has the appropriate roles assigned:_
Reading Index Data: **Search Index Data Reader**

For Test Functions host storage and Durable state, your developer identity and the AKS workload identity need **Storage Blob Data Owner**, **Storage Queue Data Contributor**, and **Storage Table Data Contributor** on the configured Test storage account. Local RBAC authentication requires Azure Functions Core Tools v4. Leave `AzureWebJobsStorage__credential` and `AzureWebJobsStorage__clientId` unset for Azure CLI login locally and workload identity on AKS.

### CI/CD deployment

Public CI runs unit tests, renders manifests with synthetic values, and builds and
smoke-tests the Functions container. Cloud publication and deployment jobs require
a private repository and the repository variable `ENABLE_PRIVATE_DEPLOYMENTS=true`.
Configure the Test and Production GitHub environments before enabling them.

See [deployment configuration](docs/deployment-configuration.md), [AKS Test](docs/aks-test.md),
and [AKS Production](docs/aks-production.md). Application credentials remain in a
private Key Vault or ignored local settings file. Agent configuration JSON files in
`configs/` are uploaded before deployment; matching blob names are overwritten and
other blobs are preserved.

### Testing

Use Python 3.14 and install `requirements.txt`, then run `python -m pytest -q`.
Tests use synthetic identifiers and do not require access to private services.
`python test.py` validates a synthetic source example. Its optional document URL
comes from `SHAREPOINT_EXAMPLE_DOCUMENT_URL`; see the configuration guide for the
private GitHub variable mapping. Never commit actual case records or document URLs.

### Public release

See the [readiness report and fresh-history release procedure](docs/open-source-readiness.md).
The code is licensed under [Apache-2.0](LICENSE).

### Evidence search and filter values

`POST /api/AIInteractionService/evidence/search` searches indexed records directly using
Azure AI Search hybrid keyword/vector retrieval with semantic ranking. Text queries
use the same AzureOpenAIEmbeddingsWithTelemetry provider as other agents
(default text-embedding-3-large, 3072 dimensions). It requires no session ID or
answer-generating LLM:

```json
{
  "accountId": "account-1",
  "query": "custody order",
  "tags": ["event", "custody"],
  "top": 20,
  "skip": 0
}
```

Every supplied tag must match the indexed value exactly, including case. Duplicate
tags and outer whitespace are removed. Omit `tags` or send `[]` for query-only
search; use `query: "*"` to browse by filters without embedding or semantic ranking.
Text queries combine keyword matches (`searchMode: all`) with a query vector and
semantic ranking. The index must have a compatible vector field (default
`content_vector`, configurable via `AZURESEARCH_FIELDS_CONTENT_VECTOR`) and semantic
configuration (default `Primary`, configurable via `SEMANTIC_CONFIGURATION_NAME`).
Tags, people, and locations are applied using vector prefiltering. Embedding
settings use the existing `TEXT_EMBEDDING_*` configuration; embedding or semantic
search failures return 500.
Responses include `accountId`, `query`, `tags`, `top`, `skip`, `totalCount`, and
`results`. Each result contains only `tags`, `who`, `whenStarted`, `whenEnded`, `asOf`,
`what`, `where`, `why`, `sourceId`, `source`, and `pages` as direct fields. Missing values
are returned as `null`. `totalCount` is Azure Search's approximate match count before pagination.
`top` defaults to 20 (1–1000) and `skip` defaults to 0 (0–100000).

`asOf` carries the structured date for a fact that is not an event, with the same
`year`, `month`, `day`, `season`, and `quarter` components as `whenStarted`.
The entire `asOf` field is `null` when unavailable. It uses the indexed value or
falls back to populated JSON metadata when the indexed value is empty.

Both endpoints resolve the account through the existing Cosmos account lookup and
use its `searchEndpoint` and `dataSourceId` index with Azure identity credentials.
Value listing requires `tags` to be facetable; search requires it to be filterable.
Account or index lookup failures return 404; invalid inputs return 400; backend
failures return 500. The complete contracts are in [openapi.yml](openapi.yml).

Run the focused tests with `python -m pytest tests/test_account_search.py -q`.

`GET /api/AIInteractionService/evidence/search/values?accountId=account-1` returns distinct,
sorted tags, people from the indexed `who` collection, and locations from `where`
in one facet query without downloading documents. Use this endpoint to populate all search
filter options:

```json
{"accountId": "account-1", "tags": ["custody", "event"], "who": ["Jordan", "Alex"], "where": ["Chicago"]}
```

The lookup uses `top: 0` and `count: 0` facets for all three fields. `count: 0`
requests every distinct value rather than Azure's default ten buckets. The
`tags`, `who`, and `where` fields must be facetable. There is no document scan
or separate request per field, and values are read fresh on each API call.

The search endpoint also accepts these filters:

```json
{
  "accountId": "account-1",
  "query": "*",
  "tags": ["event"],
  "who": ["Jordan", "Alex"],
  "where": ["Chicago"],
  "whenStarted": {"from": "2024-01-01", "to": "2024-12-31"},
  "whenEnded": {"to": "2025-02"}
}
```

`who` matches any selected person and `where` matches any selected location, with
exact indexed case. Both groups combine with the tag, query, and date restrictions
using AND. Empty or omitted people/location arrays impose no restriction. The
indexed `who` collection and `where` string must be facetable for unique-value
listing and filterable for search.

Each date filter accepts `from`, `to`, or both, using `YYYY`, `YYYY-MM`, or
`YYYY-MM-DD`. Bounds are inclusive. Partial bounds expand to their full period;
for example, `to: "2025-02"` includes February 28. Structured indexed dates are
treated as calendar periods: a record known only to be in 2024 matches a range
within 2024, and quarters/seasons match overlapping periods. `whenStarted` and
`whenEnded` are evaluated independently; a missing, invalid, or relative-year
date is excluded when that field is filtered. Winter spans December through
February of the following year, consistent with existing timeline handling.

Date filters run in the service because the existing date fields contain
structured partial dates rather than comparable Azure date values. The service
reads all ranked query/tag/person/location candidate pages, filters them, then
counts and paginates matches. This gives accurate filtered pages and an exact
observed `totalCount`, but can take longer for broad queries over large indexes.
Date filters do not require the structured date subfields to be filterable.
Hybrid text queries request at least 50 vector neighbors, increasing to cover
`skip + top` up to 1000; date-filtered queries request 1000 neighbors. Counts refer
to the retrieved hybrid candidate set, not all conceptually relevant evidence.
Azure semantic ranking reranks up to 50 candidates. Date filtering occurs after
retrieval and may exclude vector neighbors outside the requested dates.
Responses echo any supplied additional filters.

### AKS Test deployment

The first Kubernetes migration preserves the Azure Functions and Durable Functions runtime. See [AKS Test deployment](docs/aks-test.md) for the Docker image, Key Vault configuration, workload identity, private ingress, CI/CD setup, and staged Operations cutover. The former Function App deployment workflows have been removed; the Function Apps remain available during cutover.

Text searches return only candidates with a semantic reranker score of at least
1.8. Missing scores are excluded. The cutoff is applied before counting and
pagination, over the top 50 semantically ranked candidates. `query: "*"` browsing
bypasses the score cutoff. Scores are relevance estimates, not probabilities;
a cutoff of 1.8 can still admit unrelated records.
