
from typing_extensions import Any, Dict, Generic, List, Optional, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.vectorstores import VectorStore

from ...common import LawRetrieverProvider, BaseAgent
from ....utils.formatters import format_docs
from ....utils.history_only_retriever import HistoryOnlyRetriever
from .types import DiscoveryRequestRefinementWriterAgentRequest, DiscoveryRequestRefinementWriterAgentOutput

T = TypeVar('T', bound=BaseChatModel)


class BaseDiscoveryRequestRefinementWriterAgent(
        BaseAgent[T,
                  DiscoveryRequestRefinementWriterAgentRequest,
                  DiscoveryRequestRefinementWriterAgentOutput],
        Generic[T]):
    def __init__(self,
                account_id: str,
                session_id: str,
                law_provider: LawRetrieverProvider,
                **kwargs: Any):
        super().__init__(account_id, session_id, law_provider, **kwargs)
        self.__max_doc_count = kwargs.get("max_doc_count", 20)

    @property
    def max_doc_count(self) -> int:
        return self.__max_doc_count

    def get_prompt(self) -> ChatPromptTemplate:
        system_prompt = (
            "You are a legal advisory who is tasked with evaluating a discovery request/question "
            "and bob's retort to the question. Your job is to provide a refined version of the "
            "question as to make it more clear and to address BOB_BOT's retort.  You may need to produce "
            "a new set of questions/requests based on the original question and bob's retort. "
            "The questions must be able to withstand scrutiny, especially against BOB_BOT's retort. "
            "Consider the topic and the target of the question and the context, "
            "as it's contains documents relevant to the case. "
            "Be sure to remove all mention of AIMIE_BOT and BOB_BOT from the document. "
            "Also review all context data, as they may be relevant to the refinement. "
            "Besure to include a rationale for the refinement and your sources. "
            "Consider that these questions/requests must be treated as demands for information "
            "and the target is required to provide the information requested. "
            "Keep the questions/requests to no more than 4. "
            "\n\n"
            "Context: {context}"
        )
        qa_prompt = ChatPromptTemplate(
            [
                ("system", system_prompt),
                ("assistant", "Who is the subject of interrogatory?"),
                ("user", "The subject of the interrogatory is {target}"),
                ("assistant", "What is the location of the court?"),
                ("user", "The location of the court hearing is {location}"),
                ("assistant", "What type of hearing is this for?"),
                ("user", "This is a {hearing_type} case"),
                ("assistant", "Would you like the document in HTML or Markdown format?"),
                ("user", "Markdown"),
                ("assistant", "What is the AIMIE_BOT question?"),
                ("user", "Original question:\n{aimie_question}\n\n"),
                ("assistant", "What is BOB_BOT retort to the question?"),
                ("user", "Bob's retort:\n{bob_retort}\n\n"),
                ("assistant", "What are the instructions?"),
                ("user", "Original instructions:\n{input}\n\n")
            ]
        )
        return qa_prompt
    
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
        
        if not law_retriever is None:
            return EnsembleRetriever(retrievers = [primary_retriever, law_retriever], weights=[0.7, 0.3])
        return primary_retriever

    def prepare_output(self, result: Any) -> DiscoveryRequestRefinementWriterAgentOutput:
        answer: DiscoveryRequestRefinementWriterAgentOutput | str = result["answer"]
        if isinstance(answer, str):
            answer = DiscoveryRequestRefinementWriterAgentOutput.model_validate_json(answer)
        return answer

    def personae_name(self) -> str:
        return "AIMIE_Discovery_Question_Refinement_Writer"

    def prepare_chain(self, prompt: ChatPromptTemplate, retriever: RetrieverOutputLike) -> Runnable[Dict[str, Any], Any]:
        llm_chain = RunnablePassthrough.assign(**{'context': lambda x: format_docs(x, self.max_doc_count)}).with_config(
            run_name="format_inputs"
        ) | prompt | self.llm.with_structured_output(DiscoveryRequestRefinementWriterAgentOutput)
        retrieval_docs = (lambda x: x["aimie_question"]) | retriever
        retrieval_chain = (
            RunnablePassthrough.assign(
                context=retrieval_docs.with_config(
                    run_name="retrieve_refined_case_documents"),
            ).assign(answer=llm_chain)
        ).with_config(run_name="retrieval_chain")

        return retrieval_chain

    def system_role_name(self) -> str:
        return "system"