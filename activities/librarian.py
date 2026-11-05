
import azure.durable_functions as df
from azure.functions import Context
from opentelemetry import trace
from opentelemetry.propagate import extract

from AIInteractionService.generators.common import ensure_document
from AIInteractionService.generators.librarian.quote import QuoteFinder
from AIInteractionService.utils.accounts import aget_account_info
from .types import LibrarianAnswer, LibrarianRequest, LibrarianActivityResult, LibrarianSectionResult
from .providers import prepare_providers

bp = df.Blueprint()
tracer = trace.get_tracer(__name__)

@bp.activity_trigger("request", activity="librarianActivity")
async def librarian_activity(request: LibrarianRequest, context: Context):
    carrier = {
        "traceparent": context.trace_context.trace_parent,
        "tracestate": context.trace_context.trace_state,
    }
    parent_ctx = extract(carrier)

    with tracer.start_as_current_span(
        "librarian-activity",
        context=parent_ctx  # fresh context = new operation
    ) as root_span:
        account_info = await aget_account_info(request.account_id)
        vector_store, law_retriever_provider = prepare_providers(account_info, request.session_id)
        location = f"{account_info.county}, {account_info.state}" if not request.location else request.location

        quote_finder = QuoteFinder(
            request.account_id, request.session_id, vector_store, law_retriever_provider)
        context = ensure_document(request.context)
        result = await quote_finder.agenerate_exhibits(context, 
                                            request.declaration, 
                                            location)
        final_result = LibrarianActivityResult({})
        for section in result:
            refined_section_result = LibrarianSectionResult({})
            for paragraph in result[section]:
                refined_section_result[paragraph] = LibrarianAnswer.model_validate(result[section][paragraph].model_dump())
            final_result[section] = refined_section_result
        return final_result
