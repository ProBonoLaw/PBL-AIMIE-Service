import azure.durable_functions as df
from azure.functions import Context
from opentelemetry import trace
from opentelemetry.propagate import extract

import AIInteractionService.generators.argument_builders.final_response as QaFinalResponse
from AIInteractionService.generators.argument_builders.final_response import FinalResponseRequest, BaseFinalResponseAgent
from AIInteractionService.utils.agent_facilitator import AgentFacilitator
from .utils import aget_base_request_info, execute_retriable_request, generate_standard_response
from .types import QaFinalResponseActivityRequest, argument_builders_final_response_activity_name
from .providers import prepare_providers

bp = df.Blueprint()
tracer = trace.get_tracer(__name__)

@bp.activity_trigger("request", activity=argument_builders_final_response_activity_name)
async def argument_builders_final_response_activity(request: QaFinalResponseActivityRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "argument-builders-final-response-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        request_info = await aget_base_request_info(request)
        vector_store, law_retriever_provider = prepare_providers(request_info.account_info, request.session_id)
        agent_facilitator = AgentFacilitator[BaseFinalResponseAgent](QaFinalResponse)

        decision_request = FinalResponseRequest(
            original_question=request.input,
            aimie_answer=request.aimie_answer,
            bob_response=request.bob_response,
            location=request_info.location,
            aimies_client=request_info.designated_client,
            aimies_filing_role=request_info.designated_client_role,
            opposition=request_info.opposition,
            opposition_role=request_info.opposition_role
        )

        result = await execute_retriable_request(
            request_info, 
            vector_store, 
            law_retriever_provider, 
            None,
            agent_facilitator, 
            decision_request)
            
        return generate_standard_response(result)
