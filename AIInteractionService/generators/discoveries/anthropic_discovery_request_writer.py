from typing import Any
from langchain_anthropic import ChatAnthropic
from langchain_openai import AzureChatOpenAI

from .base_discovery_request_writer import BaseDiscoveryRequestWriterAgent
from .types import DiscoveryRequestWriterAgentRequest, DiscoveryRequestWriterOutput
from ..common import BaseChatAnthropicAgent, LawRetrieverProvider


class AnthropicDiscoveryRequestWriterAgent(BaseDiscoveryRequestWriterAgent[ChatAnthropic],
                                           BaseChatAnthropicAgent[DiscoveryRequestWriterAgentRequest,
                                                                  DiscoveryRequestWriterOutput]):
    def __init__(self, account_id: str, session_id: str, law_provider: LawRetrieverProvider, **kwargs: Any):
        if "temperature" not in kwargs:
            kwargs["temperature"] = 0.2
        if "top_p" not in kwargs:
            kwargs["top_p"] = 0.5
        if "model_name" not in kwargs:
            kwargs["model_name"] = "claude-3-opus-20240229"
        if "max_tokens_to_sample" not in kwargs:
            kwargs["max_tokens_to_sample"] = 4096
        super().__init__(account_id, session_id, law_provider, **kwargs)
