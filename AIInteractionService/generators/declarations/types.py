from typing_extensions import Any, List, Optional

from ..common import BaseRequestModel, SourceResult, AnswersWithSources

class DeclarationBuilderOutput(BaseRequestModel):
    answer: str
    has_error: Optional[bool]
    sources: List[SourceResult]

class DeclarationWriterAgentRequest(BaseRequestModel):
    statement: str
    location: str
    hearing_type: str
    opposition: str
    opposition_role: str
    designated_client: str
    designated_client_role: str

class DeclarationWriterOutput(AnswersWithSources):
    pass
