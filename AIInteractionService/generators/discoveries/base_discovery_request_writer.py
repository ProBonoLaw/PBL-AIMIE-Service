
from typing import Any, Dict, Generic, List, Optional, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.vectorstores import VectorStore

from ..common import LawRetrieverProvider, BaseAgent
from .topic_questions import DiscoveryTopicQuestionsWriterOutput
from .types import DiscoveryRequestWriterAgentRequest, DiscoveryRequestWriterOutput
from ...utils.history_only_retriever import HistoryOnlyRetriever

T = TypeVar('T', bound=BaseChatModel)

class BaseDiscoveryRequestWriterAgent(
        BaseAgent[T,
                  DiscoveryRequestWriterAgentRequest,
                  DiscoveryRequestWriterOutput],
        Generic[T]):
    def __init__(self, account_id: str, session_id: str, law_provider: LawRetrieverProvider, **kwargs: Any):
        super().__init__(account_id, session_id, law_provider, **kwargs)
        self.__max_doc_count = kwargs.get("max_doc_count", 10)

    @property
    def max_doc_count(self) -> int:
        return self.__max_doc_count

    def get_prompt(self) -> ChatPromptTemplate:
        system_prompt = (
            "You are a legal editor tasked with write a local document requesting "
            "information as part of a discovery inquiry. The request is to be submitted to "
            "subject.  Your job is to ensure that the declaration is well-written, "
            "clear, and free of errors. If you find any issues, "
            "you should make corrections and provide suggestions for improvement. "
            "Remove all mention of AIMIE_BOT and BOB_BOT from the document. "
            "The preferred format of the document is of the following: "
            "1. Introduction: A brief introduction to the case. Include the case "
            "number, if it could be found. "
            "It should be started with the markdown header `## Introduction`. "
            "2. Questions and Requests: The main argument of the case. It should "
            "be started with the markdown header `## Questions and Requests`. "
            "All subsequent questions based per topic should be started with the "
            "markdown header `### ` followed by the name of the topic. "
            "All questions/requests should be numbered, based on their topic. "
            "Leave a 3 blank lines after each question, giving the target room "
            "to answer the question. "
        )
        qa_prompt = ChatPromptTemplate(
            [
                ("assistant", system_prompt),
                ("assistant", "Who is the subject of interrogatory?"),
                ("user", "The subject of the interrogatory is {target}"),
                ("assistant", "What is the location of the court?"),
                ("user", "The location of the court hearing is {location}"),
                ("assistant", "What type of hearing is this for?"),
                ("user", "This is a {hearing_type} case"),
                ("assistant", "Would you like the document in HTML or Markdown format?"),
                ("user", "Markdown"),
                ("assistant", "What are the instructions?"),
                ("user", "Original instructions:\n{input}\n\n"),
                ("assistant", "What are the questions?"),
                ("user", "The questions are: {questions}")
            ]
        )
        return qa_prompt

    def get_retriever(self,
                      vector_store: Optional[VectorStore] = None,
                      context: Optional[List[Document]] = None,
                      law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
        return HistoryOnlyRetriever(context=context)

    def prepare_output(self, result: Any) -> DiscoveryRequestWriterOutput:
        return DiscoveryRequestWriterOutput(discovery_order=result['answer'], location=result['location'] if 'location' in result else '')

    def personae_name(self) -> str:
        return "AIMIE_Discovery_Request_Writer"

    def format_docs(self, inputs: dict) -> str:
        def format_questions(doc: DiscoveryTopicQuestionsWriterOutput) -> str:
            questions = '\n'.join(doc.questions)
            return f"### {doc.topic}:\n\n{questions}"
        return '\n\n'.join(
            format_questions(doc)
            for doc in inputs['questions']
        )

    def prepare_chain(self, prompt: ChatPromptTemplate, retriever: RetrieverOutputLike) -> Runnable[Dict[str, Any], Any]:
        chain = prompt | self.llm.with_retry(stop_after_attempt=5) | StrOutputParser()
        retrieval_chain = (
            RunnablePassthrough.assign(**{'questions': self.format_docs}
            ).assign(answer=chain)
        ).with_config(run_name="format_inputs")
        return retrieval_chain

    def system_role_name(self) -> str:
        return "system"