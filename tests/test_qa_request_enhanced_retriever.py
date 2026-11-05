import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from AIInteractionService.generators.qa.fast.base_qa_agent import BaseQaAgent
from AIInteractionService.generators.qa.fast.types import QARequest


class ConcreteQaAgent(BaseQaAgent):
    def prepare_output(self, output):
        return output


def _qa_request(**kwargs):
    values = {
        "input": "What happened?",
        "aimies_client": "Client",
        "aimies_filing_role": "Petitioner",
        "opposition": "Opposition",
        "opposition_role": "Respondent",
        "location": "CA",
    }
    values.update(kwargs)
    return QARequest(**values)


def test_qa_request_accepts_use_enhanced_retriever_alias():
    request = _qa_request(useEnhancedRetriever=False)

    assert request.use_enhanced_retriever is False


def test_qa_configurable_uses_request_enhanced_retriever_flag(monkeypatch):
    class DummyTracer:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(
        "AIInteractionService.generators.qa.fast.base_qa_agent.AzureAIOpenTelemetryTracer",
        DummyTracer,
    )

    agent = object.__new__(ConcreteQaAgent)
    agent.session_id = "session-1"
    agent.account_id = "account-1"

    config = ConcreteQaAgent.generate_configurable(agent, _qa_request(use_enhanced_retriever=False))

    assert config["configurable"]["use_enhanced_retriever"] is False


def test_qa_configurable_uses_mapping_enhanced_retriever_flag(monkeypatch):
    class DummyTracer:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(
        "AIInteractionService.generators.qa.fast.base_qa_agent.AzureAIOpenTelemetryTracer",
        DummyTracer,
    )

    agent = object.__new__(ConcreteQaAgent)
    agent.session_id = "session-1"
    agent.account_id = "account-1"

    config = ConcreteQaAgent.generate_configurable(agent, {"use_enhanced_retriever": False})

    assert config["configurable"]["use_enhanced_retriever"] is False


def test_qa_configurable_uses_mapping_enhanced_retriever_alias(monkeypatch):
    class DummyTracer:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(
        "AIInteractionService.generators.qa.fast.base_qa_agent.AzureAIOpenTelemetryTracer",
        DummyTracer,
    )

    agent = object.__new__(ConcreteQaAgent)
    agent.session_id = "session-1"
    agent.account_id = "account-1"

    config = ConcreteQaAgent.generate_configurable(agent, {"useEnhancedRetriever": False})

    assert config["configurable"]["use_enhanced_retriever"] is False
