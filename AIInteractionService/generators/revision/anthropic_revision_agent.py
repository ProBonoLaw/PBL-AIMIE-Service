
from typing import Any, Optional, Sequence

from langchain_core.prompts.chat import MessageLikeRepresentation


from ...utils.common_types import Source
from ..common import AgentBaseType, AgentResult, AnswersWithSources, formal_answers_with_sources_json_schema
from .base_revision_agent import BaseRevisionAgent


class AnthropicRevisionAgent(
        BaseRevisionAgent,
        metaclass=AgentBaseType,
        llm_type="azureanthropic"):

    def prepare_output(self, output: Any) -> AgentResult:
        structured_output = output['answer']
        if isinstance(structured_output, AnswersWithSources):
            return AgentResult(
                answer=structured_output.answer,
                sources=[Source(docId=x.doc_id, pages=x.pages) for x in structured_output.sources],
                chat_history=output["chat_history"] if "chat_history" in output else [],
                context=output["context"]
            )
        
        return AgentResult(
            answer=output["answer"],
            sources=output["sources"],
            chat_history=output["chat_history"] if "chat_history" in output else [],
            context=output["context"]
        )
    
    @property
    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return [
            ("assistant", "Please provide the JSON schema for the answer."),
            ("human", formal_answers_with_sources_json_schema)
        ]
