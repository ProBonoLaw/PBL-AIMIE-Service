from typing import List
import azure.durable_functions as df


from activities import DiscoveryActivityRequest
from activities.types import DiscoveryActivityResults
from orchestrators.utils import normalize_session_id
from .types import DiscoveryOrchestrationRequest

discovery_bp = df.Blueprint()

@discovery_bp.orchestration_trigger(context_name="context", orchestration="DiscoveryOrchestration")
def discovery_orchestration(context: df.DurableOrchestrationContext):
    body = context.get_input()
    if body is None:
        raise ValueError("Missing body parameter")
    request = DiscoveryOrchestrationRequest.model_validate(body)
    account_id: str = request.account_id
    session_id = normalize_session_id(request.session_id)
    if not account_id:
        raise ValueError("Missing accountId parameter")
    max_doc_count: int = request.max_doc_count if request.max_doc_count else 20
    location: str = request.location if request.location else "Snohomish County"
    hearing_type: str = request.hearing_type if request.hearing_type else "Family Law"
    target: str = request.target if request.target else "court"

    topics: List[str] = request.topics if request.topics else []
    if 'General' not in topics:
        topics.append('General')

    qa_request = DiscoveryActivityRequest(account_id=account_id,
                                session_id=session_id,
                                input=request.input if request.input else 'Generic Discovery Request',
                                location=location, 
                                hearing_type=hearing_type,
                                topics=topics,
                                target=target,
                                max_doc_count=max_doc_count)

    discovery_request_activity_result:DiscoveryActivityResults = yield context.call_activity("discovery_request_activity", qa_request)
    return discovery_request_activity_result.model_dump(mode='json', by_alias=True)