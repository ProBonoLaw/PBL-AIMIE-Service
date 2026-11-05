from typing import List
from toon import encode
from langchain_core.documents import Document

from ...common import BaseRequestModel
from ....utils.formatters import format_document2

class ClosingArgumentRequest(BaseRequestModel):
    original_question: str
    aimie_answer: str
    bob_response: str
    opposition: str
    opposition_role: str
    designated_client: str
    designated_client_role: str

def limit_tokens_used(documents: List[Document], max_tokens: int) -> List[Document]:
    total_tokens = 0
    final_documents: List[Document] = []
    for doc in documents:
        document_value = encode(format_document2(doc))
        total_tokens += (len(document_value) / 4)
        if total_tokens > max_tokens:
            break
        final_documents.append(doc)
    return final_documents