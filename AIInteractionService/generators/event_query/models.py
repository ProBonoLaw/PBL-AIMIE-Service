from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from AIInteractionService.generators.timelines.models import (
    ApplicableSource as EventQuerySource,
    EventDateRange,
    TimelineEntry,
    normalize_event_type_label,
    partition_timeline_entries,
)


def camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(item.title() for item in rest)


class EventQueryModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class EventQueryEntryDraft(EventQueryModel):
    date_range: EventDateRange = Field(default_factory=EventDateRange)
    event_type: str = Field(
        description="Human-readable, space-separated event label; never snake_case or camelCase.",
    )
    summary: str
    citation_keys: list[str] = Field(
        min_length=1,
        description="Citation keys copied exactly from the supplied evidence records.",
    )


    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_event_type(cls, value: object) -> object:
        return normalize_event_type_label(value)


class EventQueryEntries(EventQueryModel):
    time_range: EventDateRange = Field(default_factory=EventDateRange)
    entries: list[EventQueryEntryDraft] = Field(
        description="Source-backed events matching the query; empty when none are supported.",
    )


class EventQueryResult(EventQueryModel):
    session_id: str
    account_id: str
    tags: list[str]
    originalRequest: str
    time_range: EventDateRange = Field(default_factory=EventDateRange)
    entries: list[TimelineEntry]
    footnotes: list[TimelineEntry] = Field(
        default_factory=list,
        description="Entries without both startDate and endDate; retained outside chronological timeline entries.",
    )

    @model_validator(mode="after")
    def move_undated_entries_to_footnotes(self) -> "EventQueryResult":
        self.entries, undated_entries, _ = partition_timeline_entries(self.entries)
        self.footnotes.extend(undated_entries)
        return self


__all__ = [
    "EventQueryEntries",
    "EventQueryEntryDraft",
    "EventQueryResult",
    "EventQuerySource",
]
