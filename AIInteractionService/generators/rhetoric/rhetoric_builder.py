
import logging
from typing import Any, List, Optional

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_core.messages import BaseMessage

import AIInteractionService.generators.rhetoric as RhetoricModule
from AIInteractionService.generators.rhetoric.base_rhetoric_writer_agent import BaseRhetoricWriterAgent
from .types import RhetoricWriterAgentRequest, RhetoricWriterOutput
from ..common import AnswersWithSources, SourceResult, normalize_source, BaseRequestModel, LawRetrieverProvider
from ...utils.document_tools import deduplicate_sources
from ...utils.section_extractor import SectionExtractor
from ...utils.agent_facilitator import AgentFacilitator

class RhetoricBuilderOutput(BaseRequestModel):
    answer: str
    context: List[Document]
    chat_history: List[BaseMessage]
    sources: List[SourceResult]

class RhetoricBuilder:
    def __init__(self, account_id: str, session_id: str, max_doc_count: int, **kwargs: Any):
        self.account_id = account_id
        self.session_id = session_id
        self.max_doc_count = max_doc_count
        self.agent_facilitator = AgentFacilitator[BaseRhetoricWriterAgent](RhetoricModule)
    
    async def agenerate_rhetoric_response(self, statement: str, vector_store: VectorStore, law_provider: LawRetrieverProvider, location: str) -> RhetoricBuilderOutput:
        section_extractor = SectionExtractor()
        sections = section_extractor.extract_sections_all(statement)
        chat_history = []
        if len(sections) == 0:
            sections = {"Argument": [statement, ""]}
        
        context: List[Document] = []
        source_keys: set = set()
        sources: List[SourceResult] = []
        for section in sections:
            logging.info("Generating additional context for section (%s - %s): %s", self.account_id, self.session_id, section[:15])
            original_section = '\n'.join(sections[section])
            if original_section.strip() == "":
                continue
            request = RhetoricWriterAgentRequest(statement=original_section, location=location)
            try:
                results = await self.execute_retriable_request_with_context(request, vector_store, law_provider)
                context.extend(results["context"])
                chat_history = results["chat_history"]
            except Exception as bre:
                logging.warning("Error invoking primary retrieval chain for generating rhetoric.  Trying alternative chain. (%s - %s)", self.account_id, self.session_id)
                logging.error(bre)
        
            answer: AnswersWithSources = results["answer"]
            iteration_sources = answer.sources
            for source in iteration_sources:
                if source.doc_id not in source_keys:
                    source_keys.add(source.doc_id)
                    sources.append(normalize_source(source)) 
            additional_section: str = answer.answer
            if additional_section.startswith("AIMIE_BOT Response:"):
                additional_section = additional_section[15:]
            sections[section] = [additional_section]
                
        adjusted_answer = section_extractor.reapply_sections(
            statement, sections)
        results = RhetoricBuilderOutput(answer=adjusted_answer, 
                                        context=deduplicate_sources(context),
                                        location=location,
                                        chat_history=chat_history,
                                        sources=sources)
        return results
    
    async def execute_retriable_request_with_context(
            self,
            qa_request: RhetoricWriterAgentRequest,
            vector_store: VectorStore, 
            law_retriever_provider: LawRetrieverProvider):
        backup_agent_count = await self.agent_facilitator.get_agent_variant_count() - 1
        result: RhetoricWriterOutput
        last_exception: Optional[Exception] = None
        for i in range(0, backup_agent_count):
            try:
                primary_agent = await self.agent_facilitator.get_agent_variant_instance(
                    i, 
                    self.account_id, 
                    self.session_id, 
                    self.max_doc_count)
                result = await primary_agent.agenerate_response(qa_request, vector_store, law_retriever_provider)
                break
            except Exception as e:
                logging.warning(f"Error generating response: {e}")
                logging.info("Retrying with secondary model")
                last_exception = e
        
        if not result and last_exception:
            raise last_exception
                
        return result