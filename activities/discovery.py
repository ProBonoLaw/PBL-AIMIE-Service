from typing import List, Optional
import azure.durable_functions as df
from azure.functions import Context
from opentelemetry import trace
from opentelemetry.propagate import extract

from AIInteractionService.db.azuresearch import AzureSearch
from AIInteractionService.generators.discoveries import DiscoveryRequestBuilder
from AIInteractionService.generators.common.law_retriever_provider import LawRetrieverProvider
from AIInteractionService.utils.accounts import aget_account_info
from .types import DiscoveryActivityRequest, DiscoveryActivityResults
from .providers import init

bp = df.Blueprint()
tracer = trace.get_tracer(__name__)

@bp.activity_trigger("request")
async def discovery_request_activity(request: DiscoveryActivityRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "discovery-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        account_info = await aget_account_info(request.account_id)
        aoai_embeddings, vector_store_address, vector_store_password = init()
        location = f"{account_info.county}, {account_info.state}" if not request.location else request.location

        if not vector_store_address or not vector_store_password:
            raise ValueError("Missing essential configuration settings")
        vector_store: AzureSearch = AzureSearch(
            azure_search_endpoint=vector_store_address,
            azure_search_key=vector_store_password,
            index_name=account_info.data_source_id,
            embedding_function=aoai_embeddings.embed_query,
            semantic_configuration_name='Primary',
            additional_search_client_options={"api_version": "2026-08-01-preview"},
            vector_search_dimensions=aoai_embeddings.dimensions
        )
        law_retriever_provider = LawRetrieverProvider(
            account_info,
            vector_store_address,
            vector_store_password,
            aoai_embeddings)
        discovery_builder = DiscoveryRequestBuilder(
            request.account_id,
            request.session_id,
            vector_store_address,
            vector_store_password,
            aoai_embeddings,
            law_retriever_provider)
        topics: Optional[List[str]] = request.topics
        if not topics:
            topics = []
        if 'General' not in topics:
            topics.append('General')
        result = await discovery_builder.agenerate_response(
            request.input if request.input else 'Generic Discovery Request',
            location,
            request.hearing_type if request.hearing_type else '',
            topics,
            request.target if request.target else '',
            vector_store)

        refined_result = DiscoveryActivityResults.model_validate(result)
        return refined_result
