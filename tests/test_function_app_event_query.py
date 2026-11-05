import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from langchain_core.documents import Document

import azure.functions as func
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("TEXT_EMBEDDING_OPENAI_ENDPOINT", "https://example.openai.azure.com")
os.environ.setdefault("TEXT_EMBEDDING_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_VERSION", "2024-02-01")

instrumentation = ModuleType("utils.instrumentation")
instrumentation.enable_instrumentation = lambda: None
sys.modules["utils.instrumentation"] = instrumentation

import function_app


def _request(body: object) -> func.HttpRequest:
    return func.HttpRequest(
        method="POST",
        url="/api/AIInteractionService/events/query",
        body=json.dumps(body).encode(),
        headers={},
    )


def _context():
    return SimpleNamespace(trace_context=SimpleNamespace(trace_parent=None, trace_state=None))


@pytest.mark.asyncio
async def test_event_query_endpoint_invokes_account_scoped_agent(monkeypatch):
    request_info = SimpleNamespace(account_info=("account-info",))
    captured = {}

    class FakeFacilitator:
        def __init__(self, module):
            captured["module"] = module

        async def get_agent_config(self):
            return SimpleNamespace(primary_prompt=["Search events."])

        async def get_agent_variant_count(self):
            return 1

        async def get_agent_variant_config(self, index):
            return SimpleNamespace(class_name="AzureOpenAiEventQueryAgent", kwargs={}, llm_type="azureOpenAI")

    class FakeAgent:
        async def ainvoke(self, value, config):
            captured["invoke"] = (value, config)
            return {
                "structured_response": {
                    "timeRange": {"startDate": "2024-01", "endDate": "2024-03"},
                    "entries": [{
                        "dateRange": {"startDate": "2024-01-10", "endDate": "2024-01-10"},
                        "eventType": "Custody order",
                        "summary": "A supported answer.",
                        "citationKeys": ["S1"],
                    }]
                }
            }

    async def fake_request_info(request):
        captured["request"] = request
        return request_info

    monkeypatch.setattr(function_app, "aget_base_request_info", fake_request_info)
    monkeypatch.setattr(function_app, "prepare_providers", lambda account, session: ("store", None))

    async def fake_search(store, query, tags, count):
        captured["search"] = (store, query, tags, count)
        return [Document(
            page_content="A supported event.",
            metadata={
                "id": "document-1",
                "sourceId": "source-1",
                "title": "Evidence.pdf",
                "tags": ["event", "custody"],
            },
        )]

    monkeypatch.setattr(function_app, "search_event_documents", fake_search)
    monkeypatch.setattr(function_app, "AgentFacilitator", FakeFacilitator)
    monkeypatch.setattr(function_app, "build_event_query_model", lambda *args: "model")
    monkeypatch.setattr(
        function_app,
        "build_event_query_agent",
        lambda records, model, prompt: FakeAgent(),
    )

    response = await function_app.event_query(
        _request({
            "accountId": "account-1",
            "sessionId": "session-1",
            "tags": ["Custody"],
            "query": "What custody orders were entered?",
        }),
        _context(),
    )

    assert response.status_code == 200
    payload = json.loads(response.get_body())
    assert payload["sessionId"] == "session-1"
    assert payload["accountId"] == "account-1"
    assert payload["tags"] == ["event", "custody"]
    assert payload["originalRequest"] == "What custody orders were entered?"
    assert payload["timeRange"] == {"startDate": "2024-01-10", "endDate": "2024-01-10"}
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["dateRange"]["startDate"] == "2024-01-10"
    assert payload["entries"][0]["eventType"] == "Custody order"
    assert payload["entries"][0]["summary"] == "A supported answer."
    assert captured["request"].account_id == "account-1"
    assert captured["search"] == ("store", "What custody orders were entered?", ["event", "custody"], 20)
    assert captured["invoke"][1]["configurable"]["account_id"] == "account-1"
    assert captured["invoke"][1]["configurable"]["thread_id"].startswith(
        "event_query:v3:"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "message"),
    [
        ([], "Invalid JSON body."),
        (7, "Invalid JSON body."),
        ({"sessionId": "s", "tags": ["event"], "query": "q"}, "Missing accountId parameter."),
        ({"accountId": "a", "tags": ["event"], "query": "q"}, "Missing sessionId parameter."),
        ({"accountId": 123, "sessionId": "s", "tags": ["event"], "query": "q"}, "accountId must be a non-empty string."),
        ({"accountId": "a", "sessionId": 456, "tags": ["event"], "query": "q"}, "sessionId must be a non-empty string."),
        ({"accountId": "a", "sessionId": "s", "query": "q"}, "Missing tags parameter."),
        ({"accountId": "a", "sessionId": "s", "tags": [], "query": "q"}, "tags must be a non-empty array of strings."),
        ({"accountId": "a", "sessionId": "s", "tags": ["event"]}, "Missing query parameter."),
    ],
)
async def test_event_query_endpoint_validates_request(body, message):
    response = await function_app.event_query(_request(body), _context())
    assert response.status_code == 400
    assert json.loads(response.get_body())["message"] == message


