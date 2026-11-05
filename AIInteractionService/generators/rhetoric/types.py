from typing_extensions import List
from langchain_core.messages import BaseMessage
from langchain_core.documents import Document

from ..common import BaseRequestModel, AnswersWithSources
from ..librarian.quote import LibrarianOutput
from ...utils.state import State


class RhetoricWriterAgentRequest(BaseRequestModel):
    statement: str

class RhetoricWriterOutput(LibrarianOutput):
    answer: AnswersWithSources
    context: List[Document]
    location: str
    chat_history: List[BaseMessage]

class RhetoricState(State):
    statement: str
    location: str