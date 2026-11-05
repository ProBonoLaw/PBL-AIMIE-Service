
from typing import Any, Dict, Type

from langchain_core.language_models import LLM
from langchain_openai import ChatOpenAI

from .types import QARequest, VerbosityLevel
from .base_qa_agent import BaseQaAgent
from ...common import AgentResult, AgentBaseType
from ....utils.state import StateOpenAi


class OpenAiQaAgent(BaseQaAgent[StateOpenAi],
                    metaclass=AgentBaseType,
                   llm_type="openai"):

    def adjust_primary_llm(self, input: QARequest, llm: LLM) -> Dict[str, Any]:
        verbosity_level = input.verbosity_level
        if verbosity_level is not None and verbosity_level != VerbosityLevel.DEFAULT:
            return {"verbosity": verbosity_level.value}
        return {}
        
    def prepare_output(self, output: Any) -> AgentResult:
        return AgentResult(
            answer=output["answer"],
            sources=output["sources"],
            chat_history=output["chat_history"],
            context=output["context"]
        )

    @property
    def output_class_type(self) -> Type:
        return StateOpenAi