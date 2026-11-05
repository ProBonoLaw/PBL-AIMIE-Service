from typing import Any
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from ...common import LawRetrieverProvider, BaseAzureOpenAiAgent
from .types import DiscoveryTopicQuestionsWriterAgentRequest, DiscoveryTopicQuestionsWriterOutput
from .base_discovery_topic_questions_writer_agent import BaseDiscoveryTopicQuestionsWriterAgent


class AzureOpenAiDiscoveryTopicQuestionsWriterAgent(BaseDiscoveryTopicQuestionsWriterAgent[AzureChatOpenAI],
                                                    BaseAzureOpenAiAgent[DiscoveryTopicQuestionsWriterAgentRequest, 
                                                                         DiscoveryTopicQuestionsWriterOutput]):
    def __init__(self, account_id: str, session_id: str, law_provider: LawRetrieverProvider, vector_store_address: str, vector_store_password: str, aoai_embeddings: AzureOpenAIEmbeddings, **kwargs: Any):
        if "use_o1_preview" not in kwargs:
            kwargs["use_o1_preview"] = True
        if not kwargs["use_o1_preview"]:
            if "temperature" not in kwargs:
                kwargs["temperature"] = 0.6
            if "top_p" not in kwargs:
                kwargs["top_p"] = 0.8
            if "max_tokens" not in kwargs:
                kwargs["max_tokens"] = 16384
        else:
            if "model" not in kwargs:
                kwargs["model"] = "o3-mini"
            if "azure_deployment" not in kwargs:
                kwargs["azure_deployment"] = f"{kwargs['model']}-decision"
        super().__init__(account_id, session_id, law_provider, vector_store_address,
                         vector_store_password, aoai_embeddings, **kwargs)
