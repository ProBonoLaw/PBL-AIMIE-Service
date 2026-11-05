
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, TypeVar
from pydantic import BaseModel

from langchain_core.documents import Document
from langchain_core.language_models import LanguageModelInput
from langchain_core.runnables import RunnableLambda, Runnable
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.retrievers import RetrieverLike
from langchain_core.vectorstores import VectorStore

from ...common import AgentResult, BaseHistoryAwareAgent, AnswersWithSources
from ....utils.history_only_retriever import HistoryOnlyRetriever
from ....utils.state import State
from .types import InitialArgumentRequest

U = TypeVar('U', bound=State)

class BaseInitialArgumentAgent(BaseHistoryAwareAgent[InitialArgumentRequest, AgentResult, U]):
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
                ("assistant", "What is your request:"),
                ("human", "{input}\n\n"),
                ("assistant", "Who am I writing this declaration against?"),
                ("user", "You are writing this declaration against {opposition}, who is the {opposition_role}."),
                ("assistant", "Who am I writing this declaration for?"),
                ("user", "You are writing this declaration advocating {designated_client}, who is the {designated_client_role}.")
            ]

        additional_instructions = self.additional_prompt()
        if additional_instructions:
            instructions.extend(additional_instructions)
        qa_prompt = ChatPromptTemplate(messages=instructions)

        return qa_prompt
    
    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return self.llm.with_structured_output(AnswersWithSources, include_raw=True)
    
    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return None

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
    
    def prepare_output(self, output: Any) -> AgentResult:
        return AgentResult(
            answer=output["answer"],
            sources=output["sources"],
            chat_history=output["chat_history"],
            context=output["context"]
        )

    @property
    def check_chat_history(self) -> bool:
        return True

    def get_request_chat_message(self, state: State, parsed_response: Dict[str, Any]) -> str:
        return state["input"] if state["input"] else ""

    @property
    def personae_name(self) -> str:
        return "AIMIE"

    def generate_input_retriever(self) -> RunnableLambda[State, str]:
        async def async_input_getter(x):
            return {
                "question": x["input"] if "input" in x and x["input"] else "",
                "use_enhanced_retriever": x["use_enhanced_retriever"] if "use_enhanced_retriever" in x else True
            }

        return RunnableLambda[State, str](
            func=lambda x: {
                "question": x["input"] if "input" in x and x["input"] else "",
                "use_enhanced_retriever": x["use_enhanced_retriever"] if "use_enhanced_retriever" in x else True
            },
            afunc=async_input_getter
        )

    @property
    def system_role_name(self) -> str:
        return "system"
    
    def generate_configurable(self, input: InitialArgumentRequest) -> Dict[str, Any]:
        original_config = super().generate_configurable(input)
        original_config["configurable"]["use_enhanced_retriever"] = True
        return original_config
        
    