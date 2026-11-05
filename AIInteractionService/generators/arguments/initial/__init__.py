from typing import Type


from ....utils.state import StateOpenAi
from ...common import AgentBaseType

from .types import InitialArgumentRequest
from .base_initial_declaration_writer_agent import BaseInitialArgumentAgent


class InitialArgumentAzureOpenAiAgent(
        BaseInitialArgumentAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="azureOpenAI"):

    @property
    def output_class_type(self) -> Type:
        return StateOpenAi


class InitialArgumentOpenAiAgent(BaseInitialArgumentAgent[StateOpenAi],
                                 metaclass=AgentBaseType,
                                 llm_type="openai"):
    @property
    def output_class_type(self) -> Type:
        return StateOpenAi


__all__ = [
    "InitialArgumentRequest",
    "BaseInitialArgumentAgent"
]

module_identifier = "initial_argument"
