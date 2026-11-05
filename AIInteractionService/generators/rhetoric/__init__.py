from typing import Optional, Sequence
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts.chat import MessageLikeRepresentation

from .types import *
from .base_rhetoric_writer_agent import BaseRhetoricWriterAgent
from ..common import AgentBaseType, answers_with_sources_json_schema

class AnthropicRhetoricWriterAgent(
    BaseRhetoricWriterAgent[ChatAnthropic], 
    metaclass=AgentBaseType,
    llm_type="azureanthropic"):
    
    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return [("assistant", "Please provide the JSON schema for the answer."),
                ("human", answers_with_sources_json_schema)]

class AzureOpenAiRhetoricWriterAgent(
    BaseRhetoricWriterAgent, 
    metaclass=AgentBaseType,
    llm_type="azureOpenAI"):

    pass

class OpenAiRhetoricWriterAgent(
    BaseRhetoricWriterAgent, 
    metaclass=AgentBaseType,
    llm_type="openai"):

    pass

__all__ = [
    "RhetoricWriterAgentRequest",
    "RhetoricWriterOutput",
    "RhetoricState",
    "AnthropicRhetoricWriterAgent",
    "AzureOpenAiRhetoricWriterAgent",
    "OpenAiRhetoricWriterAgent"
]

module_identifier = "rhetoric"