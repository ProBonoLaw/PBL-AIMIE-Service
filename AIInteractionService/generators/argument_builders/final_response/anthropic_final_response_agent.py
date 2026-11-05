
from typing import Any, Type, Dict

from langchain_anthropic import ChatAnthropic
from langchain_core.runnables import Runnable
from langchain_core.language_models import LanguageModelInput
from pydantic import BaseModel

from .base_final_response_agent import BaseFinalResponseAgent
from ...common import AgentBaseType, AgentResult, AnswersWithSources
from .types import FinalResponseRequest
from ....utils.state import State


class AnthropicFinalResponseAgent(
        BaseFinalResponseAgent[State],
        metaclass=AgentBaseType,
        llm_type="anthropic"):

    @property
    def output_class_type(self) -> Type:
        return State