
import orjson
from typing import Union
from typing_extensions import List, Optional
from pydantic import AliasChoices, BaseModel, Extra, Field

from ...utils.common_types import Source


class BaseRequestModel(BaseModel):
    location: str | None = Field(
        default=None,
        description="The location associated with the case"
    )
    swap_roles: bool | None = Field(
        default=None,
        serialization_alias="swapRoles",
        description="Indicates whether to swap roles",
        validation_alias=AliasChoices('swap_roles','swapRoles', 'SwapRoles')
    )


class SourceResult(BaseModel):
    doc_id: str = Field(
        ...,
        serialization_alias="docId",
        validation_alias=AliasChoices('docId', 'doc_id', 'DocId'),
        description="Mandatory field, the ID of the document"
    )
    pages: List[int] = Field(
        ...,
        alias="pages",
        description="List of pages, if known and could be extracted from the document.  If not, provide an empty list.")

    class Config:
        extra = 'forbid'

        @staticmethod
        def json_schema_extra(schema, model):
            # Explicitly set additionalProperties to False
            schema["additionalProperties"] = False


class AnswersWithSources(BaseModel):
    answer: str = Field(
        ...,
        alias="answer",
        description=(
            "The answer to the question with citations (docId references).  The citation format is (\"docId\":docId). \nExample: \"Alex Example was born in 1990 (\"docId\":\"123456\").\" ")
    )
    sources: List[SourceResult] = Field(
        ...,
        alias="sources")

    class Config:
        extra = 'forbid'

        @staticmethod
        def json_schema_extra(schema, model):
            # Explicitly set additionalProperties to False
            schema["additionalProperties"] = False


class FormalAnswersWithSources(AnswersWithSources):
    answer: str = Field(
        ...,
        alias="answer",
        description=(
            "The response format MUST be in the form of a legal declaration in MARKDOWN syntax. "
            "Every paragraph in sections Background and Argument must be numbered in sequential order, "
            "starting with 1, and continuing to the end of the document. Do not number the paragraphs "
            "in Introduction and Conclusion sections. "
            "The MARKDOWN format of the document must be of the following: "
            "1. Introduction: A brief introduction to the case. It should be started with the markdown header `## Introduction`. "
            "2. Background: A brief background of the case. It should be started with the markdown header `## Background`. "
            "3. Argument: The main argument of the case. It should be started with the markdown header `## Arguments`.  When numbering paragraphs, "
            "continue the numbering from the previous paragraph and section.  So, if the last paragraph from 'Background' section was 5, then "
            "the first paragraph of the 'Arguments' section should be numbered 6. "
            "All subsequent arguments should be started with the markdown header `### ` followed by the name of the sub-argument. "
            "This section requires a detailed explanation and quotes from the original documents cited. Details are key."
            "4. Conclusion: A brief conclusion of the case. It should be started with the markdown header `## Conclusion`. "
            "When numbering paragraphs, continue the numbering from the previous paragraph and section.  "
            "So, if the last paragraph from 'Arguments' section was 10, then "
            "the first paragraph of the 'Conclusion' section should be numbered 11. "
            "Also, the answer to the question with citations (docId references) or of the paragraph numbers found in this "
            "generated document.  The citation format is (\"docId\":docId), or (¶5) if referencing the 5th paragraph of "
            "the generated document. Do not add a reference if it is referring to the same paragraph."
            "Example: \"Alex Example was born in 1990 (\"docId\":\"123456\", \"pages\":[5, 6]).\" ")
    )


answers_with_sources_json_schema = orjson.dumps(AnswersWithSources.model_json_schema(
    by_alias=True, mode='validation')).decode().replace('{', '{{').replace('}', '}}')
formal_answers_with_sources_json_schema = orjson.dumps(FormalAnswersWithSources.model_json_schema(
    by_alias=True, mode='validation')).decode().replace('{', '{{').replace('}', '}}')

answers_with_sources_response_format = {
    "type": "json_schema",
    "json_schema": {
            "name": "answers_with_sources",
            "strict": True,
            "schema": AnswersWithSources.model_json_schema(by_alias=True, mode="serialization")
    }
}


def normalize_source(source: Union[Source, SourceResult]) -> SourceResult:
    if isinstance(source, SourceResult):
        return source
    return SourceResult(doc_id=source['docId'] if 'docId' in source else source['doc_id'], pages=source['pages'] if 'pages' in source and source['pages'] is not None else [])
