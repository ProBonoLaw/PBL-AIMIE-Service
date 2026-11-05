import logging
from typing import Any, Dict, Tuple, TypeAlias, List
from typing_extensions import Optional
from pydantic import AliasChoices, BaseModel, Field

from langchain_core.messages import BaseMessage

from activities.types import FactValidatorActivityResults, LibrarianActivityResult, SourceActivityResult


class BaseRequest(BaseModel):
    session_id: Optional[str] = Field(
        default_factory= lambda: None,
        serialization_alias='sessionId',
        validation_alias=AliasChoices('session_id', 'sessionId', 'SessionId'))
    account_id: str = Field(
        ...,
        serialization_alias='accountId',
        validation_alias=AliasChoices('account_id', 'accountId', 'AccountId'))
    location: Optional[str] = Field(
        default_factory=lambda: None,
        serialization_alias='location',
        validation_alias=AliasChoices('location')
    )
    hearing_type: Optional[str] = Field(
        default_factory=lambda: None,
        serialization_alias='hearingType',
        validation_alias=AliasChoices('hearing_type', 'hearingType', 'HearingType'))
    target: Optional[str] = Field(
        default_factory=lambda: None,
        serialization_alias='target',
        validation_alias=AliasChoices('target')
    )
    max_doc_count: Optional[int] = Field(
        default_factory=lambda: None,
        serialization_alias='maxDocCount',
        validation_alias=AliasChoices('max_doc_count', 'maxDocCount', 'MaxDocCount'))
    
    @classmethod
    def from_json(cls, json_string: str):
        logging.debug(f"Deserializing: {json_string}")
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        logging.debug(f"Serializing: {self}")
        return self.model_dump_json()


class QuestionRequest(BaseRequest):
    question: str = Field(
        ...,
        serialization_alias='question',
        validation_alias=AliasChoices('question')
    )
    provide_thorough_response: Optional[bool] = Field(
        default_factory=lambda: False,
        serialization_alias='provideThoroughResponse',
        validation_alias=AliasChoices('provide_thorough_response', 'provideThoroughResponse', 'ProvideThoroughResponse')
    )
    use_secondary_model: Optional[bool] = Field(
        default_factory=lambda: False,
        serialization_alias='useSecondaryModel',
        validation_alias=AliasChoices('use_secondary_model', 'useSecondaryModel', 'UseSecondaryModel')
    )


class DeclarationRequest(BaseRequest):
    declaration_request: str = Field(
        ..., 
        serialization_alias='declarationRequest',
        validation_alias=AliasChoices('declaration_request', 'declarationRequest', 'DeclarationRequest', 'input')                            
    )

class DiscoveryOrchestrationRequest(BaseRequest):
    topics: List[str] = Field(
        default_factory=lambda: [],
        serialization_alias='topics',
        validation_alias=AliasChoices('topics')
    )
    input: Optional[str] = Field(
        default_factory=lambda: None,
        serialization_alias='input',
        validation_alias=AliasChoices('input', 'question')
    )

class RhetoricBuilderOrchestrationRequest(BaseRequest):
    statement: str = Field(
        ...,
        serialization_alias='statement',
        validation_alias=AliasChoices('statement'))


Progress_Status: TypeAlias = Tuple[int, int]

class AnswerWithSourcesOnly(BaseModel):
    answer: str = Field(
        ...,
        serialization_alias='answer',
        validation_alias=AliasChoices('answer'))
    applicable_sources: List[SourceActivityResult] = Field(
        serialization_alias='applicableSources',
        validation_alias=AliasChoices('applicable_sources', 'applicableSources', 'ApplicableSources'))
    

