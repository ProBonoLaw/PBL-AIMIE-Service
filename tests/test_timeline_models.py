import pytest
from pydantic import ValidationError
from AIInteractionService.generators.timelines.models import (
    ApplicableSource,
    EventDateRange,
    FactDate,
    TimelineDraft,
    TimelineEntry,
    TimelineResult,
    fact_date_to_event_date_range,
    normalize_timeline_entries,
)


def test_timeline_result_serializes_public_fields_as_camel_case():
    result = TimelineResult(
        session_id='session-456',
        account_id='account-123',
        original_request='Build a timeline',
        summary='No supported events.',
    )
    serialized = result.model_dump(by_alias=True)
    assert serialized['sessionId'] == 'session-456'
    assert serialized['accountId'] == 'account-123'
    assert serialized['originalRequest'] == 'Build a timeline'
    assert serialized['footnotes'] == []


def test_timeline_result_moves_undated_entries_to_footnotes():
    undated_entry = TimelineEntry(
        event_type='Filing',
        summary='A filing was submitted.',
        applicable_sources=[ApplicableSource(doc_id='document-1', source_id='source-1')],
    )
    result = TimelineResult(
        session_id='session-456',
        account_id='account-123',
        original_request='Build a timeline',
        summary='One undated event.',
        entries=[undated_entry],
    )

    assert result.entries == []
    assert result.footnotes == [undated_entry]


@pytest.mark.parametrize('value', ['2024', '2024-02', '2024-02-29', 'YR-0', 'YR-1-03', 'YR-2-02-29'])
def test_event_date_range_preserves_supported_precision(value):
    assert EventDateRange(start_date=value).start_date == value


@pytest.mark.parametrize('value', ['February 2024', 'YR-1-13', 'YR-2-02-30'])
def test_event_date_range_rejects_fabricated_precision(value):
    with pytest.raises(ValidationError):
        EventDateRange(start_date=value)


@pytest.mark.parametrize(
    ('when_started', 'when_ended', 'start_date', 'end_date'),
    [
        ({'year': '2024'}, None, '2024', '2024'),
        ({'year': '2024', 'month': '02'}, None, '2024-02', '2024-02'),
        ({'year': '2024', 'month': 'November'}, None, '2024-11', '2024-11'),
        ({'year': '2024', 'month': '02', 'day': '29'}, None, '2024-02-29', '2024-02-29'),
        ({'year': '2024', 'quarter': 'Q2'}, None, '2024-04-01', '2024-06-30'),
        ({'year': '2024', 'season': 'fall'}, None, '2024-09-01', '2024-11-30'),
        ({'year': '2024', 'season': 'winter'}, None, '2024-12-01', '2025-02-28'),
        ({'year': 'YR-1', 'season': 'winter'}, None, 'YR-1-12-01', 'YR-2-02-29'),
        ({'year': '2024', 'month': '01'}, {'year': '2024', 'month': '03', 'day': '15'}, '2024-01', '2024-03-15'),
        ({'year': '2024', 'quarter': 'Q1'}, {'year': '2024', 'season': 'summer'}, '2024-01-01', '2024-08-31'),
        ({'month': '02'}, None, None, None),
        ({'year': '2024', 'month': '02', 'day': '30'}, None, None, None),
    ],
)
def test_fact_date_to_event_date_range(
    when_started,
    when_ended,
    start_date,
    end_date,
):
    result = fact_date_to_event_date_range(
        FactDate.model_validate(when_started),
        FactDate.model_validate(when_ended) if when_ended else None,
    )
    assert result.start_date == start_date
    assert result.end_date == end_date


def test_applicable_source_requires_doc_id():
    from AIInteractionService.generators.timelines.models import ApplicableSource

    source = ApplicableSource(
        doc_id='chunk-1',
        source_id='284',
    )
    assert source.doc_id == 'chunk-1'
    assert source.model_dump(by_alias=True)['docId'] == 'chunk-1'

    with pytest.raises(ValidationError):
        ApplicableSource(doc_id=None, source_id='284')


