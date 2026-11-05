import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import azure.functions as func
import pytest
from azure.core.exceptions import ResourceNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import search_api
from AIInteractionService.db import account_search
from AIInteractionService.db.search_dates import date_matches, normalize_date_filter


class Results:
    def __init__(self, pages, count=0, facets=None):
        self.pages = pages
        self.count = count
        self.facets = facets

    async def get_facets(self):
        return self.facets

    async def __aiter__(self):
        for page in self.pages:
            for item in page:
                yield item

    async def get_count(self):
        return self.count


def stub_client(monkeypatch, results):
    client = SimpleNamespace(search=AsyncMock(return_value=results))

    @asynccontextmanager
    async def factory(account_id):
        assert account_id == "account-1"
        yield client

    monkeypatch.setattr(account_search, "account_search_client", factory)
    monkeypatch.setattr(account_search, "_embed_evidence_query", AsyncMock(return_value=[0.1, 0.2]))
    return client


@pytest.mark.asyncio
async def test_search_escapes_tags_and_returns_ranked_records_without_private_fields(monkeypatch):
    client = stub_client(monkeypatch, Results([[{
        "id": "record-1", "content": "Evidence", "@search.score": 3.5, "@search.reranker_score": 2.5,
        "tags": ["O'Brien", "custody"], "title": "Indexed title",
        "metadata": json.dumps({"title": "Old title", "sourceId": "source-1", "private": "secret"}),
        "content_vector": [0.1], "private": "secret",
    }]], count=42))
    result = await account_search.search_account_records(
        "account-1", "custody order", ["O'Brien", "custody"], 10, 0,
    )
    client.search.assert_awaited_once_with(
        search_text="custody order", query_type="semantic", search_mode="all",
        semantic_configuration_name="Primary", vector_filter_mode="preFilter",
        vector_queries=client.search.await_args.kwargs["vector_queries"],
        select=["tags", "who", "whenStarted", "whenEnded", "asOf", "what", "where", "why", "sourceId", "source", "pages", "metadata"],
        filter="tags/any(tag: tag eq 'O''Brien') and tags/any(tag: tag eq 'custody')",
        top=50, skip=None, include_total_count=False,
    )
    assert result["totalCount"] == 1
    vector_query = client.search.await_args.kwargs["vector_queries"][0]
    assert vector_query.vector == [0.1, 0.2]
    assert vector_query.fields == "content_vector"
    assert vector_query.k_nearest_neighbors == 50
    account_search._embed_evidence_query.assert_awaited_once_with("account-1", "custody order")
    assert result["results"] == [{
        "tags": ["O'Brien", "custody"], "who": None, "whenStarted": None, "whenEnded": None, "asOf": None,
        "what": None, "where": None, "why": None, "sourceId": "source-1", "source": None, "pages": None,
    }]


@pytest.mark.asyncio
async def test_query_only_and_no_matches(monkeypatch):
    client = stub_client(monkeypatch, Results([], count=0))
    result = await account_search.search_account_records("account-1", "missing", [], 20, 0)
    assert result["results"] == []
    assert result["totalCount"] == 0
    assert client.search.await_args.kwargs["filter"] is None


@pytest.mark.asyncio
async def test_semantic_cutoff_filters_before_counting_and_pagination(monkeypatch):
    scores = [None, 1.79, 1.8, 2.2, float("nan"), True, 3.0]
    client = stub_client(monkeypatch, Results([
        [{"sourceId": str(index), "@search.reranker_score": score, "@search.score": 0.02}
         for index, score in enumerate(scores)],
    ], count=100))
    result = await account_search.search_account_records("account-1", "therapy", [], 1, 1)
    assert result["totalCount"] == 3
    assert [item["sourceId"] for item in result["results"]] == ["3"]
    assert client.search.await_args.kwargs["top"] == 50
    assert client.search.await_args.kwargs["skip"] is None


@pytest.mark.asyncio
async def test_semantic_results_without_qualifying_scores_are_empty(monkeypatch):
    stub_client(monkeypatch, Results([[{"@search.score": 1.0}, {"@search.reranker_score": 0.4}]], count=2))
    result = await account_search.search_account_records("account-1", "unrelated", [], 20, 0)
    assert result["totalCount"] == 0
    assert result["results"] == []


