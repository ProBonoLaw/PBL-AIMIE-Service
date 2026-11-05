import os
from typing import List
import logging

from azure.monitor.opentelemetry import configure_azure_monitor

from langchain_core.embeddings import Embeddings
from openai import AzureOpenAI
# One-time telemetry init
_appinsights_connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if _appinsights_connection_string:
    try:
        configure_azure_monitor(connection_string=_appinsights_connection_string)
    except Exception as exc:
        logging.warning("Failed to configure Azure Monitor: %s", exc)
else:
    logging.warning("APPLICATIONINSIGHTS_CONNECTION_STRING is not set; Azure Monitor will not be configured.")
default_dimensions = 3072

aoai_endpoint = os.getenv("TEXT_EMBEDDING_OPENAI_ENDPOINT")
if not aoai_endpoint:
    raise RuntimeError(
        "Environment variable 'TEXT_EMBEDDING_OPENAI_ENDPOINT' must be set to a valid Azure OpenAI endpoint URL."
    )

aoai_embeddings = AzureOpenAI(
        azure_deployment=os.getenv("TEXT_EMBEDDING_AZURE_DEPLOYMENT_NAME", "text-embedding-3-large"),
        api_key= os.getenv("TEXT_EMBEDDING_API_KEY", ""),
        azure_endpoint=aoai_endpoint,
    )


class AzureOpenAIEmbeddingsWithTelemetry(Embeddings):
    def __init__(self, account_id: str | None, session_id: str | None, dimensions: int = default_dimensions):
        self.account_id = account_id
        self.session_id = session_id
        self.dimensions = dimensions
        self.deployment = os.getenv("TEXT_EMBEDDING_AZURE_DEPLOYMENT_NAME", "text-embedding-3-large")
        self.model = os.getenv("TEXT_EMBEDDING_AZURE_MODEL_NAME", "text-embedding-3-large")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        resp = aoai_embeddings.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
        )

        # Provider-reported token usage for embeddings
        usage = getattr(resp, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", input_tokens) or input_tokens)

        logging.warning(
            "aoai.embeddings.tokens",
            extra={
                "microsoft.custom_event.name": "token_usage",
                "accountId": self.account_id,
                "sessionId": self.session_id,
                "type": "azure-openai-chat",
                "model": self.model,
                "inputCount": len(texts),
                "inputTokens": input_tokens,
                "outputTokens": 0,
                "reasoningTokens": 0,
                "totalTokens": total_tokens,
                "isSecondaryLLM": False,
            }
        )

        # Return vectors in the shape LangChain expects
        # resp.data is a list of Embedding objects with .embedding
        return [d.embedding for d in resp.data]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]
