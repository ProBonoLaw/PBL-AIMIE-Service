from typing import Any
from langchain_anthropic import ChatAnthropic
from langchain_openai import AzureOpenAIEmbeddings

from ...common import LawRetrieverProvider, BaseChatAnthropicAgent
from .types import DiscoveryTopicQuestionsWriterAgentRequest, DiscoveryTopicQuestionsWriterOutput
from .base_discovery_topic_questions_writer_agent import BaseDiscoveryTopicQuestionsWriterAgent


class AnthropicChatDiscoveryTopicQuestionsWriterAgent(BaseDiscoveryTopicQuestionsWriterAgent[ChatAnthropic],
                                        BaseChatAnthropicAgent[DiscoveryTopicQuestionsWriterAgentRequest, DiscoveryTopicQuestionsWriterOutput]):
    def __init__(self, account_id: str, session_id: str, law_provider: LawRetrieverProvider, vector_store_address: str, vector_store_password: str, aoai_embeddings: AzureOpenAIEmbeddings, **kwargs: Any):
        if "temperature" not in kwargs:
            kwargs["temperature"] = 0.6
        if "top_p" not in kwargs:
            kwargs["top_p"] = 0.8
        if "model_name" not in kwargs:
            kwargs["model_name"] = "claude-3-opus-20240229"
        if "max_tokens_to_sample" not in kwargs:
            kwargs["max_tokens_to_sample"] = 4096
        super().__init__(account_id, session_id, law_provider, vector_store_address,
                         vector_store_password, aoai_embeddings, **kwargs)
