from calendar import month_abbr, month_name, monthrange
from datetime import datetime
import re
from typing import Any, Iterable, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

def camel(value: str) -> str:
    first, *rest = value.split('_')
    return first + ''.join(item.title() for item in rest)


_EVENT_TYPE_WORD_BOUNDARY = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)


def normalize_event_type_label(value: Any) -> Any:
    """Convert machine-style event labels into human-readable text."""
    if not isinstance(value, str):
        return value
    label = _EVENT_TYPE_WORD_BOUNDARY.sub(" ", value.strip())
    label = re.sub(r"[_-]+", " ", label)
    label = " ".join(label.split())
    if not label:
        raise ValueError("eventType must not be empty")
    return label[0].upper() + label[1:]


class TimelineModel(BaseModel):
    model_config = ConfigDict(alias_generator=camel, populate_by_name=True, serialize_by_alias=True)

class EventDateRange(TimelineModel):
    start_date: Optional[str] = Field(
        default=None,
        description=(
            'Supported event start date. Use YYYY, YYYY-MM, or YYYY-MM-DD for calendar dates; '
            'use YR-n, YR-n-MM, or YR-n-MM-DD when the source uses an anonymized relative year.'
        ),
    )
    end_date: Optional[str] = Field(
        default=None,
        description=(
            'Supported event end date. Use YYYY, YYYY-MM, or YYYY-MM-DD for calendar dates; '
            'use YR-n, YR-n-MM, or YR-n-MM-DD when the source uses an anonymized relative year.'
        ),
    )

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_precision(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        relative_match = re.fullmatch(
            r'YR-(?:0|[1-9]\d*)(?:-(\d{2})(?:-(\d{2}))?)?',
            value,
        )
        if relative_match:
            month, day = relative_match.groups()
            if month is not None:
                datetime.strptime(f'2000-{month}' + (f'-{day}' if day else ''), '%Y-%m-%d' if day else '%Y-%m')
            return value
        date_format = {4: '%Y', 7: '%Y-%m', 10: '%Y-%m-%d'}.get(len(value))
        if not date_format:
            raise ValueError(
                'Date must use YYYY, YYYY-MM, YYYY-MM-DD, YR-n, YR-n-MM, or YR-n-MM-DD precision.'
            )
        datetime.strptime(value, date_format)
        return value


class FactDate(BaseModel):
    """Structured date metadata stored on fact and event records."""

    year: Optional[str] = None
    month: Optional[str] = None
    day: Optional[str] = None
    season: Optional[str] = None
    quarter: Optional[str] = None


_YEAR_PATTERN = re.compile(r'(?:\d{4}|YR-(?:0|[1-9]\d*))')
_RELATIVE_YEAR_PATTERN = re.compile(r'YR-(0|[1-9]\d*)')
_QUARTER_MONTHS = {
    '1': (1, 3),
    '2': (4, 6),
    '3': (7, 9),
    '4': (10, 12),
}
_SEASON_MONTHS = {
    'spring': (3, 1, 5, 31),
    'summer': (6, 1, 8, 31),
    'autumn': (9, 1, 11, 30),
    'fall': (9, 1, 11, 30),
}


_MONTH_NUMBER_BY_NAME = {
    name.lower(): number
    for names in (month_name, month_abbr)
    for number, name in enumerate(names)
    if name
} | {'sept': 9}


def _fact_month_number(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return _MONTH_NUMBER_BY_NAME.get(value.lower().rstrip('.'))


def _fact_date_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _format_fact_date(year: str, month: int | None = None, day: int | None = None) -> str:
    if month is None:
        return year
    if day is None:
        return f'{year}-{month:02d}'
    return f'{year}-{month:02d}-{day:02d}'


def _next_fact_year(year: str) -> Optional[str]:
    if year.isdigit() and len(year) == 4:
        return str(int(year) + 1)
    relative_match = _RELATIVE_YEAR_PATTERN.fullmatch(year)
    if relative_match:
        return f'YR-{int(relative_match.group(1)) + 1}'
    return None


def _last_day_of_fact_month(year: str, month: int) -> int:
    if year.startswith('YR-'):
        # Relative years use the schema's leap-year-safe reference calendar.
        return monthrange(2000, month)[1]
    return monthrange(int(year), month)[1]


def fact_date_to_event_date_range(
    when_started: FactDate | dict[str, Any] | None,
    when_ended: FactDate | dict[str, Any] | None = None,
) -> EventDateRange:
    """Convert FactDate start/end metadata to the most precise date range."""
    start_range = _fact_date_to_event_date_range(when_started)
    end_range = _fact_date_to_event_date_range(when_ended)
    return EventDateRange(
        start_date=start_range.start_date or end_range.start_date,
        end_date=end_range.end_date or start_range.end_date,
    )


def _fact_date_to_event_date_range(
    fact_date_value: FactDate | dict[str, Any] | None,
) -> EventDateRange:
    if fact_date_value is None:
        return EventDateRange()
    try:
        fact_date = (
            fact_date_value
            if isinstance(fact_date_value, FactDate)
            else FactDate.model_validate(fact_date_value)
        )
    except (TypeError, ValueError):
        return EventDateRange()
    year = _fact_date_value(fact_date.year)
    month = _fact_date_value(fact_date.month)
    day = _fact_date_value(fact_date.day)
    season = _fact_date_value(fact_date.season)
    quarter = _fact_date_value(fact_date.quarter)
    if year is None or not _YEAR_PATTERN.fullmatch(year):
        return EventDateRange()

    try:
        if month is not None:
            month_number = _fact_month_number(month)
            if month_number is None or not 1 <= month_number <= 12:
                return EventDateRange()
            if day is not None:
                day_number = int(day)
                if not 1 <= day_number <= _last_day_of_fact_month(year, month_number):
                    return EventDateRange()
                date = _format_fact_date(year, month_number, day_number)
                return EventDateRange(start_date=date, end_date=date)
            date = _format_fact_date(year, month_number)
            return EventDateRange(start_date=date, end_date=date)

        if quarter is not None:
            normalized_quarter = quarter.lower().replace('quarter', '').replace('q', '').strip()
            quarter_months = _QUARTER_MONTHS.get(normalized_quarter)
            if quarter_months is None:
                return EventDateRange()
            start_month, end_month = quarter_months
            return EventDateRange(
                start_date=_format_fact_date(year, start_month, 1),
                end_date=_format_fact_date(
                    year,
                    end_month,
                    _last_day_of_fact_month(year, end_month),
                ),
            )

        if season is not None:
            normalized_season = season.lower().strip()
            if normalized_season == 'winter':
                end_year = _next_fact_year(year)
                if end_year is None:
                    return EventDateRange()
                return EventDateRange(
                    start_date=_format_fact_date(year, 12, 1),
                    end_date=_format_fact_date(
                        end_year,
                        2,
                        _last_day_of_fact_month(end_year, 2),
                    ),
                )
            season_months = _SEASON_MONTHS.get(normalized_season)
            if season_months is None:
                return EventDateRange()
            start_month, start_day, end_month, end_day = season_months
            return EventDateRange(
                start_date=_format_fact_date(year, start_month, start_day),
                end_date=_format_fact_date(year, end_month, end_day),
            )
    except ValueError:
        return EventDateRange()

    return EventDateRange(start_date=year, end_date=year)


def fill_missing_event_date_range(
    date_range: EventDateRange,
    source_date_ranges: Iterable[EventDateRange],
) -> EventDateRange:
    """Fill blank draft bounds from the first dated cited record.

    Model output can omit a range even though its cited record has indexed event
    dates. Preserve every bound the model supplied and use only a cited record's
    already-normalized range to fill missing bounds. Citation order identifies
    the primary fallback when an entry has more than one supporting record.
    """
    fallback = next(
        (
            candidate
            for candidate in source_date_ranges
            if candidate.start_date is not None or candidate.end_date is not None
        ),
        None,
    )
    if fallback is None:
        return date_range.model_copy(deep=True)
    return EventDateRange(
        start_date=(
            date_range.start_date
            or fallback.start_date
            or fallback.end_date
        ),
        end_date=(
            date_range.end_date
            or fallback.end_date
            or fallback.start_date
        ),
    )


class ApplicableSource(TimelineModel):
    doc_id: str = Field(
        min_length=1,
        description='Copy docId exactly from the supporting search result; never return null.',
    )
    source_id: str = Field(
        min_length=1,
        description='Copy sourceId exactly from the supporting search result.',
    )
    url: Optional[str] = Field(
        default=None,
        description='Copy url exactly from the supporting search result when available.',
    )
    pages: Optional[list[int | str]] = Field(
        default=None,
        description='Copy the relevant page or pages from the supporting search result.',
    )


def deduplicate_applicable_sources(
    sources: list[ApplicableSource],
) -> list[ApplicableSource]:
    merged: dict[tuple[str, str], ApplicableSource] = {}
    for source in sources:
        source_key = (source.doc_id, source.source_id)
        existing = merged.get(source_key)
        if existing is None:
            merged[source_key] = source.model_copy(deep=True)
            continue

        pages = list(existing.pages or [])
        for page in source.pages or []:
            if page not in pages:
                pages.append(page)
        merged[source_key] = ApplicableSource(
            doc_id=existing.doc_id,
            source_id=existing.source_id,
            url=existing.url or source.url,
            pages=pages or None,
        )
    return list(merged.values())


class TimelineEntry(TimelineModel):
    date_range: EventDateRange = Field(default_factory=EventDateRange)
    event_type: str = Field(
        description="Human-readable, space-separated event label; never snake_case or camelCase.",
    )
    summary: str
    applicable_sources: list[ApplicableSource] = Field(
        min_length=1,
        description="At least one indexed source supporting this event.",
    )

    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_event_type(cls, value: Any) -> Any:
        return normalize_event_type_label(value)

    @field_validator("applicable_sources")
    @classmethod
    def deduplicate_sources(
        cls,
        sources: list[ApplicableSource],
    ) -> list[ApplicableSource]:
        return deduplicate_applicable_sources(sources)


def _date_bound(value: str, *, upper: bool) -> tuple[str, tuple[int, int, int]]:
    """Return a comparable bound without changing the source date precision."""
    relative = value.startswith('YR-')
    parts = [int(part) for part in value.removeprefix('YR-').split('-')]
    year = parts[0]
    month = parts[1] if len(parts) > 1 else (12 if upper else 1)
    if len(parts) > 2:
        day = parts[2]
    elif upper:
        day = monthrange(2000 if relative else year, month)[1]
    else:
        day = 1
    return ('relative' if relative else 'calendar', (year, month, day))


def _entry_chronology_key(
    entry: TimelineEntry,
) -> tuple[int, tuple[int, int, int], tuple[int, int, int]]:
    values = [
        value
        for value in (entry.date_range.start_date, entry.date_range.end_date)
        if value is not None
    ]
    if not values:
        return (3, (0, 0, 0), (0, 0, 0))

    systems = {_date_bound(value, upper=False)[0] for value in values}
    if len(systems) != 1:
        # A range spanning incomparable date systems cannot be ordered
        # chronologically. Keep it in a stable block before undated entries.
        return (2, (0, 0, 0), (0, 0, 0))

    system = systems.pop()
    start_value = entry.date_range.start_date or entry.date_range.end_date
    end_value = entry.date_range.end_date or entry.date_range.start_date
    assert start_value is not None and end_value is not None
    return (
        0 if system == 'calendar' else 1,
        _date_bound(start_value, upper=False)[1],
        _date_bound(end_value, upper=True)[1],
    )


def timeline_time_range(entries: list[TimelineEntry]) -> EventDateRange:
    """Derive the chronology envelope while preserving boundary precision."""
    start_values: list[str] = []
    end_values: list[str] = []
    for entry in entries:
        start_value = entry.date_range.start_date or entry.date_range.end_date
        end_value = entry.date_range.end_date or entry.date_range.start_date
        if start_value is not None and end_value is not None:
            start_values.append(start_value)
            end_values.append(end_value)
    systems = {
        _date_bound(value, upper=False)[0]
        for value in start_values + end_values
    }
    if len(systems) != 1:
        return EventDateRange()
    return EventDateRange(
        start_date=min(
            start_values,
            key=lambda value: _date_bound(value, upper=False)[1],
        ) if start_values else None,
        end_date=max(
            end_values,
            key=lambda value: _date_bound(value, upper=True)[1],
        ) if end_values else None,
    )


def normalize_timeline_entries(
    entries: list[TimelineEntry],
) -> tuple[list[TimelineEntry], EventDateRange]:
    """Return entries in deterministic chronological order and their envelope."""
    ordered_entries = sorted(entries, key=_entry_chronology_key)
    return ordered_entries, timeline_time_range(ordered_entries)


def partition_timeline_entries(
    entries: list[TimelineEntry],
) -> tuple[list[TimelineEntry], list[TimelineEntry], EventDateRange]:
    """Separate undated entries into footnotes after chronological ordering."""
    ordered_entries, time_range = normalize_timeline_entries(entries)
    dated_entries: list[TimelineEntry] = []
    footnotes: list[TimelineEntry] = []
    for entry in ordered_entries:
        if entry.date_range.start_date is None and entry.date_range.end_date is None:
            footnotes.append(entry)
        else:
            dated_entries.append(entry)
    return dated_entries, footnotes, time_range


class TimelineEntryDraft(TimelineModel):
    date_range: EventDateRange = Field(default_factory=EventDateRange)
    event_type: str = Field(
        description="Human-readable, space-separated event label; never snake_case or camelCase.",
    )
    summary: str
    citation_keys: list[str] = Field(
        min_length=1,
        description='Citation keys copied exactly from supporting search results.',
    )

    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_event_type(cls, value: Any) -> Any:
        return normalize_event_type_label(value)

class TimelineDraft(TimelineModel):
    original_request: str
    time_range: EventDateRange = Field(default_factory=EventDateRange)
    summary: str = Field(
    description=(
        "Brief evidence-based orientation to the returned timeline. "
        "It may identify major themes or periods, but must not merge, "
        "replace, or omit the atomic event entries."
    )
)
    entries: list[TimelineEntryDraft] = Field(default_factory=list)

class TimelineResult(TimelineModel):
    session_id: str
    account_id: str
    original_request: str
    time_range: EventDateRange = Field(default_factory=EventDateRange)
    summary: str
    entries: list[TimelineEntry] = Field(default_factory=list)
    footnotes: list[TimelineEntry] = Field(
        default_factory=list,
        description="Entries without both startDate and endDate; retained outside chronological timeline entries.",
    )
    time_to_completion_seconds: Optional[float] = None

    @model_validator(mode="after")
    def move_undated_entries_to_footnotes(self) -> "TimelineResult":
        self.entries, undated_entries, _ = partition_timeline_entries(self.entries)
        self.footnotes.extend(undated_entries)
        return self