@pytest.mark.asyncio
async def test_event_query_endpoint_returns_immediately_when_search_is_empty(monkeypatch):
    request_info = SimpleNamespace(account_info=("account-info",))

    async def fake_request_info(request):
        return request_info

    async def fake_search(store, query, tags, count):
        return []

    monkeypatch.setattr(function_app, "aget_base_request_info", fake_request_info)
    monkeypatch.setattr(function_app, "prepare_providers", lambda account, session: ("store", None))
    monkeypatch.setattr(function_app, "search_event_documents", fake_search)

    response = await function_app.event_query(
        _request({
            "accountId": "account-1",
            "sessionId": "session-1",
            "tags": ["event"],
            "query": "No matching event",
        }),
        _context(),
    )

    assert response.status_code == 200
    assert json.loads(response.get_body())["timeRange"] == {"startDate": None, "endDate": None}
    assert json.loads(response.get_body())["entries"] == []

@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [
    "success", "refusal", "backup", "unsupported", "schema_error",
    "content_filter", "quoted_evidence", "timeout", "no_variants",
])
async def test_event_query_refusal_recovery_preserves_evidence_semantics(monkeypatch, outcome, caplog):
    from langchain.agents.structured_output import StructuredOutputValidationError
    from langchain_core.messages import AIMessage

    calls = []

    class FakeFacilitator:
        def __init__(self, module):
            pass

        async def get_agent_config(self):
            return SimpleNamespace(primary_prompt=['Extract supported events.'])

        async def get_agent_variant_count(self):
            return 0 if outcome == "no_variants" else 2 if outcome == "backup" else 1

        async def get_agent_variant_config(self, index):
            return SimpleNamespace(class_name='test-model', kwargs={'azure_deployment': f'deployment-{index}'}, llm_type='test')

    class FakeAgent:
        async def ainvoke(self, value, config):
            calls.append(value)
            if outcome == 'content_filter':
                raise ValueError('Azure has not provided the response due to a content filter being triggered')
            if outcome == 'timeout':
                raise TimeoutError('review timed out')
            if outcome == 'quoted_evidence':
                raise StructuredOutputValidationError(
                    'EventQueryEntries', ValueError('invalid JSON'),
                    AIMessage(content='{"entries":[{"summary":"The witness said I cannot remember."'),
                )
            if outcome == 'schema_error':
                raise ValueError('invalid schema unrelated to refusal')
            if len(calls) == 1 or outcome == 'refusal' or (outcome == 'backup' and len(calls) == 2):
                raise StructuredOutputValidationError(
                    'EventQueryEntries',
                    ValueError('invalid JSON'),
                    AIMessage(
                        content='',
                        additional_kwargs={'refusal': 'I cannot assist with that request.'},
                    ),
                )
            if outcome == 'unsupported':
                return {'structured_response': {'entries': []}}
            return {
                'structured_response': {
                    'entries': [{
                        'eventType': 'reported_incident',
                        'summary': 'A source-supported incident was reported.',
                        'citationKeys': ["S1"],
                    }],
                },
            }

    async def fake_request_info(request):
        return SimpleNamespace(account_info='account-info')

    async def fake_search(store, query, tags, count):
        return [Document(
            page_content='A source-supported incident.',
            metadata={
                'id': 'document-1', 'sourceId': 'source-1', 'title': 'Evidence.pdf',
                'pages': [2], 'url': 'https://example.com/evidence.pdf',
                'private_internal_field': 'must not be exposed',
                'what': 'The source reported an incident.',
                'whenStarted': {'year': '2018', 'month': '10'},
            },
        )]

    monkeypatch.setattr(function_app, 'aget_base_request_info', fake_request_info)
    monkeypatch.setattr(function_app, 'prepare_providers', lambda account, session: ('store', None))
    monkeypatch.setattr(function_app, 'search_event_documents', fake_search)
    monkeypatch.setattr(function_app, 'AgentFacilitator', FakeFacilitator)
    monkeypatch.setattr(function_app, 'build_event_query_model', lambda *args: 'model')
    monkeypatch.setattr(function_app, 'build_event_query_agent', lambda *args: FakeAgent())

    response = await function_app.event_query(
        _request({
            'accountId': 'account-1',
            'sessionId': 'session-1',
            'tags': ['event'],
            'query': 'All examples of rape.',
        }),
        _context(),
    )

    payload = json.loads(response.get_body())
    assert len(calls) == (0 if outcome == 'no_variants' else 3 if outcome == 'backup' else 1 if outcome in {'schema_error', 'quoted_evidence', 'timeout'} else 2)
    for call in calls:
        content = call['messages'][0]['content']
        assert 'retrospective evidence extraction' in content
        assert 'All examples of rape.' in content
        assert 'do not generate illustrative scenarios' in content
    failure_reasons = {
        'refusal': 'model_refusal',
        'content_filter': 'content_filter',
        'quoted_evidence': 'invalid_structured_output',
        'schema_error': 'model_error',
        'timeout': 'timeout',
        'no_variants': 'no_model_variants',
    }
    if outcome in failure_reasons:
        assert response.status_code == 200
        assert payload['code'] == 'EVENT_QUERY_PARTIAL_RESULT'
        assert payload['retrievalStatus'] == 'succeeded'
        assert payload['reviewStatus'] == 'incomplete'
        assert payload['retrievedRecordCount'] == 1
        assert payload['failureReasons'] == [failure_reasons[outcome]]
        assert payload['originalRequest'] == 'All examples of rape.'
        assert payload['accountId'] == 'account-1'
        assert payload['tags'] == ['event']
        assert payload['retrievedRecords'] == [{
            'recordIndex': 0,
            'docId': 'document-1',
            'sourceId': 'source-1',
            'title': 'Evidence.pdf',
            'url': 'https://example.com/evidence.pdf',
            'pages': [2],
            'tags': [],
            'where': None,
            'what': 'The source reported an incident.',
            'who': [],
            'why': None,
            'dateRange': {'startDate': '2018-10', 'endDate': '2018-10'},
        }]
        assert 'private_internal_field' not in payload['retrievedRecords'][0]
        assert 'Azure AI Search returned 1 citable records' in payload['message']
        assert len(payload["entries"]) == 1
        assert payload["footnotes"] == []
        assert payload['entries'][0] == {
            'dateRange': {'startDate': '2018-10', 'endDate': '2018-10'},
            'eventType': 'Retrieved event',
            'summary': 'The source reported an incident.',
            'applicableSources': [{
                'docId': 'document-1',
                'sourceId': 'source-1',
                'pages': [2],
                'url': 'https://example.com/evidence.pdf',
            }],
        }
        assert payload['timeRange'] == {'startDate': '2018-10', 'endDate': '2018-10'}
        function_app.EventQueryResult.model_validate(payload)
        if outcome == 'refusal':
            assert 'attempt=2 deployment=deployment-0' in caplog.text
            assert 'prompt=retrospective-evidence-v3' in caplog.text
    else:
        assert response.status_code == 200
        assert payload['originalRequest'] == 'All examples of rape.'
        assert len(payload["entries"]) == (0 if outcome == "unsupported" else 1)
        assert payload["footnotes"] == []
        if outcome != "unsupported":
            assert payload["entries"][0]["dateRange"] == {'startDate': '2018-10', 'endDate': '2018-10'}
            assert payload["entries"][0]["eventType"] == "Reported incident"
        assert 'retrievedRecords' not in payload


