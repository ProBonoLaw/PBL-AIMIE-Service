from typing import Generator, Any
import azure.durable_functions as df
from azure.durable_functions.models.Task import TaskBase

from activities.types import (
    AnswerWithSourcesResult,
    QARequest,
    QaCrossExaminationRequest,
    QaFinalResponseActivityRequest,
    argument_builders_cross_examination_activity_name,
    argument_builders_final_response_activity_name,
    argument_builders_initial_activity_name,
)
from .statement_revisor import StatementRevisor
from .progress import update_progress
from .types import ArgumentBuilderResult, QuestionRequest
from .utils import (
    unique_context,
    unique_sources,
    convert_documents_to_simplified_documents,
    get_validation_status,
    normalize_session_id,
)

argument_builders_orchestrator_bp = df.Blueprint()


@argument_builders_orchestrator_bp.orchestration_trigger(context_name="context", orchestration="ArgumentBuildersOrchestration")
def argument_builders_orchestrator(activity_context: df.DurableOrchestrationContext) -> Generator[TaskBase, Any, Any]:
    body = activity_context.get_input()
    request = QuestionRequest.model_validate(body)
    if body is None:
        raise ValueError("Missing body parameter")
    provide_thorough_response = request.provide_thorough_response if request.provide_thorough_response else False
    actions = ['Initial Question', 'Cross Examination',
               'Final Response'] if provide_thorough_response else ['Question']
    actions_completed = 0
    actions_remaining = len(actions)
    activity_context.set_custom_status(
        {'actionsCompleted': actions_completed, 'actionsRemaining': actions_remaining, 'actionsToComplete': actions})
    account_id: str = request.account_id
    max_doc_count: int = request.max_doc_count if request.max_doc_count else 20
    location: str = request.location if request.location else "Snohomish County, Washington"
    hearing_type: str = request.hearing_type if request.hearing_type else "Family Law"
    opposition: str = request.target if request.target else "court"
    session_id = normalize_session_id(request.session_id)

    statement_revisor = StatementRevisor(
        activity_context, 
        location,
        max_doc_count, 
        hearing_type, 
        account_id, 
        session_id)

    qa_initial_request = QARequest(
        account_id=account_id,
        session_id=session_id,
        input=request.question,
        location=location,
        hearing_type=hearing_type,
        target=opposition,
        max_doc_count=max_doc_count,
        use_secondary_model=request.use_secondary_model if request.use_secondary_model else provide_thorough_response)
    qa_initial_activity_result: AnswerWithSourcesResult = yield activity_context.call_activity(argument_builders_initial_activity_name, 
                                                                                               qa_initial_request)
    actions_completed, actions_remaining = update_progress(
        activity_context,
        actions,
        actions_completed,
        actions_remaining)

    if not provide_thorough_response:
        final_answer, validation_results = yield from statement_revisor.review_and_revise(qa_initial_activity_result.answer, 
                                                                                          actions_completed, 
                                                                                          actions_remaining, 
                                                                                          False)

        orchestrator_result = ArgumentBuilderResult(
            initial_argument=final_answer,
            counter_argument="",
            final_argument="",
            sources=qa_initial_activity_result.sources,
            context=convert_documents_to_simplified_documents(
                qa_initial_activity_result.context),
            validation_status=get_validation_status(validation_results)
        )
        return orchestrator_result.model_dump(mode="json", by_alias=True)

    qa_cross_exam_request = QaCrossExaminationRequest(
        account_id=account_id,
        session_id=session_id,
        input=request.question,
        location=location,
        hearing_type=hearing_type,
        target=opposition,
        max_doc_count=max_doc_count,
        aimie_answer=qa_initial_activity_result.answer,
        use_secondary_model=request.use_secondary_model if request.use_secondary_model else False)

    qa_cross_exam_activity_result = yield activity_context.call_activity(argument_builders_cross_examination_activity_name, 
                                                                         qa_cross_exam_request)
    if not isinstance(qa_cross_exam_activity_result, AnswerWithSourcesResult):
        raise ValueError("Invalid response from cross examination activity")

    actions_completed, actions_remaining = update_progress(
        activity_context, actions, actions_completed, actions_remaining)

    qa_final_response_request = QaFinalResponseActivityRequest(
        account_id=account_id,
        session_id=session_id,
        input=request.question,
        location=location,
        hearing_type=hearing_type,
        target=opposition,
        max_doc_count=max_doc_count,
        aimie_answer=qa_initial_activity_result.answer,
        bob_response=qa_cross_exam_activity_result.answer,
        use_secondary_model=request.use_secondary_model if request.use_secondary_model else False)

    # type: ignore
    qa_final_response_result = yield \
        activity_context.call_activity(argument_builders_final_response_activity_name, 
                                       qa_final_response_request)
    if not isinstance(qa_final_response_result, AnswerWithSourcesResult):
        raise ValueError("Invalid response from final response activity")

    actions_completed, actions_remaining = update_progress(
        activity_context, actions, actions_completed, actions_remaining)

    final_answer, validation_results = yield from \
        statement_revisor.review_and_revise(qa_final_response_result.answer, 
                                            actions_completed, 
                                            actions_remaining,
                                            False)


    combined_context = unique_context(
        qa_initial_activity_result.context,
        qa_cross_exam_activity_result.context,
        qa_final_response_result.context)
    combined_sources = unique_sources(
        qa_initial_activity_result.sources,
        qa_cross_exam_activity_result.sources,
        qa_final_response_result.sources)

    orchestrator_result = ArgumentBuilderResult(
        initial_argument=qa_initial_activity_result.answer,
        counter_argument=qa_cross_exam_activity_result.answer,
        final_argument=final_answer,
        sources=combined_sources,
        context=convert_documents_to_simplified_documents(combined_context),
        validation_status=get_validation_status(validation_results)
    )

    return orchestrator_result.model_dump(mode="json", by_alias=True)

