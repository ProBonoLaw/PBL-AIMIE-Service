
from operator import itemgetter
from typing import Any, Dict, List, Optional, Sequence


from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.language_models import LanguageModelInput
from langchain_core.documents import Document
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.vectorstores import VectorStore
from pydantic import BaseModel

from .types import AmieLibrarianClaimAgentRequest, LibrarianClaimAnswer, LibrarianClaimOutput
from ...common.base_agent import BaseAgent
from ....utils.formatters import format_docs
from ....utils.history_only_retriever import HistoryOnlyRetriever
from ....utils.result import get_answer

class BaseLibrarianClaimAgent(
        BaseAgent[
            AmieLibrarianClaimAgentRequest,
            LibrarianClaimOutput]):
    def __init__(self, account_id: str, session_id: str, max_doc_count: int, **kwargs: Any):
        super().__init__(account_id, session_id, **kwargs)
        self.__max_doc_count = max_doc_count

    @property
    def max_doc_count(self) -> int:
        return self.__max_doc_count

    def get_prompt(self) -> ChatPromptTemplate:
        instructions: List[MessageLikeRepresentation] = [
            {"role": self.system_role_name, "content": self.primary_prompt},
            {"role": self.system_role_name, "content": "Context:\n{context}"},
            ("assistant", "What is your request:"),
            ("human", "{claim}\n\n")
        ]
        additional_instructions = self.additional_prompt()
        if additional_instructions:
            instructions.extend(additional_instructions)
        qa_prompt = ChatPromptTemplate(messages=instructions)

        return qa_prompt

    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return None

    def get_retriever(self,
                      vector_store: Optional[VectorStore] = None,
                      context: Optional[List[Document]] = None,
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

    def prepare_chain(
            self,
            prompt: ChatPromptTemplate,
            retriever: RetrieverOutputLike) -> Runnable[Dict[str, Any], Any]:
        llm_chain = (RunnablePassthrough.assign(**{'context': format_docs})
                     .with_config(run_name="format_inputs") |
                     prompt |
                     self.prepare_llm_for_chain()).with_config(
            run_name=self.personae_name + "_llm_chain"
        )
        retrieval_chain = (
            RunnablePassthrough.assign(
                context=itemgetter("claim") | retriever.with_config(
                    run_name=self.personae_name + "_retrieve_documents"),
            ).assign(answer=llm_chain.with_retry(stop_after_attempt=3))
        ).with_config(run_name=self.personae_name + "_request_fulfillment_chain")
        return retrieval_chain

    def prepare_output(self, result: Dict[str, Any]) -> LibrarianClaimOutput:
        answer = get_answer(result)
        if isinstance(answer, LibrarianClaimAnswer):
            has_multiple_sources = len(answer.docs) > 1
            context_ids = dict()
            unique_source_ids = set()
            for doc in result.get("context", []):
                context_ids[doc.metadata.get(
                    "id", "")] = doc.metadata.get("sourceId", "")
            for doc in answer.docs:
                source_id = context_ids.get(doc.doc_id, None)
                if source_id:
                    unique_source_ids.add(source_id)
            has_multiple_sources = len(unique_source_ids) > 1
            return LibrarianClaimOutput(answer=answer, has_multiple_sources=has_multiple_sources, context=result["context"])
        else:
            raise ValueError(f"Unexpected type for answer: {type(answer)}")

    @property
    def personae_name(self) -> str:
        return "AIMIE_Librarian_Claim_Confirmation_Agent"

    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        on_end = self.generate_listener_for_primary_llm_with_structured_output()
        return self.llm.with_structured_output(LibrarianClaimAnswer, include_raw=True).with_alisteners(on_end=on_end)

    @property
    def system_role_name(self) -> str:
        return "system"
