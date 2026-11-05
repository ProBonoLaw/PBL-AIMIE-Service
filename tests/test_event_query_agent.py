from concurrent.futures import ThreadPoolExecutor
from time import sleep
from typing import cast
from unittest.mock import Mock

import pytest
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel

from AIInteractionService.db.azuresearch import AzureSearch
from AIInteractionService.generators.event_query import agent as event_query_agent
from AIInteractionService.generators.event_query.agent import (
    build_event_filter,
    build_event_query_agent,
    event_query_request_thread_id,
    event_query_thread_id,
    materialize_event_entries,
    normalize_event_tags,
    search_event_records,
)
from AIInteractionService.generators.timelines.models import ApplicableSource


def test_event_query_thread_id_is_stable_cosmos_safe_and_collision_resistant():
    unsafe_session_id = r"case/session\\part?#1"
    thread_id = event_query_thread_id(unsafe_session_id)

    assert thread_id == event_query_thread_id(unsafe_session_id)
    assert not any(character in thread_id for character in "/\\?#")
    assert thread_id != event_query_thread_id(r"case-session-part--1")


def test_event_query_request_thread_id_is_unique_and_cosmos_safe():
    session_id = r"case/session\\part?#1"

    first = event_query_request_thread_id(session_id)
    second = event_query_request_thread_id(session_id)

    assert first != second
    assert first.startswith("event_query:v3:")
    assert not any(character in first for character in "/\\?#")


def test_build_event_query_agent_reuses_cosmos_checkpointer_concurrently(monkeypatch):
    handler = object()
    saver = object()

    def create_handler(*args):
        sleep(0.01)
        return handler

    handler_factory = Mock(side_effect=create_handler)
    saver_factory = Mock(return_value=saver)
    create_agent = Mock(return_value="agent")

    monkeypatch.setenv("COSMOS_MESSAGE_HISTORY_ENDPOINT", "https://cosmos.example")
    monkeypatch.delenv("COSMOS_MESSAGE_HISTORY_DATABASE", raising=False)
    monkeypatch.delenv("COSMOS_MESSAGE_HISTORY_CONTAINER", raising=False)
    monkeypatch.setattr(event_query_agent, "_event_query_checkpointer", None)
    monkeypatch.setattr(event_query_agent, "CosmosDBHandler", handler_factory)
    monkeypatch.setattr(event_query_agent, "CosmosDBSaver", saver_factory)
    monkeypatch.setattr("langchain.agents.create_agent", create_agent)

    with ThreadPoolExecutor(max_workers=8) as executor:
        agents = list(executor.map(
            lambda records: build_event_query_agent(
                records, cast(BaseChatModel, "model"), "prompt"
            ),
            (f"records-{index}" for index in range(8)),
        ))

    assert agents == ["agent"] * 8
    handler_factory.assert_called_once_with(
        "https://cosmos.example",
        "db_conversation_history",
        "messages2",
    )
    saver_factory.assert_called_once_with(
        handler,
        allowed_msgpack_modules=[
            ("AIInteractionService.generators.event_query.models", "EventQueryEntries"),
            ("AIInteractionService.generators.event_query.models", "EventQueryEntryDraft"),
            ("AIInteractionService.generators.timelines.models", "EventDateRange"),
        ],
    )
    assert create_agent.call_count == 8
    assert all(
        call.kwargs["checkpointer"] is saver
        for call in create_agent.call_args_list
    )
    assert all(
        call.kwargs["tools"] == []
        for call in create_agent.call_args_list
    )


def test_normalize_event_tags_adds_event_and_deduplicates():
    assert normalize_event_tags(["Fact", "event", " fact "]) == ["fact", "event"]
    assert normalize_event_tags(["custody"]) == ["event", "custody"]


def test_build_event_filter_escapes_odata_literals():
    assert build_event_filter(["event", "parent's statement"]) == (
        "tags/any(tag: tag eq 'event') and "
        "tags/any(tag: tag eq 'parent''s statement')"
    )


def test_normalize_event_tags_rejects_invalid_values():
    with pytest.raises(ValueError, match="non-empty strings"):
        normalize_event_tags([""])


