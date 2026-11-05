import azure.durable_functions as df
from activities.types import BaseActivityRequest
from .types import TimelineRequest, TimelineOrchestrationResult
from .utils import normalize_session_id

timeline_bp = df.Blueprint()

@timeline_bp.orchestration_trigger(context_name='context', orchestration='TimelineOrchestration')
def timeline_orchestration(context: df.DurableOrchestrationContext):
    request = TimelineRequest.model_validate(context.get_input())
    activity_request = BaseActivityRequest(
        account_id=request.account_id,
        session_id=normalize_session_id(request.session_id),
        input=request.input,
        location='',
        hearing_type=None,
        max_doc_count=request.max_doc_count or 20,
    )
    context.set_custom_status({'actionsCompleted': 0, 'actionsRemaining': 1, 'actionsToComplete': ['Timeline']})
    result = yield context.call_activity('timelineActivity', activity_request.model_dump(mode='json'))
    context.set_custom_status({'actionsCompleted': 1, 'actionsRemaining': 0, 'actionsToComplete': []})
    result = dict(result)
    result['sessionId'] = request.session_id
    result['accountId'] = request.account_id
    return TimelineOrchestrationResult.model_validate(result).model_dump(mode='json', by_alias=True)
