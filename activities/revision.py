from typing import cast
import azure.durable_functions as df
from azure.functions import Context
from opentelemetry import trace
from opentelemetry.propagate import extract

from AIInteractionService.generators.common.agent_result import AgentResult
from AIInteractionService.generators.revision import RevisionRequest, BaseRevisionAgent
import AIInteractionService.generators.revision as RevisionAgentModule
from AIInteractionService.utils.agent_facilitator import AgentFacilitator

from .utils import aget_base_request_info, execute_retriable_request, normalize_answer, normalize_sources
from .types import AnswerWithSourcesResult, RevisionActivityRequest, revision_activity_name
from .providers import prepare_providers

revision_activity_bp = df.Blueprint()
tracer = trace.get_tracer(__name__)

@revision_activity_bp.activity_trigger("request", activity=revision_activity_name)
async def revision_activity(request: RevisionActivityRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "revision-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        request_info = await aget_base_request_info(request)
        vector_store, law_retriever_provider = prepare_providers(request_info.account_info, request.session_id)
        agent_facilitator = AgentFacilitator[BaseRevisionAgent](RevisionAgentModule)
        qa_request = RevisionRequest(
            statement=request.statement, 
            feedback=request.feedback,
            location=request_info.location,
            use_retrievers=request.use_retrievers if request.use_retrievers else True)
            
        result: AgentResult = await execute_retriable_request(
            request_info, 
            vector_store, 
            law_retriever_provider, 
            agent_facilitator, 
            qa_request) #type: ignore
            
        final_answer:str = cast(str, result["answer"] if result["answer"] and isinstance(result["answer"] , str) else "")
        return AnswerWithSourcesResult(
            answer=normalize_answer(final_answer), 
            chat_history=result["chat_history"] if "chat_history" in result else [],
            context=result["context"],
            sources=normalize_sources(result['sources'])
        )