@pytest.mark.asyncio
async def test_search_event_records_filters_in_azure_search():
    class FakeVectorStore:
        def __init__(self):
            self.calls = []

        async def asemantic_hybrid_search(self, query, **kwargs):
            self.calls.append((query, kwargs))
            return [Document(
                page_content="A supported event.",
                metadata={
                    "id": "event-1",
                    "sourceId": "source-1",
                    "title": "Evidence.pdf",
                    "url": "https://example.com/evidence.pdf",
                    "pages": [3],
                    "tags": ["event", "custody"],
                },
            )]

    vector_store = FakeVectorStore()
    result = await search_event_records(cast(AzureSearch, vector_store), "parenting order", ["custody"], 100)

    assert vector_store.calls == [(
        "parenting order",
        {
            "k": 100,
            "filters": "tags/any(tag: tag eq 'event') and tags/any(tag: tag eq 'custody')",
        },
    )]
    assert result.startswith("[1]:")
    assert "citationKey: S1" in result
    assert "docId:" not in result
    assert "sourceId:" not in result
    assert "title:" not in result
    assert "url:" not in result
    assert "pages:" not in result
    assert "content:" not in result
    assert not result.lstrip().startswith("[{")
    assert '"docId"' not in result



def test_event_query_event_types_are_human_readable():
    from AIInteractionService.generators.event_query import EventQueryEntries

    generated = EventQueryEntries.model_validate({
        "entries": [{
            "eventType": "reportedIncident",
            "summary": "A supported event.",
            "citationKeys": ["S1"],
        }],
    })

    assert generated.entries[0].event_type == "Reported Incident"


def test_event_query_result_contains_inputs_and_timeline_entries():
    from AIInteractionService.generators.event_query import EventQueryEntries, EventQueryResult

    assert EventQueryEntries.model_json_schema()["type"] == "object"
    generated = EventQueryEntries.model_validate({
        "timeRange": {"startDate": "2024-01", "endDate": "2024-03"},
        "entries": [{
            "eventType": "Custody order",
            "summary": "A supported event.",
            "citationKeys": ["S1"],
        }],
    })
    documents = [Document(
        page_content="A supported event.",
        metadata={
            "id": "document-1",
            "sourceId": "source-1",
        },
    )]
    result = EventQueryResult(
        session_id="session-1",
        account_id="account-1",
        tags=["event", "custody"],
        originalRequest="What happened?",
        time_range=generated.time_range,
        entries=materialize_event_entries(generated, documents),
    )

    payload = result.model_dump(mode="json", by_alias=True)
    assert payload["sessionId"] == "session-1"
    assert payload["accountId"] == "account-1"
    assert payload["tags"] == ["event", "custody"]
    assert payload["originalRequest"] == "What happened?"
    assert payload["entries"] == []
    assert payload["timeRange"] == {"startDate": "2024-01", "endDate": "2024-03"}
    assert payload["footnotes"][0] == {
        "dateRange": {"startDate": None, "endDate": None},
        "eventType": "Custody order",
        "summary": "A supported event.",
        "applicableSources": [{
            "docId": "document-1",
            "sourceId": "source-1",
            "url": None,
            "pages": None,
        }],
    }


def test_event_query_schema_requires_citation_keys():
    from AIInteractionService.generators.event_query import EventQueryEntries

    schema = EventQueryEntries.model_json_schema()
    assert "timeRange" in schema["properties"]
    entry_schema = schema["$defs"]["EventQueryEntryDraft"]
    assert "citationKeys" in entry_schema["required"]
    assert entry_schema["properties"]["citationKeys"]["minItems"] == 1


def test_event_query_schema_allows_empty_entries_when_no_record_supports_query():
    from AIInteractionService.generators.event_query import EventQueryEntries

    generated = EventQueryEntries.model_validate({"entries": []})

    assert generated.entries == []

    schema = EventQueryEntries.model_json_schema()
    assert "minItems" not in schema["properties"]["entries"]


def test_materialize_event_entries_rejects_unknown_citation_key():
    from AIInteractionService.generators.event_query import EventQueryEntries

    generated = EventQueryEntries.model_validate({"entries": [{
        "eventType": "Custody order",
        "summary": "A supported event.",
        "citationKeys": ["S2"],
    }]})
    with pytest.raises(ValueError, match="not supplied with the request evidence"):
        materialize_event_entries(generated, [Document(
            page_content="event",
            metadata={"id": "document-1", "sourceId": "source-1"},
        )])


