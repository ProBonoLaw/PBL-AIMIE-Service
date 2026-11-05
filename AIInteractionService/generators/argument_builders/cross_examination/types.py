
from ...common import BaseRequestModel


class CrossExaminationRequest(BaseRequestModel):
    original_question: str
    aimie_answer: str
    aimies_client: str
    aimies_filing_role: str
    opposition: str
    opposition_role: str