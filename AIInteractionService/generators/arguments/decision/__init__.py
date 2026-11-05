from typing import Any, Optional, Sequence, Type

from langchain_core.prompts.chat import MessageLikeRepresentation
from ...common import AgentBaseType, answers_with_sources_json_schema
from ....utils.state import StateOpenAi

from .types import FinalDecisionRequest
from .base_final_decision_agent import BaseFinalDecisionAgent

class AzureOpenAiFinalDecisionAgent(
        BaseFinalDecisionAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="azureOpenAI"):
    
    @property
    def output_class_type(self) -> Type:
        return StateOpenAi
    
class OpenAiFinalDecisionAgent(
        BaseFinalDecisionAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="openai"):
    
    @property
    def output_class_type(self) -> Type:
        return StateOpenAi

class AnthropicFinalDecisionAgent(
        BaseFinalDecisionAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="anthropic"):
    
    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return [
            ("assistant", "Please provide the JSON schema for the answer."),
            ("human", answers_with_sources_json_schema)
        ]
    
    @property
    def output_class_type(self) -> Type:
        return StateOpenAi
    
__all__ = [
    "FinalDecisionRequest",
    "OpenAiFinalDecisionAgent",
    "AzureOpenAiFinalDecisionAgent",
    "BaseFinalDecisionAgent"
]

module_identifier = "final_decision"