@pytest.mark.asyncio
async def test_browse_does_not_embed_or_use_semantic_ranker(monkeypatch):
    client = stub_client(monkeypatch, Results([]))
    await account_search.search_account_records("account-1", "*", ["event"], 20, 0)
    account_search._embed_evidence_query.assert_not_awaited()
    options = client.search.await_args.kwargs
    assert options["query_type"] == "simple"
    assert options["vector_queries"] is None
    assert options["semantic_configuration_name"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("date_filter,top,skip,k", [(None, 20, 70, 90), (None, 1000, 30, 1000), ({"from": "2024"}, 20, 0, 1000)])
async def test_hybrid_candidates_and_configured_search_fields(monkeypatch, date_filter, top, skip, k):
    monkeypatch.setenv("SEMANTIC_CONFIGURATION_NAME", "Evidence")
    monkeypatch.setenv("AZURESEARCH_FIELDS_CONTENT_VECTOR", "evidence_vector")
    client = stub_client(monkeypatch, Results([]))
    await account_search.search_account_records("account-1", "custody", ["event"], top, skip, when_started=date_filter)
    options = client.search.await_args.kwargs
    assert options["semantic_configuration_name"] == "Evidence"
    assert options["vector_queries"][0].fields == "evidence_vector"
    assert options["vector_queries"][0].k_nearest_neighbors == k
    assert options["vector_filter_mode"] == "preFilter"


@pytest.mark.asyncio
async def test_embedding_failure_does_not_silently_run_keyword_search(monkeypatch):
    client = stub_client(monkeypatch, Results([]))
    monkeypatch.setattr(account_search, "_embed_evidence_query", AsyncMock(side_effect=RuntimeError("embedding unavailable")))
    with pytest.raises(RuntimeError, match="embedding unavailable"):
        await account_search.search_account_records("account-1", "custody", [], 20, 0)
    client.search.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_embedding_reuses_service_provider_and_async_method(monkeypatch):
    provider = SimpleNamespace(aembed_query=AsyncMock(return_value=[0.3, 0.4]))
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return provider

    module = ModuleType("utils.azure_open_ai_embeddings")
    module.AzureOpenAIEmbeddingsWithTelemetry = factory
    monkeypatch.setitem(sys.modules, "utils.azure_open_ai_embeddings", module)
    assert await account_search._embed_evidence_query("account-1", "custody") == [0.3, 0.4]
    assert captured == {"account_id": "account-1", "session_id": None}
    provider.aembed_query.assert_awaited_once_with("custody")


@pytest.mark.asyncio
async def test_search_returns_only_requested_fields_with_metadata_fallback(monkeypatch):
    expected = {
        "tags": ["event"], "who": ["Jordan"], "whenStarted": {"year": "2024"},
        "whenEnded": {"year": "2025"}, "asOf": None, "what": "An incident", "where": "Chicago",
        "why": "Reported reason", "sourceId": "source-1", "source": "https://example.com/evidence.pdf", "pages": [2, 3],
    }
    stub_client(monkeypatch, Results([[{
        **expected, "what": "Updated incident", "source": None,
        "metadata": json.dumps({**expected, "private": "secret"}),
        "id": "record-1", "content": "Full text", "@search.score": 2,
        "title": "Evidence", "pages": None, "url": "private", "private": "secret",
    }]], count=1))
    result = await account_search.search_account_records("account-1", "*", [], 20, 0)
    assert result["results"] == [{**expected, "what": "Updated incident"}]


@pytest.mark.parametrize("indexed", [None, [], "", " \t", {}])
def test_empty_indexed_values_preserve_populated_json_metadata(indexed):
    metadata = {
        "tags": ["event"], "who": ["Jordan"], "whenStarted": {"year": "2024"},
        "whenEnded": {"year": "2025"}, "asOf": {"year": "2024", "month": "6"}, "what": "An incident", "where": "Chicago",
        "why": "Reported reason", "sourceId": "source-1",
        "source": "https://example.com/evidence.pdf", "pages": [2, 3],
    }
    record = {field: indexed for field in metadata}
    record["metadata"] = json.dumps(metadata)
    assert account_search._serialize_record(record) == metadata


@pytest.mark.asyncio
async def test_date_filter_uses_metadata_when_indexed_date_is_empty(monkeypatch):
    stub_client(monkeypatch, Results([[{
        "whenStarted": {}, "who": [],
        "metadata": json.dumps({"whenStarted": {"year": "2024"}, "who": ["Jordan"]}),
    }]]))
    result = await account_search.search_account_records(
        "account-1", "*", [], 20, 0, when_started={"from": "2024", "to": "2024"},
    )
    assert result["totalCount"] == 1
    assert result["results"][0]["whenStarted"] == {"year": "2024"}
    assert result["results"][0]["who"] == ["Jordan"]


@pytest.mark.parametrize("indexed,metadata,expected", [
    ({"year": "2024", "month": None}, {"year": "2023"}, {"year": "2024", "month": None}),
    (None, {"year": "2023", "quarter": "Q2"}, {"year": "2023", "quarter": "Q2"}),
    ({}, {"year": "2023"}, {"year": "2023"}),
    (None, None, None),
])
def test_as_of_preserves_structured_dates_and_nullable_field(indexed, metadata, expected):
    record = {"tags": ["fact"], "asOf": indexed, "metadata": json.dumps({"asOf": metadata})}
    assert account_search._serialize_record(record)["asOf"] == expected


@pytest.mark.asyncio
async def test_client_uses_only_account_index_and_closes_resources(monkeypatch):
    events = []

    class Credential:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            events.append("credential closed")

    class Client(Credential):
        def __init__(self, **kwargs):
            assert kwargs["endpoint"] == "https://exampleaccount.search.windows.net"
            assert kwargs["index_name"] == "account-index"
            assert kwargs["api_version"] == "2026-08-01-preview"
            assert isinstance(kwargs["credential"], Credential)

        async def __aexit__(self, *args):
            events.append("client closed")

    lookup = AsyncMock(return_value=SimpleNamespace(
        search_endpoint="https://exampleaccount.search.windows.net", data_source_id="account-index",
    ))
    monkeypatch.setattr(account_search, "aget_account_info", lookup)
    monkeypatch.setattr(account_search, "DefaultAzureCredential", Credential)
    monkeypatch.setattr(account_search, "SearchClient", Client)
    with pytest.raises(RuntimeError):
        async with account_search.account_search_client("account-1"):
            raise RuntimeError("search failure")
    lookup.assert_awaited_once_with("account-1")
    assert events == ["client closed", "credential closed"]


def request(body=None, params=None):
    return func.HttpRequest(
        method="POST" if body is not None else "GET", url="/api/AIInteractionService/evidence/search" if body is not None else "/api/AIInteractionService/evidence/search/values",
        headers={}, params=params, body=json.dumps(body).encode(),
    )


@pytest.mark.asyncio
async def test_search_endpoint_needs_no_session_or_model(monkeypatch):
    lookup = AsyncMock(return_value={"results": [], "totalCount": 0})
    monkeypatch.setattr(search_api, "search_account_records", lookup)
    response = await search_api.account_search(request({
        "accountId": "account-1", "query": "*", "tags": [" custody ", "custody", "Event"],
    }))
    assert response.status_code == 200
    lookup.assert_awaited_once_with("account-1", "*", ["custody", "Event"], 20, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    None, [], {}, {"accountId": 123, "query": "test"},
    {"accountId": "account-1", "query": " "},
    *[{"accountId": "account-1", "query": "test", "tags": tags} for tags in [None, "event", [123], [""]]],
    *[{"accountId": "account-1", "query": "test", "top": top} for top in [True, 0, 1001, "20"]],
    *[{"accountId": "account-1", "query": "test", "skip": skip} for skip in [False, -1, 100001, 1.5]],
])
async def test_invalid_search_requests_do_not_query_azure(monkeypatch, body):
    lookup = AsyncMock()
    monkeypatch.setattr(search_api, "search_account_records", lookup)
    assert (await search_api.account_search(request(body))).status_code == 400
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_malformed_json():
    req = func.HttpRequest(method="POST", url="/search", headers={}, body=b"{")
    assert (await search_api.account_search(req)).status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status", [
    (FileNotFoundError("private"), 404), (ResourceNotFoundError("private"), 404),
    (RuntimeError("private"), 500),
])
async def test_failures_have_status_and_do_not_expose_backend_details(monkeypatch, error, status):
    monkeypatch.setattr(search_api, "search_account_records", AsyncMock(side_effect=error))
    monkeypatch.setattr(search_api, "list_account_search_values", AsyncMock(side_effect=error))
    for response in [
        await search_api.account_search(request({"accountId": "account-1", "query": "test"})),
        await search_api.account_search_values(request(params={"accountId": "account-1"})),
    ]:
        assert response.status_code == status
        assert b"private" not in response.get_body()


