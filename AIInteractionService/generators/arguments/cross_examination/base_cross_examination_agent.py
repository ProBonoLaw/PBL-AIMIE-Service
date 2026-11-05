
from datetime import datetime
import logging
from typing import Sequence, TypeVar
from typing_extensions import Any, Dict, List, Optional
from pydantic import BaseModel

from langchain_core.documents import Document
from langchain_core.language_models import LanguageModelInput
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.retrievers import RetrieverLike, BaseRetriever, RetrieverOutputLike
from langchain_core.runnables import RunnableLambda, Runnable
from langchain_core.vectorstores import VectorStore

from .types import CrossExaminationRequest
from ...common import AgentResult, BaseHistoryAwareAgent, AnswersWithSources
from ....utils.history_only_retriever import HistoryOnlyRetriever
from ....utils.state import State

logger = logging.getLogger(__name__)

U = TypeVar('U', bound=State)


class BaseCrossExaminationAgent(
        BaseHistoryAwareAgent[CrossExaminationRequest, AgentResult, U]):
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
            ("assistant", "Who am I representing?"),
            ("user",
             "You are representing {opposition}; who is the {opposition_role}."),
            ("assistant", "Who is my opposition?"),
            ("user",
             "You're opponent is {designated_client}; who is the {designated_client_role}."),
            ("assistant", "What is the location of the court?"),
            ("assistant", "What was the original request sent to AIMIE_BOT?"),
            ("user",
             "The original request is: \n{original_question}\n-------\\n"),
            ("assistant", "What was AIMIE_BOT's answer?"),
            ("user",
             "Refute AIMIE_BOT's response, as you are the representative of the opposition of AIMIE's client:\n {aimie_answer}")
        ]
        additional_instructions = self.additional_prompt()
        if additional_instructions:
            instructions.extend(additional_instructions)
        qa_prompt = ChatPromptTemplate(messages=instructions)

        return qa_prompt

    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return None

    def prepare_history_aware_chain(self, retriever: RetrieverOutputLike) -> RetrieverOutputLike:
        '''
        We are not using using chat history in this agent, so we return the retriever as is.
        '''
        return self.generate_input_retriever() | retriever

    def get_retriever(self, vector_store: Optional[VectorStore] = None, context: Optional[List[Document]] = None, law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
        primary_retriever: Optional[BaseRetriever] = None
        if vector_store is None:
            primary_retriever = HistoryOnlyRetriever(
                context=context if context is not None else [])
        else:
            primary_retriever = vector_store.as_retriever(
                search_type="semantic_hybrid",
                k=self.max_doc_count)
        if law_retriever is None:
            return primary_retriever
        return EnsembleRetriever(retrievers=[primary_retriever, law_retriever], weights=[0.5, 0.5])

    def prepare_output(self, output: Any) -> AgentResult:
        return AgentResult(
            answer=output["answer"],
            sources=output["sources"],
            chat_history=output["chat_history"],
            context=output["context"]
        )

    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return self.llm.with_structured_output(AnswersWithSources, include_raw=True)

    def generate_input_retriever(self) -> RunnableLambda[State, str | Dict]:
        async def async_input_getter(x: State):
            logger.info("tool.cross_exam_input_retriever", extra={"state": str(x)})
            result = {'question': (x['original_question'] if 'original_question' in x and x['original_question'] else "")
                + '\n\nFind the opposite of the following: '
                + (x["aimie_answer"]
                   if "aimie_answer" in x and x["aimie_answer"] else ""),
             'use_enhanced_retriever': x['use_enhanced_retriever'] if 'use_enhanced_retriever' in x else True}
            return result

        return RunnableLambda[State, str](
            func=(lambda input: ("Original Request: "
                                 + (input['original_question'] if 'original_question' in input and input['original_question'] else "")
                                 + '\n\nFind the opposite of the following: '
                                 + (input["aimie_answer"] if "aimie_answer" in input and input["aimie_answer"] else ""))),
            afunc=async_input_getter
        )

    def get_request_chat_message(self, state: State, parsed_response: Dict[str, Any]) -> str:
        return "Refute AIMIE_BOT's response, as you are the representative of the opposition of AIMIE's client."

    @property
    def personae_name(self) -> str:
        return "BOB"

    @property
    def system_role_name(self) -> str:
        return "system"
    
    def generate_configurable(self, input: CrossExaminationRequest) -> Dict[str, Any]:
        original_config = super().generate_configurable(input)
        original_config["configurable"]["use_enhanced_retriever"] = True
        return original_config
        
