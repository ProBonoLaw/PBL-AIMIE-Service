import os
from typing import List, Optional
from langchain_openai import AzureOpenAIEmbeddings
import logging

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, ContainerProxy
from azure.ai.textanalytics import TextAnalyticsClient
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.retrievers import BaseRetriever

from ...db.azuresearch import AzureSearch
from ...utils.accounts import AccountInfo
from ...utils.azure_credentials import default_azure_credential_options


class LawRetrieverProvider:
    def __init__(self, 
                 account_info: AccountInfo,
                 vector_store_address: str,
                 aoai_embeddings: AzureOpenAIEmbeddings,
                 max_retrieval_results: int = 5):
        if not account_info:
            raise ValueError("AccountInfo is required")
        self.account_info = account_info
        self.vector_store_address = vector_store_address
        self.aoai_embeddings = aoai_embeddings
        self.max_retrieval_results = max_retrieval_results
        endpoint = os.getenv("AZURE_COGNITIVE_SERVICE_ENDPOINT")
        if not endpoint:
            raise ValueError("Please provide the Azure Cognitive Service endpoint in the environment variable AZURE_COGNITIVE_SERVICE_ENDPOINT")
        key = os.getenv("AZURE_COGNITIVE_SERVICE_KEY")
        if not key:
            raise ValueError("Please provide the Azure Cognitive Service key in the environment variable AZURE_COGNITIVE_SERVICE_KEY")
        credential = AzureKeyCredential(key)
        self.question_answer_client = TextAnalyticsClient(endpoint, credential)

    def get_law_retriever(self) -> Optional[EnsembleRetriever]:
        logging.info("Getting Laws for {0}".format(self.account_info.account_id))
        default_credential = DefaultAzureCredential(**default_azure_credential_options())
        cosmos_endpoint = os.getenv("ACCOUNT_COSMOS_ENDPOINT", None)
        database_name = os.getenv(
            "ACCOUNT_COSMOS_DATABASE", "db_conversation_history")
        container_name = os.getenv("ACCOUNT_COSMOS_CONTAINER", "accounts")
        if not cosmos_endpoint:
            raise ValueError("COSMOS_ENDPOINT is missing")
        cosmos_client = CosmosClient(
            cosmos_endpoint, default_credential)
        database = cosmos_client.get_database_client(database_name)
        container = database.get_container_client(container_name)
        results = list()
        results.extend(self.__find_state_laws(self.account_info, container))
        results.extend(self.__find_county_laws(self.account_info, container))
        results.extend(self.__find_city_laws(self.account_info, container))
        if len(results) == 0:
            logging.info("No laws found for account {0}".format(self.account_info.account_id))
            return None
        weights = [1.0 for _ in results]
        return EnsembleRetriever(retrievers=results, weights=weights)
    
    def __find_city_laws(self, accountInfo, container):
        resultsCounties = list(
            container.query_items(
                ("SELECT * FROM c WHERE c.type = 'ACCOUNT_DETAILS' AND c.isSharedResource = true AND "
                 "(STRINGEQUALS(c.state, @state, true) OR STRINGEQUALS(c.stateCd, @state, true)) AND "
                 "STRINGEQUALS(c.county, @county, true) AND STRINGEQUALS(c.city, @city, true)"),
                parameters=[dict(name="@state", value=accountInfo.state),
                            dict(name="@city", value=accountInfo.county)],
                enable_cross_partition_query=True,
                max_item_count=1))
        if len(resultsCounties) == 0:
            logging.info("County is not found for account {0}".format(accountInfo.account_id))
            return []
        logging.info("County found for account info for {0}".format(accountInfo.account_id))
        return [self._generate_retriever(result["dataSourceId"]) for result in resultsCounties]

    def __find_county_laws(self, accountInfo, container):
        resultsCounties = list(
            container.query_items(
                ("SELECT * FROM c WHERE c.type = 'ACCOUNT_DETAILS' AND c.isSharedResource = true AND "
                 "(STRINGEQUALS(c.state, @state, true) OR STRINGEQUALS(c.stateCd, @state, true)) AND "
                 "STRINGEQUALS(c.county, @county, true) AND NOT IS_DEFINED(c.city)"),
                parameters=[dict(name="@state", value=accountInfo.state),
                            dict(name="@county", value=accountInfo.county)],
                enable_cross_partition_query=True,
                max_item_count=1))
        if len(resultsCounties) == 0:
            logging.info("County is not found for account {0}".format(accountInfo.account_id))
            return []
        logging.info("County found for account info for {0}".format(accountInfo.account_id))
        return [self._generate_retriever(result["dataSourceId"]) for result in resultsCounties]

    def __find_state_laws(self, accountInfo: AccountInfo, container:ContainerProxy) -> List[BaseRetriever]:
        resultsStates = list(
            container.query_items(
                ("SELECT * FROM c WHERE c.type = 'ACCOUNT_DETAILS' AND c.isSharedResource = true AND "
                 "(STRINGEQUALS(c.state, @state, true) OR STRINGEQUALS(c.stateCd, @state, true)) AND "
                 "NOT IS_DEFINED(c.county) AND NOT IS_DEFINED(c.city)"),
                parameters=[dict(name="@state", value=accountInfo.state)],
                enable_cross_partition_query=True,
                max_item_count=1))
        if len(resultsStates) == 0:
            raise FileNotFoundError(
                "State is not supported for account {0}".format(accountInfo.account_id))
        logging.info("State found for account info for {0}".format(accountInfo.account_id))
        return [self._generate_retriever(result["dataSourceId"]) for result in resultsStates]
    
    def _generate_retriever(self, index_name: str):
        vector_store =  AzureSearch(
            azure_search_endpoint=self.vector_store_address,
            index_name=index_name,
            embedding_function=self.aoai_embeddings.embed_query,
            semantic_configuration_name='Primary',
            additional_search_client_options={"api_version": "2026-08-01-preview"},
            vector_search_dimensions=self.aoai_embeddings.dimensions
        )
        return vector_store.as_retriever(
            search_type="semantic_hybrid",
            k=self.max_retrieval_results
        )
    