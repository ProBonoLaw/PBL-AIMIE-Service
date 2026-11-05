
from operator import itemgetter
import os
from typing import Any, Dict, List, Optional, Sequence

from langchain_azure_ai.callbacks.tracers import AzureAIOpenTelemetryTracer
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnablePassthrough, RunnableConfig
from langchain_core.language_models import LanguageModelInput
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.vectorstores import VectorStore
from pydantic import BaseModel

from .types import FactValidatorRequest, FactValidatorResponse
from ...common import BaseAgent
from ....utils.history_only_retriever import HistoryOnlyRetriever
from ....utils.formatters import format_docs


class BaseFactValidatorAgent(BaseAgent[FactValidatorRequest, FactValidatorResponse]):
    def __init__(self, account_id: str,
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
            {"role": self.system_role_name(), "content": self.primary_prompt},
            {"role": self.system_role_name(), "content": "Context:\n{context}"},
            ("assistant", "Which statement needs verifying:"),
            ("human", "Statement needing verification: \"{input}\"\n\n"),
            ("assistant", "Is this the last paragraph of a larger statement? "),
            ("human", "{is_last_paragraph}\n\n"),
            ("assistant", "What was the original request that was used to generate the input? "),
            ("human", "The original request was: \"{original_request}\"\n\n")
        ]

        additional_instructions = self.additional_prompt()
        if additional_instructions:
            instructions.extend(additional_instructions)
        qa_prompt = ChatPromptTemplate(messages=instructions)

        return qa_prompt

    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return None

    def get_retriever(self,
                      vector_store: Optional[VectorStore],
                      context: Optional[List[Document]],
                      law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
        primary_retriever: RetrieverLike
        if vector_store is None:
            primary_retriever = HistoryOnlyRetriever(
                context=context if context is not None else [])
        else:
            vector_retriever = vector_store.as_retriever(
                search_type="semantic_hybrid_score_threshold",
                k=self.max_doc_count)
            if context is not None and len(context) > 0:
                primary_retriever = EnsembleRetriever(
                    retrievers=[vector_retriever,
                                HistoryOnlyRetriever(context=context)],
                    weights=[0.7, 0.3])
            else:
                primary_retriever = vector_store.as_retriever(
                    search_type="semantic_hybrid",
                    k=self.max_doc_count)

        if law_retriever is None:
            return primary_retriever
        return EnsembleRetriever(
            retrievers=[
                primary_retriever,
                law_retriever
            ],
            weights=[0.7, 0.3]
        )

    def prepare_chain(
            self,
            prompt: ChatPromptTemplate,
            retriever: RetrieverOutputLike) -> Runnable[Dict[str, Any], Any]:
        llm_chain = (RunnablePassthrough.assign(**{'context': format_docs})
                     .with_config(run_name="format_inputs") |
                     prompt |
                     self.prepare_llm_for_chain().with_alisteners(on_end=self.generate_listener_for_primary_llm_with_structured_output())
        )
        retrieval_chain = (
            RunnablePassthrough.assign(
                context=itemgetter("input") | retriever.with_config(
                    run_name=self.personae_name + "_retrieve_documents"),
            ).assign(answer=llm_chain.with_retry(stop_after_attempt=3))
        ).with_config(run_name=self.personae_name + "_request_fulfillment_chain")
        return retrieval_chain

    @property
    def personae_name(self) -> str:
        return "AIMIE_Fact_Validator"

    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return self.llm.with_structured_output(FactValidatorResponse, include_raw=True)

    def system_role_name(self) -> str:
        return "system"

    def generate_configurable(self, input: FactValidatorRequest) -> RunnableConfig:
        """
        Generates the runtime configurable for the agent.
        """
        azure_tracer = AzureAIOpenTelemetryTracer(
            connection_string=os.environ.get(
                "APPLICATIONINSIGHTS_CONNECTION_STRING"),
            enable_content_recording=True,
            name=self.personae_name,
            agent_id=f"{self.personae_name}_{self.account_id}_{self.session_id}",
        )
        return {
            "configurable": {
                "thread_id": self.session_id,
                "account_id": self.account_id,
                "arbitrary_types_allowed": True,
                "use_enhanced_retriever": False,
            },
            "callbacks": [azure_tracer]
        }
