from .types import *

from ...common import AgentBaseType


from .base_librarian_claim_agent import BaseLibrarianClaimAgent

class AzureOpenAiLibrarianClaimAgent(
        BaseLibrarianClaimAgent,
        metaclass=AgentBaseType,
        llm_type="azureOpenAI"):
    pass

class OpenAiLibrarianClaimAgent(
        BaseLibrarianClaimAgent,
        metaclass=AgentBaseType,
        llm_type="openai"):
    pass

class AnthropicLibrarianClaimAgent(
        BaseLibrarianClaimAgent,
        metaclass=AgentBaseType,
        llm_type="anthropic"):
    pass

__all__ = [
    "AzureOpenAiLibrarianClaimAgent",
    "OpenAiLibrarianClaimAgent",
    "AnthropicLibrarianClaimAgent",
    "BaseLibrarianClaimAgent",
    "AmieLibrarianClaimAgentRequest",
    "LibrarianClaimAnswer",
    "LibrarianClaimOutput"
]

module_identifier = "claim_confirmation_librarian"