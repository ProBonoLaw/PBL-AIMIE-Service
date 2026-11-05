from concurrent.futures import ThreadPoolExecutor
import logging

import pytest
from langchain_core.documents import Document
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from AIInteractionService.generators.timelines import agent as timeline_agent
from AIInteractionService.generators.timelines.agent import (
    EVENT_FILTER,
    DOMESTIC_VIOLENCE_PROFILE,
    TimelineSearchBudget,
    TimelineSourceRegistry,
    _records,
    _records_with_artifact,
    _records_with_context,
    _search_event_records,
    build_timeline_agent,
    domestic_violence_scope_requested,
    preload_critical_scope_records,
    timeline_skill_files,
)
from AIInteractionService.generators.timelines.models import (
    ApplicableSource,
    TimelineDraft,
    TimelineEntryDraft,
)


def test_domestic_violence_scope_detection_is_explicit():
    assert domestic_violence_scope_requested('Build a Domestic Violence timeline.')
    assert domestic_violence_scope_requested('Review allegations of intimate-partner violence.')
    assert not domestic_violence_scope_requested('Build a child-support timeline.')


@pytest.mark.asyncio
async def test_domestic_violence_profile_searches_every_cluster_and_tracks_coverage():
    class FakeStore:
        def __init__(self):
            self.calls = []

        async def asemantic_hybrid_search(self, query, *, k, filters):
            self.calls.append((query, k, filters))
            index = len(self.calls)
            return [Document(
                page_content=f'Supported record {index}.',
                metadata={'id': f'document-{index}', 'sourceId': f'source-{index}'},
            )]

    store = FakeStore()
    budget = TimelineSearchBudget()
    records, coverage = await preload_critical_scope_records(
        store,
        'Generate a timeline about domestic violence.',
        5,
        TimelineSourceRegistry(),
        budget,
    )

    assert [call[0] for call in store.calls] == list(DOMESTIC_VIOLENCE_PROFILE.values())
    assert all(call[1:] == (5, EVENT_FILTER) for call in store.calls)
    assert coverage.profile_name == 'domestic_violence'
    assert list(coverage.searched_clusters) == list(DOMESTIC_VIOLENCE_PROFILE)
    assert coverage.unsearched_clusters == []
    assert coverage.complete
    assert budget.remaining == 14
    assert records.count('citationKey:') == len(DOMESTIC_VIOLENCE_PROFILE)
    assert 'Supported record 1.' not in records


@pytest.mark.asyncio
async def test_domestic_violence_profile_marks_unsearched_clusters_when_budget_exhausts():
    class FakeStore:
        async def asemantic_hybrid_search(self, query, *, k, filters):
            return []

    _, coverage = await preload_critical_scope_records(
        FakeStore(),
        'Generate a timeline about domestic abuse.',
        5,
        TimelineSourceRegistry(),
        TimelineSearchBudget(limit=2),
    )

    assert list(coverage.searched_clusters) == list(DOMESTIC_VIOLENCE_PROFILE)[:2]
    assert coverage.unsearched_clusters == list(DOMESTIC_VIOLENCE_PROFILE)[2:]
    assert not coverage.complete


def test_timeline_search_records_are_encoded_as_toon():
    result, artifact = _records_with_artifact([
        Document(
            page_content='A supported event.',
            metadata={
                'id': 'event-1',
                'sourceId': 'source-1',
                'title': 'Evidence.pdf',
                'source': 'https://example.com/evidence.pdf',
                'tags': ['fact', 'event'],
                'pages': [3],
            },
        )
    ])

    assert result.startswith('[1]:')
    assert 'citationKey: S1' in result
    assert 'docId' not in result
    assert 'sourceId' not in result
    assert 'tags[2]: fact,event' in result
    assert 'title:' not in result
    assert 'url:' not in result
    assert 'pages:' not in result
    assert 'content:' not in result
    assert artifact['sources']['S1']['url'] == 'https://example.com/evidence.pdf'
    assert not result.lstrip().startswith('{')


def test_timeline_context_records_include_only_citation_key_and_page_content():
    content, artifact = _records_with_context([
        Document(
            page_content='Background evidence for the event.',
            metadata={
                'id': 'context-1',
                'sourceId': 'source-1',
                'url': 'https://example.com/context.pdf',
                'tags': ['event', 'custody'],
                'where': 'Everett',
                'what': 'A hearing occurred.',
                'who': ['Parent'],
                'why': 'To determine custody.',
                'whenStarted': {'year': '2024'},
            },
        )
    ])

    assert '{citationKey,content}:' in content
    assert 'S1,Background evidence for the event.' in content
    for event_field in ('tags:', 'where:', 'what:', 'who:', 'why:', 'dateRange:'):
        assert event_field not in content
    assert 'url:' not in content
    assert artifact['sources']['S1']['url'] == 'https://example.com/context.pdf'

