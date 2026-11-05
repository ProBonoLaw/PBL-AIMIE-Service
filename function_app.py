import asyncio
import os
from dotenv import load_dotenv
from AIInteractionService.db.azuresearch import AzureSearch
from orchestrators.validation_revision import statement_revision as statement_revision_bp
from orchestrators.rhetoric import rhetoric_builder_bp
from orchestrators.declaration_writer import declaration_bp
from orchestrators.timeline import timeline_bp
from orchestrators.argument_builders import argument_builders_orchestrator_bp
from activities.revision import revision_activity_bp
from activities.fact_validator import fact_validator_activity_bp
from activities.declaration import bp as declaration_activity_bp
from activities.timeline import bp as timeline_activity_bp
from activities.rhetoric import bp as rhetoric_bp
from activities.decision import bp as decision_bp
from activities.rebuttal import bp as rebuttal_bp
from activities.cross_exam import bob_bp
from activities.initial_declaration import initial_declaration_activity_bp
from activities.argument_builders_final_response import bp as argument_builders_final_response_bp
from activities.argument_builders_cross_exam import bp as argument_builders_cross_exam_bp
from activities.argument_builders_initial import argument_builders_activity_bp
from activities.utils import aget_base_request_info, execute_retriable_request, generate_standard_response, normalize_answer, normalize_sources
import azure.durable_functions as df
import azure.functions as func
import logging
import orjson
from typing import List, Optional, cast, Hashable
from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_openai.chat_models.base import OpenAIRefusalError
from AIInteractionService.generators.event_query.agent import (
    EVENT_QUERY_PROMPT_VERSION,
    event_query_model_request,
    build_event_query_fallback,
)
from opentelemetry import trace
from langchain_core.callbacks import UsageMetadataCallbackHandler
from opentelemetry.context import Context
from opentelemetry.propagate import extract

from AIInteractionService.generators.common.agent_result import AgentResult
from AIInteractionService.generators.common.types import AnswersWithSources
import AIInteractionService.generators.librarian.claim as BaseLibrarianClaimAgentModule
import AIInteractionService.generators.event_query as EventQueryModule
from AIInteractionService.generators.event_query import EventQueryEntries, EventQueryResult, EventQuerySourceRegistry, build_event_query_agent, build_event_query_model, encode_event_records, event_query_request_thread_id, materialize_event_entries, normalize_event_tags, search_event_documents, serialize_event_records
from AIInteractionService.generators.timelines.models import partition_timeline_entries
from AIInteractionService.generators.librarian.claim import BaseLibrarianClaimAgent, LibrarianClaimOutput, AmieLibrarianClaimAgentRequest

from AIInteractionService.generators.facts.validator import BaseFactValidatorAgent
import AIInteractionService.generators.facts.validator as FactFinderAgentModule
from AIInteractionService.generators.facts.validator.types import FactValidatorAgentResult, FactValidatorRequest
import AIInteractionService.generators.revision as FactFinderRevisionModule
from AIInteractionService.generators.revision import RevisionRequest, BaseRevisionAgent
from AIInteractionService.generators.qa.fast import BaseQaAgent, QARequest, VerbosityLevel
import AIInteractionService.generators.qa.fast as QaAgentModel
from AIInteractionService.utils.agent_facilitator import AgentFacilitator
from AIInteractionService.utils.token_types import log_agent_token_usage
from activities.providers import prepare_providers
from activities.types import BaseActivityRequest, FactValidatorActivityResults
from orchestrators.types import QAResult
from orchestrators.utils import convert_documents_to_simplified_documents, get_validation_status
from utils.instrumentation import enable_instrumentation
from search_api import bp as search_bp

# from activities.librarian import bp as librarian_bp
# from activities.discovery import bp as discovery_activity_bp
# from orchestrators.discovery import discovery_bp

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)
app.register_functions(search_bp)
app.register_functions(argument_builders_activity_bp)
app.register_functions(argument_builders_cross_exam_bp)
app.register_functions(argument_builders_final_response_bp)
app.register_functions(initial_declaration_activity_bp)
app.register_functions(bob_bp)
app.register_functions(rebuttal_bp)
app.register_functions(decision_bp)
app.register_functions(rhetoric_bp)
app.register_functions(declaration_activity_bp)
app.register_functions(timeline_activity_bp)
# app.register_functions(librarian_bp)
app.register_functions(argument_builders_orchestrator_bp)
app.register_functions(declaration_bp)
app.register_functions(timeline_bp)
app.register_functions(rhetoric_builder_bp)
# app.register_functions(discovery_bp)
app.register_functions(statement_revision_bp)
# app.register_functions(discovery_activity_bp)
app.register_functions(fact_validator_activity_bp)
app.register_functions(revision_activity_bp)