@pytest.mark.parametrize(('content', 'additional_kwargs', 'expected'), [
    ("I'm sorry, but I cannot assist with that request.", {}, True),
    ('', {'refusal': 'Unable to complete this request.'}, True),
    ([{'type': 'refusal', 'refusal': 'Unable to complete this request.'}], {}, True),
    ([{'type': 'text', 'text': "I cannot assist with that request."}], {}, True),
    ('{"summary":"I cannot remember, the witness said."', {}, False),
    ('{"summary":"I am sorry, the witness said."', {}, False),
    ('{"summary":"A record mentions content_filter and a content filter."', {}, False),
    ('{"entries": []}', {}, False),
])
def test_event_query_identifies_structured_output_refusal(content, additional_kwargs, expected):
    from langchain.agents.structured_output import StructuredOutputValidationError
    from langchain_core.messages import AIMessage

    error = StructuredOutputValidationError(
        "EventQueryEntries",
        ValueError("not JSON"),
        AIMessage(content=content, additional_kwargs=additional_kwargs),
    )
    assert function_app._is_structured_output_refusal(error) is expected
    assert not function_app._is_content_filter_failure(error)


def test_event_query_identifies_provider_failure_signals():
    from langchain.agents.structured_output import StructuredOutputValidationError
    from langchain_core.messages import AIMessage
    from langchain_openai.chat_models.base import OpenAIRefusalError

    assert function_app._is_structured_output_refusal(OpenAIRefusalError('refused'))
    filtered = StructuredOutputValidationError(
        'EventQueryEntries', ValueError('invalid JSON'),
        AIMessage(content='', response_metadata={'finish_reason': 'content_filter'}),
    )
    assert function_app._event_query_review_failure_reason(filtered) == 'content_filter'

    error = RuntimeError('provider failed')
    error.body = {'error': {'code': 'BadRequest', 'innererror': {'code': 'ResponsibleAIPolicyViolation'}}}
    assert function_app._is_content_filter_failure(error)
    error.body = None
    error.code = 'content_filter'
    assert function_app._is_content_filter_failure(error)
    assert not function_app._is_content_filter_failure(ValueError('Invalid content_filter field'))