@pytest.mark.asyncio
async def test_unique_tags_people_and_locations_in_one_facet_search(monkeypatch):
    class FacetOnlyResults(Results):
        async def __aiter__(self):
            raise AssertionError("Value listing must not download or iterate documents")
            yield

    client = stub_client(monkeypatch, FacetOnlyResults([], facets={
        field: [{"value": value, "count": 1} for value in values]
        for field, values in {
            "tags": ["event", "event", "custody", "Event", "", " "],
            "who": ["Jordan", "Alex", "Jordan", "Casey", "", " ", None],
            "where": ["Chicago", "Chicago", "Boston"],
        }.items()
    }))
    assert await account_search.list_account_search_values("account-1") == {
        "tags": ["Event", "custody", "event"],
        "who": ["Alex", "Casey", "Jordan"], "where": ["Boston", "Chicago"],
    }
    client.search.assert_awaited_once_with(search_text="*", top=0, facets=[
        "tags,count:0,sort:value", "who,count:0,sort:value", "where,count:0,sort:value",
    ])


@pytest.mark.asyncio
async def test_values_include_more_than_ten_buckets(monkeypatch):
    values = [f"Person {number:02d}" for number in range(35)]
    stub_client(monkeypatch, Results([], facets={"who": [{"value": value} for value in values]}))
    assert await account_search.list_account_search_values("account-1") == {
        "tags": [], "who": values, "where": [],
    }


