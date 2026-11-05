import logging
from typing import Generator, Any, List

from azure.durable_functions import DurableOrchestrationContext, RetryOptions, Blueprint
from azure.durable_functions.models.Task import TaskBase

from activities.types import RhetoricActivityRequest, RhetoricActivityResult, SourceActivityResult
from activities.types import rhetoric_activity_name
from AIInteractionService.utils.section_extractor import SectionExtractor

from .types import SimplifiedDocument, rhetoric_builder_orchestrator_name, RhetoricBuilderOrchestrationRequest, RhetoricOrchestrationResult
from .utils import convert_documents_to_simplified_documents, normalize_session_id

rhetoric_builder_bp = Blueprint()

@rhetoric_builder_bp.orchestration_trigger(context_name="context", orchestration=rhetoric_builder_orchestrator_name)
def rhetoric_builder_orchestrator(activity_context: DurableOrchestrationContext) -> Generator[TaskBase, Any, Any]:
    try:
        body = activity_context.get_input()
        request = RhetoricBuilderOrchestrationRequest.model_validate(
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
        section_extractor = SectionExtractor()
        sections = section_extractor.extract_sections_all(statement)
        requests = []
        for section in sections:
            logging.info("Generating additional context for section (%s - %s): %s",
                        account_id, session_id, section[:15])
            original_section = '\n'.join(sections[section])
            if original_section.strip() == "":
                continue
            request = RhetoricActivityRequest(
                account_id=account_id,
                session_id=session_id,
                max_doc_count=max_doc_count,
                hearing_type=hearing_type,
                input=original_section,
                location=location)
            
            activity_request = activity_context.call_activity_with_retry(
                rhetoric_activity_name,
                retry_options,
                request)
            
            requests.append(activity_request)

        results: List[RhetoricActivityResult] = yield activity_context.task_all(requests)
        overall_context: List[SimplifiedDocument] = []
        sources: List[SourceActivityResult] = []
        for result in results:
            section = result.original_section
            additional_section: str = result.answer
            if additional_section.startswith("AIMIE_BOT Response:"):
                additional_section = additional_section[15:]
            sections[section] = [additional_section]
            context = convert_documents_to_simplified_documents(result.context)
            overall_context.extend(context)
            sources.extend(result.sources)

        adjusted_answer = section_extractor.reapply_sections(
                statement, 
                sections)
        
        final_result = RhetoricOrchestrationResult(
            answer=adjusted_answer,
            context=overall_context,
            sources=sources
        )

        logging.info("Rhetoric builder orchestration completed for (%s - %s)",
                     account_id, session_id)
        return final_result.model_dump(mode="json", exclude_none=False)
    except Exception as e:
        logging.error("Error in rhetoric_builder_orchestrator: %s", str(e))
        return RhetoricOrchestrationResult(
            answer=statement,
            context=[],
            sources=[]
        ).model_dump(mode="json", exclude_none=False)