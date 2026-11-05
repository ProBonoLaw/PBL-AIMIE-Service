
from typing import Any, Type, Dict

from langchain_core.runnables import Runnable
from langchain_core.language_models import LanguageModelInput
from pydantic import BaseModel

from .base_final_response_agent import BaseFinalResponseAgent
from ...common import AgentBaseType, AgentResult, AnswersWithSources
from ....utils.state import StateOpenAi


class AzureOpenAiFinalResponseAgent(
        BaseFinalResponseAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="azureOpenAI"):

    @property
    def output_class_type(self) -> Type:
        return StateOpenAi