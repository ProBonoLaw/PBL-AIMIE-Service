from collections.abc import Mapping

from .types import BaseRequestModel
from .law_retriever_provider import LawRetrieverProvider
from ...utils.unique_multi_query_retriever import UniqueMultiQueryRetriever
from AIInteractionService.utils.token_types import TokenUsage, parse_token_usage
from AIInteractionService.utils.formatters import format_docs
from langchain_core.tools import StructuredTool
from langchain_core.tools import tool
from langchain_classic.globals import set_llm_cache
from langchain_core.runnables import Runnable, RunnableConfig, RunnableBranch, RunnableLambda
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike, BaseRetriever
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.vectorstores import VectorStore
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document
from langchain_core.language_models import LLM
from langchain_azure_ai.callbacks.tracers import AzureAIOpenTelemetryTracer
from abc import ABC, abstractmethod
from datetime import datetime
import logging
import orjson
import os
import re
from langsmith import RunTree
from typing_extensions import Any, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)


U = TypeVar('U', bound=BaseRequestModel)
V = TypeVar('V')


async def _on_start(input: RunTree | Dict[str, Any]) -> None:
    if isinstance(input, RunTree):
        id = input.id
        name = input.name
    elif isinstance(input, dict):
        id = input.get("id", "unknown")
        name = input.get("name", "unknown")
    logger.info(
        "chain.started",
        extra={"run_id": id, "run_name": name},
    )


async def _on_end(output: Dict[str, Any]) -> None:
    if isinstance(output, RunTree):
        id = output.id
        name = output.name
    elif isinstance(output, dict):
        id = output.get("id", "unknown")
        name = output.get("name", "unknown")
    logger.info(
        "chain.completed",
        extra={"run_id": id, "run_name": name},
    )


async def _on_error(error: Dict[str, Any]) -> None:
    logger.error("chain.error", extra={"error": error})


def replacer(match: re.Match):
    # Extract the content within the double quotes
    content = match.group('answer')
    # Replace unescaped \n with \\\n within the quoted content
    updated_content = content.replace("\'", "'").replace('\\n', '\n')
    json_content = orjson.dumps(updated_content)
    logging.info(f"Encoded content: {json_content}")
    return f'"answer\": {json_content}, \"sources\":'