enable_instrumentation()
tracer = trace.get_tracer(__name__)

load_dotenv(override=True)


@app.route(route="healthz", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
async def healthz(req: func.HttpRequest) -> func.HttpResponse:
    """Readiness requires the host to have indexed this application's functions."""
    return func.HttpResponse("ok", status_code=200, mimetype="text/plain")


@app.route(route="AIInteractionService/status/{instanceId}")
@app.durable_client_input(client_name="client")
async def status(req: func.HttpRequest,
                 client: df.DurableOrchestrationClient) -> func.HttpResponse:
    instance_id = req.route_params.get('instanceId')
    logging.info(f'Checking status of orchestration instance {instance_id}.')

    if not instance_id:
        return func.HttpResponse(
            body=orjson.dumps(
                {"message": "Missing instanceId parameter."}, default=lambda x: x.__dict__),
            status_code=400,
            mimetype='application/json'
        )
    try:
        status = await client.get_status(instance_id, True, True, True)
        return func.HttpResponse(
            body=orjson.dumps(status.to_json()),
            status_code=200,
            mimetype='application/json'
        )
    except Exception as e:
        logging.error(
            f'Error checking status of orchestration instance {instance_id}: {str(e)}.')
        return func.HttpResponse(
            body=orjson.dumps(
                {"errorMessage": str(e)}, default=lambda x: x.__dict__),
            status_code=200,
            mimetype='application/json'
        )


@app.route(route="AIInteractionService/terminate/{instanceId}")
@app.durable_client_input(client_name="client")
async def terminate(req: func.HttpRequest,
                    client: df.DurableOrchestrationClient) -> func.HttpResponse:
    instance_id = req.route_params.get('instanceId')
    if not instance_id:
        return func.HttpResponse(
            body=orjson.dumps(
                {"message": "Missing instanceId parameter."}, default=lambda x: x.__dict__),
            status_code=400,
            mimetype='application/json'
        )
    logging.info(f'Terminating an orchestration instance {instance_id}')
    status = await client.terminate(instance_id, "By User Request")
    return func.HttpResponse(
        body=orjson.dumps(status, default=lambda x: x.__dict__),
        status_code=200,
        mimetype='application/json'
    )


@app.route(route="AIInteractionService/argument_builder")
@app.durable_client_input(client_name="client")
async def argument_builder_trigger(req: func.HttpRequest, client: df.DurableOrchestrationClient, context: func.Context) -> func.HttpResponse:
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "argument-builder",
        context=parent_ctx
    ) as root_span:
        logging.info('Python HTTP trigger function processed a request.')
        if req.headers.get("X-Forwarded-For"):
            root_span.set_attribute(
                "operation.client.ip", req.headers.get("X-Forwarded-For", "Unknown"))

        body: dict = req.get_json()
        account_id: str = body.get('accountId', '')
        session_id: str = body.get('sessionId', '')

        root_span.set_attribute("operation.name", "argument-builder")
        root_span.set_attribute("operation.account_id", account_id)
        root_span.set_attribute("operation.session_id", session_id)

        if not account_id:
            return func.HttpResponse(
                body=orjson.dumps(
                    {"message": "Missing accountId parameter."}, default=lambda x: x.__dict__),
                status_code=400,
                mimetype='application/json'
            )

        if 'question' not in body:
            return func.HttpResponse(
                body=orjson.dumps(
                    {"message": "Missing question parameter"}, default=lambda x: x.__dict__),
                status_code=400,
                mimetype='application/json'
            )

        instance_id = await client.start_new("ArgumentBuildersOrchestration", client_input=body)
        return client.create_check_status_response(request=req, instance_id=instance_id)


