import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any
from langchain_core.documents import Document
from toon import encode
from langchain_core.tools import tool
from langchain_core.language_models import BaseChatModel
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from deepagents.profiles import HarnessProfile, register_harness_profile
from AIInteractionService.db.azuresearch import AzureSearch
from AIInteractionService.generators.common.agent_base import AgentBaseType
from AIInteractionService.generators.common.azure_anthropic import AzureChatAnthropic
from AIInteractionService.db.cosmosdb_checkpointer import CosmosDBSaver
from AIInteractionService.db.cosmosdb_handler import CosmosDBHandler
from .models import (
    ApplicableSource,
    EventDateRange,
    TimelineDraft,
    TimelineEntry,
    TimelineEntryDraft,
    TimelineResult,
    fact_date_to_event_date_range,
    fill_missing_event_date_range,
    partition_timeline_entries,
)

EVENT_FILTER = "tags/any(tag: tag eq 'event')"
TIMELINE_SOURCE_ARTIFACT_TYPE = 'aimie.timeline.sources'
TIMELINE_SOURCE_ARTIFACT_VERSION = 2
SourceKey = tuple[str, str]
TIMELINE_SKILL_SOURCE = '/skills/timeline'
TIMELINE_SKILLS_DIRECTORY = Path(__file__).parent / 'skills'
AZURE_ANTHROPIC_PROVIDER = 'azure_anthropic'
_azure_anthropic_harness_lock = Lock()
_azure_anthropic_harness_registered = False



TIMELINE_SEARCH_CALL_BUDGET = 20
DOMESTIC_VIOLENCE_PROFILE = {
    'direct_terminology': (
        'domestic violence domestic abuse family violence intimate partner violence DV'
    ),
    'physical_conduct': (
        'hit struck slapped punched kicked shoved pushed grabbed restrained dragged bit'
    ),
    'high_risk_threats': (
        'strangled choked suffocated weapon threatened to kill death threat intimidation'
    ),
    'coercion_stalking_property': (
        'coercive control isolation surveillance monitoring financial control prevented leaving '
        'stalking followed repeated calls tracking harassment damaged property broke door '
        'punched wall destroyed phone'
    ),
    'law_enforcement_and_orders': (
        'police sheriff deputy 911 incident report arrest probable cause protection order '
        'restraining order no contact order emergency order order violation'
    ),
    'injury_safety_and_child_exposure': (
        'injury bruise swelling fracture emergency room photographs safety plan shelter victim '
        'advocate crisis line lethality assessment child witnessed child present child intervened '
        'CPS report sexual assault forced sex unwanted sexual contact'
    ),
}
_DOMESTIC_VIOLENCE_SCOPE_PATTERN = re.compile(
    r'\b(?:domestic[\s-]+(?:violence|abuse)|family violence|'
    r'intimate[\s-]+partner violence|DV)\b',
    re.IGNORECASE,
)


@dataclass
class TimelineScopeCoverage:
    """Records deterministic retrieval coverage for a critical request scope."""

    profile_name: str | None = None
    required_clusters: list[str] = field(default_factory=list)
    searched_clusters: dict[str, int] = field(default_factory=dict)
    unsearched_clusters: list[str] = field(default_factory=list)

    @property
    def scope_requested(self) -> bool:
        return self.profile_name is not None

    @property
    def complete(self) -> bool:
        return self.scope_requested and not self.unsearched_clusters

    def record_search(self, cluster: str, new_source_count: int) -> None:
        self.searched_clusters[cluster] = new_source_count

    def record_unsearched(self, cluster: str) -> None:
        if cluster not in self.unsearched_clusters:
            self.unsearched_clusters.append(cluster)

    def prompt_context(self) -> str:
        if not self.scope_requested:
            return ''
        searched = ', '.join(
            f'{cluster} ({count} new source records)'
            for cluster, count in self.searched_clusters.items()
        ) or 'none'
        unsearched = ', '.join(self.unsearched_clusters) or 'none'
        return (
            'Application retrieval coverage for the domestic-violence scope: '
            f'searched clusters: {searched}; unsearched required clusters: {unsearched}. '
            'These are retrieval cues only, not findings. Do not characterize conduct as '
            'domestic violence, abuse, a crime, or a legal violation unless a returned '
            'source or adjudication supports that characterization.'
        )


