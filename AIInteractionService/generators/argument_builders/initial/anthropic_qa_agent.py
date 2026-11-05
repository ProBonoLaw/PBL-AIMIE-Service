
from typing import Any, Dict, Union, Optional, Sequence

from langchain_core.prompts.chat import MessageLikeRepresentation

from ...common import AgentResult, AgentBaseType, answers_with_sources_json_schema
from .base_qa_agent import BaseQaAgent
from ....utils.state import State, StateOpenAi


class AnthropicQaAgent(
        BaseQaAgent[State],
        metaclass=AgentBaseType,
        llm_type="anthropic"):

    def prepare_output(self, result: Dict[str, Any]) -> Union[AgentResult, StateOpenAi]:
        return AgentResult(
            answer=result["answer"],
            context=result["context"],
            sources=result["sources"],
            chat_history=result["chat_history"]
        )

    @property
    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return [
            ("assistant", "Please provide the JSON schema for the answer."),
            ("human", answers_with_sources_json_schema)
        ]
