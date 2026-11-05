import azure.durable_functions as df
from azure.functions import Context
from opentelemetry import trace
from opentelemetry.propagate import extract

from AIInteractionService.generators.common import ensure_document
import AIInteractionService.generators.declarations as DeclarationModule
from AIInteractionService.generators.declarations import DeclarationWriterAgentRequest, BaseDeclarationWriterAgent, DeclarationWriterOutput
from AIInteractionService.utils.agent_facilitator import AgentFacilitator
from .utils import aget_base_request_info, execute_retriable_request_with_context, normalize_answer, normalize_sources
from .types import DeclarationRequest, DeclarationActivityResult
from .providers import prepare_providers

bp = df.Blueprint()
tracer = trace.get_tracer(__name__)

@bp.activity_trigger("request", activity="declarationActivity")
async def declaration_activity(request: DeclarationRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "declaration-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        request_info = await aget_base_request_info(request)
        _, law_retriever_provider = prepare_providers(request_info.account_info, request.session_id)
        context = ensure_document(request.context)
        source_ids = request.source_ids if request.source_ids else []
        agent_facilitator = AgentFacilitator[BaseDeclarationWriterAgent](DeclarationModule)
        writer_request = DeclarationWriterAgentRequest(
            statement=request.rhetorical_response, 
            location=request_info.location, 
            hearing_type=request.hearing_type if request.hearing_type else '', 
            opposition=request_info.opposition, 
            opposition_role=request_info.opposition_role, 
            designated_client=request_info.designated_client,
            designated_client_role=request_info.designated_client_role)
        new_context = [doc for doc in context if doc.metadata["id"] not in source_ids]
        try:
            result = await execute_retriable_request_with_context(
                    request_info, 
                    None, 
                    new_context,
                    law_retriever_provider, 
                    agent_facilitator, 
                    writer_request)
        except Exception as e:
            return DeclarationActivityResult(
                answer=request.rhetorical_response,
                sources=[],
                has_error=True
            )
        if not isinstance(result, DeclarationWriterOutput):
            return DeclarationActivityResult(
                answer=request.rhetorical_response,
                sources=[],
                has_error=True
            )
        return DeclarationActivityResult(
            answer=normalize_answer(result.answer),
            sources=normalize_sources(result.sources),
            has_error=False
        )
