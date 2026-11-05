import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

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
from AIInteractionService.generators.qa.fast.types import VerbosityLevel


def _fast_qa_request(body: dict) -> func.HttpRequest:
    return func.HttpRequest(
        method="POST",
        url="/api/AIInteractionService/qa/fast",
        body=json.dumps(body).encode("utf-8"),
        headers={},
    )


def _function_context():
    return SimpleNamespace(
        trace_context=SimpleNamespace(trace_parent=None, trace_state=None)
    )


@pytest.mark.asyncio
async def test_qa_trigger_normalizes_low_verbosity_to_default(monkeypatch):
    request_info = SimpleNamespace(
        account_info=("account-info",),
        location="Cook County, IL",
        designated_client="Jane Client",
        designated_client_role="Petitioner",
        opposition="John Opponent",
        opposition_role="Respondent",
    )
    captured_requests = []

    class DummyAgentFacilitator:
        def __init__(self, *args, **kwargs):
            pass

        @classmethod
        def __class_getitem__(cls, item):
            return cls

    async def fake_get_base_request_info(request):
        return request_info

    async def fake_execute_retriable_request(
        request_info_arg,
        vector_store,
        law_provider,
        context,
        agent_facilitator,
        agent_request,
    ):
        captured_requests.append(agent_request)
        if len(captured_requests) == 1:
            return {
                "answer": "QA answer",
                "chat_history": [],
                "sources": [],
                "context": [],
            }

        return {
            "answer": "Fact check passed",
            "context": [],
            "sources": [],
            "is_valid": True,
            "is_contradictory": False,
            "is_inferred": False,
            "is_reasonably_inferred": False,
            "is_not_found_in_context": False,
            "is_summary_or_conclusion": False,
            "is_implied": False,
            "is_vague": False,
            "contradiction_source": "",
            "contradiction_statement": "",
        }

    monkeypatch.setattr(function_app, "AgentFacilitator", DummyAgentFacilitator)
    monkeypatch.setattr(function_app, "aget_base_request_info", fake_get_base_request_info)
    monkeypatch.setattr(
        function_app,
        "prepare_providers",
        lambda account_info, session_id: ("vector-store", "law-provider"),
    )
    monkeypatch.setattr(
        function_app, "execute_retriable_request", fake_execute_retriable_request
    )

    req = _fast_qa_request(
        {
            "accountId": "account-1",
            "sessionId": "session-1",
            "question": "What happened?",
            "maxDocCount": 3,
            "verbosityLevel": "low",
            "useEnhancedRetriever": False,
        }
    )

    resp = await function_app.qa_trigger(req, _function_context())

    assert resp.status_code == 200
    assert len(captured_requests) == 2
    assert captured_requests[0].verbosity_level == VerbosityLevel.DEFAULT
    assert captured_requests[0].use_enhanced_retriever is False
