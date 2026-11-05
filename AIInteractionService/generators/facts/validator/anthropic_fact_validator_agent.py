
from typing import Any, Optional, Sequence

from langchain_core.prompts.chat import MessageLikeRepresentation

from .utils import convert_llm_result_to_agent_result
from ...common import AgentBaseType
from .base_fact_validator_agent import BaseFactValidatorAgent
from .types import FactValidatorAgentResult, fact_validator_json_schema


class AnthropicFactValidatorAgent(
        BaseFactValidatorAgent,
        metaclass=AgentBaseType,
        llm_type="anthropic"):

    def prepare_output(self, output: Any) -> FactValidatorAgentResult:
        results = convert_llm_result_to_agent_result(output)
        if results:
            return results
        
        is_valid = output.get("is_valid", False)
        if not is_valid:
            is_valid = output.get("is_inferred", False) and output.get("is_reasonably_inferred", False)
            if not is_valid:
                is_valid = output.get("is_implied", False) or output.get("is_summary_or_conclusion", False)
        
        return FactValidatorAgentResult(
            answer=output["answer"],
            sources=output["sources"],
            chat_history=output["chat_history"] if "chat_history" in output else [],
            context=output["context"] if "context" in output else [],
            contradiction_source=output["contradiction_source"] if "contradiction_source" in output else None,
            contradiction_statement=output["contradiction_statement"] if "contradiction_statement" in output else None,
            is_valid=output["is_valid"] if "is_valid" in output else False,
            is_contradictory=output["is_contradictory"] if "is_contradictory" in output else False,
            is_inferred=output["is_inferred"] if "is_inferred" in output else False,
            is_reasonably_inferred=output["is_reasonably_inferred"] if "is_reasonably_inferred" in output else False,
            is_not_found_in_context=output["is_not_found_in_context"] if "is_not_found_in_context" in output else False,
            is_summary_or_conclusion=output["is_summary_or_conclusion"] if "is_summary_or_conclusion" in output else False,
            is_implied=output.get("is_implied", False),
            is_vague=output.get("is_vague", False)
        )
    
    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return [
            ("assistant", "Please provide the JSON schema for the answer."),
            ("human", fact_validator_json_schema)
        ]