class BaseAgent(Generic[U, V], ABC):
    def __init__(self,
                 account_id: str,
                 session_id: str,
                 **kwargs: Any):
        set_llm_cache(None)
        # set_verbose(False)
        # set_debug(False)
        self.account_id = account_id
        self.session_id = session_id
        logging.info(
            f"Creating agent with account_id: {account_id}, session_id: {session_id} and kwargs: {kwargs}")
        instantiate_llm = self.__getattribute__("instantiate_llm")
        if instantiate_llm is None:
            raise NotImplementedError(
                "The instantiate_llm method must be implemented in order to be used!")
        primary_config = kwargs.get("primary", {})
        self.llm: LLM = instantiate_llm(primary_config)
        self.llm.name = f"{self.personae_name}_primary_llm"
        self._primary_llm_bindings: Dict[str, Any] = {}
        secondary_config: LLM = kwargs.get("secondary", {})
        self.secondary_llm: LLM = instantiate_llm(secondary_config)
        self.secondary_llm.name = f"{self.personae_name}_secondary_llm"
        self.primary_prompt: List[str] = kwargs.get("primary_prompt", [])

    def generate_response(self,
                          input: U,
                          vector_store: Optional[VectorStore] = None,
                          law_retriever_provider: Optional[LawRetrieverProvider] = None,
                          context: Optional[List[Document]] = None) -> V:
        prompt = self.get_prompt()
        self.vector_store = vector_store
        self.law_retriever_provider = law_retriever_provider
        bind_tools = getattr(self.llm, "bind_tools", None)
        if callable(bind_tools):
            case_context = StructuredTool.from_function(
                func=self.case_context,
                name="case_context",
                description="Retrieve detailed case information."
            )
            legal_context = StructuredTool.from_function(
                func=self.legal_context,
                name="legal_context",
                description="Retrieve legal information."
            )
            self.llm = bind_tools([case_context, legal_context])
        self._primary_llm_bindings = self.adjust_primary_llm(input, self.llm)
        law_retriever = law_retriever_provider.get_law_retriever(
        ) if law_retriever_provider else None
        retriever = self.get_retriever(vector_store, context, law_retriever)
        config = self.generate_configurable(input)
        enhanced_retriever = self.enhance_retriever(retriever, config)
        history_aware_chain = self.prepare_history_aware_chain(
            enhanced_retriever)
        chain = self.prepare_chain(prompt, history_aware_chain)
        input_request = dict(input)
        input_request["response_detail_instruction"] = self.get_response_detail_instruction(input)
        if "now" not in input_request:
            input_request["now"] = datetime.now().isoformat()
        result = chain.invoke(input=input_request,
                              config=config)
        if result is None:
            raise Exception("No results returned from the chain")
        return self.prepare_output(result)

    async def agenerate_response(self,
                                 input: U,
                                 vector_store: Optional[VectorStore] = None,
                                 law_retriever_provider: Optional[LawRetrieverProvider] = None,
                                 context: Optional[List[Document]] = None) -> V:
        prompt = self.get_prompt()
        self.vector_store = vector_store
        self.law_retriever_provider = law_retriever_provider
        bind_tools = getattr(self.llm, "bind_tools", None)
        if callable(bind_tools):
            case_context = StructuredTool.from_function(
                func=self.case_context,
                name="case_context",
                description="Retrieve detailed case information."
            )
            legal_context = StructuredTool.from_function(
                func=self.legal_context,
                name="legal_context",
                description="Retrieve legal information."
            )
            self.llm = bind_tools([case_context, legal_context])

        self._primary_llm_bindings = self.adjust_primary_llm(input, self.llm)
        law_retriever = law_retriever_provider.get_law_retriever(
        ) if law_retriever_provider else None
        retriever = self.get_retriever(vector_store, context, law_retriever)
        config = self.generate_configurable(input)
        enhanced_retriever = self.enhance_retriever(retriever, config)
        history_aware_chain = self.prepare_history_aware_chain(
            enhanced_retriever)
        chain = self.prepare_chain(prompt, history_aware_chain)
        input_request = dict(input)
        input_request["response_detail_instruction"] = self.get_response_detail_instruction(input)
        if "now" not in input_request:
            input_request["now"] = datetime.now().isoformat()
        result = await chain.ainvoke(input=input_request, config=config)
        if result is None:
            raise Exception("No results returned from the chain")
        return self.prepare_output(result)

    def case_context(self, query: str) -> str:
        '''
        A tool that can be used to retrieve additional context about the case. This is meant to be used by the agent when it needs more information about a case in order to answer a question. It uses the same retriever as the one used in the chain, but can be called separately by the agent.
        Args:
            query: The query to retrieve additional context about the case.
        Returns:
            A string containing the additional context about the case.
        '''
        logger.info("tool.case_context", extra={"query": query})
        if self.vector_store is None:
            return format_docs([])
        retriever = self.vector_store.as_retriever(
            search_type="semantic_hybrid",
            k=self.max_doc_count)
        results = retriever.invoke(query)
        return format_docs(results)

    def legal_context(self, query: str) -> str:
        '''
        A tool that can be used to retrieve additional legal context. This is meant to be used by the agent when it needs more information about legal precedents or similar cases in order to answer a question. It uses the law retriever provider to get a law retriever, which is then used to retrieve relevant legal documents.
        Args:
            query: The query to retrieve additional legal context.
        Returns:
            A string containing the additional legal context.
        '''
        logger.info("tool.legal_context", extra={"query": query})
        if self.law_retriever_provider is None:
            return format_docs([])
        law_retriever = self.law_retriever_provider.get_law_retriever()
        results = law_retriever.invoke(query)
        return format_docs(results)

    def generate_configurable(self, input: U) -> RunnableConfig:
        """
        Generate a configurable response based on the input.
        This method is used to generate a response that can be configured with additional parameters.
        Args:
            input: The input to the agent.
        Returns:
            A dictionary containing the response and any additional configuration.
        """
        azure_tracer = AzureAIOpenTelemetryTracer(
            connection_string=os.environ.get(
                "APPLICATIONINSIGHTS_CONNECTION_STRING"),
            enable_content_recording=True,
            name=self.personae_name,
            agent_id=f"{self.personae_name}_{self.account_id}_{self.session_id}",
        )
        use_enhanced_retriever = self._get_use_enhanced_retriever(input)
        return {
            "configurable": {
                "thread_id": self.session_id,
                "account_id": self.account_id,
                "arbitrary_types_allowed": True,
                "use_enhanced_retriever": use_enhanced_retriever
            },
            "callbacks": [azure_tracer]
        }

    @staticmethod
    def _get_use_enhanced_retriever(input: U) -> bool:
        if isinstance(input, Mapping):
            for key in ("use_enhanced_retriever", "useEnhancedRetriever", "UseEnhancedRetriever"):
                if key in input:
                    return input[key]
            return True

        return getattr(input, "use_enhanced_retriever", True)

    def adjust_primary_llm(self, input: U, llm: LLM) -> Dict[str, Any]:
        """
        Return request-specific primary LLM arguments.

        Child classes can override this to supply parameters that must be bound to
        the runnable ultimately invoked by the chain.
        Args:
            input: The input to the agent.
            llm: The primary language model.
        """
        return {}

    def bind_primary_llm(self, runnable: Runnable) -> Runnable:
        """Bind request-specific arguments to the runnable used by the chain."""
        if not self._primary_llm_bindings:
            return runnable
        return runnable.bind(**self._primary_llm_bindings)

    @staticmethod
    def get_response_detail_instruction(input: U) -> str:
        """Return an application-enforced answer-detail instruction for the request."""
        verbosity_level = getattr(input, "verbosity_level", None)
        level = getattr(verbosity_level, "value", verbosity_level)
        instructions = {
            "low": (
                "Answer in one concise sentence of no more than 50 words. Include only "
                "the direct answer and essential qualification."
            ),
            "medium": (
                "Answer in one short paragraph of 80 to 140 words when the record supports "
                "it. State the direct answer, then the most relevant supporting facts and "
                "qualifications."
            ),
            "high": (
                "Answer in 2 to 4 short paragraphs totaling 180 to 300 words when the record "
                "supports it. State the direct answer first, then explain relevant background, "
                "facts, dates or roles, and necessary qualifications. Do not pad or invent facts."
            ),
        }
        return instructions.get(level, "Answer at the normal level of detail appropriate to the question.")

    def __log_generate_token_usage(self, llm: LLM, tokens: TokenUsage, is_secondary: bool = False) -> None:
        if llm and tokens:
            llm_type = getattr(llm, "_llm_type", None)
            if callable(llm_type):  # defensive for older/custom implementations
                llm_type = llm_type()

            # Configured model name (common patterns across integrations)
            model = (
                # langchain-openai v0.3+
                getattr(llm, "model", None) or
                getattr(llm, "model_name", None) or     # legacy
                getattr(llm, "model_id", None)
            )

            lc_id = ','.join(llm.lc_id()) if hasattr(llm, "lc_id") else None

            logging.warning(
                "token_usage",
                extra={
                    "microsoft.custom_event.name": "token_usage",
                    "accountId": self.account_id,
                    "sessionId": self.session_id,
                    "inputTokens": tokens.input_tokens,
                    "outputTokens": tokens.output_tokens,
                    "totalTokens": tokens.total_tokens,
                    "isSecondaryLLM": is_secondary,
                    "type": llm_type,
                    "model": model,
                    "lc_id": lc_id,
                    "reasoningTokens": tokens.output_token_details.reasoning if tokens.output_token_details is not None and tokens.output_token_details.reasoning is not None else 0,
                },
            )

    def generate_listener_for_primary_llm_with_structured_output(self):
        async def on_end(run: Any) -> None:
            out = getattr(run, "output", None) or getattr(run, "outputs", None)
            if isinstance(out, dict) and "raw" in out:
                msg = out["raw"]
                tokens = parse_token_usage(getattr(msg, "usage_metadata", {}))
                self.__log_generate_token_usage(
                    llm=self.llm, tokens=tokens, is_secondary=False)
        return on_end

    def generate_listener_for_secondary_llm(self):
        def on_end(run: Any) -> None:
            out = getattr(run, "output", None) or getattr(run, "outputs", None)
            if isinstance(out, dict) and "llm_output" in out:
                msg: Dict = out["llm_output"]
                usage = msg.get("token_usage") or msg.get("usage") or {}
                tokens = parse_token_usage(usage)
                self.__log_generate_token_usage(
                    llm=self.secondary_llm, tokens=tokens, is_secondary=True)
        return on_end

    def enhance_retriever(self, retriever: RetrieverLike, configurable: RunnableConfig) -> RetrieverLike:
        '''
        Enhance the retriever with additional functionality if needed.  This uses the MultiQueryRetriever and 
        secondary_llm to generate queries for the retriever.
        Args:
            retriever: The retriever object to enhance.
        Returns:
            The enhanced retriever object.
        '''

        def response(x: Any) -> RetrieverLike:
            logger.info("retriever.enhance", extra={"input": str(x)})
            return retriever

        if isinstance(retriever, BaseRetriever):
            on_end = self.generate_listener_for_secondary_llm()
            mq_retriever = UniqueMultiQueryRetriever.from_llm(
                retriever, self.secondary_llm.with_alisteners(on_end=on_end), include_original=False)
            mq_retriever.max_doc_count = self.max_doc_count
            return RunnableBranch(
                (lambda x: isinstance(x, Dict) and x.get("use_enhanced_retriever", True),
                 mq_retriever
                 .with_alisteners(on_start=_on_start,
                                  on_end=_on_end,
                                  on_error=_on_error)
                 .with_listeners(on_start=lambda x: logging.info(f"MultiQueryRetriever started with input: {x}"),
                                 on_end=lambda x: logging.info(
                                     f"MultiQueryRetriever ended with output: {x}"),
                                 on_error=lambda x: logging.error(f"MultiQueryRetriever error with input: {x}"))
                 .with_config(run_name="multi_query_retriever")),
                RunnableLambda(response)
            )
        else:
            return retriever

    def prepare_history_aware_chain(self, retriever: RetrieverLike) -> RetrieverOutputLike:
        """
        Create a history-aware retrieval chain that uses the given language model and retriever.

        Args:
            llm: The language model to use for generating a search term given chat history
            retriever: The retriever object that takes a string as input and outputs a list of Documents.
        Returns:
            An LCEL Runnable. The runnable input must take in `input`, and if there is chat history should take it in the form of `chat_history`.
            The Runnable output is a list of Documents
        Note:
            This method should be implemented by the child class, otherwise it will return the retriever as is.
        """
        return retriever

    def replace_newlines_in_double_quoted_strings(self, input_string):
        """
        Replaces all \n characters with \\\n only within double-quoted strings in the given input string.

        Args:
            input_string (str): The input string containing double-quoted substrings.

        Returns:
            str: The modified string with \n replaced by \\\n inside double-quoted strings.
        """

        # Pattern to match content within double quotes (excluding the quotes themselves)
        pattern = r'"answer":[\s|\n]*"(?P<answer>(.|\n)*)"[\s|\n]*,[\s|\n]*"sources":'
        # Replace matches using the replacer function
        return re.sub(pattern, replacer, input_string, flags=re.MULTILINE)

    @abstractmethod
    def get_retriever(self,
                      vector_store: Optional[VectorStore] = None,
                      context: Optional[List[Document]] = None,
                      law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
        pass

    @abstractmethod
    def get_prompt(self) -> ChatPromptTemplate:
        pass

    @abstractmethod
    def prepare_chain(self,
                      prompt: ChatPromptTemplate,
                      retriever: RetrieverOutputLike) -> Runnable[Dict[str, Any], Any]:
        pass

    @abstractmethod
    def prepare_output(self, output: Any) -> V:
        pass

    @property
    @abstractmethod
    def personae_name(self) -> str:
        pass

    @property
    @abstractmethod
    def system_role_name(self) -> str:
        pass

    @property
    @abstractmethod
    def max_doc_count(self) -> int:
        pass
