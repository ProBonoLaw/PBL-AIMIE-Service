import azure.durable_functions as df
from azure.functions import Context 
from opentelemetry import trace
from opentelemetry.propagate import extract

from AIInteractionService.generators.argument_builders.initial import QARequest, BaseQaAgent
import AIInteractionService.generators.argument_builders.initial as QaAgent
from AIInteractionService.generators.argument_builders.initial.anthropic_qa_agent import AnthropicQaAgent
from AIInteractionService.utils.agent_facilitator import AgentFacilitator

from .utils import aget_base_request_info, execute_retriable_request, generate_standard_response
from .types import BaseActivityRequest, argument_builders_initial_activity_name
from .providers import prepare_providers

tracer = trace.get_tracer(__name__)
argument_builders_activity_bp = df.Blueprint()
@argument_builders_activity_bp.activity_trigger("request", activity=argument_builders_initial_activity_name)
async def argument_builders_initial_activity(request: BaseActivityRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "argument-builders-initial-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        request_info = await aget_base_request_info(request)
        vector_store, law_retriever_provider = prepare_providers(request_info.account_info, request.session_id)
        agent_facilitator = AgentFacilitator[BaseQaAgent](QaAgent)
        amies_client = request_info.designated_client
        qa_request = QARequest(
            input=request.input, 
            aimies_client=amies_client,
            aimies_filing_role=request_info.designated_client_role,
            opposition=request_info.opposition,
            opposition_role=request_info.opposition_role,
            location=request_info.location)
            
        result = await execute_retriable_request(
            request_info, 
            vector_store, 
            law_retriever_provider, 
            None,
            agent_facilitator, 
            qa_request)
            
        return generate_standard_response(result)
