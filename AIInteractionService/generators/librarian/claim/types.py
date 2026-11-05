import orjson
import logging
from typing import Optional
from pydantic import AliasChoices, BaseModel, Field
from typing_extensions import Annotated, Any, List, TypedDict

from langchain_core.documents import Document
from ...common import BaseRequestModel


class AmieLibrarianClaimAgentRequest(BaseRequestModel):
    claim: str

class LibrarianClaimElement(BaseModel):
    exact_quote: str = Field(..., 
                             description="The exact quote that was found.", 
                             serialization_alias="exactQuote",
                             validation_alias=AliasChoices("exact_quote", "exactQuote", "ExactQuote"))
    doc_id: str = Field(...,
                        serialization_alias="docId",
                        validation_alias=AliasChoices("doc_id", "docId", "DocId"),
                        description='The identifier of the document from which the claim has been validated.')
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

class LibrarianClaimAnswer(BaseModel):
    docs: List[LibrarianClaimElement] = Field(
        ...,
        serialization_alias="docs",
        validation_alias=AliasChoices("docs", "Docs"),
        description="List of documents that substantiates the claim")
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

class LibrarianClaimOutput(TypedDict):
    answer: LibrarianClaimAnswer
    has_multiple_sources: bool
    context: Any

