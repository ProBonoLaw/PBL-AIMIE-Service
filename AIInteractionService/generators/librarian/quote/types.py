import orjson
import logging
from typing import Optional
from pydantic import AliasChoices, BaseModel, Field
from typing_extensions import Annotated, Any, List, TypedDict

from langchain_core.documents import Document
from ...common import BaseRequestModel


class AmieLibrarianAgentRequest(BaseRequestModel):
    quote: str
    doc_id: str

class LibrarianElement(BaseModel):
    exact_quote: str = Field(..., 
                             description="The exact quote that was found.", 
                             serialization_alias="exactQuote",
                             validation_alias=AliasChoices("exact_quote", "exactQuote", "ExactQuote"))
    doc_id: str = Field(...,
                        serialization_alias="docId",
                        validation_alias=AliasChoices("doc_id", "docId", "DocId"),
                        description='The identifier of the document from which the quote originates.')
    document_with_highlighted_quote: str = Field(
        ...,
        serialization_alias="documentWithHighlightedQuote",
        validation_alias=AliasChoices("document_with_highlighted_quote", "documentWithHighlightedQuote", "DocumentWithHighlightedQuote"),
        description=('The original document, in its entirety and in converted to markdown format, with the quote '
                     'highlighted in yellow via the <mark></mark> element .')
    )
    class Config:
        extra = 'forbid'
        @staticmethod
        def json_schema_extra(schema, model):
            # Explicitly set additionalProperties to False
            schema["additionalProperties"] = False

class LibrarianAnswer(BaseModel):
    quotes: List[LibrarianElement] = Field(
        ...,
        serialization_alias="quotes",
        validation_alias=AliasChoices("quotes", "Quotes"),
        description="List of quotes that were found in the document")
    hasError: Optional[bool] = Field(
        ...,
        serialization_alias="hasError",
        validation_alias=AliasChoices("has_error", "hasError", "HasError"),
        description="Flag to indicate if there was an error")
    class Config:
        extra = 'forbid'
        @staticmethod
        def json_schema_extra(schema, model):
            # Explicitly set additionalProperties to False
            schema["additionalProperties"] = False

class LibrarianOutput(TypedDict):
    answer: LibrarianAnswer
    context: Any

librarian_answer_response_schema = orjson.dumps(LibrarianAnswer.model_json_schema(by_alias=True, mode='validation')).decode().replace('{', '{{').replace('}', '}}')

librarian_answer_response_format = {
    "type": "json_schema",
    "json_schema": {
            "name": "answers_with_sources",
            "strict": True,
            "schema": LibrarianAnswer.model_json_schema(by_alias=True, mode="serialization")
    }
}

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
    return '\n\n'.join(
        extract_content_from_page(doc)
        for doc in inputs['context']
    )