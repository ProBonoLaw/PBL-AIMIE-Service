from datetime import datetime
from typing import TypeVar
from typing_extensions import Any, Dict, List, Optional, Sequence

from langchain_core.prompts.chat import MessageLikeRepresentation, MessagesPlaceholder
from langchain_core.documents import Document
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.language_models import LanguageModelInput, BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import RetrieverLike, BaseRetriever, RetrieverOutputLike
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.vectorstores import VectorStore
from pydantic import BaseModel

from .types import CrossExaminationRequest
from ...common import AgentResult, BaseHistoryAwareAgent, answers_with_sources_json_schema, AnswersWithSources
from ....utils.history_only_retriever import HistoryOnlyRetriever
from ....utils.state import State

U = TypeVar('U', bound=State)


class BaseCrossExaminationAgent(
        BaseHistoryAwareAgent[CrossExaminationRequest, AgentResult, U]):
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
            ("assistant", "Who am I defending?"),
            ("human",
             "You are to advocate for {opposition}, in the role of {opposition_role}, and their interests."),
            ("assistant", "What is the opposition's position?"),
            ("human",
                "The opposition is {aimies_client} and is in the role of {aimies_filing_role}."),
            ("assistant", "What was the original request sent to AIMIE_BOT?"),
            ("user",
             "The original request is: \n{original_question}\n-------\\n"),
            ("assistant", "What was AIMIE_BOT's answer?"),
            ("user",
             "Refute AIMIE_BOT's response, as you are the representative of the opposition of AIMIE's client:\n {aimie_answer}")
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

    def get_retriever(self,
                      vector_store: Optional[VectorStore] = None,
                      context: Optional[List[Document]] = None,
                      law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
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
        return EnsembleRetriever(retrievers=[primary_retriever, law_retriever], weights=[0.5, 0.5])

    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return self.llm.with_structured_output(AnswersWithSources, include_raw=True)

    def generate_input_retriever(self) -> RunnableLambda[State, str]:
        return RunnableLambda[State, str](lambda input: ("Find the opposite of the following: " 
                                                         + input.get('original_question', '')
                                                         + '\n\n'
                                                         + input.get("aimie_answer", '')))

    def get_request_chat_message(self, state: State, parsed_response: Dict[str, Any]) -> str:
        return "Refute AIMIE_BOT's response, as you are the representative of the opposition of AIMIE's client."

    def prepare_output(self, output: Any) -> AgentResult:
        return AgentResult(
            answer=output["answer"],
            sources=output["sources"],
            chat_history=output["chat_history"],
            context=output["context"]
        )

    @property
    def personae_name(self) -> str:
        return "BOB"
    
    @property
    def system_role_name(self) -> str:
        return "system"
