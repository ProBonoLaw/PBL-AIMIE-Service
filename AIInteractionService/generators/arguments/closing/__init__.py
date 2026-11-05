from typing import Type

from ....utils.state import StateOpenAi
from ...common import AgentBaseType

from .types import ClosingArgumentRequest, limit_tokens_used
from .base_closing_argument_agent import BaseClosingArgumentAgent


class OpenAiClosingArgumentAgent(
        BaseClosingArgumentAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="openai"):

    @property
    def output_class_type(self) -> Type:
        return StateOpenAi


class AzureOpenAiClosingArgumentAgent(
        BaseClosingArgumentAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="azureOpenAI"):

    @property
    def output_class_type(self) -> Type:
        return StateOpenAi


__all__ = [
    'ClosingArgumentRequest',
    'BaseClosingArgumentAgent',
    'limit_tokens_used',
    'OpenAiClosingArgumentAgent'
]


module_identifier = "closing_argument"
