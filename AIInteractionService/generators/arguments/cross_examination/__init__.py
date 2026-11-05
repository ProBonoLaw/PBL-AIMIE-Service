from typing import Type
from ....utils.state import StateOpenAi
from ...common import AgentBaseType

from .types import CrossExaminationRequest
from .base_cross_examination_agent import BaseCrossExaminationAgent

class OpenAiCrossExaminationAgent(
        BaseCrossExaminationAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="openai"):

    @property
    def output_class_type(self) -> Type:
        return StateOpenAi

class AzureOpenAiCrossExaminationAgent(
        BaseCrossExaminationAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="azureOpenAI",):

    @property
    def output_class_type(self) -> Type:
        return StateOpenAi


__all__ = [
    "CrossExaminationRequest",
    "OpenAiCrossExaminationAgent",
    "AzureOpenAiCrossExaminationAgent",
    "BaseCrossExaminationAgent"
]

module_identifier = "arguments_cross_examination"
