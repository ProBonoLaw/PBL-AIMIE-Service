
from typing import Type
from typing_extensions import Any


from .base_cross_examination_agent import BaseCrossExaminationAgent
from ...common import AgentResult, AgentBaseType
from ....utils.state import StateOpenAi

class AzureOpenAiCrossExaminationAgent(
        BaseCrossExaminationAgent[StateOpenAi],
        metaclass=AgentBaseType,
        llm_type="azureOpenAI"):

    @property
    def output_class_type(self) -> Type:
        return StateOpenAi
    
    def prepare_output(self, output: Any) -> AgentResult:
        return AgentResult(
            answer=output["answer"],
            sources=output["sources"],
            chat_history=output["chat_history"],
            context=output["context"]
        )