from typing import cast
import azure.durable_functions as df
from azure.functions import Context
from opentelemetry import trace
from opentelemetry.propagate import extract

from AIInteractionService.generators.facts.validator import FactValidatorRequest, BaseFactValidatorAgent
import AIInteractionService.generators.facts.validator as FactFinderAgentModule
from AIInteractionService.generators.facts.validator import FactValidatorAgentResult
from AIInteractionService.utils.agent_facilitator import AgentFacilitator

from .utils import aget_base_request_info, execute_retriable_request, generate_standard_response, normalize_answer, normalize_sources
from .types import FactValidatorActivityRequest, FactValidatorActivityResults, fact_validator_activity_name
from .providers import prepare_providers

fact_validator_activity_bp = df.Blueprint()
tracer = trace.get_tracer(__name__)

@fact_validator_activity_bp.activity_trigger("request", activity=fact_validator_activity_name)
async def fact_validator_activity(request: FactValidatorActivityRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "fact-validator-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        request_info = await aget_base_request_info(request)
        vector_store, law_retriever_provider = prepare_providers(
            request_info.account_info, request.session_id)
        agent_facilitator = AgentFacilitator[BaseFactValidatorAgent](
            FactFinderAgentModule)
        qa_request = FactValidatorRequest(
            input=request.input,
            location=request_info.location,
            is_last_paragraph=request.is_last_paragraph,
            original_request=request.original_request)

        result: FactValidatorAgentResult = cast(
            FactValidatorAgentResult,
            await execute_retriable_request(
                request_info,
                vector_store,
                law_retriever_provider,
                None,
                agent_facilitator,
                qa_request))

        raw_answer = result["answer"]
        final_answer: str = raw_answer if raw_answer and isinstance(
            raw_answer, str) else ""
        return FactValidatorActivityResults(
            original_statement=request.input,
            raw_original_statement=request.raw_input,
            answer=normalize_answer(final_answer),
            context=result["context"],
            sources=normalize_sources(result['sources']),
            is_valid=result["is_valid"],
            is_contradictory=result['is_contradictory'],
            is_inferred=result['is_inferred'],
            is_reasonably_inferred=result['is_reasonably_inferred'],
            is_not_found_in_context=result['is_not_found_in_context'],
            is_summary_or_conclusion=result['is_summary_or_conclusion'],
            is_implied=result['is_implied'],
            is_vague=result['is_vague'],
            contradiction_source=result['contradiction_source'],
            contradiction_statement=result['contradiction_statement'],
        )
