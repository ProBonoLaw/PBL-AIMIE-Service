
from abc import abstractmethod
import logging
from typing import Any, Dict, Generic, List, Optional, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.language_models import LanguageModelInput
from langchain_core.documents import Document
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.vectorstores import VectorStore
from pydantic import BaseModel

from .types import AmieLibrarianAgentRequest, LibrarianAnswer, LibrarianOutput, format_docs_without_metadata
from ...common.base_agent import BaseAgent
from .types import librarian_answer_response_schema
from AIInteractionService.utils.history_only_retriever import HistoryOnlyRetriever


class BaseLibrarianAgent(
        BaseAgent[
            AmieLibrarianAgentRequest,
            LibrarianOutput]):
    def get_prompt(self) -> ChatPromptTemplate:
        system_prompt = (
            "You are a librarian tasked with finding quotes that bests fits the user's statement. "
            "You are to search for quotes that best suits a given statement and its docIds. "
            "The quotes must originate from the document referenced by the docIds in the user's input. "
            "If you find a quote that matches the user's query, you should include the quote in your response."
            "Return the document, in it's entirety, with the quote highlighted. "
            "The document should be returned in markdown format, using the <mark> and </mark> HTML elements to highlight the quote in yellow. "
            "Do not highlight the docIds, as that is redundant. "
            "Do not make any corrections to the document.  That includes spelling, grammar, or punctuation. "
            "The document that is highlighted is to be returned in verbatim form, with the exception of the highlighted quote. "
            "Failure to do may cause our client to face perjury charges and may be subject to severe legal action. "
            "Do your best to find the most relevant quote that matches the user's query. "
            "Also, if a quote is found, but there are artifacts or gibberish within in the quote, only highlight the relevant portion of the document. "
            "Do not rearrange the content of the document in any way or form. "
            "If a quote is not found, return nothing at all. "
            "Your quote must originate from the document referenced by the docIds in the user's input. "
            "Do not generate fake quotes, as that would be devastating to the case. "
            "\n\n"
            "Context: {context}"
        )
        qa_prompt = ChatPromptTemplate(
            [
                ("assistant", system_prompt),
                ("assistant", "What is the docId of the document to focus on?"),
                ("user", "docId: {doc_id}"),
                ("assistant", "What is the statement you would like to find quotes for?"),
                ("human",
                 "The statement requiring argument strengthening quotes are:\n{quote}"),
                ("assistant", "Please provide the JSON schema for the answer."),
                ("human", librarian_answer_response_schema)
            ]
        )
        return qa_prompt

    def get_retriever(self,
                      vector_store: Optional[VectorStore] = None,
                      context: Optional[List[Document]] = None,
                      law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
        return HistoryOnlyRetriever(
            context=context)

    def prepare_chain(self, prompt: ChatPromptTemplate, retriever: RetrieverOutputLike) -> Runnable[Dict[str, Any], Any]:
        llm_chain = RunnablePassthrough.assign(**{'context': format_docs_without_metadata}).with_config(
            run_name="format_inputs"
        ) | prompt | self.prepare_llm_for_chain()
        retrieval_chain = (
            RunnablePassthrough.assign(
                context=retriever.with_config(run_name="retrieve_documents"),
            ).assign(answer=llm_chain)
        ).with_config(run_name="retrieval_chain")
        return retrieval_chain

    def prepare_output(self, result: Dict[str, Any]) -> LibrarianOutput:
        answer = result["answer"]
        if isinstance(answer, LibrarianAnswer):
            return LibrarianOutput(answer=answer, context=result["context"])
        else:
            raise ValueError(f"Unexpected type for answer: {type(answer)}")

    @property
    def personae_name(self) -> str:
        return "AIMIE_Librarian_Writer"

    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return self.llm.with_structured_output(LibrarianAnswer)
    
    @property
    def system_role_name(self) -> str:
        return "system"