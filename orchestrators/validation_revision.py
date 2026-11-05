from typing import Generator, Any, Optional

from azure.durable_functions import DurableOrchestrationContext, RetryOptions, Blueprint
from azure.durable_functions.models.Task import TaskBase

from activities.types import AnswerWithSourcesResult, FactValidatorActivityRequest, FactValidatorActivityResults, RevisionActivityRequest
from activities.types import fact_validator_activity_name, revision_activity_name
from .types import StatementValidationRevisionOrchestrationRequest, StatementValidationRevisionOrchestrationResult, statement_revisor_orchestrator_name
from .utils import normalize_session_id

statement_revision = Blueprint()


@statement_revision.orchestration_trigger(context_name="context", orchestration=statement_revisor_orchestrator_name)
def statement_validation_revisions_orchestrator(activity_context: DurableOrchestrationContext) -> Generator[TaskBase, Any, Any]:
    body = activity_context.get_input()
    request = StatementValidationRevisionOrchestrationRequest.model_validate(
        body)
    if body is None:
        raise ValueError("Missing body parameter")
    retry_options: RetryOptions = RetryOptions(1000, 3)
    session_id = normalize_session_id(request.session_id)
    account_id: str = request.account_id
    max_doc_count: int = request.max_doc_count if request.max_doc_count else 20
    location: str = request.location if request.location else "Snohomish County, Washington"
    hearing_type: str = request.hearing_type if request.hearing_type else "Family Law"
    statement: str = request.statement if request.statement else ""
    original_input_statement: str = request.original_input_statement if request.original_input_statement else ""
    fact_validator_request = FactValidatorActivityRequest(
        input=statement,
        raw_input=original_input_statement,
        is_last_paragraph=request.is_last_paragraph,
        original_request=request.original_request,
        location=location,
        max_doc_count=max_doc_count,
        hearing_type=hearing_type,
        account_id=account_id,
        session_id=session_id)
    fact_validator_activity_result = yield activity_context.call_activity_with_retry(
        fact_validator_activity_name,
        retry_options,
        fact_validator_request)

    if not fact_validator_activity_result.is_valid:
        revsion_validation_result = yield from statement_revision_activity(
            fact_validator_activity_result,
            original_input_statement,
            request.is_last_paragraph,
            request.original_request,
            location,
            max_doc_count,
            hearing_type,
            account_id,
            session_id,
            activity_context)

        return revsion_validation_result.model_dump(mode="json", exclude_none=False)

    return StatementValidationRevisionOrchestrationResult(
        original_input_statement=original_input_statement,
        validation_status=fact_validator_activity_result).model_dump(mode="json", exclude_none=False)


def statement_revision_activity(request: FactValidatorActivityResults,
                                original_input_statement: str,
                                is_last_paragraph: bool,
                                original_request: Optional[str],
                                location: str,
                                max_doc_count: int,
                                hearing_type: str,
                                account_id: str,
                                session_id: str,
                                activity_context: DurableOrchestrationContext,
                                rety_count: int = 0) -> Generator[Any, Any, StatementValidationRevisionOrchestrationResult]:
    """
    Handles the revision of a fact validator activity.

    :param request: The request to revise.
    :param original_input_statement: The original input statement to be revised.
    :param original_request: The original request for the activity.
    :param location: The location for the activity.
    :param max_doc_count: The maximum document count for the activity.
    :param hearing_type: The type of hearing for the activity.
    :param account_id: The account ID for the activity.
    :param session_id: The session ID for the activity.
    :param activity_context: The context for the activity.
    :param rety_count: The retry count for the activity.

    :return: The result of the revision activity.
    """
    if rety_count > 3:
        raise ValueError(
            f"Max retry count exceeded for revision activity: {request.raw_original_statement}")
    revision_request = RevisionActivityRequest(
        input=request.raw_original_statement,
        statement=request.raw_original_statement,
        feedback=request.answer,
        location=location,
        max_doc_count=max_doc_count,
        hearing_type=hearing_type,
        use_secondary_model=False,
        account_id=account_id,
        session_id=session_id)
    revision_activity_result: AnswerWithSourcesResult = yield activity_context.call_activity(
        revision_activity_name,
        revision_request)
    if revision_activity_result.answer and isinstance(revision_activity_result.answer, str):
        revised_fact_validator_request = FactValidatorActivityRequest(
            input=revision_activity_result.answer,
            raw_input=revision_activity_result.answer,
            is_last_paragraph=is_last_paragraph,
            original_request=original_request,
            location=location,
            max_doc_count=max_doc_count,
            hearing_type=hearing_type,
            account_id=account_id,
            session_id=session_id)
        # type: ignore
        revised_fact_validator_activity_result: FactValidatorActivityResults = yield activity_context.call_activity(
            fact_validator_activity_name,
            revised_fact_validator_request)
        if (revised_fact_validator_activity_result.is_valid == False):
            if (revised_fact_validator_activity_result.is_not_found_in_context == True):
                value = yield from statement_revision_activity(
                    revised_fact_validator_activity_result,
                    original_input_statement,
                    is_last_paragraph,
                    original_request,
                    location,
                    max_doc_count,
                    hearing_type,
                    account_id,
                    session_id,
                    activity_context,
                    rety_count + 1)
                return StatementValidationRevisionOrchestrationResult(
                    original_input_statement=original_input_statement,
                    revised_statement=value.revised_statement,
                    was_revised = value.was_revised,
                    validation_status=request)
        return StatementValidationRevisionOrchestrationResult(
            original_input_statement=original_input_statement,
            revised_statement=revision_activity_result.answer,
            was_revised = True,
            validation_status=request)
    else:
        raise ValueError(
            f"Invalid response from revision activity: {revision_activity_result.answer}")
