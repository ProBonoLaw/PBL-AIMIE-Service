from types import SimpleNamespace

import pytest
from azure.search.documents.indexes import SearchIndexClient

from AIInteractionService.db import azuresearch


class SearchResults(list):
    def get_answers(self):
        return []

    async def __aiter__(self):
        for record in self:
            yield record


@pytest.fixture(params=["content_vector", "custom_embedding"])
def store(monkeypatch, request):
    import azure.search.documents
    import azure.search.documents.aio

    monkeypatch.setattr(azuresearch, "FIELDS_CONTENT_VECTOR", request.param)
    field_names = ["id", "content", "metadata", "tags", "who", "whenStarted",
                   "whenEnded", "where", "what", "why", "custom_source_field",
                   azuresearch.FIELDS_CONTENT_VECTOR]
    schema = SimpleNamespace(fields=[SimpleNamespace(name=name, hidden=False) for name in field_names]
                             + [SimpleNamespace(name="private_field", hidden=True)])
    monkeypatch.setattr(SearchIndexClient, "get_index", lambda self, name: schema)

    class Client:
        def __init__(self, **kwargs):
            self.calls = []

        def search(self, **kwargs):
            self.calls.append(kwargs)
            record = {
                "id": "evidence-1", "content": "Evidence text", "metadata": "{}",
                "tags": ["fact", "event"], "who": ["Witness"],
                "whenStarted": {"year": "2024"}, "where": "Court",
                "what": "A hearing occurred", "custom_source_field": "retained",
                azuresearch.FIELDS_CONTENT_VECTOR: [0.1, 0.2],
            }
            # Emulate the server projection, so document conversion and MMR
            # genuinely run without any fields that were not requested.
            selected = {key: value for key, value in record.items() if key in kwargs["select"]}
            return SearchResults([{**selected, "@search.score": 2.0, "@search.reranker_score": 3.0}])

        def close(self):
            pass

    class AsyncClient(Client):
        async def search(self, **kwargs):
            return super().search(**kwargs)

        async def close(self):
            pass

    monkeypatch.setattr(azure.search.documents, "SearchClient", Client)
    monkeypatch.setattr(azure.search.documents.aio, "SearchClient", AsyncClient)
    instance = azuresearch.AzureSearch(
        azure_search_endpoint="https://example.search.windows.net",
        azure_search_key="test-key",
        index_name="evidence-alias",
        embedding_function=lambda text: [0.1, 0.2],
        vector_search_dimensions=2,
        semantic_configuration_name="Primary",
    )
    yield instance
    instance.client = None
    instance.async_client = None


@pytest.mark.parametrize("method", [
    "vector_search_with_score", "hybrid_search_with_score",
    "semantic_hybrid_search_with_score_and_rerank",
])
def test_search_omits_returned_vectors_and_preserves_evidence_fields(store, method):
    results = getattr(store, method)("hearing", k=1)
    options = store.client.calls[0]
    assert azuresearch.FIELDS_CONTENT_VECTOR not in options["select"]
    assert "private_field" not in options["select"]
    assert "custom_source_field" in options["select"]
    assert options["vector_queries"][0].fields == azuresearch.FIELDS_CONTENT_VECTOR
    assert options["vector_queries"][0].vector == pytest.approx([0.1, 0.2])
    document = results[0][0]
    assert document.page_content == "Evidence text"
    assert document.metadata["who"] == ["Witness"]
    assert document.metadata["whenStarted"] == {"year": "2024"}
    assert document.metadata["where"] == "Court"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", [
    "avector_search_with_score", "ahybrid_search_with_score",
    "asemantic_hybrid_search_with_score_and_rerank",
])
async def test_async_search_omits_returned_vectors(store, method):
    results = await getattr(store, method)("hearing", k=1)
    options = store.async_client.calls[0]
    assert azuresearch.FIELDS_CONTENT_VECTOR not in options["select"]
    assert "custom_source_field" in options["select"]
    assert options["vector_queries"][0].fields == azuresearch.FIELDS_CONTENT_VECTOR
    assert results[0][0].page_content == "Evidence text"


@pytest.mark.parametrize("method", [
    "max_marginal_relevance_search_with_score", "hybrid_max_marginal_relevance_search_with_score",
])
def test_mmr_keeps_vectors_for_local_reranking(store, method):
    results = getattr(store, method)("hearing", k=1)
    assert azuresearch.FIELDS_CONTENT_VECTOR in store.client.calls[0]["select"]
    assert results[0][0].page_content == "Evidence text"
    assert azuresearch.FIELDS_CONTENT_VECTOR not in results[0][0].metadata


@pytest.mark.asyncio
@pytest.mark.parametrize("method", [
    "amax_marginal_relevance_search_with_score", "ahybrid_max_marginal_relevance_search_with_score",
])
async def test_async_mmr_keeps_vectors_for_local_reranking(store, method):
    results = await getattr(store, method)("hearing", k=1)
    assert azuresearch.FIELDS_CONTENT_VECTOR in store.async_client.calls[0]["select"]
    assert results[0][0].page_content == "Evidence text"
    assert azuresearch.FIELDS_CONTENT_VECTOR not in results[0][0].metadata


def test_explicit_projection_is_preserved_without_mutating_caller_options(store):
    selected = ["id", "content", "metadata"]
    store.hybrid_search_with_score("hearing", select=selected)
    assert store.client.calls[0]["select"] == selected
    store.hybrid_max_marginal_relevance_search_with_score("hearing", k=1, select=selected)
    assert store.client.calls[1]["select"] == [*selected, azuresearch.FIELDS_CONTENT_VECTOR]
    assert selected == ["id", "content", "metadata"]


def test_none_projection_uses_the_default_without_returning_vectors(store):
    store.hybrid_search_with_score("hearing", select=None)
    assert azuresearch.FIELDS_CONTENT_VECTOR not in store.client.calls[0]["select"]