def test_timeline_context_records_include_content_after_event_search():
    registry = TimelineSourceRegistry()
    document = Document(
        page_content='Context content remains available.',
        metadata={'id': 'event-1', 'sourceId': 'source-1', 'what': 'An event.'},
    )
    _records([document], registry)
    content, _ = _records_with_context([document], registry)

    assert '{citationKey,content}:' in content
    assert 'S1,Context content remains available.' in content
    assert 'what:' not in content

def test_timeline_search_serializes_precomputed_date_range(monkeypatch):
    result = _records([
        Document(
            page_content='A supported event.',
            metadata={
                'id': 'event-1',
                'sourceId': 'source-1',
                'whenStarted': {'year': '2024', 'quarter': 'Q3'},
                'whenEnded': {'year': '2024', 'quarter': 'Q4'},
            },
        )
    ])

    assert 'dateRange:' in result
    assert 'startDate: 2024-07-01' in result
    assert 'endDate: 2024-12-31' in result
    assert 'whenStarted' not in result
    assert 'whenEnded' not in result


def test_timeline_agent_excludes_fact_date_conversion_tool(monkeypatch):
    captured = {}

    def create_deep_agent(**kwargs):
        captured.update(kwargs)
        return 'agent'

    monkeypatch.setenv('COSMOS_MESSAGE_HISTORY_ENDPOINT', 'https://cosmos.example')
    monkeypatch.setattr('deepagents.create_deep_agent', create_deep_agent)
    monkeypatch.setattr(timeline_agent, 'CosmosDBHandler', lambda *args: 'handler')
    monkeypatch.setattr(timeline_agent, 'CosmosDBSaver', lambda *args, **kwargs: 'saver')

    agent = build_timeline_agent(
        vector_store=object(),
        max_doc_count=20,
        model=object(),
        system_prompt='Build a timeline.',
    )

    assert agent == 'agent'
    assert {tool.name for tool in captured['tools']} == {
        'search_case_events',
        'search_case_context',
    }
    assert captured['skills'] == ['/skills/timeline']


def test_timeline_candidate_extraction_skill_is_packaged_for_state_backend(caplog):
    caplog.set_level(logging.INFO)
    files = timeline_skill_files()

    assert [path for path in files if path.endswith('/SKILL.md')] == [
        '/skills/timeline/atomic-timeline-events/SKILL.md',
        '/skills/timeline/completeness-review/SKILL.md',
        '/skills/timeline/evidence-reconciliation/SKILL.md',
        '/skills/timeline/gap-analysis/SKILL.md',
        '/skills/timeline/identity-resolution/SKILL.md',
        '/skills/timeline/legal-timeline-candidate-extraction/SKILL.md',
        '/skills/timeline/relationship-analysis/SKILL.md',
        '/skills/timeline/serialization/SKILL.md',
        '/skills/timeline/timeline-materiality-review/SKILL.md',
    ]
    first_skill = files[next(iter(files))]
    assert first_skill['encoding'] == 'utf-8'
    assert first_skill['content'].startswith(
        '---\nname: atomic-timeline-events\n',
    )
    assert (
        '/skills/timeline/atomic-timeline-events/references/atomization-examples.md'
        in files
    )
    record = next(
        item for item in caplog.records if item.message == 'timeline_skill_loader'
    )
    assert record.skillCount == 9
    assert record.skillFileCount == len(files)
    assert record.skills == 'atomic-timeline-events,completeness-review,evidence-reconciliation,gap-analysis,identity-resolution,legal-timeline-candidate-extraction,relationship-analysis,serialization,timeline-materiality-review'


def test_timeline_search_records_accept_existing_provenance_aliases():
    result, artifact = _records_with_artifact([
        Document(
            page_content='A supported event.',
            metadata={
                'docId': 'event-2',
                'sourceId': 'source-2',
                'docTitle': 'Alternate.pdf',
                'url': 'https://example.com/alternate.pdf',
            },
        )
    ])

    assert 'citationKey: S1' in result
    assert 'url:' not in result
    assert artifact['sources']['S1']['url'] == 'https://example.com/alternate.pdf'


