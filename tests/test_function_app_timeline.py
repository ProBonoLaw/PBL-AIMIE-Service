import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

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
        url="/api/AIInteractionService/timeline",
        body=json.dumps(body).encode(),
        headers={},
    )


def _context():
    return SimpleNamespace(
        trace_context=SimpleNamespace(trace_parent=None, trace_state=None)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [[], 7, "invalid-shape", None])
async def test_timeline_endpoint_rejects_non_object_json(body):
    client = SimpleNamespace(start_new=AsyncMock())
    timeline_handler = function_app.timeline._function._func.__wrapped__

    response = await timeline_handler(_request(body), client, _context())

    assert response.status_code == 400
    assert json.loads(response.get_body()) == {"message": "Invalid JSON body."}
    client.start_new.assert_not_awaited()