class TimelineSearchBudget:
    """Thread-safe limit shared by deterministic and agent-directed searches."""

    def __init__(self, limit: int = TIMELINE_SEARCH_CALL_BUDGET) -> None:
        self._remaining = max(0, limit)
        self._lock = Lock()

    @property
    def remaining(self) -> int:
        with self._lock:
            return self._remaining

    def consume(self) -> bool:
        with self._lock:
            if self._remaining <= 0:
                return False
            self._remaining -= 1
            return True


def domestic_violence_scope_requested(request_input: str) -> bool:
    return bool(_DOMESTIC_VIOLENCE_SCOPE_PATTERN.search(request_input))


def timeline_skill_files() -> dict[str, dict[str, str]]:
    """Return packaged timeline skills for DeepAgents' state-backed filesystem."""
    skill_names: list[str] = []
    files: dict[str, dict[str, str]] = {}
    try:
        for skill_file in sorted(TIMELINE_SKILLS_DIRECTORY.glob('*/SKILL.md')):
            skill_names.append(skill_file.parent.name)
            for source_file in sorted(skill_file.parent.rglob('*')):
                if not source_file.is_file():
                    continue
                relative_path = source_file.relative_to(
                    TIMELINE_SKILLS_DIRECTORY,
                ).as_posix()
                files[f'{TIMELINE_SKILL_SOURCE}/{relative_path}'] = {
                    'content': source_file.read_text(encoding='utf-8'),
                    'encoding': 'utf-8',
                }
    except OSError:
        logging.exception(
            'timeline_skill_loader_failed',
            extra={
                'microsoft.custom_event.name': 'timeline_skill_loader_failed',
                'skillCount': len(skill_names),
                'skillFileCount': len(files),
                'skills': ','.join(skill_names),
            },
        )
        raise

    logging.info(
        'timeline_skill_loader',
        extra={
            'microsoft.custom_event.name': 'timeline_skill_loader',
            'skillCount': len(skill_names),
            'skillFileCount': len(files),
            'skills': ','.join(skill_names),
        },
    )
    return files


class UnknownTimelineCitationError(ValueError):
    def __init__(self, citation_key: str) -> None:
        self.citation_key = citation_key
        super().__init__(
            'Timeline citation key was not returned by a search tool: '
            f'{citation_key!r}'
        )


def _source_from_document(
    document: Document,
    result_index: int,
) -> ApplicableSource | None:
    metadata = document.metadata
    doc_id = (
        metadata.get('documentId')
        or metadata.get('docId')
        or metadata.get('id')
    )
    source_id = metadata.get('sourceId') or metadata.get('source_id')
    if (
        doc_id is None
        or source_id is None
        or not str(doc_id).strip()
        or not str(source_id).strip()
    ):
        logging.warning(
            'Skipping uncitable timeline result %d without docId/sourceId',
            result_index,
        )
        return None

    raw_pages = metadata.get('pages') or metadata.get('pageNumbers')
    if raw_pages is None:
        pages = None
    elif isinstance(raw_pages, (list, tuple, set)):
        pages = [
            page for page in raw_pages
            if isinstance(page, (int, str)) and not isinstance(page, bool)
        ] or None
    elif isinstance(raw_pages, (int, str)) and not isinstance(raw_pages, bool):
        pages = [raw_pages]
    else:
        pages = None

    url = metadata.get('url') or metadata.get('source')
    return ApplicableSource(
        doc_id=str(doc_id),
        source_id=str(source_id),
        url=str(url) if url is not None else None,
        pages=pages,
    )


class TimelineSourceRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._citation_keys: dict[SourceKey, str] = {}
        self._date_ranges: dict[str, EventDateRange] = {}
        self._sources: dict[str, ApplicableSource] = {}

    @staticmethod
    def _source_key(source: ApplicableSource) -> SourceKey:
        return source.doc_id, source.source_id

    def _new_citation_key(self) -> str:
        index = len(self._sources) + 1
        while f'S{index}' in self._sources:
            index += 1
        return f'S{index}'

    def register(self, source: ApplicableSource) -> str:
        citation_key, _ = self.register_with_status(source)
        return citation_key

    def register_with_status(self, source: ApplicableSource) -> tuple[str, bool]:
        """Register a source and report whether it was new to this registry."""
        with self._lock:
            source_key = self._source_key(source)
            citation_key = self._citation_keys.get(source_key)
            if citation_key is None:
                citation_key = self._new_citation_key()
                self._store(citation_key, source)
                return citation_key, True

            self._store(citation_key, source)
            return citation_key, False

    def _store(self, citation_key: str, source: ApplicableSource) -> None:
        source_key = self._source_key(source)
        existing_key = self._citation_keys.get(source_key)
        if existing_key is not None and existing_key != citation_key:
            raise ValueError(
                'Timeline source is mapped to conflicting citation keys: '
                f'{existing_key!r} and {citation_key!r}'
            )

        existing = self._sources.get(citation_key)
        if existing is not None and self._source_key(existing) != source_key:
            raise ValueError(
                f'Timeline citation key {citation_key!r} maps to conflicting sources.'
            )

        self._citation_keys[source_key] = citation_key
        if existing is None:
            self._sources[citation_key] = source.model_copy(deep=True)
            return

        pages = list(existing.pages or [])
        for page in source.pages or []:
            if page not in pages:
                pages.append(page)
        self._sources[citation_key] = ApplicableSource(
            doc_id=existing.doc_id,
            source_id=existing.source_id,
            url=existing.url or source.url,
            pages=pages or None,
        )

    def set_date_range(
        self,
        citation_key: str,
        date_range: EventDateRange,
    ) -> None:
        with self._lock:
            if citation_key not in self._sources:
                raise UnknownTimelineCitationError(citation_key)
            if date_range.start_date is None and date_range.end_date is None:
                return
            existing_date_range = self._date_ranges.get(citation_key)
            if (
                existing_date_range is None
                or (
                    existing_date_range.start_date is None
                    and existing_date_range.end_date is None
                )
            ):
                self._date_ranges[citation_key] = date_range.model_copy(deep=True)

    def artifact(self, citation_keys: list[str]) -> dict[str, object]:
        with self._lock:
            sources = {
                citation_key: self._sources[citation_key].model_dump(
                    mode='json',
                    by_alias=True,
                )
                for citation_key in dict.fromkeys(citation_keys)
            }
            date_ranges = {
                citation_key: self._date_ranges[citation_key].model_dump(
                    mode='json',
                    by_alias=True,
                )
                for citation_key in sources
                if citation_key in self._date_ranges
            }
        return {
            'type': TIMELINE_SOURCE_ARTIFACT_TYPE,
            'version': TIMELINE_SOURCE_ARTIFACT_VERSION,
            'sources': sources,
            'dateRanges': date_ranges,
        }

    def restore_artifact(self, artifact: object) -> None:
        if not isinstance(artifact, dict):
            return
        if artifact.get('type') != TIMELINE_SOURCE_ARTIFACT_TYPE:
            return
        if artifact.get('version') != TIMELINE_SOURCE_ARTIFACT_VERSION:
            raise ValueError('Unsupported timeline source artifact version.')
        raw_sources = artifact.get('sources')
        if not isinstance(raw_sources, dict):
            raise ValueError('Timeline source artifact must contain a source mapping.')

        raw_date_ranges = artifact.get('dateRanges', {})
        if not isinstance(raw_date_ranges, dict):
            raise ValueError('Timeline source artifact dateRanges must be a mapping.')

        sources: list[tuple[str, ApplicableSource]] = []
        for citation_key, raw_source in raw_sources.items():
            if not isinstance(citation_key, str) or not citation_key:
                raise ValueError('Timeline source artifact contains an invalid citation key.')
            sources.append((
                citation_key,
                ApplicableSource.model_validate(raw_source),
            ))

        date_ranges: dict[str, EventDateRange] = {}
        for citation_key, raw_date_range in raw_date_ranges.items():
            if citation_key not in raw_sources:
                raise ValueError('Timeline source artifact date range has no source.')
            date_ranges[citation_key] = EventDateRange.model_validate(
                raw_date_range,
            )

        with self._lock:
            for citation_key, source in sources:
                self._store(citation_key, source)

            for citation_key, date_range in date_ranges.items():
                existing_date_range = self._date_ranges.get(citation_key)
                if existing_date_range is None or (
                    existing_date_range.start_date is None
                    and existing_date_range.end_date is None
                ):
                    self._date_ranges[citation_key] = date_range.model_copy(deep=True)

    def restore_from_messages(self, messages: object) -> None:
        if not isinstance(messages, list):
            return
        for message in messages:
            artifact = (
                message.get('artifact')
                if isinstance(message, dict)
                else getattr(message, 'artifact', None)
            )
            self.restore_artifact(artifact)

    def citation_keys(self) -> list[str]:
        with self._lock:
            return list(self._sources)

    def resolve_timeline(
        self,
        timeline: TimelineDraft,
        *,
        account_id: str,
        session_id: str,
    ) -> TimelineResult:
        with self._lock:
            sources = {
                key: source.model_copy(deep=True)
                for key, source in self._sources.items()
            }
            date_ranges = {
                key: date_range.model_copy(deep=True)
                for key, date_range in self._date_ranges.items()
            }
        resolved_entries: list[TimelineEntry] = []
        for entry in timeline.entries:
            resolved_sources: list[ApplicableSource] = []
            source_date_ranges: list[EventDateRange] = []
            seen: set[str] = set()
            for citation_key in entry.citation_keys:
                source = sources.get(citation_key)
                if source is None:
                    raise UnknownTimelineCitationError(citation_key)
                if citation_key not in seen:
                    resolved_sources.append(source.model_copy(deep=True))
                    date_range = date_ranges.get(citation_key)
                    if date_range is not None:
                        source_date_ranges.append(date_range.model_copy(deep=True))
                    seen.add(citation_key)
            resolved_entries.append(TimelineEntry(
                date_range=fill_missing_event_date_range(
                    entry.date_range,
                    source_date_ranges,
                ),
                event_type=entry.event_type,
                summary=entry.summary,
                applicable_sources=resolved_sources,
            ))
        resolved_entries, footnotes, time_range = partition_timeline_entries(
            resolved_entries
        )
        return TimelineResult(
            session_id=session_id,
            account_id=account_id,
            original_request=timeline.original_request,
            time_range=time_range,
            summary=timeline.summary,
            entries=resolved_entries,
            footnotes=footnotes,
        )