@pytest.mark.asyncio
async def test_values_endpoint_and_empty_index(monkeypatch):
    stub_client(monkeypatch, Results([]))
    response = await search_api.account_search_values(request(params={"accountId": "account-1"}))
    assert response.status_code == 200
    assert json.loads(response.get_body()) == {"accountId": "account-1", "tags": [], "who": [], "where": []}
    assert (await search_api.account_search_values(request())).status_code == 400


@pytest.mark.asyncio
async def test_people_locations_and_tags_combine_without_filter_injection(monkeypatch):
    client = stub_client(monkeypatch, Results([]))
    await account_search.search_account_records(
        "account-1", "*", ["event"], 20, 0,
        who=["O'Brien", "Jordan"], where=["O'Hare", "Chicago"],
    )
    assert client.search.await_args.kwargs["filter"] == (
        "tags/any(tag: tag eq 'event') and who/any(person: person eq 'O''Brien' or person eq 'Jordan') "
        "and (where eq 'O''Hare' or where eq 'Chicago')"
    )


@pytest.mark.asyncio
async def test_date_filters_count_and_paginate_after_all_pages(monkeypatch):
    def record(identifier, start, end):
        return {"id": identifier, "sourceId": identifier, "whenStarted": start, "whenEnded": end}
    client = stub_client(monkeypatch, Results([
        [record("old", {"year": "2019"}, {"year": "2019"}),
         record("partial", {"year": "2024"}, {"year": "2024", "quarter": "Q3"})],
        [record("match", {"year": "2024", "month": "6", "day": "1"}, {"year": "2024", "month": "8"}),
         record("missing", None, {"year": "2024"}),
         record("end-outside", {"year": "2024"}, {"year": "2025"}),
         record("late", {"year": "2024", "month": "6"}, {"year": "2024", "month": "9"})],
    ], count=999))
    result = await account_search.search_account_records(
        "account-1", "*", [], 1, 1,
        when_started={"from": "2024-06-01", "to": "2024-06-30"},
        when_ended={"from": "2024-07", "to": "2024-09"},
    )
    assert result["totalCount"] == 3
    assert [record["sourceId"] for record in result["results"]] == ["match"]
    assert client.search.await_args.kwargs["top"] is None
    assert client.search.await_args.kwargs["skip"] is None
    assert client.search.await_args.kwargs["include_total_count"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("date_filter", [None, {"from": "2024", "to": "2024"}])
async def test_search_projects_only_public_fields_and_configured_metadata(monkeypatch, date_filter):
    monkeypatch.setenv("AZURESEARCH_FIELDS_TAG", "custom_metadata")
    client = stub_client(monkeypatch, Results([]))
    await account_search.search_account_records(
        "account-1", "*", [], 20, 0, when_started=date_filter,
    )
    assert client.search.await_args.kwargs["select"] == [
        "tags", "who", "whenStarted", "whenEnded", "asOf", "what", "where", "why",
        "sourceId", "source", "pages", "custom_metadata",
    ]


@pytest.mark.parametrize("value,bounds,expected", [
    ({"year": "2024"}, {"from": "2024-12-31"}, True),
    ({"year": "2024", "month": "February"}, {"from": "2024-02-29", "to": "2024-02-29"}, True),
    ({"year": "2024", "month": "2", "day": "29"}, {"to": "2024-02-28"}, False),
    ({"year": "2023", "month": "2", "day": "29"}, {"from": "2023"}, False),
    ({"year": "2024", "quarter": "Q3"}, {"from": "2024-09-30"}, True),
    ({"year": "2024", "quarter": "Q5"}, {"from": "2024"}, False),
    ({"year": "2024", "season": "winter"}, {"from": "2025-02-28", "to": "2025-02-28"}, True),
    ({"year": "2024", "season": "summer"}, {"to": "2024-05-31"}, False),
    ({"year": "YR-3"}, {"from": "2024"}, False),
    (None, {"to": "2024"}, False),
    ("2024-06-01", {"from": "2024-06-01", "to": "2024-06-01"}, True),
])
def test_partial_and_invalid_indexed_dates(value, bounds, expected):
    assert date_matches(value, bounds) is expected


@pytest.mark.asyncio
async def test_endpoint_passes_all_filters(monkeypatch):
    lookup = AsyncMock(return_value={"results": []})
    monkeypatch.setattr(search_api, "search_account_records", lookup)
    response = await search_api.account_search(request({
        "accountId": "account-1", "query": "*", "who": [" Jordan ", "Jordan"], "where": ["Chicago"],
        "whenStarted": {"from": "2024"}, "whenEnded": {"to": "2025-02"},
    }))
    assert response.status_code == 200
    lookup.assert_awaited_once_with("account-1", "*", [], 20, 0,
        who=["Jordan"], where=["Chicago"], when_started={"from": "2024"}, when_ended={"to": "2025-02"})


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("who", "Jordan"), ("who", [""]), ("where", None), ("where", [123]),
    *[(field, value) for field in ("whenStarted", "whenEnded") for value in (
        None, {}, "2024", {"from": "2024-02-30"}, {"to": "YR-3"},
        {"from": "2025", "to": "2024"}, {"from": 2024}, {"start": "2024"},
    )],
])
async def test_invalid_filters_fail_before_search(monkeypatch, field, value):
    lookup = AsyncMock()
    monkeypatch.setattr(search_api, "search_account_records", lookup)
    response = await search_api.account_search(request({"accountId": "account-1", "query": "*", field: value}))
    assert response.status_code == 400
    lookup.assert_not_awaited()


def test_filter_accepts_same_partial_period():
    assert normalize_date_filter({"from": "2024", "to": "2024"}, "whenStarted") == {"from": "2024", "to": "2024"}
