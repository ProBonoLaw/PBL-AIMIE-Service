
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, TypeVar
from pydantic import BaseModel

from langchain_core.documents import Document
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.runnables import Runnable
from langchain_core.language_models import LanguageModelInput
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike
from langchain_core.vectorstores import VectorStore
from langchain_core.prompts.chat import MessageLikeRepresentation

from ..closing import limit_tokens_used
from .types import FinalDecisionRequest
from ...common import FormalAnswersWithSources, BaseHistoryAwareAgent, AgentResult
from ....utils.history_only_retriever import HistoryOnlyRetriever
from ....utils.state import State

U = TypeVar('U', bound=State)


class BaseFinalDecisionAgent(BaseHistoryAwareAgent[FinalDecisionRequest, AgentResult, U]):
    def __init__(self,
                 account_id: str,
                 session_id: str,
                 max_doc_count: int,
                 **kwargs: Any):
        self.__max_doc_count = max_doc_count
        super().__init__(account_id, session_id, **kwargs)

    @property
    def max_doc_count(self) -> int:
        return self.__max_doc_count

    def get_prompt(self) -> ChatPromptTemplate:
        instructions: List[MessageLikeRepresentation] = [
            {"role": self.system_role_name, "content": self.primary_prompt},
            {"role": self.system_role_name, "content": "Context:\n{context}"},
            MessagesPlaceholder("chat_history"),
            {"role": self.system_role_name, "content": "Context:\n{context}"},
            ("assistant", "What is the original question?"),
            ("human", "{original_question}\n\n"),
            ("assistant", "What was AIMIE_BOT's answer?"),
            ("human", "{aimie_answer}\n\n"),
            ("assistant", "What was BOB_BOT's response?"),
            ("human", "{bob_response}\n\n"),
            ("assistant", "What was AIMIE_BOT's rebuttal?"),
            ("human", "{aimie_rebuttal}\n\n"),
            ("assistant", "Who am I writing this declaration against?"),
            ("user",
             "You are writing this declaration against {opposition} (BOB_BOT client), who is the {opposition_role}."),
            ("assistant", "Who am I writing this declaration for?"),
            ("user",
             "You are writing this declaration advocating {designated_client} (AIMIT_BOT client), who is the {designated_client_role}.")
        ]

        additional_instructions = self.additional_prompt()
        if additional_instructions:
            instructions.extend(additional_instructions)
        qa_prompt = ChatPromptTemplate(messages=instructions)

        return qa_prompt

    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return None

    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return self.llm.with_structured_output(FormalAnswersWithSources, include_raw=True)

    def prepare_history_aware_chain(self, retriever: RetrieverOutputLike) -> RetrieverOutputLike:
        '''
        We are not using using chat history in this agent, so we return the retriever as is.
        '''
        return self.generate_input_retriever() | retriever

    def get_retriever(self,
                      vector_store: Optional[VectorStore] = None,
                      context: Optional[List[Document]] = None,
                      law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
        if not context and vector_store:
            return vector_store.as_retriever(
                search_type="semantic_hybrid",
                k=self.max_doc_count)
        return HistoryOnlyRetriever(
            context=limit_tokens_used(context if context else [], 60000))

    def generate_input_retriever(self):
        return (lambda input:
                input['original_question'])

    def prepare_output(self, output: Any) -> AgentResult:
        return AgentResult(
            answer=output["answer"],
            sources=output["sources"],
            chat_history=output["chat_history"],
            context=output["context"]
        )

    @property
    def personae_name(self) -> str:
        return "AIMIE_Decision_Writer"

    def get_request_chat_message(self, state: State, parsed_response: Dict[str, Any]) -> str:
        return "Generate a final decision between AIMIE's original answer and rebuttal to BOB_BOT's response."

    @property
    def system_role_name(self) -> str:
        return "system"

