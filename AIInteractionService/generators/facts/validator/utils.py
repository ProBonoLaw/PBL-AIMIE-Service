from typing import Optional

from ....utils.result import get_answer
from ....utils.common_types import Source
from .types import FactValidatorAgentResult, FactValidatorResponse


def convert_llm_result_to_agent_result(output) -> Optional[FactValidatorAgentResult]:
        structured_output = get_answer(output) 
        if isinstance(structured_output, FactValidatorResponse):
            is_valid = structured_output.is_valid
            if not is_valid:
                is_valid = structured_output.is_inferred and structured_output.is_reasonably_inferred
                if not is_valid:
                    is_valid = structured_output.is_implied or structured_output.is_summary_or_conclusion
            return FactValidatorAgentResult(
                answer=structured_output.answer,
                sources=[Source(docId=x.doc_id, pages=x.pages) for x in structured_output.sources],
                chat_history=output["chat_history"] if "chat_history" in output else [],
                context=output["context"] if "context" in output else [],
                contradiction_source=structured_output.contradiction_source,
                contradiction_statement=structured_output.contradiction_statement,
                is_valid=is_valid,
                is_contradictory=structured_output.is_contradictory,
                is_inferred=structured_output.is_inferred,
                is_reasonably_inferred=structured_output.is_reasonably_inferred,
                is_not_found_in_context=structured_output.is_not_found_in_context,
                is_summary_or_conclusion=structured_output.is_summary_or_conclusion,
                is_implied=structured_output.is_implied,
                is_vague=structured_output.is_vague
            )
        return None