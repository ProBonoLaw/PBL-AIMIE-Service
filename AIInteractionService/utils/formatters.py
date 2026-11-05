import orjson
import logging
import marko
from typing import Any, Dict, Generator, List, Optional
from langchain_core.documents import Document
from toon import encode


def format_document2(doc: Document):
    if isinstance(doc, str) and len(doc):
        metadata = ''
        page_content = doc
    elif not isinstance(doc, str) and len(doc.page_content):
        metadata = doc.metadata
        page_content = doc.page_content
    if isinstance(metadata, str):
        metadata = orjson.loads(metadata)
    data_structure = format_source(
        metadata if metadata else {})
    data_structure['pageContent'] = page_content
    return data_structure


FACT_EVENT_TAGS = {"fact", "claim", "assertion", "allegation"}
FACT_EVENT_REQUIRED_TAG = "event"
FACT_EVENT_METADATA_FIELDS = (
    "where",
    "what",
    "who",
    "why",
    "whenStarted",
    "whenEnded",
)


def _has_metadata_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


def _is_fact_event_metadata(metadata: dict) -> bool:
    tags = metadata.get("tags")
    if not isinstance(tags, list):
        return False
    normalized_tags = {str(tag).lower() for tag in tags}
    return (
        FACT_EVENT_REQUIRED_TAG in normalized_tags
        and bool(FACT_EVENT_TAGS & normalized_tags)
    )


def format_source(doc_metadata: dict):
    source: Dict[str, Any] = dict()
    if 'id' not in doc_metadata and 'title' not in doc_metadata:
        logging.warning("Document metadata does not contain 'docId'. Returning empty source.")
        return source

    if 'id' in doc_metadata:
        source['docId'] = doc_metadata['id']
    if 'title' in doc_metadata:
        source['docTitle'] = doc_metadata['title']
    if _has_metadata_value(doc_metadata.get('sourceId')):
        source['sourceId'] = doc_metadata['sourceId']
    if _has_metadata_value(doc_metadata.get('pages')):
        source['pages'] = doc_metadata['pages']
    if _has_metadata_value(doc_metadata.get('tags')):
        source['tags'] = doc_metadata['tags']
    if _is_fact_event_metadata(doc_metadata):
        for field in FACT_EVENT_METADATA_FIELDS:
            if _has_metadata_value(doc_metadata.get(field)):
                source[field] = doc_metadata[field]

    sections = []
    if 'header1' in doc_metadata:
        sections.append(doc_metadata['Header 1'])

    if 'header2' in doc_metadata:
        sections.append(doc_metadata['Header 2'])

    if 'header3' in doc_metadata:
        sections.append(doc_metadata['Header 3'])

    if 'header4' in doc_metadata:
        sections.append(doc_metadata['Header 4'])

    if 'header5' in doc_metadata:
        sections.append(doc_metadata['Header 5'])

    if 'header6' in doc_metadata:
        sections.append(doc_metadata['Header 6'])
    
    if len(sections) > 0:
        source['sections'] = sections

    return source


def extract_content_from_page(doc: Document | str):
    if isinstance(doc, str) and len(doc):
        page_content = doc
    elif not isinstance(doc, str) and len(doc.page_content):
        page_content = doc.page_content
    else:
        logging.warning("There isn't any content in the document")
        page_content = ''
    return page_content


def format_docs_without_metadata(inputs: dict) -> str:
    encoded_docs = encode(
        [extract_content_from_page(doc)
        for doc in inputs['context']]
    )

    return f"```toon\n{encoded_docs}\n```"


def format_docs(inputs: dict, max_doc_count: Optional[int] = None) -> str:
    adj_context = get_unique_docs(inputs['context'], max_doc_count)
    inputs['context'] = adj_context
    encoded_docs = encode([
        format_document2(doc) for doc in adj_context if analyze_docs(extract_content_from_page(doc))
    ]) if inputs['context'] else 'docs[0]:'

    return f"```toon\n{encoded_docs}\n```"

def get_total_score(doc: Document) -> float:
    reranker_score = doc.metadata.get('reranker_score', 0) or 0
    score = doc.metadata.get('score', 0) or 0
    total_score = reranker_score * 100 + score
    return total_score


def get_unique_docs(inputs: list[Document], max_doc_count: Optional[int] = None) -> List[Document]:
    seen_content: Dict[str, Document] = dict()
    for doc in inputs:
        doc_id = doc.metadata.get('id', '')
        if (doc_id not in seen_content):
            seen_content[doc_id] = doc
        else:
            old_document = seen_content[doc_id]
            old_document_score = get_total_score(old_document)
            new_document_score = get_total_score(doc)
            if new_document_score > old_document_score:
                seen_content[doc_id] = doc

    result_list = list(seen_content.values())
    result_list.sort(key=lambda x: get_total_score(x), reverse=True)
    final_result_list: List[Document] = result_list[:max_doc_count] if max_doc_count is not None else result_list
    return final_result_list


def analyze_docs(page_content: str) -> bool:
    doc = marko.parse(page_content)
    if len(doc.children) > 1:
        if not isinstance(doc.children[0], marko.block.Heading):
            return True
        else:
            for child in doc.children[1:]:
                if not isinstance(child, marko.block.BlankLine):
                    return True
    if len(doc.children) == 1:
        only_child = doc.children[0]
        if not isinstance(only_child, marko.block.Heading):
            return True
    return False
