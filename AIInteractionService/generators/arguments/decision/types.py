from ...common import BaseRequestModel

class FinalDecisionRequest(BaseRequestModel):
    original_question: str
    aimie_answer: str
    bob_response: str
    aimie_rebuttal: str
    opposition: str
    opposition_role: str
    designated_client: str
    designated_client_role: str