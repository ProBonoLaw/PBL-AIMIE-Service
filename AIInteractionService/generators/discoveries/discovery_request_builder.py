
import logging
from typing_extensions import Any, List, Optional, TypedDict

import anthropic
from langchain_core.vectorstores import VectorStore
import openai
from langchain_openai import AzureOpenAIEmbeddings

from AIInteractionService.generators.common.law_retriever_provider import LawRetrieverProvider
from ...utils.common_types import Source
from .anthropic_discovery_request_writer import AnthropicDiscoveryRequestWriterAgent
from .azure_open_ai_discovery_request_writer import AzureOpenAiDiscoveryRequestWriterAgent
from .base_discovery_request_writer import DiscoveryRequestWriterAgentRequest
from .refine import AzureOpenAiDiscoveryRequestRefinementWriterAgent, DiscoveryRequestRefinementWriterAgentRequest
from .topic_questions import DiscoveryTopicQuestionsWriterAgentRequest, AzureOpenAiDiscoveryTopicQuestionsWriterAgent, AnthropicChatDiscoveryTopicQuestionsWriterAgent, DiscoveryTopicQuestionsWriterOutput
from .cross_examination import AzureOpenAiDiscoveryCrossExaminationAgent, DiscoveryCrossExaminationRequest
from .types import DiscoveryBuilderOutput, TopicQuestions