class SimplifiedDocument(BaseModel):
    doc_id: str = Field(
        ...,
        serialization_alias='docId',
        validation_alias=AliasChoices('doc_id', 'docId', 'DocId')
    )
    title: Optional[str]
    source_url: str = Field(
        ...,
        serialization_alias='sourceUrl',
        validation_alias=AliasChoices('source_url', 'sourceUrl', 'SourceUrl')
    )
    headers: List[str] = Field(
        default_factory=lambda: [],
        serialization_alias='headers',
        validation_alias=AliasChoices('headers')
    )
    pages: List[int] = Field(
        default_factory=lambda: [],
        serialization_alias='pages',
        validation_alias=AliasChoices('pages')
    )
    position: Optional[int]
    source_id: str = Field(
        serialization_alias='sourceId',
        validation_alias=AliasChoices('source_id', 'sourceId', 'SourceId')
    )
    page_content : str = Field(
        serialization_alias='pageContent',
        validation_alias=AliasChoices('page_content', 'pageContent', 'PageContent')
    )
    tags: List[str] = Field(
        default_factory=lambda: [],
        serialization_alias='tags',
        validation_alias=AliasChoices('tags', 'Tags')
    )
    where: Optional[str] = Field(
        default=None,
        serialization_alias='where',
        validation_alias=AliasChoices('where', 'Where')
    )
    what: Optional[str] = Field(
        default=None,
        serialization_alias='what',
        validation_alias=AliasChoices('what', 'What')
    )
    who: List[str] = Field(
        default_factory=lambda: [],
        serialization_alias='who',
        validation_alias=AliasChoices('who', 'Who')
    )
    why: Optional[str] = Field(
        default=None,
        serialization_alias='why',
        validation_alias=AliasChoices('why', 'Why')
    )
    when_started: Optional[Dict[str, Any]] = Field(
        default=None,
        serialization_alias='whenStarted',
        validation_alias=AliasChoices('when_started', 'whenStarted', 'WhenStarted')
    )
    when_ended: Optional[Dict[str, Any]] = Field(
        default=None,
        serialization_alias='whenEnded',
        validation_alias=AliasChoices('when_ended', 'whenEnded', 'WhenEnded')
    )

class ValidationStatus(BaseModel):
    claim: str = Field(
        ...,
        serialization_alias='claim',
        validation_alias=AliasChoices('claim'))
    explanation: str = Field(
        ...,
        serialization_alias='explanation',
        validation_alias=AliasChoices('explanation'))
    is_valid: bool = Field(
        ...,
        serialization_alias='isValid',
        validation_alias=AliasChoices('is_valid', 'isValid'))
    is_contradictory: bool = Field(
        ...,
        serialization_alias='isContradictory',
        validation_alias=AliasChoices('is_contradictory', 'isContradictory'))
    is_inferred: bool = Field(
        ...,
        description="Set the value to True if the statement is inferred from the context.  " \
        "False if the statement is not inferred.",
        serialization_alias="isInferred",
        validation_alias=AliasChoices('isInferred', 'is_inferred', 'IsInferred')
        )
    is_reasonably_inferred: bool = Field(
        ...,
        description="Set the value to True if the statement is reasonably inferred from the context.  " \
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
        "False if the statement is not a summary or conclusion.",
        serialization_alias="isSummaryOrConclusion",
        validation_alias=AliasChoices('isSummaryOrConclusion', 'is_summary_or_conclusion', 'IsSummaryOrConclusion')
        )
    is_implied: bool = Field(
        default=False,
        description="Set the value to True if the statement is implied by the context.  " \
        "False if the statement is not implied.",
        serialization_alias="isImplied",
        validation_alias=AliasChoices('isImplied', 'is_implied', 'IsImplied')
        )
    is_vague: bool = Field(
        default=False,
        description="Set the value to True if the statement is vague.  " \
        "False if the statement is not vague.",
        serialization_alias="isVague",
        validation_alias=AliasChoices('isVague', 'is_vague', 'IsVague')
        )
    contradiction_statement: str = Field(
        default_factory=lambda: '',
        serialization_alias='contradictionStatement',
        validation_alias=AliasChoices('contradiction_statement', 'contradictionStatement', 'ContradictionStatement'))
    contradiction_sources: List[str] = Field(
        default_factory=lambda: [],
        serialization_alias='contradictionSources',
        validation_alias=AliasChoices('contradiction_sources', 'contradictionSources', 'ContradictionSources'))
    sources: List[SourceActivityResult] = Field(
        default_factory=lambda: [],
        serialization_alias='sources',
        validation_alias=AliasChoices('sources'),
        description="List of sources")
    
