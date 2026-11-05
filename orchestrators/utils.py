import re
from typing import Iterable, Sequence
from uuid import uuid4
from typing_extensions import List, Union
from langchain_core.documents import Document
from AIInteractionService.generators.common import AgentResult
import orjson
from activities.types import AnswerWithSourcesResult, FactValidatorActivityResults, SourceActivityResult
from orchestrators.types import SimplifiedDocument, ValidationStatus


def _document_id(document: Document) -> str | None:
    return document.metadata.get("id")


def unique_context(*contexts: Iterable[Document]) -> List[Document]:
    unique_documents: dict[str, Document] = {}
    documents_without_ids: List[Document] = []
    for context in contexts:
        for document in context:
            doc_id = _document_id(document)
            if not doc_id:
                documents_without_ids.append(document)
                continue
            if doc_id not in unique_documents:
                unique_documents[doc_id] = document

    return [*unique_documents.values(), *documents_without_ids]


def unique_sources(*source_groups: Iterable[SourceActivityResult]) -> List[SourceActivityResult]:
    unique_sources: dict[str, SourceActivityResult] = {}
    sources_without_ids: List[SourceActivityResult] = []
    for sources in source_groups:
        for source in sources:
            if not source.doc_id:
                sources_without_ids.append(source)
                continue
            if source.doc_id not in unique_sources:
                unique_sources[source.doc_id] = source

    return [*unique_sources.values(), *sources_without_ids]


def convert_document_to_simplified_document(document: Document) -> SimplifiedDocument:
    metadata = document.metadata
    headers = []
    if 'Header 1' in metadata:
        headers.append(metadata['Header 1'])
    if 'Header 2' in metadata:
        headers.append(metadata['Header 2'])
    if 'Header 3' in metadata:
        headers.append(metadata['Header 3'])
    if 'Header 4' in metadata:
        headers.append(metadata['Header 4'])
    if 'Header 5' in metadata:
        headers.append(metadata['Header 5'])
    if 'Header 6' in metadata:
        headers.append(metadata['Header 6'])
    return SimplifiedDocument(
        doc_id=document.metadata['id'],
        pages=document.metadata['pages'] if 'pages' in document.metadata else [
        ],
        title=document.metadata['title'] if 'title' in document.metadata else None,
        source_url=document.metadata['source'] if 'source' in document.metadata else 'N/A',
        source_id=document.metadata['sourceId'] if 'sourceId' in document.metadata else 'N/A',
        position=document.metadata['pos'] if 'pos' in document.metadata else None,
        page_content=document.page_content,
        headers=headers,
        tags=document.metadata['tags'] if 'tags' in document.metadata else [],
        where=document.metadata['where'] if 'where' in document.metadata else None,
        what=document.metadata['what'] if 'what' in document.metadata else None,
        who=document.metadata['who'] if 'who' in document.metadata else [],
        why=document.metadata['why'] if 'why' in document.metadata else None,
        when_started=document.metadata['whenStarted'] if 'whenStarted' in document.metadata else None,
        when_ended=document.metadata['whenEnded'] if 'whenEnded' in document.metadata else None
    )


def convert_documents_to_simplified_documents(document: List[Document]) -> List[SimplifiedDocument]:
    return [convert_document_to_simplified_document(doc) for doc in document]


def ensure_document(docs: list) -> List[Document]:
    return [doc if isinstance(doc, Document) else Document(**doc) for doc in docs]


def convert_to_document(docs: List[SimplifiedDocument]) -> List[Document]:
    return [Document(page_content=doc.page_content,
                     metadata={
                         'id': doc.doc_id,
                         'pages': doc.pages,
                         'title': doc.title,
                         'source': doc.source_url,
                         'sourceId': doc.source_id,
                         'pos': doc.position,
                         'headers': doc.headers,
                         'tags': doc.tags,
                         'where': doc.where,
                         'what': doc.what,
                         'who': doc.who,
                         'why': doc.why,
                         'whenStarted': doc.when_started,
                         'whenEnded': doc.when_ended
                     }) for doc in docs]


def get_refined_context(results: Union[AgentResult, AnswerWithSourcesResult]) -> List[Document]:
    if isinstance(results, dict):
        current_context = results['context']
        if current_context:
            if isinstance(current_context, list):
                return ensure_document(current_context)
            elif isinstance(current_context, str):
                return orjson.loads(current_context)
    elif isinstance(results, AnswerWithSourcesResult):
        return ensure_document(results.context)
    return list()


def normalize_session_id(session_id: str | None) -> str:
    """
    Normalize the session ID by replacing non-alphanumeric characters with hyphens.
    """
    if session_id is None:
        return str(uuid4())
    return re.sub(r'[^a-zA-Z0-9-]+', '-', session_id)


def get_validation_status(results: Sequence[FactValidatorActivityResults]) -> List[ValidationStatus]:
    validation_status: List[ValidationStatus] = []
    for result in results:
        new_validation_status = ValidationStatus(
            explanation=result.answer,
            claim=result.original_statement,
            is_valid=result.is_valid,
            is_contradictory=result.is_contradictory,
            is_inferred=result.is_inferred,
            is_reasonably_inferred=result.is_reasonably_inferred,
            is_not_found_in_context=result.is_not_found_in_context,
            is_summary_or_conclusion=result.is_summary_or_conclusion,
            contradiction_statement=result.contradiction_statement,
            contradiction_sources=result.contradiction_source.split(
                ",") if result.contradiction_source else [],
            sources=result.sources
        )
        validation_status.append(new_validation_status)
    return validation_status