class DiscoveryRequestBuilder:
    def __init__(self, account_id: str,
                 session_id: str,
                 vector_store_address: str,
                 vector_store_password: str,
                 aoai_embeddings: AzureOpenAIEmbeddings,
                 law_retriever_provider: LawRetrieverProvider,
                 **kwargs: Any):
        self.account_id = account_id
        self.session_id = session_id
        self.law_provider = law_retriever_provider
        self.primary_topic_questions_agent = AzureOpenAiDiscoveryTopicQuestionsWriterAgent(
            account_id, session_id, self.law_provider, vector_store_address, vector_store_password, aoai_embeddings, **kwargs)
        self.backup_topic_questions_agent = AnthropicChatDiscoveryTopicQuestionsWriterAgent(
            account_id, session_id, self.law_provider, vector_store_address, vector_store_password, aoai_embeddings, **kwargs)
        self.primary_request_agent = AzureOpenAiDiscoveryRequestWriterAgent(
            account_id, session_id, self.law_provider, **kwargs)
        self.backup_request_agent = AnthropicDiscoveryRequestWriterAgent(
            account_id, session_id, self.law_provider, **kwargs)
        self.bob_refute_agent = AzureOpenAiDiscoveryCrossExaminationAgent(
            account_id, session_id, self.law_provider, **kwargs)
        self.question_refinement_agent = AzureOpenAiDiscoveryRequestRefinementWriterAgent(
            account_id, session_id, self.law_provider, **kwargs)
        

    def generate_response(self,
                          input: str,
                          location: str,
                          hearing_type: str,
                          topics: List[str],
                          target: str,
                          vector_store: VectorStore) -> DiscoveryBuilderOutput:
        list_of_topic_questions: List[TopicQuestions] = []
        for topic in topics:
            request = DiscoveryTopicQuestionsWriterAgentRequest(
                input=input, topic=topic, target=target, location=location)
            try:
                topic_results = self.primary_topic_questions_agent.generate_response(
                    request, vector_store)
            except openai.BadRequestError as bre:
                logging.warning(
                    "Error invoking primary retrieval chain for generating rhetoric.  Trying alternative chain. (%s - %s)", self.account_id, self.session_id)
                logging.error(bre)
                try:
                    topic_results = self.backup_topic_questions_agent.generate_response(
                        request, vector_store)
                except anthropic.BadRequestError as bre:
                    logging.error(bre)
                    logging.error(
                        "Error invoking alternative retrieval chain for generating rhetoric. (%s - %s)", self.account_id, self.session_id)
            if topic_results:
                new_topic_results = TopicQuestions(
                    topic=topic_results.topic, questions=topic_results.questions, sources=[])
                new_topic_questions: List[str] = []
                new_sources: Optional[List[Source]] = []
                for topic_question in topic_results.questions:
                    refute = self._generate_refute(
                        input, topic, target, topic_question, location, vector_store)
                    if refute:
                        refinement_request = DiscoveryRequestRefinementWriterAgentRequest(
                            input=input, topic=topic, target=target, aimie_question=topic_question, bob_retort=refute, location=location, hearing_type=hearing_type)
                        refined_questions = self.question_refinement_agent.generate_response(
                            refinement_request, vector_store)
                        if refined_questions:
                            new_topic_questions.extend(
                                refined_questions.refine_questions)
                            new_sources.extend(refined_questions.sources)
                new_topic_results["questions"] = new_topic_questions
                new_topic_results["sources"] = new_sources
                list_of_topic_questions.append(new_topic_results)
            else:
                list_of_topic_questions.append(TopicQuestions(
                    topic=topic, questions=[], sources=[]))

        return self._generate_discovery_request(input, location, hearing_type, target, list_of_topic_questions)
    
    async def agenerate_response(self,
                          input: str,
                          location: str,
                          hearing_type: str,
                          topics: List[str],
                          target: str,
                          vector_store: VectorStore) -> DiscoveryBuilderOutput:
        list_of_topic_questions: List[TopicQuestions] = []
        for topic in topics:
            request = DiscoveryTopicQuestionsWriterAgentRequest(
                input=input, topic=topic, target=target, location=location)
            try:
                topic_results = await self.primary_topic_questions_agent.agenerate_response(
                    request, vector_store)
            except openai.BadRequestError as bre:
                logging.warning(
                    "Error invoking primary retrieval chain for generating rhetoric.  Trying alternative chain. (%s - %s)", self.account_id, self.session_id)
                logging.error(bre)
                try:
                    topic_results = await self.backup_topic_questions_agent.agenerate_response(
                        request, vector_store)
                except anthropic.BadRequestError as bre:
                    logging.error(bre)
                    logging.error(
                        "Error invoking alternative retrieval chain for generating rhetoric. (%s - %s)", self.account_id, self.session_id)
            if topic_results:
                new_topic_results = TopicQuestions(
                    topic=topic_results.topic, questions=topic_results.questions, sources=[])
                new_topic_questions: List[str] = []
                new_sources: Optional[List[Source]] = []
                for topic_question in topic_results.questions:
                    refute = await self._agenerate_refute(
                        input, topic, target, topic_question, location, vector_store)
                    if refute:
                        refinement_request = DiscoveryRequestRefinementWriterAgentRequest(
                            input=input, topic=topic, target=target, aimie_question=topic_question, bob_retort=refute, location=location, hearing_type=hearing_type)
                        refined_questions = await self.question_refinement_agent.agenerate_response(
                            refinement_request, vector_store)
                        if refined_questions:
                            new_topic_questions.extend(
                                refined_questions.refine_questions)
                            new_sources.extend(refined_questions.sources)
                new_topic_results["questions"] = new_topic_questions
                new_topic_results["sources"] = new_sources
                list_of_topic_questions.append(new_topic_results)
            else:
                list_of_topic_questions.append(TopicQuestions(
                    topic=topic, questions=[], sources=[]))

        return await self._agenerate_discovery_request(input, location, hearing_type, target, list_of_topic_questions)

    def _generate_discovery_request(self, input: str, location: str, hearing_type: str, target: str, list_of_topic_questions: List[TopicQuestions]) -> DiscoveryBuilderOutput:
        questions = [DiscoveryTopicQuestionsWriterOutput(
            topic=topic["topic"], questions=topic["questions"], location=location) for topic in list_of_topic_questions for x in topic["questions"]]
        try:
            request_input = DiscoveryRequestWriterAgentRequest(
                questions=questions,
                input=input,
                hearing_type=hearing_type,
                target=target,
                location=location)
            request_results = self.primary_request_agent.generate_response(
                request_input)
            return DiscoveryBuilderOutput(discovery_order=request_results.discovery_order, questions_by_topic=list_of_topic_questions, has_error=False)
        except openai.BadRequestError as bre:
            logging.warning(
                "Error invoking primary agent.  Trying alternative chain. (%s - %s)", self.account_id, self.session_id)
            logging.error(bre)
            try:
                request_input = DiscoveryRequestWriterAgentRequest(
                    questions=questions,
                    input=input,
                    hearing_type=hearing_type,
                    target=target,
                    location=location)
                request_results = self.backup_request_agent.generate_response(
                    request_input)
                return DiscoveryBuilderOutput(
                    discovery_order=request_results.discovery_order,
                    questions_by_topic=list_of_topic_questions,
                    has_error=False)
            except anthropic.BadRequestError as bre:
                logging.error(bre)
                logging.error(
                    "Error invoking alternative agent for generating discovery request. (%s - %s)",
                    self.account_id,
                    self.session_id)
        return DiscoveryBuilderOutput(
            discovery_order="",
            questions_by_topic=list_of_topic_questions,
            has_error=True)
    
    async def _agenerate_discovery_request(self, input: str, location: str, hearing_type: str, target: str, list_of_topic_questions: List[TopicQuestions]) -> DiscoveryBuilderOutput:
        questions = [DiscoveryTopicQuestionsWriterOutput(
            topic=topic["topic"], questions=topic["questions"], location=location) for topic in list_of_topic_questions for x in topic["questions"]]
        try:
            request_input = DiscoveryRequestWriterAgentRequest(
                questions=questions,
                input=input,
                hearing_type=hearing_type,
                target=target,
                location=location)
            request_results = await self.primary_request_agent.agenerate_response(
                request_input)
            return DiscoveryBuilderOutput(discovery_order=request_results.discovery_order, questions_by_topic=list_of_topic_questions, has_error=False)
        except openai.BadRequestError as bre:
            logging.warning(
                "Error invoking primary agent.  Trying alternative chain. (%s - %s)", self.account_id, self.session_id)
            logging.error(bre)
            try:
                request_input = DiscoveryRequestWriterAgentRequest(
                    questions=questions,
                    input=input,
                    hearing_type=hearing_type,
                    target=target,
                    location=location)
                request_results = await self.backup_request_agent.agenerate_response(
                    request_input)
                return DiscoveryBuilderOutput(
                    discovery_order=request_results.discovery_order,
                    questions_by_topic=list_of_topic_questions,
                    has_error=False)
            except anthropic.BadRequestError as bre:
                logging.error(bre)
                logging.error(
                    "Error invoking alternative agent for generating discovery request. (%s - %s)",
                    self.account_id,
                    self.session_id)
        return DiscoveryBuilderOutput(
            discovery_order="",
            questions_by_topic=list_of_topic_questions,
            has_error=True)

    def _generate_refute(self, input: str, topic: str, target: str, aimie_question: str, location: str, vector_store: VectorStore) -> str:
        request = DiscoveryCrossExaminationRequest(
            input=input,
            topic=topic,
            target=target,
            topic_question=aimie_question,
            location=location)
        try:
            refute_results = self.bob_refute_agent.generate_response(request, vector_store)
            return refute_results.answer
        except openai.BadRequestError as bre:
            logging.error(bre)
            logging.error(
                "Error invoking primary agent for generating refute. (%s - %s)", self.account_id, self.session_id)
            return ""
        except anthropic.BadRequestError as bre:
            logging.error(bre)
            logging.error(
                "Error invoking alternative agent for generating refute. (%s - %s)", self.account_id, self.session_id)
            return ""

    async def _agenerate_refute(self, input: str, topic: str, target: str, aimie_question: str, location: str, vector_store: VectorStore) -> str:
        request = DiscoveryCrossExaminationRequest(
            input=input,
            topic=topic,
            target=target,
            topic_question=aimie_question,
            location=location)
        try:
            refute_results = await self.bob_refute_agent.agenerate_response(request, vector_store)
            return refute_results.answer
        except openai.BadRequestError as bre:
            logging.error(bre)
            logging.error(
                "Error invoking primary agent for generating refute. (%s - %s)", self.account_id, self.session_id)
            return ""
        except anthropic.BadRequestError as bre:
            logging.error(bre)
            logging.error(
                "Error invoking alternative agent for generating refute. (%s - %s)", self.account_id, self.session_id)
            return ""