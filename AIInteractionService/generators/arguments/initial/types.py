
from ...common import BaseRequestModel

class InitialArgumentRequest(BaseRequestModel):
    input: str
    opposition: str
    opposition_role: str
    designated_client: str
    designated_client_role: str