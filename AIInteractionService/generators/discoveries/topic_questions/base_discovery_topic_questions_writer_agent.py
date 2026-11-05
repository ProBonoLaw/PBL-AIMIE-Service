

import orjson
import os
from types import CoroutineType
from typing_extensions import Any, Callable, Dict, Generic, List, Optional, Sequence, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document
from langchain_core.retrievers import RetrieverLike, RetrieverOutputLike
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_core.vectorstores import VectorStore
from langchain_openai import AzureOpenAIEmbeddings
from langgraph.graph import START, StateGraph

from ....db.azuresearch import AzureSearch
from ....db.cosmosdb_checkpointer import CosmosDBSaver
from ....db.cosmosdb_handler import CosmosDBHandler
from ...common import LawRetrieverProvider, BaseAgent, LawRetrieverProvider
from ....utils.formatters import extract_content_from_page, format_docs
from ....utils.history_only_retriever import HistoryOnlyRetriever
from .types import DiscoveryTopicQuestionsWriterAgentRequest, DiscoveryTopicQuestionsWriterOutput, DiscoveryState

T = TypeVar('T', bound=BaseChatModel)


class BaseDiscoveryTopicQuestionsWriterAgent(BaseAgent[T, DiscoveryTopicQuestionsWriterAgentRequest, DiscoveryTopicQuestionsWriterOutput], Generic[T]): # type: ignore
    def __init__(self, account_id: str, session_id: str, vector_store_address: str, vector_store_password:str, aoai_embeddings: AzureOpenAIEmbeddings, **kwargs: Any):
        super().__init__(account_id, session_id, **kwargs)
        self.__max_doc_count = kwargs.get("max_doc_count", 20)
        self.samples_vector_store: AzureSearch = AzureSearch(
            azure_search_endpoint=vector_store_address,
            azure_search_key=vector_store_password,
            index_name="generallegaltemplates_general",
            embedding_function=aoai_embeddings.embed_query,
            semantic_configuration_name='Primary',
            additional_search_client_options={"api_version": "2026-08-01-preview"},
            vector_search_dimensions=aoai_embeddings.dimensions
    )
    
    @property
    def max_doc_count(self) -> int:
        return self.__max_doc_count
    
    
    def get_prompt(self) -> ChatPromptTemplate:
        system_prompt = (
            "You are an attorney tasked with preparing a financial discovery for a "
            "an upcoming court hearing. The discovery is to be submitted to "
            "court.  Your job is generate questions for the type of "
            "discovery based on the context of the case. Be sure not to include "
            "terms like 'spouse' or 'husband' or 'wife' in the questions, "
            "if the subject's marital status is single. "
            "Attempt to generate at most 4 questions/requests. "
            "The discovery questions are to be based on topic {topic}, well-written, "
            "clear, and free of errors. If you find any issues, "
            "you should make corrections and provide suggestions for improvement. "
            "Considering evidence like bank statements, tax returns, check stubs, other "
            "financial documents, depositions, doctor's reports, police reports, "
            "and eyewitness statements to be high-quality sources. "
            "Do not repeat the same question multiple times, especially if it has "
            "been asked in the chat history, unless the topic is \"General\". "
            "If the topic is \"General\", you may ask questions that would force the "
            "target to provide additional information based on the chat history. "
            "In any case, be sure the questions are closed-ended. "
            "\n\n"
            "The following are some examples of questions that you can ask: "
            "{topic_questions}\n\n\n\n"
            "Context: {context}"
        )
        qa_prompt = ChatPromptTemplate(
            [
                ("system", system_prompt),
                ("assistant", "What are the questions that were asked perviously?"),
                ("human", "Previously asked questions: {chat_history}"),
                ("assistant", "Who is the target of the interrogatory?"),
                ("human", "The target of the interrogatory is {target}"),
                ("assistant", "What is the topic of the discovery?"),
                ("human", "The topic of the discovery is {topic}"),
                ("assistant", "What is this discovery about?"),
                ("human", "{input}"),
            ]
        )
        return qa_prompt
    
    def get_sample_questions_retriever(self) -> RetrieverLike:
        return self.samples_vector_store.as_retriever(
            search_type="semantic_hybrid_score_threshold",
            k=10,
            search_kwargs={'score_threshold': 0.5, 'score_type': 'reranker_score'})
    
    def get_retriever(self, 
                      vector_store: Optional[VectorStore] = None, 
                      context: Optional[List[Document]] = None, 
                      law_retriever: Optional[EnsembleRetriever] = None) -> RetrieverLike:
        if vector_store is None:
            return HistoryOnlyRetriever(
                context=context)
        return vector_store.as_retriever(
            search_type="semantic_hybrid",
            k=self.max_doc_count)
    
    def format_docs_without_metadata(self, inputs: Dict) -> str:
        context = inputs['topic_questions']
        if isinstance(context, str):
            try:
                metadata = orjson.loads(context)
                if isinstance(metadata, Sequence):
                    context = metadata
            except orjson.JSONDecodeError:
                pass
        return '\n\n'.join(
            extract_content_from_page(doc)
            for doc in context
        )
    
    def prepare_chain(self, prompt: ChatPromptTemplate, retriever: RetrieverOutputLike) -> Runnable[Dict[str, Any], Any]:
        llm_chain = RunnablePassthrough.assign(**{'context': lambda x: format_docs(x, self.max_doc_count)}).with_config(
            run_name="format_inputs"
        ) | RunnablePassthrough.assign(**{'topic_questions': self.format_docs_without_metadata}).with_config(
            run_name="format_topics_inputs"
        ) | prompt | self.llm.with_structured_output(DiscoveryTopicQuestionsWriterOutput)
        retrieval_samples = (lambda x: x["topic"]) | self.get_sample_questions_retriever()
        retrieval_chain_with = (
            RunnablePassthrough.assign(
                topic_questions=retrieval_samples.with_config(run_name="retrieve_sample_questions"),
            ).assign(answer=llm_chain)
        ).with_config(run_name="retrieval_chain")
        retrieval_docs = (lambda x: x["input"]) | retriever
        retrieval_chain = (
            RunnablePassthrough.assign(
                context=retrieval_docs.with_config(run_name="retrieve_documents"),
            ).assign(answer=retrieval_chain_with)
        ).with_config(run_name="retrieval_chain")
        

        return self.prepare_context_runnable(retrieval_chain)

    def prepare_output(self, result: Dict[str, Any]) -> DiscoveryTopicQuestionsWriterOutput:
        return DiscoveryTopicQuestionsWriterOutput(questions=result["questions"], topic=result["topic"], location=result["location"] if "location" in result else "")
        
    def personae_name(self) -> str:
        return "discovery_writer"
    
    def prepare_context_runnable(self, rag_chain: Runnable) -> Runnable:
        # Our graph consists only of one node:
        call_model = self.generate_call_model(rag_chain)
        workflow = StateGraph(state_schema=DiscoveryState)
        workflow.add_edge(START, "model")
        workflow.add_node("model", call_model) # type: ignore

        # Finally, we compile the graph with a checkpointer object.
        # This persists the state, in this case in memory.
        handler = CosmosDBHandler(os.environ['COSMOS_MESSAGE_HISTORY_ENDPOINT'],
                                  os.environ.get('COSMOS_MESSAGE_HISTORY_DATABASE', 'db_conversation_history'), 
                                  os.environ.get('COSMOS_MESSAGE_HISTORY_CONTAINER', 'messages2'))
        memory = CosmosDBSaver(handler)
        compiled_workflow = workflow.compile(checkpointer=memory, debug=False)
        return compiled_workflow

    def generate_call_model(self, rag_chain) -> Callable[[DiscoveryState], CoroutineType[Any, Any, Dict[str, Any]]]:
        # We then define a simple node that runs the `rag_chain`.
        # The `return` values of the node update the graph state, so here we just
        # update the chat history with the input message and response.
        async def call_model(state: DiscoveryState):
            if (state["topic"] == "General"):
                chat_history_raw = [message if isinstance(message, BaseMessage) and message.name != "topic" and message.name != self.personae_name() else None for message in state["chat_history"]]
                chat_history = [message for message in chat_history_raw if message is not None]
                state["chat_history"] = chat_history
            response = await rag_chain.ainvoke(state)
            llm_response = response["answer"]
            answer: DiscoveryTopicQuestionsWriterOutput = llm_response["answer"] 
            questions: List[str] = []
            if isinstance(answer, str):
                answer = orjson.loads(answer)
            if answer.questions:
                if isinstance(answer.questions, str):
                    answer.questions = orjson.loads(answer.questions)
            questions = answer.questions
            stringify_questions = "\n".join(questions)
            return {
                "input": state["input"],
                "topic": state["topic"],
                "target": state["target"],
                "chat_history": [
                    HumanMessage(content=f"Topic of Discovery: {state['topic']}", name="topic"),
                    AIMessage(stringify_questions, name=self.personae_name())
                ],
                "context": response["context"],
                "questions": questions,
                "sources": llm_response["sources"] if "sources" in llm_response else [],
                "location": response["location"] if "location" in response else ""
            }
        return call_model
    
    def system_role_name(self) -> str:
        return "system"