def _records_with_artifact(
    documents: list[Document],
    source_registry: TimelineSourceRegistry | None = None,
) -> tuple[str, dict[str, object]]:
    registry = source_registry or TimelineSourceRegistry()
    records = []
    citation_keys = []
    for result_index, document in enumerate(documents):
        source = _source_from_document(document, result_index)
        if source is None:
            continue
        citation_key, is_new_source = registry.register_with_status(source)
        registry.set_date_range(
            citation_key,
            fact_date_to_event_date_range(
                document.metadata.get('whenStarted'),
                document.metadata.get('whenEnded'),
            ),
        )
        if not is_new_source:
            continue
        citation_keys.append(citation_key)
        records.append({
            'citationKey': citation_key,
            'tags': document.metadata.get('tags', []),
            'where': document.metadata.get('where'),
            'what': document.metadata.get('what'),
            'who': document.metadata.get('who', []),
            'why': document.metadata.get('why'),
            'dateRange': fact_date_to_event_date_range(
                document.metadata.get('whenStarted'),
                document.metadata.get('whenEnded'),
            ).model_dump(mode='json', by_alias=True)
        })
    return encode(records), registry.artifact(citation_keys)

def _records_with_context(
    documents: list[Document],
    source_registry: TimelineSourceRegistry | None = None,
) -> tuple[str, dict[str, object]]:
    registry = source_registry or TimelineSourceRegistry()
    records = []
    citation_keys = []
    seen_citation_keys: set[str] = set()
    for result_index, document in enumerate(documents):
        source = _source_from_document(document, result_index)
        if source is None:
            continue
        citation_key, _ = registry.register_with_status(source)
        registry.set_date_range(
            citation_key,
            fact_date_to_event_date_range(
                document.metadata.get('whenStarted'),
                document.metadata.get('whenEnded'),
            ),
        )
        if citation_key in seen_citation_keys:
            continue
        seen_citation_keys.add(citation_key)
        citation_keys.append(citation_key)
        records.append({
            'citationKey': citation_key,
            'content': document.page_content,
        })
    return encode(records), registry.artifact(citation_keys)


