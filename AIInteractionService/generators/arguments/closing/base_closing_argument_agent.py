
from datetime import datetime
from typing import Sequence, TypeVar, cast
from typing_extensions import Any, Dict, List, Optional
from pydantic import BaseModel

from langchain_core.documents import Document
from langchain_core.language_models import LanguageModelInput
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.retrievers import RetrieverLike, BaseRetriever
from langchain_core.runnables import RunnableLambda, Runnable
from langchain_core.vectorstores import VectorStore

from .types import ClosingArgumentRequest, limit_tokens_used
from ...common import BaseHistoryAwareAgent, AnswersWithSources, AgentResult
from ....utils.history_only_retriever import HistoryOnlyRetriever
from ....utils.state import State

U = TypeVar('U', bound=State)


class BaseClosingArgumentAgent(BaseHistoryAwareAgent[ClosingArgumentRequest, AgentResult, U]):
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
            ("assistant", "What was the original question?"),
            ("user", "The original request: {original_question} \n\n"),
            ("assistant", "What was AIMIE_BOT's answer?"),
            ("user", "You're original argument: {aimie_answer} \n\n"),
            ("assistant", "Who am I writing this against?"),
            ("user",
             "You are writing this against {opposition}; who is the {opposition_role}."),
            ("assistant", "Who am I representing?"),
            ("user",
             "You are representing {designated_client}; who is the {designated_client_role}."),
            ("assistant", "What was BOB_BOT response?"),
            ("user",
             "BOB_BOT's argument, which is refuting your original response: {bob_response}\n\n")
        ]

        additional_instructions = self.additional_prompt()
        if additional_instructions:
            instructions.extend(additional_instructions)
        qa_prompt = ChatPromptTemplate(messages=instructions)

        return qa_prompt

    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return None

    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return self.llm.with_structured_output(AnswersWithSources, include_raw=True)

    def get_retriever(self,
                      vector_store: Optional[VectorStore] = None,
                      context: Optional[List[Document]] = None,
                      law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
        primary_retriever: Optional[BaseRetriever] = None
        if not context and vector_store:
            primary_retriever = vector_store.as_retriever(
                search_type="semantic_hybrid",
                k=self.max_doc_count)
        else:
            primary_retriever = HistoryOnlyRetriever(
                context=limit_tokens_used(context if context else [], 60000))

        if law_retriever is None:
            return primary_retriever
        return EnsembleRetriever(retrievers=[primary_retriever, law_retriever], weights=[0.5, 0.5])

    def generate_input_retriever(self) -> RunnableLambda[State, str]:
        return RunnableLambda[State, str](
            lambda x: "Find the opposite of the following: " +
            cast(str, x.get("bob_response", "")))

    def prepare_output(self, output: Any) -> AgentResult:
        return AgentResult(
            answer=output["answer"],
            sources=output["sources"],
            chat_history=output["chat_history"],
            context=output["context"]
        )

    def get_request_chat_message(self, state: State, parsed_response: Dict[str, Any]) -> str:
        return "Prepare a rebuttal for BOB_BOT's response."

    @property
    def personae_name(self) -> str:
        return "AIMIE_Rebuttal"

    @property
    def system_role_name(self) -> str:
        return "system"
