import logging
from typing_extensions import List, Optional, Dict
from pydantic import AliasChoices, BaseModel, Field, RootModel

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage

from AIInteractionService.utils.accounts import AccountInfo


class BaseRequestInfo(BaseModel):
    account_id: str
    session_id: str
    location: str
    max_doc_count: int
    opposition: str
    opposition_role: str
    designated_client: str
    designated_client_role: str
    account_info: AccountInfo


class BaseActivityRequest(BaseModel):
    account_id: str
    session_id: str
    location: str
    hearing_type: Optional[str]
    max_doc_count: int
    input: str
    use_secondary_model: bool = False

    @classmethod
    def from_json(cls, json_string: str):
        logging.debug(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.debug(f"Serializing: {self}")
        return self.model_dump_json()


class FactValidatorActivityRequest(BaseActivityRequest):
    raw_input: str
    is_last_paragraph: bool = Field(
        default_factory=lambda: False,
        serialization_alias="isLastParagraph",
        validation_alias=AliasChoices(
            "is_last_paragraph", "isLastParagraph", "IsLastParagraph"),
        description="Flag to indicate if the input is the last paragraph of the document"
    )
    original_request: Optional[str] = Field(
        default=None,
        serialization_alias="originalRequest",
        validation_alias=AliasChoices(
            "original_request", "originalRequest", "OriginalRequest"),
        description="The original request that was used to generate the input.  This is used to provide context for the input."
    )


class RevisionActivityRequest(BaseActivityRequest):
    statement: str
    feedback: str
    use_retrievers: bool = Field(
        default_factory=lambda: True,
        serialization_alias="useRetrievers",
        validation_alias=AliasChoices(
            "use_retrievers", "useRetrievers", "UseRetrievers"),
        description="Flag to indicate if retrievers should be used to provide context for the revision"
    )


class DiscoveryActivityRequest(BaseActivityRequest):
    topics: Optional[List[str]]
    target: Optional[str]
    input: str


class SourceActivityResult(BaseModel):
    doc_id: str = Field(
        ...,
        serialization_alias="docId",
        validation_alias=AliasChoices('docId', 'doc_id', 'DocId'),
        description="Mandatory field, the ID of the document")
    pages: Optional[List[int]] = Field(
        default_factory=lambda: [],
        serialization_alias="pages",
        validation_alias=AliasChoices('pages', 'Pages'),
        description="List of pages, if known and could be extracted from the document")

    @classmethod
    def from_json(cls, json_string: str):
        logging.debug(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.debug(f"Serializing: {self}")
        return self.model_dump_json()


class AnswerWithSourcesResult(BaseModel):
    answer: str
    chat_history: List[BaseMessage] = Field(
        ...,
        serialization_alias="chatHistory",
        validation_alias=AliasChoices(
            'chatHistory', 'chat_history', 'ChatHistory'),
        description="List of chat messages")
    sources: List[SourceActivityResult] = Field(
        default_factory=lambda: [],
        serialization_alias="sources",
        validation_alias=AliasChoices('sources', 'Sources'),
        description="List of sources")
    context: List[Document] = Field(
        default_factory=lambda: [],
        serialization_alias="context",
        validation_alias=AliasChoices('context', 'Context'),
        description="List of context documents"
    )

    @classmethod
    def from_json(cls, json_string: str):
        logging.debug(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.debug(f"Serializing: {self}")
        return self.model_dump_json(by_alias=True)


class QARequest(BaseActivityRequest):
    target: Optional[str]


class BobActivityRequest(BaseActivityRequest):
    aimie_answer: str


class QaCrossExaminationRequest (BobActivityRequest):
    target: Optional[str]


class AimieRebuttalActivityRequest(BobActivityRequest):
    bob_response: str


class QaFinalResponseActivityRequest(AimieRebuttalActivityRequest):
    target: Optional[str]


class DecisionActivityRequest(AimieRebuttalActivityRequest):
    aimie_rebuttal: str


class RhetoricActivityRequest(BaseActivityRequest):
    pass


class RhetoricActivityResult(AnswerWithSourcesResult):
    original_section: str = Field(
        ...,
        serialization_alias="originalSection",
        validation_alias=AliasChoices(
            "original_section", "originalSection", "OriginalSection"),
        description="The original section of the document that was used to generate the answer"
    )


class DeclarationRequest(BaseActivityRequest):
    rhetorical_response: str
    context: List[Document]
    source_ids: List[str]


class DeclarationActivityResult(BaseModel):
    answer: str
    has_error: Optional[bool] = Field(
        default_factory=lambda: False,
        serialization_alias="hasError",
        validation_alias=AliasChoices("has_error", "hasError", "HasError"),
        description="Flag to indicate if there was an error")
    sources: List[SourceActivityResult]

    @classmethod
    def from_json(cls, json_string: str):
        logging.debug(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.debug(f"Serializing: {self}")
        return self.model_dump_json()


class LibrarianRequest(BaseActivityRequest):
    declaration: str
    context: List[Document]


class LibrarianElement(BaseModel):
    exactQuote: str = Field(...,
                            serialization_alias="exactQuote",
                            validation_alias=AliasChoices(
                                "exact_quote", "exactQuote", "ExactQuote"),
                            description="The exact quote from the document.")
    doc_id: str = Field(...,
                        serialization_alias="docId",
                        validation_alias=AliasChoices(
                            "doc_id", "docId", "DocId"),
                        description='The identifier of the document from which the quote originates.')
    document_with_highlighted_quote: str = Field(
        ...,
        serialization_alias="documentWithHighlightedQuote",
        validation_alias=AliasChoices("document_with_highlighted_quote",
                                      "documentWithHighlightedQuote", "DocumentWithHighlightedQuote"),
        description=('The original document, in its entirety and in converted to markdown format, with the quote '
                     'highlighted in yellow via the <mark></mark> element .')
    )

    @classmethod
    def from_json(cls, json_string: str):
        logging.debug(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.debug(f"Serializing: {self}")
        return self.model_dump_json()


class LibrarianAnswer(BaseModel):
    quotes: List[LibrarianElement]
    hasError: Optional[bool] = Field(
        default_factory=lambda: False,
        serialization_alias="hasError",
        validation_alias=AliasChoices("has_error", "hasError", "HasError"),
        description="Flag to indicate if there was an error")

    @classmethod
    def from_json(cls, json_string: str):
        logging.debug(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.debug(f"Serializing: {self}")
        return self.model_dump_json()


class LibrarianSectionResult(RootModel):
    root: Dict[str, LibrarianAnswer]

    def __getitem__(self, key: str):
        return self.root[key]

    def __setitem__(self, key: str, value: LibrarianAnswer):
        self.root[key] = value

    @classmethod
    def from_json(cls, json_string: str):
        logging.debug(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.info(f"Serializing: {self}")
        return self.model_dump_json()


class LibrarianActivityResult(RootModel):
    root: Dict[str, LibrarianSectionResult]

    def __getitem__(self, key: str):
        return self.root[key]

    def __setitem__(self, key: str, value: LibrarianSectionResult):
        self.root[key] = value

    @classmethod
    def from_json(cls, json_string: str):
        logging.debug(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.debug(f"Serializing: {self}")
        return self.model_dump_json()


class TopicQuestions(BaseModel):
    topic: str
    questions: List[str]
    sources: Optional[List[SourceActivityResult]]

    @classmethod
    def from_json(cls, json_string: str):
        logging.debug(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.debug(f"Serializing: {self}")
        return self.model_dump_json()


class DiscoveryActivityResults(BaseModel):
    discovery_order: str = Field(
        ...,
        serialization_alias="discoveryOrder",
        validation_alias=AliasChoices(
            "discovery_order", "discoveryOrder", "DiscoveryOrder"),
        description="The order of the discovery"
    )
    questions_by_topic: List[TopicQuestions] = Field(
        default_factory=lambda: [],
        serialization_alias="questionsByTopic",
        validation_alias=AliasChoices(
            "questions_by_topic", "questionsByTopic", "QuestionsByTopic"),
        description="List of questions by topic"
    )
    has_error: Optional[bool] = Field(
        default_factory=lambda: False,
        serialization_alias="hasError",
        validation_alias=AliasChoices("has_error", "hasError", "HasError"),
        description="Flag to indicate if there was an error"
    )

    @classmethod
    def from_json(cls, json_string: str):
        logging.info(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.info(f"Serializing: {self}")
        return self.model_dump_json()


class FactValidatorActivityResults(BaseModel):
    original_statement: str = Field(
        ...,
        serialization_alias="originalStatement",
        validation_alias=AliasChoices(
            "original_statement", "originalStatement", "OriginalStatement"),
        description="The original statement to be validated"
    )
    raw_original_statement: str = Field(
        ...,
        serialization_alias="rawOriginalStatement",
        validation_alias=AliasChoices(
            "raw_original_statement", "rawOriginalStatement", "RawOriginalStatement"),
        description="The original statement to be validated"
    )
    is_valid: bool = Field(
        ...,
        serialization_alias="isValid",
        validation_alias=AliasChoices("is_valid", "isValid", "IsValid"),
        description="Flag to indicate if the answer is valid"
    )
    is_contradictory: bool = Field(
        ...,
        serialization_alias="isContradictory",
        validation_alias=AliasChoices(
            "is_contradictory", "isContradictory", "IsContradictory"),
        description="Flag to indicate if the answer is contradictory"
    )
    is_inferred: bool = Field(
        ...,
        description="Set the value to True if the statement is inferred from the context.  "
        "False if the statement is not inferred.",
        serialization_alias="isInferred",
        validation_alias=AliasChoices(
            'isInferred', 'is_inferred', 'IsInferred')
    )
    is_reasonably_inferred: bool = Field(
        ...,
        description="Set the value to True if the statement is reasonably inferred from the context.  "
        "False if the statement is not reasonably inferred.",
        serialization_alias="isReasonablyInferred",
        validation_alias=AliasChoices(
            'isReasonablyInferred', 'is_reasonably_inferred', 'IsReasonablyInferred')
    )
    is_not_found_in_context: bool = Field(
        ...,
        description="Set the value to True if the statement is not found in the context.  "
        "False if the statement is found in the context.",
        serialization_alias="isNotFoundInContext",
        validation_alias=AliasChoices(
            'isNotFoundInContext', 'is_not_found_in_context', 'IsNotFoundInContext')
    )
    is_summary_or_conclusion: bool = Field(
        ...,
        serialization_alias="isSummaryOrConclusion",
        validation_alias=AliasChoices(
            "is_summary_or_conclusion", "isSummaryOrConclusion", "IsSummaryOrConclusion"),
        description="Set the value to True if the statement is a summary or conclusion.  "
        "False if the statement is not a summary or conclusion."
    )
    is_implied: bool = Field(
        False,
        serialization_alias="isImplied",
        validation_alias=AliasChoices("is_implied", "isImplied", "IsImplied"),
        description="Set the value to True if the statement is implied by the context.  "
        "False if the statement is not implied."
    )
    is_vague: bool = Field(
        False,
        serialization_alias="isVague",
        validation_alias=AliasChoices("is_vague", "isVague", "IsVague"),
        description="Set the value to True if the statement is vague.  "
        "False if the statement is not vague."
    )
    contradiction_statement: str = Field(
        ...,
        serialization_alias="contradictionStatement",
        validation_alias=AliasChoices(
            "contradiction_statement", "contradictionStatement", "ContradictionStatement"),
        description="The contraction statement"
    )
    contradiction_source: str = Field(
        ...,
        serialization_alias="contradictionSource",
        validation_alias=AliasChoices(
            "contradiction_source", "contradictionSource", "ContradictionSource"),
        description="The contraction source"
    )
    answer: str
    sources: List[SourceActivityResult] = Field(
        default_factory=lambda: [],
        serialization_alias="sources",
        validation_alias=AliasChoices('sources', 'Sources'),
        description="List of sources"
    )
    context: List[Document] = Field(
        default_factory=lambda: [],
        serialization_alias="context",
        validation_alias=AliasChoices('context', 'Context'),
        description="List of context documents"
    )

    @classmethod
    def from_json(cls, json_string: str):
        logging.info(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.info(f"Serializing: {self}")
        return self.model_dump_json()


argument_builders_initial_activity_name = "argumentBuildersInitialActivity"
argument_builders_cross_examination_activity_name = "argumentBuildersCrossExaminationActivity"
argument_builders_final_response_activity_name = "argumentBuildersFinalResponseActivity"
fact_validator_activity_name = "factValidatorActivity"
revision_activity_name = "revisionActivity"
rhetoric_activity_name = "rhetoricActivity"

class TimelineActivityResult(BaseModel):
    session_id: str = Field(serialization_alias='sessionId', validation_alias=AliasChoices('session_id', 'sessionId'))
    account_id: str = Field(serialization_alias='accountId', validation_alias=AliasChoices('account_id', 'accountId'))
    original_request: str = Field(serialization_alias='originalRequest', validation_alias=AliasChoices('original_request', 'originalRequest'))
    time_range: Dict = Field(default_factory=dict, serialization_alias='timeRange', validation_alias=AliasChoices('time_range', 'timeRange'))
    summary: str
    entries: List[Dict] = Field(default_factory=list)
    time_to_completion_seconds: Optional[float] = Field(default=None, serialization_alias='timeToCompletionSeconds', validation_alias=AliasChoices('time_to_completion_seconds', 'timeToCompletionSeconds'))
