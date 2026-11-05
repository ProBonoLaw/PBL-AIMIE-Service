import os
import sys
from types import ModuleType, SimpleNamespace

import pytest
from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai.chat_models.base import OpenAIRefusalError

os.environ.setdefault('TEXT_EMBEDDING_OPENAI_ENDPOINT', 'https://example.openai.azure.com')
os.environ.setdefault('TEXT_EMBEDDING_API_KEY', 'test-key')
os.environ.setdefault('OPENAI_API_VERSION', '2024-02-01')

instrumentation = ModuleType('utils.instrumentation')
instrumentation.enable_instrumentation = lambda: None
sys.modules.setdefault('utils.instrumentation', instrumentation)

import activities.timeline as timeline_activity_module
from activities.timeline import (
    _is_empty_structured_output_failure,
    _is_content_filter_failure,
    _is_structured_output_refusal,
    invoke_timeline_agent,
    restore_timeline_source_registry,
    parse_timeline_request,
    timeline_thread_id,
)
from AIInteractionService.generators.timelines.agent import TimelineSourceRegistry
from AIInteractionService.generators.timelines.models import (
    ApplicableSource,
    TimelineResult,
)


def test_timeline_activity_parses_durable_dictionary_payload():
    request = parse_timeline_request({
        'account_id': 'account-123',
        'session_id': 'session-456',
        'input': 'Build a timeline.',
        'location': '',
        'hearing_type': None,
        'max_doc_count': 20,
    })

    assert request.account_id == 'account-123'
    assert request.session_id == 'session-456'


def test_timeline_content_filter_is_not_classified_as_no_evidence():
    assert _is_content_filter_failure(RuntimeError('HTTP 400: content_filter'))
    assert not _is_content_filter_failure(ValueError('invalid TimelineDraft JSON'))


def test_timeline_content_filter_metadata_is_recognized():
    error = StructuredOutputValidationError(
        'TimelineDraft',
        ValueError('invalid JSON'),
        AIMessage(content='', response_metadata={'finish_reason': 'content_filter'}),
    )

    assert _is_content_filter_failure(error)


def test_timeline_empty_structured_output_is_recoverable():
    error = StructuredOutputValidationError(
        'TimelineDraft',
        ValueError('invalid JSON'),
        AIMessage(content=''),
    )

    assert _is_empty_structured_output_failure(error)


def test_timeline_direct_provider_refusal_is_recognized():
    assert _is_structured_output_refusal(
        OpenAIRefusalError('I cannot assist with that request.')
    )


def test_timeline_checkpoint_thread_is_stable_and_variants_are_isolated():
    assert timeline_thread_id('session-456', 0) == (
        'timeline:v2:session-456:variant:0'
    )
    assert timeline_thread_id('session-456', 0) == timeline_thread_id(
        'session-456', 0
    )
    assert timeline_thread_id('session-456', 0) != timeline_thread_id(
        'session-456', 1
    )
    assert timeline_thread_id('session-456', 0) != timeline_thread_id(
        'session-789', 0
    )


@pytest.mark.asyncio
async def test_timeline_agent_hydrates_checkpoint_and_corrects_unknown_key():
    persisted_registry = TimelineSourceRegistry()
    valid_key = persisted_registry.register(ApplicableSource(
        doc_id='document-1',
        source_id='source-1',
    ))
    artifact = persisted_registry.artifact([valid_key])

    class FakeAgent:
        def __init__(self):
            self.inputs = []

        async def aget_state(self, config):
            return SimpleNamespace(values={
                'messages': [ToolMessage(
                    content=f'citationKey: {valid_key}',
                    artifact=artifact,
                    tool_call_id='search-call-1',
                )],
            })

        async def ainvoke(self, value, config):
            self.inputs.append(value)
            citation_key = 'S999' if len(self.inputs) == 1 else valid_key
            return {
                'messages': [],
                'structured_response': {
                    'originalRequest': 'Build a timeline.',
                    'summary': 'Supported summary.',
                    'entries': [{
                        'eventType': 'Order',
                        'summary': 'Supported event.',
                        'citationKeys': [citation_key],
                    }],
                },
            }

    agent = FakeAgent()
    config = {
        'configurable': {
            'account_id': 'account-123',
            'thread_id': timeline_thread_id('session-456', 0),
        },
    }

    _, timeline = await invoke_timeline_agent(
        agent,
        'Build a timeline.',
        config,
        TimelineSourceRegistry(),
        account_id='account-123',
        session_id='session-456',
    )

    assert len(agent.inputs) == 2
    assert valid_key in agent.inputs[1]['messages'][0]['content']
    assert timeline.footnotes[0].applicable_sources[0].doc_id == 'document-1'


