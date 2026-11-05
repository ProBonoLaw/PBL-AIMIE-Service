from types import SimpleNamespace

import pytest

from langgraph.graph import END, START, StateGraph
from AIInteractionService.utils.state import StateOpenAi


from AIInteractionService.generators.argument_builders.initial.azure_open_ai_qa_agent import AzureOpenAiQaAgent as InitialAzureOpenAiQaAgent
from AIInteractionService.generators.argument_builders.initial.open_ai_qa_agent import OpenAiQaAgent as InitialOpenAiQaAgent
from AIInteractionService.generators.argument_builders.initial.types import VerbosityLevel as InitialVerbosityLevel
from AIInteractionService.generators.qa.fast.azure_open_ai_qa_agent import AzureOpenAiQaAgent as FastAzureOpenAiQaAgent
from AIInteractionService.generators.qa.fast.open_ai_qa_agent import OpenAiQaAgent as FastOpenAiQaAgent
from AIInteractionService.generators.qa.fast.types import VerbosityLevel as FastVerbosityLevel
from AIInteractionService.generators.revision.azure_open_ai_revision_agent import AzureOpenAiRevisionAgent
from AIInteractionService.generators.revision.open_ai_revision_agent import OpenAiRevisionAgent
from AIInteractionService.generators.revision.types import VerbosityLevel as RevisionVerbosityLevel


class BindableRunnable:
    def __init__(self):
        self.bind_calls = []
        self.bound = object()

    def bind(self, **kwargs):
        self.bind_calls.append(kwargs)
        return self.bound


class StructuredOutputLlm:
    def __init__(self, runnable):
        self.runnable = runnable
        self.schemas = []

    def with_structured_output(self, schema, **kwargs):
        self.schemas.append((schema, kwargs))
        return self.runnable


@pytest.mark.parametrize(
    ("agent_class", "verbosity_level"),
    [
        (FastOpenAiQaAgent, FastVerbosityLevel.HIGH),
        (FastAzureOpenAiQaAgent, FastVerbosityLevel.HIGH),
        (InitialOpenAiQaAgent, InitialVerbosityLevel.HIGH),
        (InitialAzureOpenAiQaAgent, InitialVerbosityLevel.HIGH),
        (OpenAiRevisionAgent, RevisionVerbosityLevel.HIGH),
        (AzureOpenAiRevisionAgent, RevisionVerbosityLevel.HIGH),
    ],
)
def test_non_default_verbosity_returns_primary_llm_binding(agent_class, verbosity_level):
    agent = object.__new__(agent_class)
    bindings = agent.adjust_primary_llm(
        SimpleNamespace(verbosity_level=verbosity_level), object()
    )

    assert bindings == {"verbosity": verbosity_level.value}


def test_default_verbosity_returns_no_primary_llm_binding():
    agent = object.__new__(FastOpenAiQaAgent)
    bindings = agent.adjust_primary_llm(
        SimpleNamespace(verbosity_level=FastVerbosityLevel.DEFAULT), object()
    )

    assert bindings == {}


@pytest.mark.parametrize(
    "agent_class",
    [
        FastOpenAiQaAgent,
        InitialOpenAiQaAgent,
        OpenAiRevisionAgent,
    ],
)
def test_verbosity_is_bound_to_structured_output_runnable(agent_class):
    structured_output_runnable = BindableRunnable()
    llm = StructuredOutputLlm(structured_output_runnable)
    agent = object.__new__(agent_class)
    agent.llm = llm
    agent._primary_llm_bindings = {"verbosity": "high"}

    result = agent.prepare_llm_for_chain()

    assert len(llm.schemas) == 1
    assert structured_output_runnable.bind_calls == [{"verbosity": "high"}]
    assert result is structured_output_runnable.bound


@pytest.mark.parametrize(
    ("verbosity_level", "expected_fragment"),
    [
        (FastVerbosityLevel.LOW, "one concise sentence"),
        (FastVerbosityLevel.MEDIUM, "80 to 140 words"),
        (FastVerbosityLevel.HIGH, "180 to 300 words"),
    ],
)
def test_verbosity_selects_an_explicit_response_detail_instruction(
    verbosity_level, expected_fragment
):
    instruction = FastOpenAiQaAgent.get_response_detail_instruction(
        SimpleNamespace(verbosity_level=verbosity_level)
    )

    assert expected_fragment in instruction


@pytest.mark.parametrize("agent_class", [FastOpenAiQaAgent, InitialOpenAiQaAgent])
def test_qa_prompt_answers_the_user_question_after_role_context(agent_class):
    agent = object.__new__(agent_class)
    agent.primary_prompt = "Answer from the record."

    messages = agent.get_prompt().invoke(
        {
            "context": "Case context",
            "response_detail_instruction": "Answer in one concise sentence.",
            "chat_history": [],
            "input": "Who is Alex Example?",
            "aimies_client": "Alex Example",
            "aimies_filing_role": "Respondent",
            "opposition": "Jordan Example",
            "opposition_role": "Petitioner",
        }
    ).messages

    assert messages[-1].type == "human"
    assert messages[-1].content == "Who is Alex Example?\n\n"


def test_qa_state_preserves_response_detail_instruction():
    graph = StateGraph(state_schema=StateOpenAi)
    graph.add_node("model", lambda state: {"answer": state["response_detail_instruction"]})
    graph.add_edge(START, "model")
    graph.add_edge("model", END)

    result = graph.compile().invoke({"response_detail_instruction": "detail"})

    assert result["answer"] == "detail"