def test_materialize_event_entries_maps_source_metadata():
    from AIInteractionService.generators.event_query import EventQueryEntries

    generated = EventQueryEntries.model_validate({"entries": [{
        "eventType": "Custody order",
        "summary": "A supported event.",
        "citationKeys": ["S1"],
    }]})
    entries = materialize_event_entries(
        generated,
        [Document(
            page_content="event",
            metadata={
                "id": "document-9", "sourceId": "source-284",
                "source": "https://example.com/evidence.pdf",
            },
        )],
    )

    source = entries[0].applicable_sources[0]
    assert source.doc_id == "document-9"
    assert source.source_id == "source-284"
    assert source.url == "https://example.com/evidence.pdf"


def test_materialize_event_entries_fills_blank_dates_from_cited_record():
    from AIInteractionService.generators.event_query import EventQueryEntries

    generated = EventQueryEntries.model_validate({"entries": [{
        "eventType": "Recorded event",
        "summary": "A source-supported event.",
        "citationKeys": ["S1"],
    }]})
    entries = materialize_event_entries(
        generated,
        [Document(
            page_content="event",
            metadata={
                "id": "document-1",
                "sourceId": "source-1",
                "whenStarted": {
                    "year": "2019",
                    "month": "December",
                    "day": "11",
                },
            },
        )],
    )

    assert entries[0].date_range.model_dump(by_alias=True) == {
        "startDate": "2019-12-11",
        "endDate": "2019-12-11",
    }

def test_materialize_event_entries_deduplicates_sources_within_each_entry():
    from AIInteractionService.generators.event_query import EventQueryEntries

    generated = EventQueryEntries.model_validate({"entries": [
        {
            "eventType": "Custody order",
            "summary": "First supported event.",
            "citationKeys": ["S1", "S2"],
        },
        {
            "eventType": "Hearing",
            "summary": "Second supported event.",
            "citationKeys": ["S2"],
        },
    ]})
    documents = [
        Document(
            page_content="first chunk",
            metadata={
                "id": "document-9",
                "sourceId": "source-284",
                "url": "https://example.com/evidence.pdf",
                "pages": [2],
            },
        ),
        Document(
            page_content="second chunk",
            metadata={
                "id": "document-9",
                "sourceId": "source-284",
                "pages": [3],
            },
        ),
    ]

    entries = materialize_event_entries(generated, documents)

    assert entries[0].applicable_sources == [ApplicableSource(
        doc_id="document-9",
        source_id="source-284",
        url="https://example.com/evidence.pdf",
        pages=[2, 3],
    )]
    assert entries[1].applicable_sources == [ApplicableSource(
        doc_id="document-9",
        source_id="source-284",
        pages=[3],
    )]


@pytest.mark.asyncio
async def test_search_event_documents_skips_records_without_source_id():
    from AIInteractionService.generators.event_query import search_event_documents

    class FakeVectorStore:
        async def asemantic_hybrid_search(self, query, **kwargs):
            return [
                Document(page_content="uncitable", metadata={"id": "document-1"}),
                Document(
                    page_content="citable",
                    metadata={"id": "document-2", "sourceId": "source-2"},
                ),
            ]

    documents = await search_event_documents(
        cast(AzureSearch, FakeVectorStore()), "custody", ["event"], 20
    )

    assert [document.metadata["id"] for document in documents] == ["document-2"]


@pytest.mark.asyncio
async def test_search_event_documents_deduplicates_by_doc_id_and_source_id():
    from AIInteractionService.generators.event_query import search_event_documents

    class FakeVectorStore:
        async def asemantic_hybrid_search(self, query, **kwargs):
            return [
                Document(
                    page_content="First copy.",
                    metadata={"id": "doc-1", "sourceId": "source-1"},
                ),
                Document(
                    page_content="Duplicate copy.",
                    metadata={"id": "doc-1", "sourceId": "source-1"},
                ),
                Document(
                    page_content="Distinct source.",
                    metadata={"id": "doc-1", "sourceId": "source-2"},
                ),
            ]

    documents = await search_event_documents(
        cast(AzureSearch, FakeVectorStore()), "custody", ["event"], 20
    )

    assert [document.page_content for document in documents] == [
        "First copy.",
        "Distinct source.",
    ]


