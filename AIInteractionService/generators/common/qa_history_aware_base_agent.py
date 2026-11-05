
from abc import ABC
from typing import Any, Dict, Generic, Type, TypeVar, Union

from langchain_openai import AzureChatOpenAI
from langchain_core.language_models import LanguageModelInput
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from .law_retriever_provider import LawRetrieverProvider
from .agent_result import AgentResult
from .base_agent import BaseRequestModel
from .history_aware_base_agent import BaseHistoryAwareAgent
from ...utils.state import StateOpenAi
from .types import FormalAnswersWithSources

T = TypeVar('T', bound=BaseRequestModel)


class BaseQAHistoryAwareAgent(
        BaseHistoryAwareAgent[T, AgentResult, StateOpenAi],
        Generic[T],
        ABC):
    def __init__(self, account_id: str, session_id: str, **kwargs: Any):
        super().__init__(account_id, session_id, **kwargs)

    def prepare_output(self, result: Dict[str, Any]) -> Union[AgentResult, StateOpenAi]:
        return AgentResult(
            answer=result["answer"],
            context=result["context"],
            sources=result["sources"],
            chat_history=result["chat_history"]
        )

    @property
    def output_class_type(self) -> Type:
        return StateOpenAi

    def generate_input_retriever(self) -> RunnableLambda[StateOpenAi, str]:
        return RunnableLambda[StateOpenAi, str](lambda x: x.get("input", "") or "")

    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return (self.llm.with_structured_output(FormalAnswersWithSources)).with_retry(stop_after_attempt=3)

    @property
    def system_role_name(self) -> str:
        return "system"
