import azure.durable_functions as df
from azure.functions import Context
from opentelemetry import trace
from opentelemetry.propagate import extract


import AIInteractionService.generators.arguments.initial as BaseInitialArgumentModule
from AIInteractionService.generators.arguments.initial import BaseInitialArgumentAgent, InitialArgumentRequest
from AIInteractionService.utils.agent_facilitator import AgentFacilitator
from .utils import aget_base_request_info, execute_retriable_request, generate_standard_response
from .types import BaseActivityRequest
from .providers import prepare_providers

initial_declaration_activity_bp = df.Blueprint()
tracer = trace.get_tracer(__name__)

@initial_declaration_activity_bp.activity_trigger("request", activity="initialDeclarationActivity")
async def initial_declaration_activity(request: BaseActivityRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "initial-declaration-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        request_info = await aget_base_request_info(request)
        vector_store, law_retriever_provider = prepare_providers(request_info.account_info, request.session_id)
        agent_facilitator = AgentFacilitator[BaseInitialArgumentAgent](BaseInitialArgumentModule)
        
        qa_request = InitialArgumentRequest(
            input=request.input,
            opposition=request_info.opposition,
            opposition_role=request_info.opposition_role,
            designated_client=request_info.designated_client,
            designated_client_role=request_info.designated_client_role,
            location=request_info.location)
        result = await execute_retriable_request(
            request_info, 
            vector_store, 
            law_retriever_provider, 
            None,
            agent_facilitator, 
            qa_request)
            
        return generate_standard_response(result)