def test_event_query_fallback_transposes_each_record_without_merging_or_rewriting():
    from AIInteractionService.generators.event_query.agent import build_event_query_fallback

    documents = [
        Document(page_content='Serialized date and participants - source narrative.', metadata={
            'id': 'doc-1', 'sourceId': '152', 'pages': [6],
            'url': 'https://example.com/source.pdf',
            'what': 'A witness alleged an incident; the other party denied it.',
            'whenStarted': {'year': '2018', 'quarter': 'Q4'},
        }),
        Document(page_content='Other serialized content.', metadata={
            'id': 'doc-2', 'sourceId': '152', 'pages': [7],
            'what': 'A witness alleged an incident; the other party denied it.',
            'whenStarted': {'year': '2018', 'month': '01', 'day': '01'},
        }),
        Document(page_content='Undated source content.', metadata={
            'id': 'doc-3', 'sourceId': '153',
            'what': 'Only an exhibit title was available.',
        }),
    ]
    result = build_event_query_fallback(
        documents, session_id='session-1', account_id='account-1',
        tags=['event', 'fact'], query='Locate reported incidents.',
    ).model_dump(mode='json', by_alias=True)

    assert result['sessionId'] == 'session-1'
    assert result['accountId'] == 'account-1'
    assert result['tags'] == ['event', 'fact']
    assert result['originalRequest'] == 'Locate reported incidents.'
    assert len(result["entries"]) == 2
    assert len(result["footnotes"]) == 1
    assert [entry["applicableSources"][0]["docId"] for entry in result["entries"]] == [
        "doc-2",
        "doc-1",
    ]
    assert result["footnotes"][0]["applicableSources"][0]["docId"] == "doc-3"
    assert all(
        entry["eventType"] == "Retrieved event"
        for entry in result["entries"] + result["footnotes"]
    )
    assert result['entries'][1]['dateRange'] == {'startDate': '2018-10-01', 'endDate': '2018-12-31'}
    assert result['entries'][1]['applicableSources'] == [{
        'docId': 'doc-1', 'sourceId': '152', 'url': 'https://example.com/source.pdf', 'pages': [6],
    }]
    assert result["footnotes"][0]["dateRange"] == {"startDate": None, "endDate": None}
    assert result['timeRange'] == {'startDate': '2018-01-01', 'endDate': '2018-12-31'}


@pytest.mark.parametrize('what', [None, '', '  ', ['invalid metadata']])
def test_event_query_fallback_skips_records_without_what(what):
    from AIInteractionService.generators.event_query.agent import build_event_query_fallback

    result = build_event_query_fallback(
        [Document(page_content='Original source content.', metadata={
            'id': 'doc-1', 'sourceId': 'source-1', 'what': what,
        })],
        session_id='s', account_id='a', tags=['event'], query='q',
    )
    assert result.entries == []
    assert result.footnotes == []
    assert result.time_range.start_date is None
    assert result.time_range.end_date is None


@pytest.mark.parametrize(('dates', 'expected'), [
    ([{'year': '2018', 'month': '10'}, {'year': '2018'}], ('2018', '2018')),
    ([{'year': 'YR-10'}, {'year': 'YR-2'}], ('YR-2', 'YR-10')),
    ([{'year': '2018'}, {'year': 'YR-2'}], (None, None)),
    ([{}], (None, None)),
    ([], (None, None)),
])
def test_event_query_fallback_time_range_preserves_precision_and_date_system(dates, expected):
    from AIInteractionService.generators.event_query.agent import build_event_query_fallback

    result = build_event_query_fallback(
        [Document(page_content='Source content.', metadata={
            'id': f'doc-{index}', 'sourceId': 'source-1', 'what': 'Retrieved event.', 'whenStarted': date,
        }) for index, date in enumerate(dates)],
        session_id='s', account_id='a', tags=['event'], query='q',
    )
    assert (result.time_range.start_date, result.time_range.end_date) == expected
    assert len(result.entries) + len(result.footnotes) == len(dates)



def test_materialize_event_entries_normalizes_model_order_stably():
    from AIInteractionService.generators.event_query import EventQueryEntries

    generated = EventQueryEntries.model_validate({
        'timeRange': {},
        'entries': [
            {
                'dateRange': {},
                'eventType': 'Undated',
                'summary': 'Undated',
                'citationKeys': ["S1"],
            },
            {
                'dateRange': {'startDate': '2021-11-29', 'endDate': '2021-11-29'},
                'eventType': 'Later',
                'summary': 'Later',
                'citationKeys': ["S1"],
            },
            {
                'dateRange': {'startDate': '2020-11-12', 'endDate': '2020-11-12'},
                'eventType': 'Earlier',
                'summary': 'Earlier',
                'citationKeys': ["S1"],
            },
        ],
    })
    documents = [Document(
        page_content='event',
        metadata={'id': 'document-1', 'sourceId': 'source-1'},
    )]

    entries = materialize_event_entries(generated, documents)

    assert [entry.summary for entry in entries] == ['Earlier', 'Later', 'Undated']
