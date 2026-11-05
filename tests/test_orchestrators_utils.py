from langchain_core.documents import Document

from activities.types import SourceActivityResult
from orchestrators.utils import _document_id, unique_context, unique_sources


def test_document_id_reads_metadata_id():
    assert _document_id(Document(page_content="", metadata={"id": "doc-1"})) == "doc-1"
    assert _document_id(Document(page_content="", metadata={})) is None


def test_unique_context_deduplicates_by_document_id_and_keeps_first_value():
    first = Document(page_content="first", metadata={"id": "doc-1"})
    second = Document(page_content="second", metadata={"id": "doc-2"})
    duplicate = Document(page_content="duplicate", metadata={"id": "doc-1"})
    no_id = Document(page_content="no id", metadata={})

    result = unique_context([first, second], [duplicate, no_id])

    assert result == [first, second, no_id]


def test_unique_sources_deduplicates_by_doc_id_and_keeps_first_value():
    first = SourceActivityResult(doc_id="doc-1", pages=[1])
    second = SourceActivityResult(doc_id="doc-2", pages=[2])
    duplicate = SourceActivityResult(doc_id="doc-1", pages=[99])
    no_id = SourceActivityResult(doc_id="", pages=[3])

    result = unique_sources([first, second], [duplicate, no_id])

    assert result == [first, second, no_id]
