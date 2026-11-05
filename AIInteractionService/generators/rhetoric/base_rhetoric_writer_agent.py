
from typing import Any, Dict, Generic, List, Optional, Sequence, Type, TypeVar

from pydantic import BaseModel

from langchain_core.language_models import LanguageModelInput, BaseChatModel
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.runnables import RunnableLambda, Runnable
from langchain_core.vectorstores import VectorStore

from ..common import normalize_source, BaseHistoryAwareAgent, AnswersWithSources
from ...utils.history_only_retriever import HistoryOnlyRetriever
from .types import RhetoricState, RhetoricWriterAgentRequest, RhetoricWriterOutput

T = TypeVar('T', bound=BaseChatModel)


class BaseRhetoricWriterAgent(
        BaseHistoryAwareAgent[RhetoricWriterAgentRequest,
                              RhetoricWriterOutput, RhetoricState],
        Generic[T]):
    def __init__(self, account_id: str, session_id: str, max_doc_count: int, **kwargs: Any):
        self.__max_doc_count = max_doc_count
        super().__init__(account_id, session_id, **kwargs)
    
    @property
    def max_doc_count(self) -> int:
        return self.__max_doc_count

    def prepare_history_aware_chain(self, retriever: RetrieverOutputLike) -> RetrieverOutputLike:
        '''
        We are not using using chat history in this agent, so we return the retriever as is.
        '''
        return self.generate_input_retriever() | retriever

    def get_prompt(self) -> ChatPromptTemplate:
        instructions: List[MessageLikeRepresentation] = [
            {"role": self.system_role_name, "content": self.primary_prompt},
            {"role": self.system_role_name, "content": "Context:\n{context}"},
            {"role": "assistant",
                "content": "What is the statement AIMIE would like to expand upon?"},
            {"role": "human", "content": "The following statement needs to be expanded: \"{statement}\""}
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
            primary_retriever = HistoryOnlyRetriever(
                context=context)
        else:
            primary_retriever = vector_store.as_retriever(
                search_type="semantic_hybrid",
                k=self.max_doc_count)

        if law_retriever is None:
            return primary_retriever
        return EnsembleRetriever(retrievers=[primary_retriever, law_retriever], weights=[0.7, 0.3])

    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return self.llm.with_structured_output(AnswersWithSources, include_raw=True)

    def prepare_output(self, result: Dict[str, Any]) -> RhetoricWriterOutput:
        literal_answer = result["answer"]
        sources = [normalize_source(source) for source in result["sources"]]
        return RhetoricWriterOutput(
            answer=AnswersWithSources(answer=literal_answer,
                                      sources=sources),
            context=result["context"],
            location=result["location"],
            chat_history=result["chat_history"])

    @property
    def personae_name(self) -> str:
        return "AIMIE_Rhetoric_Writer"

    def get_request_chat_message(self, state: RhetoricState, parsed_response: Dict[str, Any]) -> str:
        return f'Generate additional details and rhetoric for the following statement: \n{state["statement"]}'

    @property
    def output_class_type(self) -> Type:
        return RhetoricState

    def generate_input_retriever(self) -> RunnableLambda[RhetoricState, str]:
        return RunnableLambda(lambda x: x["statement"])

    @property
    def system_role_name(self) -> str:
        return "system"
