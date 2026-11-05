"""Account evidence retrieval using Azure AI Search and shared text embeddings."""

import os
from contextlib import asynccontextmanager
from typing import Any

import orjson
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorQuery, VectorizedQuery

from AIInteractionService.utils.accounts import aget_account_info
from AIInteractionService.utils.azure_credentials import default_azure_credential_options
from .azuresearch import _has_metadata_value
from .search_dates import date_matches


@asynccontextmanager
async def account_search_client(account_id: str):
    account = await aget_account_info(account_id)
    if not account.search_endpoint or not account.data_source_id:
        raise RuntimeError("Account search configuration is missing.")
    async with DefaultAzureCredential(**default_azure_credential_options()) as credential:
        async with SearchClient(
            endpoint=account.search_endpoint,
            index_name=account.data_source_id,
            credential=credential,
            # Index aliases require an API version that supports alias queries.
            api_version="2026-08-01-preview",
        ) as client:
            yield client


def normalize_tags(tags: object) -> list[str]:
    return normalize_values(tags, "tags")


def normalize_values(tags: object, field: str) -> list[str]:
    if not isinstance(tags, list):
        raise ValueError(f"{field} must be an array of strings.")
    values = []
    for tag in tags:
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError(f"{field} must contain only non-empty strings.")
        value = tag.strip()
        if value not in values:
            values.append(value)
    return values


async def list_account_search_values(account_id: str) -> dict[str, list[str]]:
    return await _list_account_values(account_id, ["tags", "who", "where"])


async def _list_account_values(account_id: str, fields: list[str]) -> dict[str, list[str]]:
    async with account_search_client(account_id) as client:
        # count:0 requests every bucket, rather than Azure's default top ten.
        # top:0 avoids transferring documents; all fields share one query.
        records = await client.search(
            search_text="*", top=0,
            facets=[f"{field},count:0,sort:value" for field in fields],
        )
        facets = await records.get_facets() or {}
    return {
        field: sorted({
            bucket["value"] for bucket in facets.get(field, [])
            if isinstance(bucket.get("value"), str) and bucket["value"].strip()
        })
        for field in fields
    }


_PUBLIC_METADATA_FIELDS = (
    "tags", "who", "whenStarted", "whenEnded", "asOf", "what", "where", "why", "sourceId", "source", "pages",
)
MIN_SEMANTIC_SCORE = 1.8


def _serialize_record(record: dict) -> dict:
    metadata = record.get(os.getenv("AZURESEARCH_FIELDS_TAG", "metadata")) or {}
    if isinstance(metadata, str):
        try:
            metadata = orjson.loads(metadata)
        except orjson.JSONDecodeError:
            metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        field: record.get(field) if _has_metadata_value(record.get(field)) else metadata.get(field)
        for field in _PUBLIC_METADATA_FIELDS
    }


async def _embed_evidence_query(account_id: str, query: str) -> list[float]:
    from utils.azure_open_ai_embeddings import AzureOpenAIEmbeddingsWithTelemetry

    embeddings = AzureOpenAIEmbeddingsWithTelemetry(account_id=account_id, session_id=None)
    # The provider's inherited async method runs its synchronous SDK call in an
    # executor, preserving the existing deployment, dimensions and telemetry.
    return await embeddings.aembed_query(query)


async def search_account_records(
    account_id: str, query: str, tags: list[str], top: int, skip: int,
    *, who: list[str] | None = None, where: list[str] | None = None,
    when_started: dict[str, str] | None = None, when_ended: dict[str, str] | None = None,
) -> dict:
    clauses = [
        "tags/any(tag: tag eq '" + tag.replace("'", "''") + "')"
        for tag in tags
    ]
    if who:
        clauses.append("who/any(person: " + " or ".join(
            "person eq '" + value.replace("'", "''") + "'" for value in who
        ) + ")")
    if where:
        clauses.append("(" + " or ".join(
            "where eq '" + value.replace("'", "''") + "'" for value in where
        ) + ")")
    date_filters = {field: bounds for field, bounds in (
        ("whenStarted", when_started), ("whenEnded", when_ended),
    ) if bounds}
    vector_queries: list[VectorQuery] | None = None
    semantic_search = query != "*"
    filter_candidates = bool(date_filters) or semantic_search
    async with account_search_client(account_id) as client:
        if query != "*":
            vector = await _embed_evidence_query(account_id, query)
            vector_queries = [VectorizedQuery(
                vector=vector,
                fields=os.getenv("AZURESEARCH_FIELDS_CONTENT_VECTOR", "content_vector"),
                k_nearest_neighbors=1000 if date_filters else min(1000, max(50, skip + top)),
            )]
        records = await client.search(
            search_text=query,
            query_type="semantic" if query != "*" else "simple",
            semantic_configuration_name=(
                os.getenv("SEMANTIC_CONFIGURATION_NAME", "Primary") if query != "*" else None
            ),
            vector_queries=vector_queries,
            vector_filter_mode="preFilter" if query != "*" else None,
            search_mode="all",
            select=list(dict.fromkeys([
                *_PUBLIC_METADATA_FIELDS, os.getenv("AZURESEARCH_FIELDS_TAG", "metadata"),
            ])),
            filter=" and ".join(clauses) or None,
            top=50 if semantic_search else (None if date_filters else top),
            skip=None if filter_candidates else skip,
            include_total_count=not filter_candidates,
        )
        if filter_candidates:
            # Semantic ranking scores at most 50 candidates. Filter scores and
            # structured dates before counting or applying user pagination.
            total, results = 0, []
            async for record in records:
                if semantic_search:
                    score = record.get("@search.reranker_score")
                    if not isinstance(score, (int, float)) or isinstance(score, bool) or not score >= MIN_SEMANTIC_SCORE:
                        continue
                result = _serialize_record(record)
                if all(date_matches(result.get(field), bounds)
                       for field, bounds in date_filters.items()):
                    if skip <= total < skip + top:
                        results.append(result)
                    total += 1
        else:
            total = await records.get_count()
            results = [_serialize_record(record) async for record in records]
    response = {
        "accountId": account_id, "query": query, "tags": tags,
        "top": top, "skip": skip, "totalCount": total, "results": results,
    }
    response.update({key: value for key, value in (
        ("who", who), ("where", where),
        ("whenStarted", when_started), ("whenEnded", when_ended),
    ) if value is not None})
    return response