@pytest.mark.asyncio
async def test_timeline_agent_retries_a_structured_output_refusal_without_empty_release():
    registry = TimelineSourceRegistry()
    valid_key = registry.register(ApplicableSource(
        doc_id='document-1',
        source_id='source-1',
    ))

    class FakeAgent:
        def __init__(self):
            self.inputs = []

        async def aget_state(self, config):
            return SimpleNamespace(values={})

        async def ainvoke(self, value, config):
            self.inputs.append(value)
            if len(self.inputs) == 1:
                raise StructuredOutputValidationError(
                    'TimelineDraft',
                    ValueError('not JSON'),
                    AIMessage(content=(
                        '{"entries":[{"summary":"supported event"},'
                        '"summary":"I\'m sorry, but I cannot assist with that request."'
                    )),
                )
            return {
                'messages': [],
                'structured_response': {
                    'originalRequest': 'Domestic violence timeline.',
                    'summary': 'One source-grounded event.',
                    'entries': [{
                        'eventType': 'report_made',
                        'summary': 'A report was made.',
                        'citationKeys': [valid_key],
                    }],
                },
            }

    agent = FakeAgent()
    _, timeline = await invoke_timeline_agent(
        agent,
        'Domestic violence timeline.',
        {'configurable': {}},
        registry,
        account_id='account-123',
        session_id='session-456',
    )

    assert len(agent.inputs) == 2
    assert 'retrospective evidence extraction' in agent.inputs[1]['messages'][0]['content']
    assert len(timeline.footnotes) == 1


@pytest.mark.asyncio
async def test_timeline_activity_logs_usage_for_failed_and_successful_variants(
    monkeypatch,
):
    class FakeFacilitator:
        def __init__(self, module):
            pass

        async def get_agent_config(self):
            return SimpleNamespace(primary_prompt=['Build a grounded timeline.'])

        async def get_agent_variant_count(self):
            return 2

        async def get_agent_variant_config(self, index):
            return SimpleNamespace(
                class_name=f'model-{index}',
                kwargs={},
                llm_type='test',
            )

    async def fake_request_info(request):
        return SimpleNamespace(account_info='account-info')

    async def fake_invoke(
        agent,
        request_input,
        config,
        source_registry,
        *,
        account_id,
        session_id,
    ):
        callback = config['callbacks'][0]
        variant = int(agent.removeprefix('model-'))
        callback.usage_metadata[f'model-{variant}'] = {
            'input_tokens': 10 + variant,
            'output_tokens': 5,
        }
        if variant == 0:
            raise ValueError('grounding failed')
        return {'messages': []}, TimelineResult(
            session_id=session_id,
            account_id=account_id,
            original_request=request_input,
            summary='Supported timeline.',
        )

    logged = []

    async def fake_restore(*args, **kwargs):
        return None
    monkeypatch.setattr(
        timeline_activity_module,
        'aget_base_request_info',
        fake_request_info,
    )
    monkeypatch.setattr(
        timeline_activity_module,
        'prepare_providers',
        lambda account_info, session_id: ('store', None),
    )
    monkeypatch.setattr(
        timeline_activity_module,
        'AgentFacilitator',
        FakeFacilitator,
    )
    monkeypatch.setattr(
        timeline_activity_module,
        'build_timeline_model',
        lambda class_name, kwargs, llm_type: class_name,
    )
    monkeypatch.setattr(
        timeline_activity_module,
        'build_timeline_agent',
        lambda vector_store, max_docs, model, prompt, **kwargs: model,
    )
    monkeypatch.setattr(
        timeline_activity_module,
        'restore_timeline_source_registry',
        fake_restore,
    )
    monkeypatch.setattr(
        timeline_activity_module,
        'invoke_timeline_agent',
        fake_invoke,
    )
    monkeypatch.setattr(
        timeline_activity_module,
        'log_agent_token_usage',
        lambda result, **kwargs: logged.append((result, kwargs)),
    )
    request = {
        'account_id': 'account-123',
        'session_id': 'session-456',
        'input': 'Build a timeline.',
        'location': '',
        'hearing_type': None,
        'max_doc_count': 20,
    }
    context = SimpleNamespace(
        trace_context=SimpleNamespace(trace_parent=None, trace_state=None)
    )

    response = await timeline_activity_module.timeline_activity._function._func(
        request,
        context,
    )

    assert response['summary'] == 'Supported timeline.'
    assert response['sessionId'] == 'session-456'
    assert response['accountId'] == 'account-123'
    assert [entry[1]['variant'] for entry in logged] == [0, 1]
    assert logged[0][1]['usage_metadata']['model-0']['input_tokens'] == 10
    assert logged[1][1]['usage_metadata']['model-1']['input_tokens'] == 11


@pytest.mark.asyncio
async def test_checkpoint_sources_are_restored_before_preloading_records():
    persisted_registry = TimelineSourceRegistry()
    persisted_key = persisted_registry.register(
        ApplicableSource(doc_id='checkpoint-doc', source_id='checkpoint-source')
    )
    artifact = persisted_registry.artifact([persisted_key])

    class FakeAgent:
        async def aget_state(self, config):
            return SimpleNamespace(values={
                'messages': [ToolMessage(
                    content='',
                    artifact=artifact,
                    tool_call_id='checkpoint-search',
                )],
            })

    class FakeStore:
        async def asemantic_hybrid_search(self, query, *, k, filters):
            return [Document(
                page_content='New source.',
                metadata={'id': 'preloaded-doc', 'sourceId': 'preloaded-source'},
            )]

    registry = TimelineSourceRegistry()
    await restore_timeline_source_registry(FakeAgent(), {}, registry)
    await timeline_activity_module.preload_critical_scope_records(
        FakeStore(),
        'Generate a timeline about domestic violence.',
        5,
        registry,
        timeline_activity_module.TimelineSearchBudget(),
    )

    assert persisted_key == 'S1'
    assert registry.citation_keys() == ['S1', 'S2']
