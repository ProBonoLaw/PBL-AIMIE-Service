
from typing import Any
from langchain_openai import AzureChatOpenAI
from ...common import LawRetrieverProvider, BaseAzureOpenAiAgent
from .base_discovery_cross_examination_agent import BaseDiscoveryCrossExaminationAgent
from .types import DiscoveryCrossExaminationRequest, DiscoveryCrossExaminationOutput


class AzureOpenAiDiscoveryCrossExaminationAgent(
    BaseDiscoveryCrossExaminationAgent[AzureChatOpenAI],
    BaseAzureOpenAiAgent[DiscoveryCrossExaminationRequest,
                         DiscoveryCrossExaminationOutput]):
    def __init__(self, account_id: str, session_id: str, law_retriever_provider: LawRetrieverProvider, use_o1_preview: bool = False, **kwargs: Any):
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
                kwargs["azure_deployment"] = f"{kwargs['model']}-cross-exam"
        super().__init__(account_id, session_id, law_retriever_provider, **kwargs)
