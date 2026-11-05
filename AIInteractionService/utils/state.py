# We define a dict representing the state of the application.
# This state has the same input and output keys as `rag_chain`.
from typing import Annotated, List, Optional, Sequence
from typing_extensions import TypedDict

from ..db.cosmosdb_message_history_processor import BaseMessage


from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class BaseState(TypedDict):
    chat_history: Annotated[Sequence[BaseMessage],
                            add_messages]  # type: ignore

class State(TypedDict):
    input: Optional[str]
    original_question: Optional[str]
    chat_history: Annotated[Sequence[BaseMessage], 
                            add_messages]
    context: str
    answer: str
    target: Optional[str]
    designated_client: Optional[str]
    designated_client_role: Optional[str]
    opposition: Optional[str]
    opposition_role: Optional[str]
    aimies_client: Optional[str]
    aimie_answer: Optional[str]
    aimies_filing_role: Optional[str]
    bob_response: Optional[str]
    aimie_rebuttal: Optional[str]
    response_detail_instruction: Optional[str]
    now: Optional[str]
    sources: Annotated[
        List[str],
        ...,
        "List of sources used to answer the question in JSON format.  Ensure " \
        "that the page number is labeled 'pageNumber'.  If there are a range " \
        "of page numbers, create a separate list item for each page number."
    ]

class StateOpenAi(State):
    chat_history: Annotated[
        Sequence[BaseMessage], 
        add_messages(format='langchain-openai')] # type: ignore