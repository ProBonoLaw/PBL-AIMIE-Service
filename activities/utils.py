import logging
from typing import Any, Dict, Optional, Sequence
from pydantic import BaseModel
from langchain_core.documents import Document
from typing_extensions import List, Union

from AIInteractionService.db.azuresearch import AzureSearch
from AIInteractionService.generators.common.agent_result import AgentResult
from AIInteractionService.generators.common.law_retriever_provider import LawRetrieverProvider
from AIInteractionService.generators.common.types import AnswersWithSources, BaseRequestModel
from AIInteractionService.utils.accounts import PersonalInformation, aget_account_info
from AIInteractionService.utils.agent_facilitator import AgentFacilitator
from AIInteractionService.utils.common_types import Source
from AIInteractionService.utils.state import State, StateOpenAi
from .types import AnswerWithSourcesResult, BaseActivityRequest, BaseRequestInfo, SourceActivityResult

ResultType = Union[Source, SourceActivityResult, BaseModel, Dict]
AnswerType = Union[AnswersWithSources, State, StateOpenAi]

def normalize_answer(answer: str) -> str:
    return answer.replace('\\\\n', '\n').replace('\\\n', '\n').replace('\\n', '\n').replace('\\"', '"')

def normalize_source(source: ResultType) -> SourceActivityResult:
    if isinstance(source, SourceActivityResult):
        return source
    if isinstance(source, BaseModel):
        return SourceActivityResult.model_validate(source.model_dump())
    return SourceActivityResult(doc_id=source['doc_id'] if 'doc_id' in source else source['docId'], 
                                pages=source['pages'] if 'pages' in source and source['pages'] is not None else [])

def get_designated_client_info(personal_info: Optional[PersonalInformation]) -> str:
    if not personal_info:
        return ""

    first_name = (personal_info.first_name or "").strip()
    last_name = (personal_info.last_name or "").strip()

    if first_name or last_name:
        return f"{first_name} {last_name}".strip()

    return (personal_info.organization or "").strip()

async def aget_base_request_info(request: BaseActivityRequest) -> BaseRequestInfo:
    account_info = await aget_account_info(request.account_id)
    if not account_info:
        raise Exception("Account information not found")
    location = f"{account_info.county}, {account_info.state}" if not request.location else request.location
    opposition_info = account_info.opposition
    opposition = get_designated_client_info(opposition_info)
    opposition_role = opposition_info.filing_role if opposition_info else ""
    personal_info = account_info.person_information
    designated_client = get_designated_client_info(personal_info)
    designated_client_role = account_info.filing_role
    return BaseRequestInfo(
        account_id=request.account_id,
        session_id=request.session_id,
        max_doc_count=request.max_doc_count,
        location=location,
        opposition=opposition,
        opposition_role=opposition_role,
        designated_client=designated_client.strip(),
        designated_client_role=designated_client_role,
        account_info=account_info
    )


def normalize_sources(sources: Sequence[ResultType]) -> List[SourceActivityResult]:
    return [normalize_source(source) for source in sources]


async def execute_retriable_request_with_context(request: BaseRequestInfo, 
                          vector_store: Optional[AzureSearch], 
                          context: Optional[Sequence[Document]],
                          law_retriever_provider: Optional[LawRetrieverProvider], 
                          agent_facilitator: AgentFacilitator, 
                          qa_request: BaseRequestModel):
    backup_agent_count = await agent_facilitator.get_agent_variant_count()
    result: Optional[Union[AnswersWithSources, Dict]] = None
    last_exception: Optional[Exception] = None
    for i in range(0, backup_agent_count):
        try:
            primary_agent = await agent_facilitator.get_agent_variant_instance(
                i, 
                request.account_id, 
                request.session_id, 
                request.max_doc_count)
            result = await primary_agent.agenerate_response(qa_request, vector_store, law_retriever_provider, context=context)
            break
        except Exception as e:
            logging.warning(f"Error generating response: {e}")
            logging.info("Retrying with secondary model")
            last_exception = e
    
    if not result and last_exception:
        raise last_exception
            
    return result

async def execute_retriable_request(request: BaseRequestInfo, 
                          vector_store: Optional[AzureSearch], 
                          law_retriever_provider: Optional[LawRetrieverProvider], 
                          context: Optional[Sequence[Document]],
                          agent_facilitator: AgentFacilitator, 
                          qa_request: BaseRequestModel):
    return await execute_retriable_request_with_context(
        request, 
        vector_store, 
        context, 
        law_retriever_provider, 
        agent_facilitator, 
        qa_request
    )

def generate_standard_response(
    result: Optional[Union[AgentResult, Any]]) -> AnswerWithSourcesResult:
    if not result:
        raise Exception("Unable to generate a response from any agent")
    if "answer" not in result or "chat_history" not in result:
        raise Exception("Result is not an instance of AgentResult")
    return AnswerWithSourcesResult.model_validate(result)

