from typing import Any, Dict

from langchain_openai import AzureChatOpenAI
from langchain_core.language_models import LLM

from AIInteractionService.utils.result import get_answer

from .types import VerbosityLevel, RevisionRequest
from ...utils.common_types import Source
from .base_revision_agent import BaseRevisionAgent
from ..common import AgentResult, AgentBaseType, AnswersWithSources


class AzureOpenAiRevisionAgent(
        BaseRevisionAgent,
        metaclass=AgentBaseType,
        llm_type="azureOpenAI"):
    
    def adjust_primary_llm(self, input: RevisionRequest, llm: LLM) -> Dict[str, Any]:
        verbosity_level = input.verbosity_level
        if verbosity_level is not None and verbosity_level != VerbosityLevel.DEFAULT:
            return {"verbosity": verbosity_level.value}
        return {}
    
    def prepare_output(self, output: Any) -> AgentResult:
        structured_output = get_answer(output)
        if isinstance(structured_output, AnswersWithSources):
            return AgentResult(
                answer=structured_output.answer,
                sources=[
                    Source(docId=x.doc_id, pages=x.pages)
                    for x in structured_output.sources
                ],
                chat_history=output["chat_history"] if "chat_history" in output else [],
                context=output["context"],
            )
        raise ValueError("Output is not of type AnswersWithSources")