class QAResult(BaseModel):
    answer: str
    chat_history: List[BaseMessage] = Field(
        ...,
        serialization_alias="chatHistory",
        validation_alias=AliasChoices('chatHistory', 'chat_history'),
        description="List of chat messages")
    sources: List[SourceActivityResult] = Field(
        default_factory=lambda: [],
        serialization_alias="sources",
        validation_alias=AliasChoices('sources'),
        description="List of sources")
    context: List[SimplifiedDocument]
    validation_status: List[ValidationStatus] = Field(
        default_factory=lambda: [],
        serialization_alias="validationStatus",
        validation_alias=AliasChoices('validation_status'),
        description="List of Validation Status items.")
    
class ArgumentBuilderResult(BaseModel):
    initial_argument: str = Field(
        ...,
        serialization_alias='initialArgument',
        validation_alias=AliasChoices('initial_argument', 'initialArgument', 'InitialArgument'))
    counter_argument: str = Field(
        ...,
        serialization_alias='counterArgument',
        validation_alias=AliasChoices('counter_argument', 'counterArgument', 'CounterArgument'))
    final_argument: str = Field(
        ...,
        serialization_alias='finalArgument',
        validation_alias=AliasChoices('final_argument', 'finalArgument', 'FinalArgument'))
    sources: List[SourceActivityResult] = Field(
        default_factory=lambda: [],
        serialization_alias='sources',
        validation_alias=AliasChoices('sources'),
        description="List of sources")
    context: List[SimplifiedDocument]
    validation_status: List[ValidationStatus] = Field(
        default_factory=lambda: [],
        serialization_alias="validationStatus",
        validation_alias=AliasChoices('validation_status', 'validationStatus', 'ValidationStatus'),
        description="List of Validation Status items.")
    

class DeclarationWriterResult(BaseModel):
    session_id: str = Field(
        ...,
        serialization_alias='sessionId',
        validation_alias=AliasChoices('session_id', 'sessionId', 'SessionId'))
    account_id: str = Field(
        ...,
        serialization_alias='accountId',
        validation_alias=AliasChoices('account_id', 'accountId', 'AccountId'))
    initial_inquiry: AnswerWithSourcesOnly = Field(
        ...,
        serialization_alias='initialInquiry',
        validation_alias=AliasChoices('initial_inquiry', 'initialInquiry', 'InitialInquiry'))
    cross_examination: AnswerWithSourcesOnly = Field(
        ...,
        serialization_alias='crossExamination',
        validation_alias=AliasChoices('cross_examination', 'crossExamination', 'CrossExamination'))
    closing_statement: AnswerWithSourcesOnly = Field(
        ...,
        serialization_alias='closingStatement',
        validation_alias=AliasChoices('closing_statement', 'closingStatement', 'ClosingStatement'))
    decision_statement: AnswerWithSourcesOnly = Field(
        ...,
        serialization_alias='decisionStatement',
        validation_alias=AliasChoices('decision_statement', 'decisionStatement', 'DecisionStatement'))
    rhetorical_statement: AnswerWithSourcesOnly = Field(
        ...,
        serialization_alias='rhetoricalStatement',
        validation_alias=AliasChoices('rhetorical_statement', 'rhetoricalStatement', 'RhetoricalStatement'))
    final_declaration: str = Field(
        ...,
        serialization_alias='finalDeclaration',
        validation_alias=AliasChoices('final_declaration', 'finalDeclaration', 'FinalDeclaration'))
    exhibits: LibrarianActivityResult = Field(
        ...,
        serialization_alias='exhibits',
        validation_alias='exhibits')
    context: List[SimplifiedDocument] = Field(
        ...,
        serialization_alias='context',
        validation_alias='context')
    sources: List[SourceActivityResult] = Field(
        ...,
        serialization_alias='sources',
        validation_alias=AliasChoices('sources'))
    
