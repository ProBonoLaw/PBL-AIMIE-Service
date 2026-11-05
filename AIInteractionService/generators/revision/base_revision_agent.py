
import os
from typing import Any, Dict, List, Optional, Sequence, cast

from langchain_azure_ai.callbacks.tracers import AzureAIOpenTelemetryTracer
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnablePassthrough, RunnableLambda, RunnableConfig
from langchain_core.language_models import LanguageModelInput
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.vectorstores import VectorStore
from pydantic import BaseModel

from .types import RevisionRequest
from ..common import BaseAgent, AnswersWithSources, AgentResult
from ...utils.history_only_retriever import HistoryOnlyRetriever
from ...utils.formatters import format_docs


class BaseRevisionAgent(BaseAgent[RevisionRequest, AgentResult]):
    def __init__(self, account_id: str,
                 session_id: str,
                 max_doc_count: int,
                 **kwargs: Any):
        self.__max_doc_count = max_doc_count or 20
        super().__init__(account_id, session_id, **kwargs)

    @property
    def max_doc_count(self) -> int:
        return self.__max_doc_count
        

    def get_prompt(self) -> ChatPromptTemplate:
        instructions: List[MessageLikeRepresentation] = [
                {"role": self.system_role_name, "content": self.primary_prompt},
                {"role": self.system_role_name, "content": "Context:\n{context}"},
                {"role": self.system_role_name, "content": "Response-detail requirement:\n{response_detail_instruction}"},
                ("assistant", "What is the Original Statement needing revision?"),
                ("human", "Original Statement: {statement}\n\n"),
                ("assistant", "What was the feedback about the original statement?"),
                ("human", "The feedback was: {feedback}\n\n")
            ]
        
        additional_instructions = self.additional_prompt
        if additional_instructions:
            instructions.extend(additional_instructions)
        qa_prompt = ChatPromptTemplate(messages=instructions)

        return qa_prompt
    
    @property
    def additional_prompt(self) -> Optional[Sequence[MessageLikeRepresentation]]:
        return None

    def get_retriever(self,
                      vector_store: Optional[VectorStore],
                      context: Optional[List[Document]],
                      law_retriever: Optional[EnsembleRetriever] = None,
                      ) -> RetrieverLike:
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
    
    def generate_configurable(self, input: RevisionRequest) -> RunnableConfig:
        """
        Generate a RunnableConfig for the agent based on the input request.

        Args:
            input (RevisionRequest): The input request containing necessary parameters.

        Returns:
            RunnableConfig: The configuration for the agent.
        """
        azure_tracer = AzureAIOpenTelemetryTracer(
            connection_string=os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"),
            enable_content_recording=True,
            name=self.personae_name,
            agent_id=f"{self.personae_name}_{self.account_id}_{self.session_id}",
        )
        return {
            "configurable": {
                "thread_id": self.session_id,
                "account_id": self.account_id,
                "arbitrary_types_allowed": True,
                "use_retrievers": input.use_retrievers
            },
            "callbacks": [azure_tracer]
        }
    
    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        return self.bind_primary_llm(
            self.llm.with_structured_output(AnswersWithSources, include_raw=True)
        )
    

    def prepare_chain(self, prompt: ChatPromptTemplate, retriever: RetrieverOutputLike) -> Runnable[Dict[str, Any], Any]:
        on_end = self.generate_listener_for_primary_llm_with_structured_output()
        # LLM chain setup
        llm_chain = (
            RunnablePassthrough.assign(context=lambda x: format_docs(x, self.max_doc_count))
            .with_config(run_name="format_inputs")
            | prompt
            | self.prepare_llm_for_chain().with_alisteners(on_end=on_end)
        )

        # Truncate statement to 2800 characters
        truncate_statement = RunnableLambda(lambda x: cast(Dict[str, Any], x)["statement"][:2800] if len(cast(Dict[str, Any], x)["statement"]) > 2800 else cast(Dict[str, Any], x)["statement"])

        # Conditional retriever logic
        def maybe_retrieve(input: str, config: RunnableConfig):
            use_retrievers = True
            if config and "configurable" in config:
                configurable = config["configurable"] if "configurable" in config else {}
                use_retrievers = configurable.get("use_retrievers", True)
            if use_retrievers:
                return retriever.invoke(input, config=config)
            else:
                return HistoryOnlyRetriever(context=[]).invoke(input, config=config)

        conditional_retriever = RunnableLambda(maybe_retrieve)

        # Full retrieval chain
        retrieval_chain = (
            RunnablePassthrough
            .assign(context=truncate_statement | conditional_retriever)
            .assign(answer=llm_chain.with_retry(stop_after_attempt=3))
            .with_config(run_name="retrieval_chain")
        )

        return retrieval_chain


    @property
    def personae_name(self) -> str:
        return "AIMIE the Fact Finder"
    
    @property
    def system_role_name(self) -> str:
        return "system"
    
    def enhance_retriever(self, retriever: RetrieverLike, configurable: RunnableConfig) -> RetrieverLike:
        """
        Deactivate the enhance_retriever method as it doesn't add much value here.

        Args:
            retriever (RetrieverLike): The retriever to enhance.
            
        """
        return retriever
    