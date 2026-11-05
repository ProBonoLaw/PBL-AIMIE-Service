from ...common import BaseRequestModel

class FinalResponseRequest(BaseRequestModel):
    original_question: str
    aimie_answer: str
    bob_response: str
    aimies_client: str
    aimies_filing_role: str
    opposition: str
    opposition_role: str