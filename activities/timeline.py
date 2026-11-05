import logging
import time
from typing import Any
import azure.durable_functions as df
from opentelemetry import trace
from opentelemetry.propagate import extract

from azure.functions import Context
from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_openai.chat_models.base import OpenAIRefusalError
import AIInteractionService.generators.timelines as TimelineModule
from AIInteractionService.generators.timelines import build_timeline_agent
from AIInteractionService.generators.timelines.models import TimelineDraft, TimelineResult
from AIInteractionService.generators.timelines.agent import (
    TimelineSearchBudget,
    TimelineSourceRegistry,
    UnknownTimelineCitationError,
    build_timeline_model,
    preload_critical_scope_records,
    timeline_skill_files,
)
from AIInteractionService.utils.agent_facilitator import AgentFacilitator
from AIInteractionService.utils.token_types import log_agent_token_usage
from .providers import prepare_providers
from .utils import aget_base_request_info
from .types import BaseActivityRequest

bp = df.Blueprint()
tracer = trace.get_tracer(__name__)
TIMELINE_CHECKPOINT_VERSION = 'v2'
MAX_TIMELINE_GROUNDING_ATTEMPTS = 2

_TIMELINE_REFUSAL_MARKERS = (
    "i'm sorry",
    'i am sorry',
    'i cannot',
    "i can't",
    "i'm unable",
    'i am unable',
)
_TIMELINE_PROFESSIONAL_EVIDENCE_CONTEXT = (
    'This workflow performs retrospective evidence extraction and neutral '
    'summarization of existing legal and investigative records for professional '
    'case review. Requests involving violence, abuse, sexual assault, rape, threats, '
    'stalking, weapons, or injuries ask for source-supported historical evidence, not '
    'instructions '
    'to facilitate harm. Continue the evidence-review workflow, preserve '
    'attribution and denials, avoid unnecessary graphic detail, and return only '
    'the requested TimelineDraft.'
)

def parse_timeline_request(request: object) -> BaseActivityRequest:
    return BaseActivityRequest.model_validate(request)


def timeline_thread_id(session_id: str, variant: int) -> str:
    return f'timeline:{TIMELINE_CHECKPOINT_VERSION}:{session_id}:variant:{variant}'


def timeline_request_with_scope_records(
    original_request: str,
    records_toon: str,
    coverage: Any,
) -> str:
    """Attach deterministic scope evidence without changing the user request."""
    if not coverage.scope_requested:
        return original_request
    return f"""Original user request (copy this exact value to originalRequest):
{original_request}

{coverage.prompt_context()}

The application completed the mandatory scope-expansion searches before candidate extraction. Review the pre-retrieved records below together with any later tool results. Do not treat an empty cluster as proof that no event occurred.

<pre_retrieved_records format="toon">
{records_toon or '[0]:'}
</pre_retrieved_records>"""


def _is_structured_output_refusal(error: Exception) -> bool:
    """Return whether a provider declined a native structured response."""
    # LangChain raises this directly when the Responses API includes a
    # structured-output refusal, rather than wrapping it in a validation error.
    if isinstance(error, OpenAIRefusalError):
        return True
    if not isinstance(error, StructuredOutputValidationError):
        return False

    message = error.ai_message
    if message.additional_kwargs.get('refusal'):
        return True

    content = message.content
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get('type') == 'refusal' or part.get('refusal'):
                    return True
                text = part.get('text') or part.get('content')
                if isinstance(text, str):
                    text_parts.append(text)
            elif isinstance(part, str):
                text_parts.append(part)
        content = ' '.join(text_parts)

    if not isinstance(content, str):
        return False
    normalized = content.casefold().replace('\u2019', "'")
    return any(marker in normalized for marker in _TIMELINE_REFUSAL_MARKERS)


def _is_content_filter_failure(error: Exception) -> bool:
    """Recognize provider-side filtering without treating it as absent evidence."""
    message = getattr(error, 'ai_message', None)
    metadata = getattr(message, 'response_metadata', {}) or {}
    if metadata.get('finish_reason') == 'content_filter':
        return True

    detail = str(error).casefold()
    return 'content_filter' in detail or 'content filter' in detail


def _is_empty_structured_output_failure(error: Exception) -> bool:
    """Recognize a blank native structured response worth one safe retry."""
    if not isinstance(error, StructuredOutputValidationError):
        return False

    message = error.ai_message
    content = message.content
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str) and part.strip():
                return False
            if isinstance(part, dict) and any(
                isinstance(part.get(key), str) and part[key].strip()
                for key in ('text', 'content', 'refusal')
            ):
                return False
        return True
    return content is None


async def restore_timeline_source_registry(
    agent: Any, config: dict[str, Any], source_registry: TimelineSourceRegistry
) -> None:
    """Restore checkpointed source keys before allocating new ones."""
    checkpoint = await agent.aget_state(config)
    checkpoint_values = getattr(checkpoint, 'values', None)
    if isinstance(checkpoint_values, dict):
        source_registry.restore_from_messages(checkpoint_values.get('messages'))


