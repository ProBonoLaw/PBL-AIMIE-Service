
from typing import Any
from langchain_openai import AzureChatOpenAI


from .base_discovery_topic_question_refinement_writer_agent import BaseDiscoveryRequestRefinementWriterAgent
from .types import DiscoveryRequestRefinementWriterAgentRequest, DiscoveryRequestRefinementWriterAgentOutput
from ...common import BaseAzureOpenAiAgent, LawRetrieverProvider


class AzureOpenAiDiscoveryRequestRefinementWriterAgent(
        BaseDiscoveryRequestRefinementWriterAgent[AzureChatOpenAI],
        BaseAzureOpenAiAgent[DiscoveryRequestRefinementWriterAgentRequest, DiscoveryRequestRefinementWriterAgentOutput]):
    def __init__(self, account_id: str, session_id: str, law_provider: LawRetrieverProvider, **kwargs: Any):
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
                kwargs["azure_deployment"] = f"{kwargs['model']}-librarian"
        super().__init__(account_id, session_id, law_provider, **kwargs)
