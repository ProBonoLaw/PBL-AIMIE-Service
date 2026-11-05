import pytest

from orchestrators.timeline import timeline_orchestration


class FakeContext:
    def __init__(self):
        self.statuses = []
        self.activity_request = None

    def get_input(self):
        return {
            'accountId': 'account-123',
            'sessionId': 'session/456',
            'input': 'Build a timeline.',
            'location': 'Untrusted location',
            'hearingType': 'Untrusted hearing type',
        }

    def set_custom_status(self, status):
        self.statuses.append(status)

    def call_activity(self, name, request):
        self.activity_request = (name, request)
        return 'activity-task'


def test_timeline_orchestration_does_not_accept_request_location_or_hearing_type():
    context = FakeContext()
    workflow = timeline_orchestration._function._func.orchestrator_function(context)
    assert next(workflow) == 'activity-task'
    assert context.activity_request[0] == 'timelineActivity'
    assert context.activity_request[1]['session_id'] == 'session-456'
    assert context.activity_request[1]['location'] == ''
    assert context.activity_request[1]['hearing_type'] is None

    with pytest.raises(StopIteration) as completed:
        workflow.send({
            'sessionId': 'session-456',
            'accountId': 'account-123',
            'originalRequest': 'Build a timeline.',
            'timeRange': {},
            'summary': 'Supported timeline.',
            'entries': [],
        })

    response = completed.value.value
    assert response['sessionId'] == 'session/456'
    assert response['accountId'] == 'account-123'