def _records(
    documents: list[Document],
    source_registry: TimelineSourceRegistry | None = None,
) -> str:
    content, _ = _records_with_artifact(documents, source_registry)
    return content


async def _search_event_records_with_artifact(
    vector_store: AzureSearch,
    query: str,
    count: int,
    source_registry: TimelineSourceRegistry | None = None,
) -> tuple[str, dict[str, object]]:
    documents = await vector_store.asemantic_hybrid_search(
        query,
        k=count,
        filters=EVENT_FILTER,
    )
    return _records_with_artifact(documents, source_registry)

async def _search_event_records(
    vector_store: AzureSearch,
    query: str,
    count: int,
    source_registry: TimelineSourceRegistry | None = None,
) -> str:
    content, _ = await _search_event_records_with_artifact(
        vector_store,
        query,
        count,
        source_registry,
    )
    return content


async def preload_critical_scope_records(
    vector_store: AzureSearch,
    request_input: str,
    count: int,
    source_registry: TimelineSourceRegistry,
    search_budget: TimelineSearchBudget,
) -> tuple[str, TimelineScopeCoverage]:
    """Retrieve deterministic evidence clusters before model candidate extraction."""
    if not domestic_violence_scope_requested(request_input):
        return '', TimelineScopeCoverage()

    coverage = TimelineScopeCoverage(
        profile_name='domestic_violence',
        required_clusters=list(DOMESTIC_VIOLENCE_PROFILE),
    )
    records: list[str] = []
    for cluster, query in DOMESTIC_VIOLENCE_PROFILE.items():
        if not search_budget.consume():
            coverage.record_unsearched(cluster)
            continue
        documents = await vector_store.asemantic_hybrid_search(
            query,
            k=max(1, min(count, 1000)),
            filters=EVENT_FILTER,
        )
        content, artifact = _records_with_artifact(documents, source_registry)
        sources = artifact.get('sources', {})
        new_source_count = len(sources) if isinstance(sources, dict) else 0
        coverage.record_search(cluster, new_source_count)
        if new_source_count:
            records.append(content)

    logging.info(
        'timeline_scope_coverage',
        extra={
            'microsoft.custom_event.name': 'timeline_scope_coverage',
            'profile': coverage.profile_name,
            'searchedClusters': ','.join(coverage.searched_clusters),
            'unsearchedClusters': ','.join(coverage.unsearched_clusters),
            'searchBudgetRemaining': search_budget.remaining,
        },
    )
    return '\n\n'.join(records), coverage


