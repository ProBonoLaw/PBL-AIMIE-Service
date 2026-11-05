
from typing import Type
from typing_extensions import Any


from .base_cross_examination_agent import BaseCrossExaminationAgent
from ...common import AgentResult, AgentBaseType
from ....utils.state import StateOpenAi

class OpenAiCrossExaminationAgent(
        BaseCrossExaminationAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="openAI"):

    @property
    def output_class_type(self) -> Type:
        return StateOpenAi
    