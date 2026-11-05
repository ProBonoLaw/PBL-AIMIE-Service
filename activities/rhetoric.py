from typing import Dict
import azure.durable_functions as df
from azure.functions import Context
from opentelemetry import trace
from opentelemetry.propagate import extract


from AIInteractionService.generators.common.types import AnswersWithSources
import AIInteractionService.generators.rhetoric as RhetoricModule
from AIInteractionService.generators.rhetoric import BaseRhetoricWriterAgent, RhetoricWriterAgentRequest
from AIInteractionService.generators.rhetoric.types import RhetoricWriterOutput
from AIInteractionService.utils.agent_facilitator import AgentFacilitator

from .utils import aget_base_request_info, execute_retriable_request, generate_standard_response, normalize_sources
from .types import RhetoricActivityRequest, RhetoricActivityResult, rhetoric_activity_name
from .providers import prepare_providers

bp = df.Blueprint()
tracer = trace.get_tracer(__name__)

@bp.activity_trigger("request", activity=rhetoric_activity_name)
async def rhetoric_activity(request: RhetoricActivityRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "rhetoric-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        request_info = await aget_base_request_info(request)
        vector_store, law_retriever_provider = prepare_providers(request_info.account_info, request.session_id)
        agent_facilitator = AgentFacilitator[BaseRhetoricWriterAgent](RhetoricModule)

        rhetoric_builder = RhetoricWriterAgentRequest(
            location=request_info.location,
            statement=request.input)
        result = await execute_retriable_request(
            request_info, 
            vector_store, 
            law_retriever_provider,
            None,
            agent_facilitator, 
            rhetoric_builder)
        
        if isinstance(result, AnswersWithSources):
            return generate_standard_response(result)
        elif isinstance(result, Dict):
            answer_with_sources: AnswersWithSources = result['answer']
            return RhetoricActivityResult(
                answer=answer_with_sources.answer,
                context=result['context'],
                chat_history=result['chat_history'],
                sources=normalize_sources(answer_with_sources.sources),
                original_section=request.input
            )
        
        raise ValueError("Unexpected result type from rhetoric activity execution: {}".format(type(result)))