def build_timeline_agent(
    vector_store: AzureSearch,
    max_doc_count: int,
    model: BaseChatModel,
    system_prompt: str,
    source_registry: TimelineSourceRegistry | None = None,
    search_budget: TimelineSearchBudget | None = None,
) -> Any:
    try:
        from deepagents import create_deep_agent
    except ImportError as error:
        raise RuntimeError('The deepagents package is required for timeline generation.') from error
    count = max(1, min(max_doc_count, 1000))
    _configure_azure_anthropic_harness(model)
    registry = source_registry or TimelineSourceRegistry()
    budget = search_budget or TimelineSearchBudget()

    @tool(response_format='content_and_artifact')
    async def search_case_events(query: str) -> tuple[str, dict[str, object]]:
        """Search event-tagged account records for timeline facts."""
        if not budget.consume():
            logging.warning('Timeline search budget exhausted before event search.')
            return encode([]), registry.artifact([])
        return await _search_event_records_with_artifact(
            vector_store,
            query,
            count,
            registry,
        )

    @tool(response_format='content_and_artifact')
    async def search_case_context(query: str) -> tuple[str, dict[str, object]]:
        """Search account records for context supporting a timeline event."""
        if not budget.consume():
            logging.warning('Timeline search budget exhausted before context search.')
            return encode([]), registry.artifact([])
        documents = await vector_store.asemantic_hybrid_search(query, k=min(count, 50))
        return _records_with_context(documents, registry)

    handler = CosmosDBHandler(os.environ['COSMOS_MESSAGE_HISTORY_ENDPOINT'], os.environ.get('COSMOS_MESSAGE_HISTORY_DATABASE', 'db_conversation_history'), os.environ.get('COSMOS_MESSAGE_HISTORY_CONTAINER', 'messages2'))
    saver = CosmosDBSaver(
        handler,
        allowed_msgpack_modules=[
            ('AIInteractionService.generators.timelines.models', model_type.__name__)
            for model_type in (
                ApplicableSource,
                EventDateRange,
                TimelineDraft,
                TimelineEntry,
                TimelineEntryDraft,
                TimelineResult,
            )
        ],
    )
    return create_deep_agent(
        model=model,
        tools=[
            search_case_events,
            search_case_context,
        ],
        system_prompt=system_prompt,
        skills=[TIMELINE_SKILL_SOURCE],
        response_format=TimelineDraft,
        checkpointer=saver,
    )


def _configure_azure_anthropic_harness(model: BaseChatModel) -> None:
    """Prevent DeepAgents from sending unsupported Anthropic cache controls.

    AzureChatAnthropic subclasses ChatAnthropic, so DeepAgents' unconditional
    Anthropic prompt-caching middleware would otherwise decorate requests with
    ``cache_control``. Azure AI Foundry rejects those requests. The provider
    key is unique to the wrapper, leaving direct Anthropic models unchanged.
    """
    if not isinstance(model, AzureChatAnthropic):
        return

    global _azure_anthropic_harness_registered
    with _azure_anthropic_harness_lock:
        if _azure_anthropic_harness_registered:
            return
        register_harness_profile(
            AZURE_ANTHROPIC_PROVIDER,
            HarnessProfile(
                excluded_middleware=frozenset({AnthropicPromptCachingMiddleware}),
            ),
        )
        _azure_anthropic_harness_registered = True
    logging.info(
        'Disabled Anthropic prompt caching for Azure AI Foundry timeline models.',
    )


def build_timeline_model(class_name: str, kwargs: dict, llm_type: str | None = None) -> BaseChatModel:
    return AgentBaseType.build_model(llm_type or AgentBaseType.llm_type_for_class_name(class_name), kwargs)
