
from typing import Any

from .base_fact_validator_agent import BaseFactValidatorAgent
from ...common import AgentBaseType
from .types import FactValidatorAgentResult
from .utils import convert_llm_result_to_agent_result


class OpenAiFactValidatorAgent(BaseFactValidatorAgent,
                               metaclass=AgentBaseType,
                               llm_type="openai"):

    def prepare_output(self, output: Any) -> FactValidatorAgentResult:
        result = convert_llm_result_to_agent_result(output)
        if result:
            return result
        raise ValueError(
            "Output is not of type FactValidatorResponse, cannot convert to FactValidatorAgentResult")