async def invoke_timeline_agent(
    agent: Any,
    request_input: str,
    config: dict[str, Any],
    source_registry: TimelineSourceRegistry,
    *,
    account_id: str,
    session_id: str,
) -> tuple[dict[str, Any], TimelineResult]:
    await restore_timeline_source_registry(agent, config, source_registry)

    agent_input = {
        'messages': [{'role': 'user', 'content': request_input}],
        'files': timeline_skill_files(),
    }
    refusal_recovery_attempted = False
    for attempt in range(MAX_TIMELINE_GROUNDING_ATTEMPTS):
        try:
            result = await agent.ainvoke(agent_input, config=config)
        except Exception as error:
            is_refusal = _is_structured_output_refusal(error)
            is_content_filter = _is_content_filter_failure(error)
            is_empty_output = _is_empty_structured_output_failure(error)
            if not (is_refusal or is_content_filter or is_empty_output) or refusal_recovery_attempted:
                raise
            refusal_recovery_attempted = True
            if is_refusal:
                failure_kind = 'structured-output refusal'
            elif is_content_filter:
                failure_kind = 'content filter'
            else:
                failure_kind = 'empty structured output'
            logging.warning(
                'Timeline model returned %s; retrying once with professional '
                'evidence-extraction context.',
                failure_kind,
            )
            agent_input = {
                'messages': [{
                    'role': 'user',
                    'content': (
                        f'{_TIMELINE_PROFESSIONAL_EVIDENCE_CONTEXT}\n\n'
                        'Preserve the original requested scope. Do not treat a refusal, '
                        'content filter, or parser failure as evidence that no responsive '
                        'records exist.\n\n'
                        f'Original task and retrieved evidence:\n{request_input}'
                    ),
                }],
                'files': timeline_skill_files(),
            }
            continue
        source_registry.restore_from_messages(result.get('messages'))
        timeline_draft = TimelineDraft.model_validate(result['structured_response'])
        try:
            return result, source_registry.resolve_timeline(
                timeline_draft,
                account_id=account_id,
                session_id=session_id,
            )
        except UnknownTimelineCitationError as error:
            if attempt + 1 >= MAX_TIMELINE_GROUNDING_ATTEMPTS:
                raise
            valid_keys = source_registry.citation_keys()
            logging.warning(
                'Timeline model returned unknown citation key %s; requesting '
                'one grounded correction from %d available keys.',
                error.citation_key,
                len(valid_keys),
            )
            allowed = ', '.join(valid_keys) if valid_keys else '(none yet)'
            agent_input = {
                'messages': [{
                    'role': 'user',
                    'content': (
                        'Correct the previous structured response. It used the '
                        f'unknown citationKey {error.citation_key!r}. Use only '
                        f'these exact citationKey values: {allowed}. If none '
                        'support an entry, search again or omit that entry. '
                        'Never invent or alter a citationKey.'
                    ),
                }],
            }

    raise RuntimeError('Timeline grounding attempts were exhausted.')


@bp.activity_trigger('request', activity='timelineActivity')
async def timeline_activity(request: BaseActivityRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "timeline-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        request = parse_timeline_request(request)
        request_info = await aget_base_request_info(request)
        vector_store, _ = prepare_providers(request_info.account_info, request.session_id)
        facilitator = AgentFacilitator(TimelineModule)
        agent_config = await facilitator.get_agent_config()
        if not agent_config.primary_prompt:
            raise RuntimeError('Timeline agent configuration is missing primaryPrompt.')
        system_prompt = "\n\n".join(agent_config.primary_prompt)
        started = time.monotonic()
        variant_errors: list[tuple[int, Exception]] = []
        for index in range(await facilitator.get_agent_variant_count()):
            model = None
            usage_callback = None
            result = None
            try:
                model_config = await facilitator.get_agent_variant_config(index)
                model = build_timeline_model(model_config.class_name, model_config.kwargs, model_config.llm_type)
                source_registry = TimelineSourceRegistry()
                search_budget = TimelineSearchBudget()
                agent = build_timeline_agent(
                    vector_store,
                    request.max_doc_count,
                    model,
                    system_prompt,
                    source_registry=source_registry,
                    search_budget=search_budget,
                )
                usage_callback = UsageMetadataCallbackHandler()
                invoke_config = {
                    'callbacks': [usage_callback],
                    "recursion_limit": 500,
                    'configurable': {
                        'account_id': request.account_id,
                        'thread_id': timeline_thread_id(
                            request.session_id,
                            index,
                        ),
                    },
                }
                await restore_timeline_source_registry(
                    agent, invoke_config, source_registry,
                )
                preloaded_records, scope_coverage = await preload_critical_scope_records(
                    vector_store,
                    request.input,
                    request.max_doc_count,
                    source_registry,
                    search_budget,
                )
                result, timeline = await invoke_timeline_agent(
                    agent,
                    timeline_request_with_scope_records(
                        request.input,
                        preloaded_records,
                        scope_coverage,
                    ),
                    invoke_config,
                    source_registry,
                    account_id=request.account_id,
                    session_id=request.session_id,
                )
                timeline.original_request = request.input
                if scope_coverage.unsearched_clusters:
                    limitation = (
                        ' Scope coverage limitation: required domestic-violence '
                        'retrieval clusters were not searched because the search budget '
                        f'was exhausted: {", ".join(scope_coverage.unsearched_clusters)}.'
                    )
                    timeline.summary = f'{timeline.summary.rstrip()}{limitation}'
                timeline.time_to_completion_seconds = time.monotonic() - started
                return timeline.model_dump(mode='json', by_alias=True)
            except Exception as error:
                variant_errors.append((index, error))
                logging.exception('Timeline model variant %d failed', index)
            finally:
                if usage_callback is not None:
                    log_agent_token_usage(
                        result or {},
                        account_id=request.account_id,
                        session_id=request.session_id,
                        operation='timeline',
                        llm=model,
                        variant=index,
                        usage_metadata=usage_callback.usage_metadata,
                    )
        failures = '; '.join(
            f'variant {index}: {type(error).__name__}: {error}'
            for index, error in variant_errors
        )
        last_error = variant_errors[-1][1] if variant_errors else None
        raise RuntimeError(f'All timeline model variants failed. {failures}') from last_error
