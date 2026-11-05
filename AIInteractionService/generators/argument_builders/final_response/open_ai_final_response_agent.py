
from typing import Type


from ...common import AgentBaseType
from .base_final_response_agent import BaseFinalResponseAgent
from AIInteractionService.utils.state import StateOpenAi


class OpenAiFinalResponseAgent(
        BaseFinalResponseAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="openAI"):

    @property
    def output_class_type(self) -> Type:
        return StateOpenAi