@app.route(route="AIInteractionService/declaration")
@app.durable_client_input(client_name="client")
async def declaration(req: func.HttpRequest, client: df.DurableOrchestrationClient, context: func.Context) -> func.HttpResponse:
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)
    with tracer.start_as_current_span(
        "declaration",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        body: dict = req.get_json()
        account_id: str | None = body.get('accountId')
        session_id: str | None = body.get('sessionId')
        account_id_value = req.params.get('accountId') or account_id or "N/A"
        session_id_value = req.params.get('sessionId') or session_id or "N/A"

        root_span.set_attribute("operation.name", "declaration")
        root_span.set_attribute("operation.account_id", account_id_value)
        root_span.set_attribute("operation.session_id", session_id_value)
        if req.headers.get("X-Forwarded-For"):
            root_span.set_attribute(
                "operation.client.ip", req.headers.get("X-Forwarded-For", "Unknown"))
        logging.info('Python HTTP trigger function processed a request.')

        if not account_id:
            return func.HttpResponse(
                body=orjson.dumps(
                    {"message": "Missing accountId parameter."}, default=lambda x: x.__dict__),
                status_code=400,
                mimetype='application/json'
            )

        if not 'input' in body:
            return func.HttpResponse(
                body=orjson.dumps(
                    {"message": "Missing question parameter"}, default=lambda x: x.__dict__),
                status_code=400,
                mimetype='application/json'
            )

        instance_id = await client.start_new("DeclarationOrchestration", client_input=body)
        return client.create_check_status_response(request=req, instance_id=instance_id)


@app.route(route="AIInteractionService/discovery")
@app.durable_client_input(client_name="client")
async def discovery(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    body: dict = req.get_json()
    account_id: str = body.get('accountId', '')
    if not account_id:
        return func.HttpResponse(
            body=orjson.dumps(
                {"message": "Missing accountId parameter"}, default=lambda x: x.__dict__),
            status_code=400,
            mimetype='application/json'
        )

    if not 'input' in body:
        return func.HttpResponse(
            body=orjson.dumps(
                {"message": "Missing input parameter"}, default=lambda x: x.__dict__),
            status_code=400,
            mimetype='application/json'
        )

    instance_id = await client.start_new("DiscoveryOrchestration", client_input=body)
    return client.create_check_status_response(request=req, instance_id=instance_id)


@app.route(route="AIInteractionService/qa/fast")
async def qa_trigger(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "fast-qa",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        logging.info('Python HTTP trigger function processed a request.')
        if req.headers.get("X-Forwarded-For"):
            root_span.set_attribute(
                "operation.client.ip", req.headers.get("X-Forwarded-For", "Unknown"))
        body_json: dict = req.get_json()
        account_id: str = body_json.get('accountId', '')
        session_id: str = body_json.get('sessionId', '')
        use_enhanced_retriever: bool = body_json.get('useEnhancedRetriever', False)
        root_span.set_attribute("operation.name", "fast-qa")
        root_span.set_attribute("operation.account_id", account_id)
        root_span.set_attribute("operation.session_id", session_id)
        root_span.set_attribute("operation.use_enhanced_retriever", use_enhanced_retriever)

        swap_roles: bool = body_json.get('swapRoles', False)
        request = BaseActivityRequest(
            account_id=account_id,
            session_id=session_id,
            input=body_json.get('question', body_json.get('input', '')),
            location=body_json.get('location', ''),
            hearing_type=body_json.get('hearingType', None),
            max_doc_count=int(body_json.get('maxDocCount', '10')),
            use_secondary_model=False)
        logging.info(
            f"Getting account info for account_id: {request.account_id}")
        request_info = await aget_base_request_info(request)
        logging.info(f"Account info retrieved: {request_info}")
        hashtable_account_info: Hashable = cast(
            Hashable, request_info.account_info)
        vector_store, law_provider = prepare_providers(
            hashtable_account_info, request.session_id)
        logging.info(f"Vector store prepared: {vector_store}")
        agent_facilitator = AgentFacilitator[BaseQaAgent](QaAgentModel)
        verbosity_level = body_json.get('verbosityLevel', 'default')
        if verbosity_level == VerbosityLevel.LOW:
            verbosity_level = VerbosityLevel.DEFAULT
        qa_request = QARequest(
            input=request.input,
            aimies_client=request_info.designated_client if not swap_roles else request_info.opposition,
            aimies_filing_role=request_info.designated_client_role if not swap_roles else request_info.opposition_role,
            opposition=request_info.opposition if not swap_roles else request_info.designated_client,
            opposition_role=request_info.opposition_role if not swap_roles else request_info.designated_client_role,
            location=request_info.location,
            verbosity_level=verbosity_level,
            use_enhanced_retriever=use_enhanced_retriever)

        try:
            with tracer.start_as_current_span("fast-qa-generation") as span:
                span.set_attribute("operation.name", "qa-generation")
                span.set_attribute("operation.account_id", account_id)
                span.set_attribute("operation.session_id", session_id)
                result = await execute_retriable_request(
                    request_info,
                    vector_store,
                    law_provider,
                    None,
                    agent_facilitator,
                    qa_request)

            final_result = generate_standard_response(result)

            validation_agent_facilitator = AgentFacilitator[BaseFactValidatorAgent](
                FactFinderAgentModule)

            validation_result: Optional[FactValidatorAgentResult] = None
            with tracer.start_as_current_span("fast-qa-fact-validation") as span2:
                span2.set_attribute("operation.name", "fact-validation")
                span2.set_attribute("operation.account_id", account_id)
                span2.set_attribute("operation.session_id", session_id)
                fact_check_request = FactValidatorRequest(
                    input=final_result.answer,
                    location=request_info.location,
                    is_last_paragraph=False,
                    original_request=request.input)

                fact_finder_vector_store: Optional[AzureSearch] = None
                if final_result.context is None or len(final_result.context) == 0:
                    final_result.context = []
                    fact_finder_vector_store = vector_store

                validation_result = cast(
                    FactValidatorAgentResult,
                    await execute_retriable_request(
                        request_info,
                        fact_finder_vector_store,
                        None,
                        final_result.context,
                        validation_agent_facilitator,
                        fact_check_request))

            validaton_results_final_answer = validation_result["answer"] if validation_result["answer"] and isinstance(
                validation_result["answer"], str) else ""

            validation_answer: List[FactValidatorActivityResults] = []

            validation_result_str = FactValidatorActivityResults(
                original_statement=final_result.answer,
                raw_original_statement=final_result.answer,
                answer=normalize_answer(validaton_results_final_answer),
                context=validation_result["context"],
                sources=normalize_sources(validation_result['sources']),
                is_valid=validation_result["is_valid"],
                is_contradictory=validation_result['is_contradictory'],
                is_inferred=validation_result['is_inferred'],
                is_reasonably_inferred=validation_result['is_reasonably_inferred'],
                is_not_found_in_context=validation_result['is_not_found_in_context'],
                is_summary_or_conclusion=validation_result['is_summary_or_conclusion'],
                is_vague=validation_result['is_vague'],
                is_implied=validation_result['is_implied'],
                contradiction_source=validation_result['contradiction_source'],
                contradiction_statement=validation_result['contradiction_statement']
            )

            validation_answer.append(validation_result_str)

            if not validation_result['is_valid']:
                with tracer.start_as_current_span("fast-qa-revision") as span3:
                    span3.set_attribute("operation.name", "revision")
                    revision_agent_facilitator = AgentFacilitator[BaseRevisionAgent](
                        FactFinderRevisionModule)
                    revision_request = RevisionRequest(
                        location=request_info.location,
                        statement=final_result.answer,
                        feedback=validaton_results_final_answer,
                        use_retrievers=False,
                        swap_roles=body_json.get('swapRoles', False),
                        verbosity_level=body_json.get(
                            'verbosityLevel', 'default')
                    )

                    revision_result_raw = await execute_retriable_request(
                        request_info,
                        vector_store,
                        law_provider,
                        None,
                        revision_agent_facilitator,
                        revision_request
                    )
                    revised_answer = generate_standard_response(
                        revision_result_raw)
                    qa_result = QAResult(
                        answer=revised_answer.answer,
                        chat_history=final_result.chat_history,
                        sources=revised_answer.sources,
                        context=convert_documents_to_simplified_documents(
                            final_result.context),
                        validation_status=get_validation_status(
                            validation_answer)
                    )

                    return func.HttpResponse(
                        body=orjson.dumps(qa_result.model_dump(
                            mode='json', exclude_none=True, by_alias=True), default=lambda x: x.__dict__),
                        status_code=200,
                        mimetype='application/json'
                    )

            qa_result = QAResult(
                answer=final_result.answer,
                chat_history=final_result.chat_history,
                sources=final_result.sources,
                context=convert_documents_to_simplified_documents(
                    final_result.context),
                validation_status=get_validation_status(validation_answer)
            )

            return func.HttpResponse(
                body=orjson.dumps(qa_result.model_dump(
                    mode='json', exclude_none=True, by_alias=True), default=lambda x: x.__dict__),
                status_code=200,
                mimetype='application/json'
            )
        finally:
            logging.info("Cleaning up resources")


@app.route(route="AIInteractionService/claimfinder")
async def claim_finder(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "claim-finder",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        logging.info('Python HTTP trigger function processed a request.')
        if req.headers.get("X-Forwarded-For"):
            root_span.set_attribute(
                "operation.client.ip", req.headers.get("X-Forwarded-For", "Unknown"))
        body_json: dict = req.get_json()
        account_id: str = body_json.get('accountId', '')
        session_id: str = body_json.get('sessionId', '')
        root_span.set_attribute("operation.name", "claim-finder")
        root_span.set_attribute("operation.account_id", account_id)
        root_span.set_attribute("operation.session_id", session_id)

        request = BaseActivityRequest(
            account_id=account_id,
            session_id=session_id,
            input=body_json.get('claim', body_json.get('input', '')),
            location=body_json.get('location', ''),
            hearing_type=body_json.get('hearingType', None),
            max_doc_count=int(body_json.get('maxDocCount', '10')),
            use_secondary_model=False)
        logging.info(
            f"Getting account info for account_id: {request.account_id}")
        request_info = await aget_base_request_info(request)
        logging.info(f"Account info retrieved: {request_info}")
        hashtable_account_info: Hashable = cast(
            Hashable, request_info.account_info)
        vector_store, law_provider = prepare_providers(
            hashtable_account_info, request.session_id)
        logging.info(f"Vector store prepared: {vector_store}")
        agent_facilitator = AgentFacilitator[BaseLibrarianClaimAgent](
            BaseLibrarianClaimAgentModule)
        qa_request = AmieLibrarianClaimAgentRequest(
            claim=request.input,
            location=request_info.location,
            use_enhanced_retriever=False) # type: ignore

        try:
            result = await execute_retriable_request(
                request_info,
                vector_store,
                law_provider,
                None,
                agent_facilitator,
                qa_request)
            return func.HttpResponse(
                body=orjson.dumps(result, default=lambda x: x.__dict__),
                status_code=200,
                mimetype='application/json'
            )
        except Exception as e:
            logging.error(f"Error in claim-finder: {str(e)}")
            return func.HttpResponse(
                body=orjson.dumps(
                    {"message": "Internal Server Error"}, default=lambda x: x.__dict__),
                status_code=500,
                mimetype='application/json'
            )

@app.route(route="AIInteractionService/timeline")
@app.durable_client_input(client_name="client")
async def timeline(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
    context: func.Context
) -> func.HttpResponse:

    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }

    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "timeline",
        context=parent_ctx
    ) as root_span:

        logging.info(
            "Python HTTP trigger function processed a request."
        )

        if req.headers.get("X-Forwarded-For"):
            root_span.set_attribute(
                "operation.client.ip",
                req.headers.get("X-Forwarded-For", "Unknown")
            )

        try:
            body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                body=orjson.dumps({
                    "message": "Invalid JSON body."
                }),
                status_code=400,
                mimetype="application/json"
            )

        if not isinstance(body, dict):
            return func.HttpResponse(
                body=orjson.dumps({
                    "message": "Invalid JSON body."
                }),
                status_code=400,
                mimetype="application/json"
            )

        account_id: str = body.get("accountId", "")
        session_id: str = body.get("sessionId", "")

        root_span.set_attribute(
            "operation.name",
            "timeline"
        )
        root_span.set_attribute(
            "operation.account_id",
            account_id
        )
        root_span.set_attribute(
            "operation.session_id",
            session_id
        )

        if not body.get("accountId"):
            return func.HttpResponse(
                body=orjson.dumps({
                    "message": "Missing accountId parameter."
                }),
                status_code=400,
                mimetype="application/json"
            )

        if not body.get("sessionId"):
            return func.HttpResponse(
                body=orjson.dumps({
                    "message": "Missing sessionId parameter."
                }),
                status_code=400,
                mimetype="application/json"
            )

        if not body.get("input"):
            return func.HttpResponse(
                body=orjson.dumps({
                    "message": "Missing input parameter."
                }),
                status_code=400,
                mimetype="application/json"
            )

        #
        # IMPORTANT:
        # start_new() executes WHILE "timeline" is the current span.
        #
        instance_id = await client.start_new(
            "TimelineOrchestration",
            client_input=body
        )

        root_span.set_attribute(
            "durable.instance_id",
            instance_id
        )

        return client.create_check_status_response(
            request=req,
            instance_id=instance_id
        )


_STRUCTURED_OUTPUT_REFUSAL_MARKERS = (
    "i'm sorry",
    'i am sorry',
    'i cannot',
    "i can't",
    "i'm unable",
    'i am unable',
)


def _is_structured_output_refusal(error: Exception) -> bool:
    """Return whether a provider rejected or interrupted a native response."""
    if isinstance(error, OpenAIRefusalError):
        return True
    if not isinstance(error, StructuredOutputValidationError):
        return False

    message = error.ai_message
    if message.additional_kwargs.get("refusal"):
        return True

    content = message.content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "refusal" or part.get("refusal"):
                    return True
                part_text = part.get("text") or part.get("content")
                if isinstance(part_text, str):
                    parts.append(part_text)
            else:
                parts.append(str(part))
        content = "".join(parts)

    if not isinstance(content, str):
        return False

    normalized = content.strip().casefold().replace('’', "'")
    # Structured evidence may quote a witness saying "I cannot" or "I'm sorry".
    # Embedded refusals require the provider metadata checked above.
    return normalized.startswith(_STRUCTURED_OUTPUT_REFUSAL_MARKERS)


def _is_content_filter_failure(error: Exception) -> bool:
    """Recognize provider filtering without interpreting it as absent evidence."""
    message = getattr(error, "ai_message", None)
    metadata = getattr(message, "response_metadata", {}) or {}
    if metadata.get("finish_reason") == "content_filter":
        return True

    filter_codes = {"content_filter", "responsibleaipolicyviolation"}
    if str(getattr(error, "code", "")).casefold() in filter_codes:
        return True
    detail = getattr(error, "body", None)
    while isinstance(detail, dict):
        if str(detail.get("code", "")).casefold() in filter_codes:
            return True
        detail = detail.get("error") or detail.get("innererror")

    # LangChain's Azure adapter raises this ValueError without provider metadata.
    return isinstance(error, ValueError) and str(error).startswith(
        "Azure has not provided the response due to a content filter being triggered"
    )


def _event_query_review_failure_reason(error: Exception) -> str:
    if _is_content_filter_failure(error):
        return "content_filter"
    if _is_structured_output_refusal(error):
        return "model_refusal"
    if isinstance(error, StructuredOutputValidationError):
        return "invalid_structured_output"
    if isinstance(error, TimeoutError):
        return "timeout"
    return "model_error"


@app.route(route="AIInteractionService/events/query", methods=["POST"])
async def event_query(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span("event-query", context=parent_ctx) as root_span:
        try:
            body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                body=orjson.dumps({"message": "Invalid JSON body."}),
                status_code=400,
                mimetype="application/json",
            )

        if not isinstance(body, dict):
            return func.HttpResponse(
                body=orjson.dumps({"message": "Invalid JSON body."}),
                status_code=400,
                mimetype="application/json",
            )

        account_id = body.get("accountId")
        session_id = body.get("sessionId")
        tags = body.get("tags")
        query = body.get("input") or body.get("query")
        root_span.set_attribute("operation.name", "event-query")
        root_span.set_attribute("operation.account_id", account_id or "")
        root_span.set_attribute("operation.session_id", session_id or "")

        if account_id is None or account_id == "":
            return func.HttpResponse(body=orjson.dumps({"message": "Missing accountId parameter."}), status_code=400, mimetype="application/json")
        if not isinstance(account_id, str) or not account_id.strip():
            return func.HttpResponse(body=orjson.dumps({"message": "accountId must be a non-empty string."}), status_code=400, mimetype="application/json")
        if session_id is None or session_id == "":
            return func.HttpResponse(body=orjson.dumps({"message": "Missing sessionId parameter."}), status_code=400, mimetype="application/json")
        if not isinstance(session_id, str) or not session_id.strip():
            return func.HttpResponse(body=orjson.dumps({"message": "sessionId must be a non-empty string."}), status_code=400, mimetype="application/json")
        if tags is None:
            return func.HttpResponse(body=orjson.dumps({"message": "Missing tags parameter."}), status_code=400, mimetype="application/json")
        if not isinstance(tags, list) or not tags:
            return func.HttpResponse(body=orjson.dumps({"message": "tags must be a non-empty array of strings."}), status_code=400, mimetype="application/json")
        if not isinstance(query, str) or not query.strip():
            return func.HttpResponse(body=orjson.dumps({"message": "Missing query parameter."}), status_code=400, mimetype="application/json")

        try:
            normalized_tags = normalize_event_tags(tags)
            max_doc_count = max(1, min(int(body.get("maxDocCount", 20)), 1000))
            root_span.set_attribute("operation.tags", normalized_tags)
        except (TypeError, ValueError) as error:
            return func.HttpResponse(
                body=orjson.dumps({"message": str(error)}),
                status_code=400,
                mimetype="application/json",
            )

        request = BaseActivityRequest(
            account_id=account_id,
            session_id=session_id,
            input=query.strip(),
            location="",
            hearing_type=None,
            max_doc_count=max_doc_count,
        )

        try:
            request_info = await aget_base_request_info(request)
            vector_store, _ = prepare_providers(request_info.account_info, session_id)
            documents = await search_event_documents(
                vector_store,
                query.strip(),
                normalized_tags,
                max_doc_count,
            )
            if not documents:
                response = EventQueryResult(
                    session_id=session_id,
                    account_id=account_id,
                    tags=normalized_tags,
                    originalRequest=query.strip(),
                    entries=[],
                )
                return func.HttpResponse(
                    body=orjson.dumps(response.model_dump(mode="json", by_alias=True)),
                    status_code=200,
                    mimetype="application/json",
                )

            source_registry = EventQuerySourceRegistry(documents)
            records_toon = encode_event_records(documents, source_registry)
            facilitator = AgentFacilitator(EventQueryModule)
            agent_config = await facilitator.get_agent_config()
            if not agent_config.primary_prompt:
                raise RuntimeError("Event query agent configuration is missing primaryPrompt.")
            system_prompt = "\n\n".join(agent_config.primary_prompt)

            errors: list[Exception] = []
            for index in range(await facilitator.get_agent_variant_count()):
                model = None
                usage_callback = None
                result = None
                timeout_seconds = float(os.getenv("EVENT_QUERY_TIMEOUT_SECONDS", "210"))
                try:
                    model_config = await facilitator.get_agent_variant_config(index)
                    model = build_event_query_model(
                        model_config.class_name,
                        model_config.kwargs,
                        model_config.llm_type,
                    )
                    agent = build_event_query_agent(
                        records_toon,
                        model,
                        system_prompt,
                    )
                    usage_callback = UsageMetadataCallbackHandler()
                    agent_input = {
                        "messages": [{"role": "user", "content": event_query_model_request(query.strip())}],
                    }
                    recovery_attempted = False
                    while True:
                        attempt = 2 if recovery_attempted else 1
                        deployment = (
                            model_config.kwargs.get("model")
                            or model_config.kwargs.get("azure_deployment")
                            or model_config.class_name
                        )
                        logging.info(
                            "event_query_model_attempt variant=%d attempt=%d deployment=%s prompt=%s",
                            index, attempt, deployment, EVENT_QUERY_PROMPT_VERSION,
                        )
                        try:
                            result = await asyncio.wait_for(
                                agent.ainvoke(
                                    agent_input,
                                    config={
                                        "callbacks": [usage_callback],
                                        "recursion_limit": 8,
                                        "configurable": {
                                            "account_id": account_id,
                                            "thread_id": event_query_request_thread_id(session_id),
                                        },
                                    },
                                ),
                                timeout=timeout_seconds,
                            )
                            generated_entries = EventQueryEntries.model_validate(
                                result["structured_response"]
                            )
                            break
                        except Exception as error:
                            is_refusal = _is_structured_output_refusal(error)
                            is_content_filter = _is_content_filter_failure(error)
                            if is_refusal or is_content_filter:
                                message = getattr(error, "ai_message", None)
                                metadata = getattr(message, "response_metadata", {}) or {}
                                logging.warning(
                                    "event_query_model_rejected variant=%d attempt=%d deployment=%s "
                                    "prompt=%s kind=%s finish_reason=%s status=%s request_id=%s",
                                    index, attempt, deployment, EVENT_QUERY_PROMPT_VERSION,
                                    "content_filter" if is_content_filter else "model_refusal",
                                    metadata.get("finish_reason"),
                                    getattr(error, "status_code", None),
                                    getattr(error, "request_id", None),
                                )
                            if recovery_attempted or not (is_refusal or is_content_filter):
                                raise
                            recovery_attempted = True
                            failure_kind = (
                                'structured-output refusal'
                                if is_refusal else 'content filter'
                            )
                            logging.warning(
                                'Event query model variant %d returned %s; retrying once '
                                'with professional evidence-extraction context.',
                                index,
                                failure_kind,
                            )
                            agent_input = {
                                "messages": [{
                                    "role": "user",
                                    "content": event_query_model_request(query.strip(), recovery=True),
                                }],
                            }
                    materialized_entries = materialize_event_entries(
                        generated_entries,
                        source_registry,
                    )
                    entries, footnotes, time_range = partition_timeline_entries(
                        materialized_entries
                    )
                    response = EventQueryResult(
                        session_id=session_id,
                        account_id=account_id,
                        tags=normalized_tags,
                        originalRequest=query.strip(),
                        time_range=time_range,
                        entries=entries,
                        footnotes=footnotes,
                    )
                    return func.HttpResponse(
                        body=orjson.dumps(response.model_dump(mode="json", by_alias=True)),
                        status_code=200,
                        mimetype="application/json",
                    )
                except Exception as error:
                    errors.append(error)
                    if isinstance(error, TimeoutError):
                        logging.exception(
                            "Event query model variant %d timed out after %s seconds",
                            index,
                            timeout_seconds,
                        )
                    else:
                        logging.exception("Event query model variant %d failed", index)
                finally:
                    if usage_callback is not None:
                        log_agent_token_usage(
                            result or {},
                            account_id=account_id,
                            session_id=session_id,
                            operation="event_query",
                            llm=model,
                            variant=index,
                            usage_metadata=usage_callback.usage_metadata,
                        )

            response = build_event_query_fallback(
                documents,
                session_id=session_id,
                account_id=account_id,
                tags=normalized_tags,
                query=query.strip(),
            )
            return func.HttpResponse(
                body=orjson.dumps({
                    **response.model_dump(mode="json", by_alias=True),
                    "code": "EVENT_QUERY_PARTIAL_RESULT",
                    "message": (
                        f"Azure AI Search returned {len(documents)} citable records, "
                        "but model review could not be completed. The entries "
                        "are search candidates; their relevance to the query has not "
                        "been verified by the model."
                    ),
                    "retrievalStatus": "succeeded",
                    "reviewStatus": "incomplete",
                    "retrievedRecordCount": len(documents),
                    "retrievedRecords": serialize_event_records(documents),
                    "failureReasons": list(dict.fromkeys(
                        _event_query_review_failure_reason(error) for error in errors
                    )) or ["no_model_variants"],
                }),
                status_code=200,
                mimetype="application/json",
            )
        except Exception:
            logging.exception(
                "Event query failed for account %s and session %s",
                account_id,
                session_id,
            )
            return func.HttpResponse(
                body=orjson.dumps({"message": "Internal Server Error"}),
                status_code=500,
                mimetype="application/json",
            )
