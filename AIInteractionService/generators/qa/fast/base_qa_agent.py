
from datetime import datetime
from operator import itemgetter
import os
from typing import Any, Dict, List, Optional, Type, TypeVar, Sequence

from langchain_azure_ai.callbacks.tracers import AzureAIOpenTelemetryTracer
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnableLambda, RunnableConfig
from langchain_core.language_models import LanguageModelInput
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.retrievers import RetrieverLike
from langchain_core.vectorstores import VectorStore
from langchain.tools import tool
from pydantic import BaseModel

from .types import QARequest
from ...common import AgentResult, BaseHistoryAwareAgent, AnswersWithSources
from ....utils.history_only_retriever import HistoryOnlyRetriever
from ....utils.state import State

U = TypeVar('U', bound=State)


class BaseQaAgent(BaseHistoryAwareAgent[QARequest, AgentResult, U]):
    def __init__(self, account_id: str,
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
            {"role": self.system_role_name, "content": "Response-detail requirement:\n{response_detail_instruction}"},
            {
                "role": self.system_role_name,
                "content": (
                    "Advocate for {aimies_client}, whose filing role is {aimies_filing_role}, "
                    "and their interests. The opposing party is {opposition}, whose role is "
                    "{opposition_role}. Answer the user's question directly."
                ),
            },
            MessagesPlaceholder("chat_history"),
        ]

        additional_instructions = self.additional_prompt
        if additional_instructions:
            instructions.extend(additional_instructions)
        instructions.append(("human", "{input}\n\n"))
        qa_prompt = ChatPromptTemplate(messages=instructions)

        return qa_prompt

    @property
    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return None

    def generate_configurable(self, input: QARequest) -> RunnableConfig:
        azure_tracer = AzureAIOpenTelemetryTracer(
            connection_string=os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"),
            enable_content_recording=True,
            name=self.personae_name,
            agent_id=f"{self.personae_name}_{self.account_id}_{self.session_id}",
        )
        return {
            "configurable": {
                "thread_id": self.session_id,
                "account_id": self.account_id,
                "arbitrary_types_allowed": True,
                "use_enhanced_retriever": self._get_use_enhanced_retriever(input),
            },
            "callbacks": [azure_tracer]
        }
    

    def get_retriever(self,
                      vector_store: Optional[VectorStore],
                      context: Optional[List[Document]],
                      law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
        primary_retriever: RetrieverLike
        if vector_store is None:
            primary_retriever = HistoryOnlyRetriever(context=context)
        else:
            primary_retriever = vector_store.as_retriever(
                search_type="semantic_hybrid",
                k=self.max_doc_count)

        if law_retriever is None:
            return primary_retriever
        return EnsembleRetriever(retrievers=[primary_retriever, law_retriever], weights=[0.7, 0.3])

    @property
    def check_chat_history(self) -> bool:
        return False

    def get_request_chat_message(self, state: State, parsed_response: Dict[str, Any]) -> str:
        return state["input"] if state["input"] else ""

    @property
    def personae_name(self) -> str:
        return "AIMIE_QA"

    @property
    def output_class_type(self) -> Type:
        return State

    def generate_input_retriever(self) -> RunnableLambda[State, str]:
        async def async_input_getter(x: State):
            return x

        return RunnableLambda[State, str](
            func=lambda x: x,
            afunc=async_input_getter
        )

    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return self.bind_primary_llm(
            self.llm.with_structured_output(AnswersWithSources, include_raw=True)
        )

    @property
    def system_role_name(self) -> str:
        return "system"