class StatementValidationRevisionOrchestrationRequest(BaseRequest):
    statement: str = Field(
        ...,
        serialization_alias='statement',
        validation_alias=AliasChoices('statement'))
    original_input_statement: str = Field(
        ...,
        serialization_alias='originalInputStatement',
        validation_alias=AliasChoices('original_input_statement', 'originalInputStatement', 'OriginalInputStatement'))
    is_last_paragraph: bool = Field(
        default=False,
        serialization_alias='isLastParagraph',
        validation_alias=AliasChoices('is_last_paragraph', 'isLastParagraph', 'IsLastParagraph'),
        description="Set to True if the input is the last paragraph of the document.  " \
        "This is used to determine if the input is the last paragraph of the document.")
    original_request: Optional[str] = Field(
        default_factory=lambda: None,
        serialization_alias='originalRequest',
        validation_alias=AliasChoices('original_request', 'originalRequest', 'OriginalRequest'),
        description="The original request that was used to generate the input.  " \
        "This is used to provide context for the input.")
    
    @classmethod
    def from_json(cls, json_string: str):
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        return self.model_dump_json()

class StatementValidationRevisionOrchestrationResult(BaseModel):
    original_input_statement: str = Field(
        ...,
        serialization_alias='originalInputStatement',
        validation_alias=AliasChoices('original_input_statement', 'originalInputStatement', 'OriginalInputStatement'))
    revised_statement: Optional[str] = Field(
        default_factory=lambda: None,
        serialization_alias='revisedStatement',
        validation_alias=AliasChoices('revised_statement', 'revisedStatement', 'RevisedStatement'))
    was_revised: bool = Field(
        default_factory=lambda: False,
        serialization_alias='wasRevised',
        validation_alias=AliasChoices('was_revised', 'wasRevised', 'WasRevised'))
    validation_status: FactValidatorActivityResults = Field(
        ...,
        serialization_alias='validationStatus',
        validation_alias=AliasChoices('validation_status'),
        description="List of Validation Status items.")
    
    @classmethod
    def from_json(cls, json_string: str):
        request = cls.model_validate_json(json_string)
        return request

    def to_json(self) -> str:
        return self.model_dump_json()
    
class RhetoricOrchestrationResult(BaseModel):
    answer: str
    sources: List[SourceActivityResult] = Field(
        default_factory=lambda: [],
        serialization_alias="sources",
        validation_alias=AliasChoices('sources'),
        description="List of sources")
    context: List[SimplifiedDocument]
    
statement_revisor_orchestrator_name = "StatementValidationRevisionOrchestration"
rhetoric_builder_orchestrator_name = "RhetoricBuilderOrchestration"
class TimelineRequest(BaseRequest):
    input: str = Field(..., validation_alias=AliasChoices('input', 'question', 'timelineRequest'))

class TimelineOrchestrationResult(BaseModel):
    session_id: str = Field(serialization_alias='sessionId', validation_alias=AliasChoices('session_id', 'sessionId'))
    account_id: str = Field(serialization_alias='accountId', validation_alias=AliasChoices('account_id', 'accountId'))
    original_request: str = Field(serialization_alias='originalRequest', validation_alias=AliasChoices('original_request', 'originalRequest'))
    time_range: Dict = Field(default_factory=dict, serialization_alias='timeRange', validation_alias=AliasChoices('time_range', 'timeRange'))
    summary: str
    entries: List[Dict] = Field(default_factory=list)
    time_to_completion_seconds: Optional[float] = Field(default=None, serialization_alias='timeToCompletionSeconds', validation_alias=AliasChoices('time_to_completion_seconds', 'timeToCompletionSeconds'))
