import orjson
from typing import Annotated, List, Optional, Sequence, TypedDict
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import AliasChoices, Field

from ....generators.common import AgentResult, AnswersWithSources
from ...common.base_agent import BaseRequestModel


class FactValidatorRequest(BaseRequestModel):
    input: str
    original_request: Optional[str] = Field(
        None,
        description="The original request that was used to generate the input.  " \
        "This is used to provide context for the input.",
        serialization_alias='originalRequest',
        validation_alias=AliasChoices('originalRequest', 'original_request', 'OriginalRequest')
    )
    is_last_paragraph: bool = Field(
        False,
        description="Set to True if the input is the last paragraph of the document.  " \
        "This is used to determine if the input is the last paragraph of the document.",
        serialization_alias='isLastParagraph',
        validation_alias=AliasChoices('isLastParagraph', 'is_last_paragraph', 'IsLastParagraph')
    )

class FactValidatorResponse(AnswersWithSources):
    answer: str = Field(
        ...,
        description="The answer is the explanation as to why the statement is valid or invalid.  " \
        "Keep in mind that a valid statement must be substantiated by documents found in context.",
        serialization_alias="answer",
        validation_alias=AliasChoices('answer', 'Answer')
        )
    is_valid: bool = Field(
        ...,
        description=("Set the value to True if the statement can be substantiated by document found in context."
                     "If there are no documents to substantiate the claim, then the statement is invalid.  " 
                     "False if the statement was invalid and there are no documents to substantiate the claim."),
        serialization_alias="isValid",
        validation_alias=AliasChoices('isValid', 'is_valid', 'IsValid')
        )
    is_contradictory: bool = Field(
        ...,
        description=("Set the value to True if the statement contradicts what is found in some, but not all contextual documents. "
                     "False if the statement cannot be contradicted by any documents."),
        serialization_alias="isContradictory",
        validation_alias=AliasChoices('isContradictory', 'is_contradictory', 'IsContradictory')
        )
    is_inferred: bool = Field(
        ...,
        description="Set the value to True if the statement is inferred from the context.  " \
        "False if the statement is not inferred.",
        serialization_alias="isInferred",
        validation_alias=AliasChoices('isInferred', 'is_inferred', 'IsInferred')
        )
    is_reasonably_inferred: bool = Field(
        ...,
        description="Set the value to True if the statement is reasonably by a person with average intelligence inferred from the context.  " \
        "False if the statement is not reasonably inferred.",
        serialization_alias="isReasonablyInferred",
        validation_alias=AliasChoices('isReasonablyInferred', 'is_reasonably_inferred', 'IsReasonablyInferred')
        )
    is_not_found_in_context: bool = Field(
        ...,
        description="Set the value to True if the statement is not found in the context.  " \
        "False if the statement is found in the context.",
        serialization_alias="isNotFoundInContext",
        validation_alias=AliasChoices('isNotFoundInContext', 'is_not_found_in_context', 'IsNotFoundInContext')
        )
    is_summary_or_conclusion: bool = Field(
        ...,
        description="Set the value to True if the statement is a summary or conclusion.  " \
        "False if the statement is not a summary or conclusion for the product of the original request.",
        serialization_alias="isSummaryOrConclusion",
        validation_alias=AliasChoices('isSummaryOrConclusion', 'is_summary_or_conclusion', 'IsSummaryOrConclusion')
        )
    is_implied: bool = Field(
        False,
        description="Set the value to True if the statement is implied by the context.  " \
        "False if the statement is not implied.",
        serialization_alias="isImplied",
        validation_alias=AliasChoices('isImplied', 'is_implied', 'IsImplied')
        )
    is_vague: bool = Field(
        False,
        description="Set the value to True if the statement is vague.  " \
        "False if the statement is not vague.", 
        serialization_alias="isVague",
        validation_alias=AliasChoices('isVague', 'is_vague', 'IsVague')
        )
    contradiction_statement: str = Field(
        ...,
        description="The contradiction.  This is a string that contains the page number and the text of the contradiction.",
        serialization_alias="contradictionStatement",
        validation_alias=AliasChoices('contradictionStatement', 'contradiction_statement', 'ContradictionStatement')
        )
    contradiction_source: str = Field(
        ...,
        description="The docId(s) of document(s) the contradiction. If there are multiple documents, separate them with a comma.",
        serialization_alias="contradictionSource",
        validation_alias=AliasChoices('contradictionSource', 'contradiction_source', 'ContradictionSource')
        )

fact_validator_json_schema = orjson.dumps(FactValidatorResponse.model_json_schema(by_alias=True, mode='validation')).decode().replace('{', '{{').replace('}', '}}')

class FactValidatorAgentResult(AgentResult):
    is_valid: Annotated[
        bool,
        ...,
        "True if the statement was valid.  False if the statement was invalid.  " \
    ]
    is_contradictory: Annotated[
        bool,
        ...,
        "True if the statement can be contradicted.  False if the statement was not " \
        "contradictory."
    ]
    is_inferred: Annotated[
        bool,
        ...,
        "True if the statement was inferred.  False if the statement was not inferred.  " \
    ]
    is_reasonably_inferred: Annotated[
        bool,
        ...,
        "True if the statement was reasonably inferred.  False if the statement was not " \
        "reasonably inferred."
    ]
    is_not_found_in_context: Annotated[
        bool,
        ...,
        "True if the statement was not found in the context.  False if the statement " \
        "was found in the context."
    ]
    is_summary_or_conclusion: Annotated[
        bool,
        ...,
        "True if the statement was a summary or conclusion.  False if the statement " \
        "was not a summary or conclusion."
    ]
    contradiction_statement: Annotated[
        str,
        ...,
        "The contradiction.  This is a string that contains the page number and the " \
        "text of the contradiction."
    ]
    contradiction_source: Annotated[
        str,
        ...,
        "The docId of the contradiction.  This is a string that contains the page " \
        "number and the text of the contradiction."
    ]
    is_implied: Annotated[
        bool,
        ...,
        "True if the statement was implied by the context.  False if the statement was not implied."
    ]
    is_vague: Annotated[
        bool,
        ...,
        "True if the statement was vague.  False if the statement was not vague."
    ]

class FactState(TypedDict):
    input: Optional[str]
    original_question: Optional[str]
    chat_history: Annotated[Sequence[BaseMessage], 
                            add_messages]
    context: str
    answer: str
    isValid: Annotated[
        bool,
        ...,
        "True if the statement was valid.  False if the statement was invalid.  " \
    ]
    is_contradictory: Annotated[
        bool,
        ...,
        "True if the statement can be contradicted.  False if the statement was not " \
        "contradictory."
    ]
    contradiction_statement: Annotated[
        str,
        ...,
        "The contradiction.  This is a string that contains the page number and the " \
        "text of the contradiction."
    ]
    contradiction_source: Annotated[
        str,
        ...,
        "The docId of the contradiction.  This is a string that contains the page " \
        "number and the text of the contradiction."
    ]
    sources: Annotated[
        List[str],
        ...,
        "List of sources used to answer the question in JSON format.  Ensure " \
        "that the page number is labeled 'pageNumber'.  If there are a range " \
        "of page numbers, create a separate list item for each page number."
    ]