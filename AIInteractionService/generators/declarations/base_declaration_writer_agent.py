
from typing import Any, Dict, List, Optional, Sequence

from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.vectorstores import VectorStore
from langchain_core.language_models import LanguageModelInput
from pydantic import BaseModel

from ...utils.result import get_answer
from ..common import formal_answers_with_sources_json_schema, BaseAgent, FormalAnswersWithSources
from .types import DeclarationWriterAgentRequest, DeclarationWriterOutput
from ...utils.formatters import format_docs
from ...utils.history_only_retriever import HistoryOnlyRetriever


class BaseDeclarationWriterAgent(
        BaseAgent[DeclarationWriterAgentRequest, DeclarationWriterOutput]):
    def __init__(self, account_id: str, session_id: str, **kwargs: Any):
        super().__init__(account_id, session_id, **kwargs)

    @property
    def max_doc_count(self) -> int:
        return 0

    def get_prompt(self) -> ChatPromptTemplate:
        instructions: List[MessageLikeRepresentation] = [
            {"role": self.system_role_name, "content": self.primary_prompt},
            {"role": self.system_role_name, "content": "Context:\n{context}"},
            {"role": "assistant", "content": "Who am I writing this declaration against?"},
            {"role": "user", "content": "You are writing this declaration against {opposition}; who is the {opposition_role}."},
            {"role": "assistant", "content": "Who am I writing this declaration for?"},
            {"role": "user", "content": "You are writing this declaration for {designated_client}; who is the {designated_client_role}."},
            {"role": "assistant", "content": "What is the location of the court?"},
            {"role": "user", "content": "The location of the court hearing is {location}."},
            {"role": "assistant", "content": "What type of hearing is this for?"},
            {"role": "user", "content": "This is a {hearing_type} case."},
            {"role": "assistant",
                "content": "Would you like the document in HTML or Markdown format?"},
            {"role": "user", "content": "Markdown"},
            {"role": "assistant",
                "content": "Which document would you like to refine into a legal declaration?"},
            {"role": "user", "content": "Refine and augment the following statement:\n{statement}."},
            {"role": "assistant",
                "content": "Please provide the JSON schema for the answer."},
            {"role": "human", "content": formal_answers_with_sources_json_schema}
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
        if context:
            return HistoryOnlyRetriever(
                context=context)
        return HistoryOnlyRetriever()

    def prepare_chain(self, prompt: ChatPromptTemplate, retriever: RetrieverOutputLike) -> Runnable[Dict[str, Any], Any]:
        on_end = self.generate_listener_for_primary_llm_with_structured_output()
        llm_chain = RunnablePassthrough.assign(**{'context': lambda x: format_docs(x, self.max_doc_count)}).with_config(
            run_name="format_inputs"
        ) | prompt | self.prepare_llm_for_chain().with_alisteners(on_end=on_end)
        retrieval_chain = (
            RunnablePassthrough.assign(
                context=retriever.with_config(
                    run_name="retrieve_documents"),
            ).assign(answer=llm_chain.with_retry(stop_after_attempt=3))
        ).with_config(run_name="retrieval_chain")
        return retrieval_chain

    def prepare_output(self, result: Any) -> DeclarationWriterOutput:
        answer = get_answer(result)
        sources = []
        if isinstance(answer, FormalAnswersWithSources):
            sources = answer.sources
            answer = answer.answer
        elif isinstance(answer, Dict):
            sources = answer['sources']
            answer = answer["answer"]
        else:
            raise ValueError(
                "Expected answer to be of type AnswersWithSources")
        return DeclarationWriterOutput(
            answer=answer,
            sources=sources)

    @property
    def personae_name(self) -> str:
        return "AIMIE_Declaration_Writer"

    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return (self.llm.with_structured_output(FormalAnswersWithSources, include_raw=True))

    @property
    def system_role_name(self) -> str:
        return "system"
