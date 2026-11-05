
from abc import ABC, abstractmethod
import orjson
import logging
import os
from types import CoroutineType
from typing import Any, Callable, Dict, Generic, Type, TypeVar, Union, cast

from langchain_azure_ai.callbacks.tracers import AzureAIOpenTelemetryTracer
from langchain_core.retrievers import RetrieverOutputLike, RetrieverOutput, BaseRetriever
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnablePassthrough, RunnableBranch, RunnableLambda, RunnableConfig
from langchain_core.language_models import LanguageModelInput
from langgraph.graph import START, StateGraph, END
from langchain_core.exceptions import OutputParserException

from pydantic import BaseModel

from AIInteractionService.utils.result import get_answer

from ...db.cosmosdb_checkpointer import CosmosDBSaver
from ...db.cosmosdb_handler import CosmosDBHandler
from .base_agent import BaseAgent, BaseRequestModel
from .types import AnswersWithSources, FormalAnswersWithSources
from ...utils.formatters import format_docs
from ...utils.state import BaseState

U = TypeVar('U', bound=BaseRequestModel)
V = TypeVar('V')
W = TypeVar('W', bound=BaseState)


class BaseHistoryAwareAgent(BaseAgent[U, V], Generic[U, V, W], ABC):
    def __init__(self, account_id: str, session_id: str, **kwargs: Any):
        super().__init__(account_id, session_id, **kwargs)

    def prepare_history_aware_chain(self, retriever: RetrieverOutputLike) -> RetrieverOutputLike:
        if self.check_chat_history:
            logging.info("Creating historian retrieval chain")
            ### Contextualize question ###
            contextualize_q_system_prompt = (
                "Given a chat history and the latest user question "
                "which might reference context in the chat history, "
                "formulate a standalone question which can be understood "
                "without the chat history. Do NOT answer the question, "
                "just reformulate it if needed and otherwise return it as is."
                "If an answer is found in the chat history and it contains sources, "
                "you must include all docIds. "
                "Remember that a section is synonymous as a header."
            )
            contextualize_q_prompt = ChatPromptTemplate.from_messages(
                [
                    ("assistant", contextualize_q_system_prompt),
                    MessagesPlaceholder("chat_history"),
                    ("human", "{input}"),
                ]
            )

            retrieve_documents: RetrieverOutputLike = RunnableBranch(
                (
                    # Both empty string and empty list evaluate to False
                    lambda x: not isinstance(x, str) and (not isinstance(
                        x, dict) or not x.get("chat_history", False)),
                    # If no chat history, then we just pass input to retriever
                    self.generate_input_retriever() | retriever,
                ),
                # If chat history, then we pass inputs to LLM chain, then to retriever
                cast(
                    Runnable[Any, RetrieverOutput],
                    contextualize_q_prompt | self.secondary_llm | StrOutputParser() | retriever,
                ),
            ).with_config(run_name=self.personae_name + "_chat_history_retriever_chain")
            return retrieve_documents
        else:
            return (self.generate_input_retriever() | retriever).with_config(run_name=self.personae_name + "_default_retriever_chain")

    def generate_configurable(self, input: U) -> RunnableConfig:
        """
        Generate a configuration for the agent based on the input.
        This method can be overridden by child classes to provide custom configurations.

        Args:
            input (U): The input data for the agent.

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
                "history_max_count": 4
            },
            "callbacks": [azure_tracer]
        }

    @abstractmethod
    def generate_input_retriever(self) -> RunnableLambda[V, str]:
        pass

    def prepare_context_runnable(self, rag_chain: Runnable) -> Runnable:
        # Our graph consists only of one node:
        call_model = self.generate_call_model(rag_chain)
        workflow = StateGraph(state_schema=self.output_class_type)
        workflow.add_node("model", call_model)  # type: ignore
        workflow.add_edge(START, "model")
        workflow.add_edge("model", END)

        # Finally, we compile the graph with a checkpointer object.
        # This persists the state, in this case in memory.
        handler = CosmosDBHandler(
            os.environ['COSMOS_MESSAGE_HISTORY_ENDPOINT'],
            os.environ.get('COSMOS_MESSAGE_HISTORY_DATABASE',
                           'db_conversation_history'),
            os.environ.get('COSMOS_MESSAGE_HISTORY_CONTAINER', 'messages2'))
        memory = CosmosDBSaver(handler)
        compiled_workflow = workflow.compile(checkpointer=memory,
                                             debug=False,
                                             name=self.personae_name + "_history_aware_workflow")
        return compiled_workflow

    def retrieval_docs(
            self,
            retriever: Union[BaseRetriever, Runnable[U, RetrieverOutput]]) -> RetrieverOutputLike:
        if not isinstance(retriever, BaseRetriever):
            retrieval_docs: Runnable[U, RetrieverOutput] = retriever
        else:
            retrieval_docs = (self.generate_question_value() | retriever).with_config(
                run_name=self.personae_name + "_retrieval_docs")
        return retrieval_docs

    @abstractmethod
    def prepare_llm_for_chain(self) -> Runnable[LanguageModelInput, Dict[Any, Any] | BaseModel]:
        """
        Prepare the LLM for the chain. This method should be implemented by the child class.   
        """
        pass

    def generate_question_value(self) -> Runnable:
        return RunnablePassthrough.assign(
            question=self.generate_input_retriever()  # type: ignore
        ).with_config(run_name="generate_question_value")

    def prepare_chain(self, prompt: ChatPromptTemplate, retriever: RetrieverOutputLike) -> Runnable[Dict[str, Any], Any]:
        on_end = self.generate_listener_for_primary_llm_with_structured_output()
        llm_chain = (RunnablePassthrough.assign(**{'context': lambda x: format_docs(x, self.max_doc_count)}).with_config(
            run_name="format_inputs"
        ) | prompt | self.prepare_llm_for_chain().with_alisteners(on_end=on_end)).with_config(run_name=self.personae_name+"_llm_chain")
        retrieval_chain = (
            RunnablePassthrough.assign(
                context=self.retrieval_docs(retriever).with_config(
                    run_name="retrieve_documents"),
            ).assign(answer=llm_chain)
        ).with_config(run_name=self.personae_name+"_request_fulfillment_chain")
        return self.prepare_context_runnable(retrieval_chain)

    def generate_call_model(self, rag_chain: Runnable) -> Callable[[W], Any]:

        # We then define a simple node that runs the `rag_chain`.
        # The `return` values of the node update the graph state, so here we just
        # update the chat history with the input message and response.
        async def call_model(state: W):
            llm_response = None
            try:
                pre_chat_history = state.get("chat_history", [])
                if len(pre_chat_history) > 4:
                   # We only keep the last 4 messages in the chat history
                    state["chat_history"] = pre_chat_history[-4:]
                logging.info(f"Running RAG chain.")
                response = await rag_chain.ainvoke(state)
                llm_response = get_answer(response)
                parsed_response = self.parse_results(llm_response)
            except orjson.JSONDecodeError as de:
                logging.error(
                    f"Error parsing JSON Trying again!: {str(de)} --> {llm_response}")
                response = await rag_chain.ainvoke(state)
                llm_response = get_answer(response)
                parsed_response = self.parse_results(llm_response)
            except OutputParserException as de:
                if llm_response is None:
                    logging.error(
                        f"Error parsing JSON Trying again!: {str(de)}")
                else:
                    logging.error(
                        f"Error parsing JSON Trying again!: {str(de)} --> {llm_response}")
                response = await rag_chain.ainvoke(state)
                llm_response = get_answer(response)
                parsed_response = self.parse_results(llm_response)
            except Exception as e:
                logging.error(
                    f"Error parsing JSON Trying again!: {str(e)} --> {llm_response}")
                response = await rag_chain.ainvoke(state)
                llm_response = get_answer(response)
                parsed_response = self.parse_results(llm_response)
            if isinstance(parsed_response, AnswersWithSources) or isinstance(parsed_response, FormalAnswersWithSources):
                parsed_response = self.parse_results(parsed_response)
            answer = parsed_response["answer"]
            return {
                "chat_history": [
                    HumanMessage(self.get_request_chat_message(
                        state, parsed_response)),
                    AIMessage(answer, name=self.personae_name),
                ],
                "context": response["context"],
                "answer": answer,
                "sources": parsed_response["sources"] if "sources" in parsed_response else [],
                "raw_response": llm_response,
            }
        
        return call_model
    
    def parse_results(self, llm_response):
            """
            Docstring for parse_results
            
            :param self: Description
            :param llm_response: The response from the language model.
            :return: Parsed response as a dictionary.
            """
            if isinstance(llm_response, AIMessage):
                return self.__parse_json_output(llm_response)
            elif isinstance(llm_response, str):
                return orjson.loads(llm_response)
            elif isinstance(llm_response, dict):
                return llm_response
            elif isinstance(llm_response, AnswersWithSources):
                return llm_response.model_dump()
            else:
                raise OutputParserException(
                        f"Unexpected response type: {type(llm_response)}")

    def __parse_json_output(self, answer: AIMessage) -> Dict[str, Any]:
        if isinstance(answer, AIMessage):
            new_answer = answer.content
            if isinstance(new_answer, dict):
                new_answer = orjson.dumps(new_answer).decode("utf-8")
            elif isinstance(new_answer, list):
                new_answer = orjson.dumps(new_answer).decode("utf-8")
            if (new_answer.startswith("```json") and new_answer.endswith("```")):
                new_answer = new_answer[7:-3]
            if '’' in new_answer:
                new_answer = new_answer.replace('’', "'")
            new_answer = self.replace_newlines_in_double_quoted_strings(
                new_answer)
            logging.info(f"Answer to review: {new_answer}")
            new_answer = orjson.loads(new_answer)
            return new_answer
        if isinstance(answer, Dict) and 'answer' in answer:
            return answer
        if isinstance(answer, str):
            return {
                "answer": answer
            }

    @property
    def check_chat_history(self) -> bool:
        return False

    @property
    @abstractmethod
    def output_class_type(self) -> Type:
        pass

    @abstractmethod
    def get_request_chat_message(
            self,
            state: W,
            parsed_response: Dict[str, Any]) -> str:
        pass
