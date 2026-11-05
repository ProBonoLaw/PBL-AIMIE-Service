from .types import *

from ..common import AgentBaseType


from .base_declaration_writer_agent import BaseDeclarationWriterAgent

class AzureOpenAiDeclarationWriterAgent(
        BaseDeclarationWriterAgent,
        metaclass=AgentBaseType,
        llm_type="azureOpenAI"):
    pass

class OpenAiDeclarationWriterAgent(
        BaseDeclarationWriterAgent,
        metaclass=AgentBaseType,
        llm_type="openai"):
    pass

class AnthropicDeclarationWriterAgent(
        BaseDeclarationWriterAgent,
        metaclass=AgentBaseType,
        llm_type="anthropic"):
    pass

__all__ = [
    'DeclarationBuilderOutput',
    'DeclarationWriterAgentRequest',
    'DeclarationWriterOutput',
    'BaseDeclarationWriterAgent',
    'AnthropicDeclarationWriterAgent',
    'AzureOpenAiDeclarationWriterAgent',
    'OpenAiDeclarationWriterAgent'
]

module_identifier = "final_declaration"