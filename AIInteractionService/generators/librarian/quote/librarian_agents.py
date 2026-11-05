from ...common.agent_base import AgentBaseType
from .base_librarian_agent import BaseLibrarianAgent


class ChatAnthropicLibrarianAgent(BaseLibrarianAgent,
                                  metaclass=AgentBaseType,
                                  llm_type="anthropic"):
    """Anthropic AI Librarian Agent for handling librarian requests."""
    pass


class OpenAiLibrarianAgent(BaseLibrarianAgent,
                           metaclass=AgentBaseType,
                           llm_type="openAI"):
    """OpenAI Librarian Agent for handling librarian requests."""


class AzureOpenAiLibrarianAgent(BaseLibrarianAgent,
                                metaclass=AgentBaseType,
                                llm_type="azureOpenAI"):
    """Azure OpenAI Librarian Agent for handling librarian requests."""