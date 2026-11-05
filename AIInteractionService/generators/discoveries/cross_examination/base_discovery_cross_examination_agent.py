

import orjson
from typing import Any, Dict, Generic, List, Optional, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.vectorstores import VectorStore

from ...common import LawRetrieverProvider, BaseAgent
from ....utils.formatters import format_docs
from ....utils.history_only_retriever import HistoryOnlyRetriever
from .types import DiscoveryCrossExaminationRequest, DiscoveryCrossExaminationOutput

T = TypeVar('T', bound=BaseChatModel)


class BaseDiscoveryCrossExaminationAgent(
        BaseAgent[T,
                  DiscoveryCrossExaminationRequest,
                  DiscoveryCrossExaminationOutput],
        Generic[T]):
    def __init__(self, account_id: str, session_id: str, law_retriever_provider: LawRetrieverProvider, **kwargs: Any):
        super().__init__(account_id, session_id, law_retriever_provider, **kwargs)
        self.__max_doc_count = kwargs.get("max_doc_count", 20)
    
    @property
    def max_doc_count(self) -> int:
        return self.__max_doc_count

    def get_prompt(self) -> ChatPromptTemplate:
        system_prompt = (
            "You are a shady attorney tasked with representing the target in a discovery for a "
            "an upcoming court hearing. The discovery questions may ruin your client if it is submitted to "
            "court.  Your job is generate arguments to nullify, confuse or dispute the type of "
            "discovery based on the context of the case. Be sure not to include "
            "terms like 'spouse' or 'husband' or 'wife' in the questions, "
            "if the subject's marital status is single. "
            "Attempt to generate at most 4 questions/requests. "
            "The your retort is based on topic {topic}, well-written, "
            "clear, and inflammatory. If you find any issues, "
            "you should make corrections and provide suggestions for improvement. "
            "Considering evidence like bank statements, tax returns, check stubs, other "
            "financial documents, depositions, doctor's reports, police reports, "
            "and eyewitness statements to be high-quality sources. "
            "You should also consider the context as documentation of the case. "
            "Being able to use the context to your advantage is key. "
            "\n\n"
            "The following is a question/request AIMIE_BOT asked of your client: "
            "{topic_question}\n\n\n\n"
            "Context: {context}"
        )
        qa_prompt = ChatPromptTemplate(
            [
                ("assistant", system_prompt),
                ("assistant", "Who is the target of the interrogatory?"),
                ("human", "The target of the interrogatory is {target}"),
                ("assistant", "What is this discovery about?"),
                ("human", "{input}"),
            ]
        )
        return qa_prompt

    def get_retriever(self,
                      vector_store: Optional[VectorStore] = None,
                      context: Optional[List[Document]] = None, 
                      law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
        primary_retriever: RetrieverLike
        if vector_store is None:
            primary_retriever = HistoryOnlyRetriever(
                context=context)
        else:
            primary_retriever = vector_store.as_retriever(
                search_type="semantic_hybrid",
                k=self.max_doc_count)
        
        if law_retriever is None:
            return primary_retriever
        return EnsembleRetriever(retrievers=[primary_retriever, law_retriever], weights=[0.7, 0.3])

    def prepare_chain(self,
                      prompt: ChatPromptTemplate,
                      retriever: RetrieverOutputLike) -> Runnable[Dict[str, Any], Any]:
        llm_chain = RunnablePassthrough.assign(**{'context': lambda x: format_docs(x, self.max_doc_count)}).with_config(
            run_name="format_inputs"
        ) | prompt | self.llm.with_structured_output(DiscoveryCrossExaminationOutput)
        retrieval_samples = (lambda x: x["topic_question"]) | retriever
        retrieval_chain = (
            RunnablePassthrough.assign(
                context=retrieval_samples.with_config(
                    run_name="retrieve_documents_4_bob"),
            ).assign(answer=llm_chain)
        ).with_config(run_name="retrieval_chain")

        return retrieval_chain

    def prepare_output(self, result: Dict[str, Any]) -> DiscoveryCrossExaminationOutput:
        answer: DiscoveryCrossExaminationOutput | str = result["answer"]
        if isinstance(answer, str):
            answer = DiscoveryCrossExaminationOutput.model_validate_json(orjson.loads(answer))
        return answer

    def personae_name(self) -> str:
        return "bob_discovery_writer"
    
    def system_role_name(self) -> str:
        return "system"