def test_timeline_search_records_deduplicate_by_doc_id_and_source_id():
    result = _records([
        Document(
            page_content='First copy.',
            metadata={'id': 'event-1', 'sourceId': 'source-1'},
        ),
        Document(
            page_content='Duplicate copy.',
            metadata={'id': 'event-1', 'sourceId': 'source-1'},
        ),
        Document(
            page_content='A distinct source.',
            metadata={'id': 'event-1', 'sourceId': 'source-2'},
        ),
    ])

    assert result.startswith('[2]:')
    assert result.count('citationKey:') == 2
    assert 'content:' not in result
    assert 'First copy.' not in result
    assert 'Duplicate copy.' not in result
    assert 'A distinct source.' not in result


async def test_timeline_event_search_filters_in_azure_search():
    class FakeVectorStore:
        def __init__(self):
            self.calls = []

        async def asemantic_hybrid_search(self, query, **kwargs):
            self.calls.append((query, kwargs))
            return [
                Document(
                    page_content='A server-filtered event.',
                    metadata={
                        'id': 'event-1',
                        'sourceId': 'source-1',
                        'tags': ['event'],
                    },
                )
            ]

    vector_store = FakeVectorStore()
    result = await _search_event_records(vector_store, 'custody', 7)

    assert vector_store.calls == [
        ('custody', {'k': 7, 'filters': EVENT_FILTER}),
    ]
    assert 'citationKey: S1' in result


def test_timeline_search_skips_uncitable_records():
    result = _records([
        Document(
            page_content='Cannot be cited.',
            metadata={'id': 'event-uncitable'},
        ),
        Document(
            page_content='Can be cited.',
            metadata={'id': 'event-1', 'sourceId': 'source-1'},
        ),
    ])

    assert 'Cannot be cited.' not in result
    assert result.count('citationKey:') == 1
    assert 'content:' not in result


def test_source_registry_resolves_by_doc_and_source_id_with_canonical_metadata():
    registry = TimelineSourceRegistry()
    result = _records([
        Document(
            page_content='First matching chunk.',
            metadata={
                'id': 'event-1',
                'sourceId': 'source-1',
                'url': 'https://example.com/source.pdf',
                'pages': [3],
            },
        ),
        Document(
            page_content='Second matching chunk.',
            metadata={
                'id': 'event-1',
                'sourceId': 'source-1',
                'url': 'https://example.com/fabricated.pdf',
                'pages': [4],
            },
        ),
    ], registry)
    citation_key = registry.citation_keys()[0]
    assert result.count(f'citationKey: {citation_key}') == 1
    timeline = TimelineDraft(
        original_request='Build a timeline.',
        summary='Supported summary.',
        entries=[
            TimelineEntryDraft(
                event_type='Order',
                summary='Supported event.',
                citation_keys=[citation_key, citation_key],
            ),
            TimelineEntryDraft(
                event_type='Hearing',
                summary='Another supported event.',
                citation_keys=[citation_key],
            ),
        ],
    )

    resolved = registry.resolve_timeline(
        timeline,
        account_id='account-123',
        session_id='session-456',
    )

    assert resolved.footnotes[0].applicable_sources == [
        ApplicableSource(
            doc_id='event-1',
            source_id='source-1',
            url='https://example.com/source.pdf',
            pages=[3, 4],
        )
    ]
    assert resolved.footnotes[1].applicable_sources == [
        ApplicableSource(
            doc_id='event-1',
            source_id='source-1',
            url='https://example.com/source.pdf',
            pages=[3, 4],
        )
    ]


def test_timeline_records_do_not_resend_sources_seen_by_prior_searches():
    registry = TimelineSourceRegistry()
    document = Document(
        page_content='A supported event.',
        metadata={'id': 'event-1', 'sourceId': 'source-1'},
    )

    first_result = _records([document], registry)
    second_result = _records([document], registry)

    assert 'citationKey: S1' in first_result
    assert 'citationKey:' not in second_result


def test_source_registry_rejects_unknown_citation_key():
    registry = TimelineSourceRegistry()
    _records([
        Document(
            page_content='Supported event.',
            metadata={'id': 'event-1', 'sourceId': 'source-1'},
        )
    ], registry)
    timeline = TimelineDraft(
        original_request='Build a timeline.',
        summary='Unsupported summary.',
        entries=[
            TimelineEntryDraft(
                event_type='Order',
                summary='Unsupported event.',
                citation_keys=['S999'],
            )
        ],
    )

    with pytest.raises(ValueError, match='citation key was not returned'):
        registry.resolve_timeline(
            timeline,
            account_id='account-123',
            session_id='session-456',
        )


