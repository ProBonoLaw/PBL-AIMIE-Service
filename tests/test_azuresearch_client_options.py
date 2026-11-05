import sys
from pathlib import Path

import pytest
from azure.search.documents import SearchClient
from azure.search.documents.aio import SearchClient as AsyncSearchClient
from azure.search.documents.indexes import SearchIndexClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from AIInteractionService.db.azuresearch import AzureSearch


@pytest.mark.parametrize("api_version", ["2024-09-01-preview", "2026-08-01-preview"])
@pytest.mark.asyncio
async def test_vector_store_uses_configured_api_version_for_both_clients(monkeypatch, api_version):
    import azure.search.documents
    import azure.search.documents.aio

    # Record arguments at the SDK boundary while still constructing real clients.
    # This catches dropped options even when the SDK default matches the new version.
    client_options = {}

    def sync_client(**kwargs):
        client_options["sync"] = kwargs
        return SearchClient(**kwargs)

    def async_client(**kwargs):
        client_options["async"] = kwargs
        return AsyncSearchClient(**kwargs)

    monkeypatch.setattr(SearchIndexClient, "get_index", lambda self, name: None)
    monkeypatch.setattr(azure.search.documents, "SearchClient", sync_client)
    monkeypatch.setattr(azure.search.documents.aio, "SearchClient", async_client)
    store = AzureSearch(
        azure_search_endpoint="https://example.search.windows.net",
        azure_search_key="placeholder",
        index_name="account-alias",
        embedding_function=lambda text: [0.1, 0.2],
        vector_search_dimensions=2,
        additional_search_client_options={"api_version": api_version},
    )

    try:
        for options in client_options.values():
            assert options["api_version"] == api_version
            assert options["index_name"] == "account-alias"
        assert set(client_options) == {"sync", "async"}
    finally:
        store.client.close()
        await store.async_client.close()
        store.client = None
        store.async_client = None
