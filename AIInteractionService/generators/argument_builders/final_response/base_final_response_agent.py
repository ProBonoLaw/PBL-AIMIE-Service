
from typing import Any, Dict, List, Optional, TypeVar, Sequence
from pydantic import BaseModel

from langchain_core.documents import Document
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.language_models import LanguageModelInput
from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.retrievers import RetrieverLike, BaseRetriever, RetrieverOutputLike
from langchain_core.vectorstores import VectorStore

from .types import FinalResponseRequest
from ...common import BaseHistoryAwareAgent, AgentResult, AnswersWithSources
from ....utils.history_only_retriever import HistoryOnlyRetriever
from ....utils.state import State

U = TypeVar('U', bound=State)

class BaseFinalResponseAgent(BaseHistoryAwareAgent[FinalResponseRequest, AgentResult, U]):
    def __init__(self, 
                 account_id: str, 
                 session_id: str, 
                 max_doc_count: int,
                 **kwargs: Any):
        self.__max_doc_count = max_doc_count or 20
        super().__init__(account_id, session_id, **kwargs)

    @property
    def max_doc_count(self) -> int:
        return self.__max_doc_count
        

    def get_prompt(self) -> ChatPromptTemplate:
        instructions: List[MessageLikeRepresentation] = [
                {"role": self.system_role_name, "content": self.primary_prompt},
                {"role": self.system_role_name, "content": "Context:\n{context}"},
                {"role": self.system_role_name, "content": "If you have additional questions, use the following tool: case_context"},
                MessagesPlaceholder("chat_history"),
                ("assistant", "Who are you helping?"),
                ("human", "AIMIE_BOT's client is {aimies_client} who is the {aimies_filing_role} in this case.\n\n"),
                ("assistant", "Who is the opposing party?"),
                ("human",
                "BOB_BOT's represents the opposition, who is {opposition} and is in the role of {opposition_role}.\n\n"),
                ("assistant", "What is the original question?"),
                ("human", "{original_question}\n\n"),
                ("assistant", "What was AIMIE_BOT's answer?"),
                ("human", "{aimie_answer}\n\n"),
                ("assistant", "What was BOB_BOT's response?"),
                ("human", "{bob_response}\n\n")
            ]
        
        additional_instructions = self.additional_prompt()
        if additional_instructions:
            instructions.extend(additional_instructions)
        qa_prompt = ChatPromptTemplate(messages=instructions)

        return qa_prompt
    
    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return None
    
    def prepare_history_aware_chain(self, retriever: RetrieverOutputLike) -> RetrieverOutputLike:
        '''
        We are not using using chat history in this agent, so we return the retriever as is.
        '''
        return self.generate_input_retriever() | retriever

    def get_retriever(self, vector_store: Optional[VectorStore] = None, context: Optional[List[Document]] = None, law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
        primary_retriever: Optional[BaseRetriever] = None
        if vector_store is None:
            primary_retriever = HistoryOnlyRetriever(
                context=context if context is not None else [])
        else:
            primary_retriever = vector_store.as_retriever(
                search_type="semantic_hybrid",
                k=self.max_doc_count)
        if law_retriever is None:
            return primary_retriever
        return EnsembleRetriever(retrievers=[primary_retriever, law_retriever], weights=[0.7, 0.3])
    
    def generate_input_retriever(self):
        return (lambda input: 
                input['original_question'])


    @property
    def personae_name(self) -> str:
        return "AIMIE_FINAL_RESPONSE_AGENT"

    def get_request_chat_message(self, state: State, parsed_response: Dict[str, Any]) -> str:
        return "Generate a final decision between AIMIE's original answer and rebuttal to BOB_BOT's response."

    @property
    def system_role_name(self) -> str:
        return "system"
    
    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return self.llm.with_structured_output(AnswersWithSources, include_raw=True)
    
    def prepare_output(self, output: Any) -> AgentResult:
        return AgentResult(
            answer=output["answer"],
            sources=output["sources"],
            chat_history=output["chat_history"],
            context=output["context"]
        )