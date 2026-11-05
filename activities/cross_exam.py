import azure.durable_functions as df
from azure.functions import Context
from opentelemetry import trace
from opentelemetry.propagate import extract

import AIInteractionService.generators.arguments.cross_examination as BaseCrossExaminationModule
from AIInteractionService.generators.arguments.cross_examination import BaseCrossExaminationAgent, CrossExaminationRequest
from AIInteractionService.utils.agent_facilitator import AgentFacilitator
from .utils import aget_base_request_info, execute_retriable_request, generate_standard_response
from .types import BobActivityRequest
from .providers import prepare_providers

bob_bp = df.Blueprint()
tracer = trace.get_tracer(__name__)

@bob_bp.activity_trigger("request", activity="bobActivity")
async def bob_activity(request: BobActivityRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "bob-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        request_info = await aget_base_request_info(request)
        vector_store, law_retriever_provider = prepare_providers(request_info.account_info, request.session_id)
        agent_facilitator = AgentFacilitator[BaseCrossExaminationAgent](BaseCrossExaminationModule)

        bob_request = CrossExaminationRequest(
            original_question=request.input,
            aimie_answer=request.aimie_answer,
            location=request.location,
            opposition=request_info.opposition,
            opposition_role=request_info.opposition_role,
            designated_client=request_info.designated_client,
            designated_client_role=request_info.designated_client_role)

        result = await execute_retriable_request(
            request_info, 
            vector_store, 
            law_retriever_provider, 
            None,
            agent_facilitator, 
            bob_request)
            
        return generate_standard_response(result)
