import azure.durable_functions as df
from azure.functions import Context
from opentelemetry import trace
from opentelemetry.propagate import extract

import AIInteractionService.generators.arguments.decision as DecisionModule
from AIInteractionService.generators.arguments.decision import FinalDecisionRequest, BaseFinalDecisionAgent
from AIInteractionService.utils.agent_facilitator import AgentFacilitator
from .utils import aget_base_request_info, execute_retriable_request, generate_standard_response
from .types import DecisionActivityRequest
from .providers import prepare_providers

bp = df.Blueprint()
tracer = trace.get_tracer(__name__)

@bp.activity_trigger("request", activity="decisionActivity")
async def decision_activity(request: DecisionActivityRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "decision-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        request_info = await aget_base_request_info(request)
        vector_store, law_retriever_provider = prepare_providers(request_info.account_info, request.session_id)
        agent_facilitator = AgentFacilitator[BaseFinalDecisionAgent](DecisionModule)

        decision_request = FinalDecisionRequest(
            original_question=request.input,
            aimie_answer=request.aimie_answer,
            bob_response=request.bob_response,
            aimie_rebuttal=request.aimie_rebuttal,
            location=request_info.location,
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
            decision_request)
            
        return generate_standard_response(result)
