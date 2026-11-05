import orjson
from typing import Sequence, List, TypeVar, TypedDict, Union

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage

from AIInteractionService.generators.common.types import AnswersWithSources

from ...utils.common_types import Source

class AgentResult(TypedDict):
    answer: Union[str,  AnswersWithSources]
    context: List[Document]
    sources: List[Source]
    chat_history: List[BaseMessage]

T = TypeVar('T')

def get_refined_context(results: Union[AgentResult, T]) -> List[Document]:
    if isinstance(results, dict):
        current_context = results['context']
        if current_context:
            if isinstance(current_context, list):
                return ensure_document(current_context)
            elif isinstance(current_context, str):
                return orjson.loads(current_context)
    return list()

def ensure_document(docs: Sequence) -> List[Document]:
    return [doc if isinstance(doc, Document) else Document(**doc) for doc in docs]