from typing import List
import azure.durable_functions as df

from langchain_core.documents import Document

from AIInteractionService.utils.document_tools import deduplicate_sources
from activities import AimieRebuttalActivityRequest, BobActivityRequest, DecisionActivityRequest, DeclarationRequest, RhetoricActivityRequest
from activities.types import AnswerWithSourcesResult, BaseActivityRequest, DeclarationActivityResult, LibrarianActivityResult, RhetoricActivityResult, SourceActivityResult
from orchestrators import DeclarationWriterResult, DeclarationRequest as Request
from .progress import update_progress
from .types import AnswerWithSourcesOnly, RhetoricBuilderOrchestrationRequest, RhetoricOrchestrationResult, rhetoric_builder_orchestrator_name
from .utils import convert_documents_to_simplified_documents, convert_to_document, get_refined_context, ensure_document, normalize_session_id

declaration_bp = df.Blueprint()


@declaration_bp.orchestration_trigger(context_name="context", orchestration="DeclarationOrchestration")
def declaration_orchestration(activity_context: df.DurableOrchestrationContext):
    retry_options: df.RetryOptions = df.RetryOptions(1000, 3)
    body = activity_context.get_input()
    request = Request.model_validate(body)
    if request is None:
        raise ValueError("Missing body parameter")
    actions = ['Initial Inquiry', 'Cross Examination', 'Closing Statement', 'Decision Statement', 'Rhetorical Statement',
               'Final Declaration', 'Librarian']
    actions_completed = 0
    actions_remaining = len(actions)
    activity_context.set_custom_status(
        {'actionsCompleted': actions_completed, 'actionsRemaining': actions_remaining, 'actionsToComplete': actions})
    account_id: str = request.account_id
    max_doc_count: int = request.max_doc_count if request.max_doc_count else 20
    location: str = request.location if request.location else "Snohomish County, Washington"
    hearing_type: str = request.hearing_type if request.hearing_type else "Family Law"

    session_id = normalize_session_id(request.session_id)
    use_secondary_model = False

    qa_request = BaseActivityRequest(
        account_id=account_id,
        session_id=session_id,
        input=request.declaration_request,
        location=location,
        hearing_type=hearing_type,
        max_doc_count=max_doc_count,
        use_secondary_model=use_secondary_model)
    qa_activity_result = yield activity_context.call_activity("initialDeclarationActivity", qa_request)
    actions_completed, actions_remaining = update_progress(
        activity_context, actions, actions_completed, actions_remaining)
    sources: List[SourceActivityResult] = qa_activity_result.sources
    context: list[Document] = get_refined_context(qa_activity_result)
    
    qa_activity_result = AnswerWithSourcesResult.model_validate(
        qa_activity_result)
    bob_activity_request = BobActivityRequest(
        account_id=account_id,
        session_id=session_id,
        input=request.declaration_request,
        location=location,
        hearing_type=hearing_type,
        max_doc_count=max_doc_count,
        aimie_answer=qa_activity_result.answer,
        use_secondary_model=use_secondary_model
    )
    bob_activity_result = yield activity_context.call_activity("bobActivity", bob_activity_request)
    actions_completed, actions_remaining = update_progress(
        activity_context, actions, actions_completed, actions_remaining)
    bob_activity_result = AnswerWithSourcesResult.model_validate(
        bob_activity_result)
    extend_sources(sources, bob_activity_result.sources)
    bobs_response_context = get_refined_context(bob_activity_result)
    context.extend(bobs_response_context)

    aimie_rebuttal_activity_request = AimieRebuttalActivityRequest(
        account_id=account_id,
        session_id=session_id,
        input=request.declaration_request,
        location=location,
        hearing_type=hearing_type,
        max_doc_count=max_doc_count,
        aimie_answer=qa_activity_result.answer,
        bob_response=bob_activity_result.answer,
        use_secondary_model=use_secondary_model)
    aimie_rebuttal_activity_result = yield activity_context.call_activity(
        "aimieRebuttalActivity",
        aimie_rebuttal_activity_request)
    actions_completed, actions_remaining = update_progress(
        activity_context, actions, actions_completed, actions_remaining)
    aimie_rebuttal_activity_result = AnswerWithSourcesResult.model_validate(
        aimie_rebuttal_activity_result)
    extend_sources(sources, aimie_rebuttal_activity_result.sources)
    aimie_rebuttal_context = get_refined_context(aimie_rebuttal_activity_result)
    context.extend(aimie_rebuttal_context)

    decision_activity_request = DecisionActivityRequest(
        account_id=account_id,
        session_id=session_id,
        input=request.declaration_request,
        location=location,
        hearing_type=hearing_type,
        max_doc_count=max_doc_count,
        aimie_answer=qa_activity_result.answer,
        bob_response=bob_activity_result.answer,
        aimie_rebuttal=aimie_rebuttal_activity_result.answer,
        use_secondary_model=use_secondary_model)
    decision_activity_result: AnswerWithSourcesResult = yield activity_context.call_activity(
        "decisionActivity",
        decision_activity_request)
    actions_completed, actions_remaining = update_progress(
        activity_context, actions, actions_completed, actions_remaining)
    if decision_activity_result.sources:
        extend_sources(sources, decision_activity_result.sources)
    if decision_activity_result.context:
        decision_activity_context = get_refined_context(decision_activity_result)
        context.extend(decision_activity_context)

    rhetoric_activity_request = RhetoricBuilderOrchestrationRequest(
        account_id=account_id,
        session_id=session_id,
        statement=decision_activity_result.answer,
        location=location,
        hearing_type=hearing_type,
        max_doc_count=max_doc_count)
    rhetoric_activity_result = yield activity_context.call_sub_orchestrator_with_retry(
        rhetoric_builder_orchestrator_name,
        retry_options,
        rhetoric_activity_request)
    if not isinstance(rhetoric_activity_result, RhetoricOrchestrationResult):
        rhetoric_activity_result = RhetoricOrchestrationResult.model_validate(rhetoric_activity_result)
    actions_completed, actions_remaining = update_progress(
        activity_context, actions, actions_completed, actions_remaining)
    results = dict(qa_activity_result)
    if rhetoric_activity_result.sources:
        extend_sources(sources, rhetoric_activity_result.sources)
    if rhetoric_activity_result.context:
        rhetoric_activity_context = convert_to_document(rhetoric_activity_result.context)
        context.extend(rhetoric_activity_context)

    expanded_context: list[Document] = deduplicate_sources(
        context, rhetoric_activity_context)  
    context = expanded_context
    source_ids = [source.doc_id
                  for source in rhetoric_activity_result.context]
    declaration_request = DeclarationRequest(
        account_id=account_id,
        session_id=session_id,
        input=request.declaration_request,
        location=location,
        hearing_type=hearing_type,
        max_doc_count=max_doc_count,
        rhetorical_response=rhetoric_activity_result.answer,
        context=context,
        source_ids=source_ids,
        use_secondary_model=use_secondary_model)
    declaration_activity_result = yield activity_context.call_activity(
        "declarationActivity",
        declaration_request)
    actions_completed, actions_remaining = update_progress(
        activity_context, actions, actions_completed, actions_remaining)
    declaration_activity_result = DeclarationActivityResult.model_validate(
        declaration_activity_result)
    if declaration_activity_result.sources:
        extend_sources(sources, declaration_activity_result.sources)

    ## Will enable this as an add-on feature.
    # librarian_request = LibrarianRequest(
    #     account_id=account_id,
    #     session_id=session_id,
    #     input=request.declaration_request,
    #     location=location,
    #     hearing_type=hearing_type,
    #     target=target,
    #     index_post_fix=index_post_fix,
    #     max_doc_count=max_doc_count,
    #     declaration=declaration_activity_result.answer,
    #     context=context,
    #     use_secondary_model=use_secondary_model)
    
    # librarian_activity_result: LibrarianActivityResult = yield activity_context.call_activity(
    #     "librarianActivity",
    #     librarian_request)
    actions_completed, actions_remaining = update_progress(
        activity_context, actions, actions_completed, actions_remaining)

    results = DeclarationWriterResult(
        account_id=account_id,
        session_id=session_id,
        initial_inquiry=AnswerWithSourcesOnly(
            answer=qa_activity_result.answer,
            applicable_sources=qa_activity_result.sources),
        cross_examination=AnswerWithSourcesOnly(
            answer=bob_activity_result.answer,
            applicable_sources=bob_activity_result.sources),
        closing_statement=AnswerWithSourcesOnly(
            answer=aimie_rebuttal_activity_result.answer,
            applicable_sources=aimie_rebuttal_activity_result.sources),
        decision_statement=AnswerWithSourcesOnly(
            answer=decision_activity_result.answer,
            applicable_sources=decision_activity_result.sources),
        rhetorical_statement=AnswerWithSourcesOnly(
            answer=rhetoric_activity_result.answer,
            applicable_sources=rhetoric_activity_result.sources),
        final_declaration=declaration_activity_result.answer
            if not declaration_activity_result.has_error
            else "Not Available",
        exhibits=LibrarianActivityResult({}),
        context=convert_documents_to_simplified_documents(context),
        sources=sources)
    return results.model_dump(mode="json", by_alias=True)

def refine_resources(sources: List[SourceActivityResult], context: List[Document]):
    source_keys = set()
    for source in sources:
        source_keys.add(source.doc_id)
    reduced_sources = [sources if source.doc_id
                       in source_keys else None for sources in sources]
    final_sources = [
        source for source in reduced_sources if source is not None]
    context2: dict[str, Document] = dict()
    refined_context = ensure_document(context)
    for doc in refined_context:
        if doc.metadata['id'] in source_keys and doc.metadata['id'] not in context2.keys():
            context2[doc.metadata['id']] = doc
    context3 = [doc for doc in refined_context]
    return final_sources, context3


def extend_sources(sources: List[SourceActivityResult], new_sources: List[SourceActivityResult]) -> None:
    source_keys = set()
    for source in sources:
        source_keys.add(source.doc_id)
    for source in new_sources:
        if source.doc_id not in source_keys:
            sources.append(source)
