import os
from typing import Optional

from functools import lru_cache
from langchain_openai import AzureOpenAIEmbeddings
from pydantic import SecretStr
from AIInteractionService.db.azuresearch import AzureSearch
from AIInteractionService.generators.common.law_retriever_provider import LawRetrieverProvider
from AIInteractionService.utils.accounts import AccountInfo
from utils.azure_open_ai_embeddings import AzureOpenAIEmbeddingsWithTelemetry


def init(account_id: Optional[str] = None, session_id: Optional[str] = None) -> AzureOpenAIEmbeddingsWithTelemetry:
    aoai_embeddings = AzureOpenAIEmbeddingsWithTelemetry(account_id=account_id, session_id=session_id)

    return aoai_embeddings


@lru_cache()
def prepare_providers(account_info: AccountInfo, session_id: str):
    if not account_info:
        raise ValueError("Account information is required to prepare providers")
    aoai_embeddings = init(account_id=account_info.account_id, session_id=session_id)
    index_name: str = account_info.data_source_id
    if not account_info.search_endpoint:
        raise ValueError("Missing essential configuration settings")
    vector_store: AzureSearch = AzureSearch(
        azure_search_endpoint=account_info.search_endpoint,
        azure_search_key=None,
        index_name=index_name,
        embedding_function=aoai_embeddings.embed_query,
        semantic_configuration_name='Primary',
        additional_search_client_options={"api_version": "2026-08-01-preview"},
        vector_search_dimensions=aoai_embeddings.dimensions
    )
    law_retriever_provider = LawRetrieverProvider(
        account_info,
        account_info.search_endpoint,
        aoai_embeddings) if not account_info.is_shared_resource and not account_info.is_web_site else None

    return vector_store, law_retriever_provider
