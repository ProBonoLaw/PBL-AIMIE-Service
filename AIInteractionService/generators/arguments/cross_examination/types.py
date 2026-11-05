
from ...common import BaseRequestModel


class CrossExaminationRequest(BaseRequestModel):
    original_question: str
    aimie_answer: str
    opposition: str
    opposition_role: str
    designated_client: str
    designated_client_role: str