def test_source_registry_is_restored_from_checkpointed_tool_artifact():
    content, artifact = _records_with_artifact([
        Document(
            page_content='Supported event.',
            metadata={
                'id': 'event-1',
                'sourceId': 'source-1',
                'url': 'https://example.com/source.pdf',
                'pages': [3],
                'whenStarted': {'year': '2020'},
            },
        )
    ])
    citation_key = next(iter(artifact['sources']))
    message = ToolMessage(
        content=content,
        artifact=artifact,
        tool_call_id='search-call-1',
    )
    serializer = JsonPlusSerializer()
    restored_message = serializer.loads_typed(serializer.dumps_typed(message))
    restored_registry = TimelineSourceRegistry()
    restored_registry.restore_from_messages([restored_message])
    timeline = TimelineDraft(
        original_request='Build a timeline.',
        summary='Supported summary.',
        entries=[
            TimelineEntryDraft(
                event_type='Order',
                summary='Supported event.',
                citation_keys=[citation_key],
            )
        ],
    )

    resolved = restored_registry.resolve_timeline(
        timeline,
        account_id='account-123',
        session_id='session-456',
    )

    assert 'docId' not in content
    assert 'sourceId' not in content
    assert artifact['dateRanges'][citation_key] == {'startDate': '2020', 'endDate': '2020'}
    assert resolved.entries[0].date_range.model_dump(by_alias=True) == {
        'startDate': '2020',
        'endDate': '2020',
    }
    assert resolved.entries[0].applicable_sources == [
        ApplicableSource(
            doc_id='event-1',
            source_id='source-1',
            url='https://example.com/source.pdf',
            pages=[3],
        )
    ]


def test_source_registry_assigns_collision_free_keys_concurrently():
    registry = TimelineSourceRegistry()
    sources = [
        ApplicableSource(
            doc_id=f'document-{index}',
            source_id=f'source-{index}',
        )
        for index in range(64)
    ]

    first_key = registry.register(sources[0])
    with ThreadPoolExecutor(max_workers=16) as executor:
        citation_keys = [first_key, *executor.map(registry.register, sources[1:])]

    assert len(set(citation_keys)) == len(sources)
    assert set(citation_keys) == {f'S{index}' for index in range(1, 65)}
    assert TimelineSourceRegistry().register(sources[0]) == 'S1'

    with ThreadPoolExecutor(max_workers=16) as executor:
        duplicate_keys = list(executor.map(
            registry.register,
            [sources[0]] * 64,
        ))

    assert set(duplicate_keys) == {citation_keys[0]}


def test_source_registry_continues_keys_after_artifact_restoration():
    registry = TimelineSourceRegistry()
    first = ApplicableSource(doc_id='document-1', source_id='source-1')
    second = ApplicableSource(doc_id='document-2', source_id='source-2')

    first_key = registry.register(first)
    artifact = registry.artifact([first_key])
    restored_registry = TimelineSourceRegistry()
    restored_registry.restore_artifact(artifact)
    second_key = restored_registry.register(second)

    assert first_key == 'S1'
    assert second_key == 'S2'
    assert restored_registry.register(first) == first_key
    assert restored_registry.register(second) == second_key



def test_source_registry_normalizes_timeline_order_and_time_range():
    registry = TimelineSourceRegistry()
    citation_key = registry.register(ApplicableSource(
        doc_id='event-1',
        source_id='source-1',
    ))
    timeline = TimelineDraft(
        original_request='Build a timeline.',
        time_range={'startDate': '2021', 'endDate': '2020'},
        summary='Supported summary.',
        entries=[
            TimelineEntryDraft(
                date_range={'startDate': None, 'endDate': None},
                event_type='Undated',
                summary='Undated event.',
                citation_keys=[citation_key],
            ),
            TimelineEntryDraft(
                date_range={'startDate': '2021-11-29', 'endDate': '2021-11-29'},
                event_type='Later',
                summary='Later event.',
                citation_keys=[citation_key],
            ),
            TimelineEntryDraft(
                date_range={'startDate': '2020-11-12', 'endDate': '2020-11-12'},
                event_type='Earlier',
                summary='Earlier event.',
                citation_keys=[citation_key],
            ),
        ],
    )

    resolved = registry.resolve_timeline(
        timeline,
        account_id='account-1',
        session_id='session-1',
    )

    assert [entry.summary for entry in resolved.entries] == [
        "Earlier event.",
        "Later event.",
    ]
    assert [entry.summary for entry in resolved.footnotes] == ["Undated event."]
    assert resolved.time_range.model_dump(by_alias=True) == {
        'startDate': '2020-11-12',
        'endDate': '2021-11-29',
    }
