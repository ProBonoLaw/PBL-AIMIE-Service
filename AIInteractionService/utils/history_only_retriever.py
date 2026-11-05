from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import PrivateAttr


from typing import Any, List


class HistoryOnlyRetriever(BaseRetriever):
    _context: List[Document] = PrivateAttr()

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._context = kwargs.get("context", [])

    def _get_relevant_documents(
            self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> List[Document]:
        return self._context
        