def test_timeline_draft_requires_citation_keys():
    draft = TimelineDraft.model_validate({
        'originalRequest': 'Build a timeline.',
        'summary': 'Supported summary.',
        'entries': [{
            'eventType': 'Order',
            'summary': 'Supported event.',
            'citationKeys': ['S1'],
        }],
    })

    entry = draft.model_dump(mode='json', by_alias=True)['entries'][0]
    assert entry['citationKeys'] == ['S1']
    assert 'applicableSources' not in entry

    with pytest.raises(ValidationError):
        TimelineDraft.model_validate({
            'originalRequest': 'Build a timeline.',
            'summary': 'Unsupported summary.',
            'entries': [{
                'eventType': 'Order',
                'summary': 'Unsupported event.',
                'citationKeys': [],
            }],
        })




@pytest.mark.parametrize(
    ("raw_event_type", "expected_event_type"),
    [
        ("reported_incident", "Reported incident"),
        ("reportedIncident", "Reported Incident"),
        ("CPSContact", "CPS Contact"),
    ],
)
def test_timeline_event_types_are_human_readable(
    raw_event_type,
    expected_event_type,
):
    source = ApplicableSource(doc_id="document-1", source_id="source-1")
    entry = TimelineEntry(
        event_type=raw_event_type,
        summary="Supported event.",
        applicable_sources=[source],
    )
    draft = TimelineDraft.model_validate({
        "originalRequest": "Build a timeline.",
        "summary": "Supported summary.",
        "entries": [{
            "eventType": raw_event_type,
            "summary": "Supported event.",
            "citationKeys": ["S1"],
        }],
    })

    assert entry.event_type == expected_event_type
    assert draft.entries[0].event_type == expected_event_type


def _timeline_entry(summary, start=None, end=None):
    return TimelineEntry(
        date_range=EventDateRange(start_date=start, end_date=end),
        event_type='Event',
        summary=summary,
        applicable_sources=[ApplicableSource(doc_id=summary, source_id='source-1')],
    )


def test_normalize_timeline_entries_sorts_partial_overlapping_and_undated_dates():
    entries = [
        _timeline_entry('undated'),
        _timeline_entry('late', '2021-11-29', '2021-11-29'),
        _timeline_entry('range', '2020-11-23', '2020-11-30'),
        _timeline_entry('exact-first', '2020-11-23', '2020-11-23'),
        _timeline_entry('month', '2017-02', '2017-02'),
        _timeline_entry('year', '2017', '2017'),
        _timeline_entry('exact-second', '2020-11-23', '2020-11-23'),
    ]

    ordered, time_range = normalize_timeline_entries(entries)

    assert [entry.summary for entry in ordered] == [
        'year',
        'month',
        'exact-first',
        'exact-second',
        'range',
        'late',
        'undated',
    ]
    assert [entry.summary for entry in entries] == [
        'undated',
        'late',
        'range',
        'exact-first',
        'month',
        'year',
        'exact-second',
    ]
    assert (time_range.start_date, time_range.end_date) == ('2017', '2021-11-29')
    assert normalize_timeline_entries(ordered)[0] == ordered


def test_normalize_timeline_entries_handles_relative_and_open_bound_dates():
    relative, relative_range = normalize_timeline_entries([
        _timeline_entry('later', 'YR-10'),
        _timeline_entry('earlier', end='YR-2-03'),
    ])
    assert [entry.summary for entry in relative] == ['earlier', 'later']
    assert (relative_range.start_date, relative_range.end_date) == ('YR-2-03', 'YR-10')

    open_bounds, open_range = normalize_timeline_entries([
        _timeline_entry('later', '2021'),
        _timeline_entry('earlier', end='2020-02'),
    ])
    assert [entry.summary for entry in open_bounds] == ['earlier', 'later']
    assert (open_range.start_date, open_range.end_date) == ('2020-02', '2021')


def test_normalize_timeline_entries_separates_incomparable_date_systems():
    ordered, time_range = normalize_timeline_entries([
        _timeline_entry('relative', 'YR-2'),
        _timeline_entry('undated'),
        _timeline_entry('calendar', '2020'),
    ])

    assert [entry.summary for entry in ordered] == ['calendar', 'relative', 'undated']
    assert time_range == EventDateRange()
