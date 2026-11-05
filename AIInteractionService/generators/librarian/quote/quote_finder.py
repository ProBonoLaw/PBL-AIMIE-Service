
import logging
import re
from typing import Any, List, Optional

from langchain_core.documents import Document

from .librarian_agents import AzureOpenAiLibrarianAgent, ChatAnthropicLibrarianAgent
from ...common.law_retriever_provider import LawRetrieverProvider
from .types import AmieLibrarianAgentRequest, LibrarianAnswer, LibrarianOutput
from ....utils.document_tools import deduplicate_sources
from ....utils.formatters import analyze_docs
from ....utils.section_extractor import SectionExtractor
from ....db.azuresearch import AzureSearch

quote_finder = r'["|\']?docId["|\']?:(?:\s|\n)*?["|\']?(?P<docId>[a-zA-Z0-9]*?)["|\']'

class QuoteFinder:
    def __init__(self, account_id: str, session_id: str, vector_store: AzureSearch, law_provider: Optional[LawRetrieverProvider], **kwargs: Any):
        self.account_id = account_id
        self.session_id = session_id
        self.vector_store = vector_store
        self.backup_agent = ChatAnthropicLibrarianAgent(account_id, session_id, **kwargs)
        self.primary_agent = AzureOpenAiLibrarianAgent(account_id, session_id, **kwargs)
        self.law_provider = law_provider
    
    def generate_exhibits(self, context: List[Document], declaration: str, location: str) -> dict[str, dict[str, LibrarianAnswer]]:
        logging.info("Generating exhibits for declaration (%s - %s)", self.account_id, self.session_id)
        exhibits: dict[str, dict[str, LibrarianAnswer]] = dict()
        extractor = SectionExtractor()
        sections = extractor.extract_sections(declaration)
        for section in sections:
            exhibits[section] = dict()
            for paragraph in sections[section]:
                if ("docId" in paragraph):
                    quote_matcher = self.librarian_quote_matcher(context, paragraph, location)
                    exhibits[section][paragraph] = quote_matcher
        return exhibits
    
    async def agenerate_exhibits(self, context: List[Document], declaration: str, location: str) -> dict[str, dict[str, LibrarianAnswer]]:
        logging.info("Generating exhibits for declaration (%s - %s)", self.account_id, self.session_id)
        exhibits: dict[str, dict[str, LibrarianAnswer]] = dict()
        extractor = SectionExtractor()
        sections = extractor.extract_sections(declaration)
        for section in sections:
            exhibits[section] = dict()
            for paragraph in sections[section]:
                if ("docId" in paragraph):
                    quote_matcher = await self.alibrarian_quote_matcher(context, paragraph, location)
                    exhibits[section][paragraph] = quote_matcher
        return exhibits
    
    async def alibrarian_quote_matcher(self, context: List[Document], statement: str, location: str) -> LibrarianAnswer:
        logging.info(
            "Running Librarian Quote Matcher for statement (%s -%s): %s", self.account_id, self.session_id, statement[:15])
        docs_of_interest = self.get_relevant_documents(context, statement)
        librarian_quotes: List[LibrarianAnswer] = []
        
        for doc in docs_of_interest:
            logging.info(
            "Running Librarian Quote Matcher with docId (%s -%s): %s", self.account_id, self.session_id, doc.metadata['id'])
            request = AmieLibrarianAgentRequest(quote=statement, doc_id=doc.metadata['id'], location=location)
            try:
                result = await self.aattempt_librarian_quote_match(request, doc)
                context.extend(result["context"])
                librarian_quotes.append(result["answer"])
            except Exception as e:
                logging.error(f"Error invoking librarian_quote_matcher: {str(e)}")
                librarian_quotes.append(LibrarianAnswer(quotes=[], hasError = True))
        if len(librarian_quotes) > 1:
            total_quotes = []
            total_errors = False
            for quotes in librarian_quotes:
                if quotes.hasError:
                    continue
                total_quotes.extend(quotes.quotes)
            return LibrarianAnswer(quotes=total_quotes, hasError=total_errors)
        return librarian_quotes[0] if len(librarian_quotes) == 1 else LibrarianAnswer(quotes=[], hasError=True)
    
    def librarian_quote_matcher(self, context: List[Document], statement: str, location: str) -> LibrarianAnswer:
        logging.info(
            "Running Librarian Quote Matcher for statement (%s -%s): %s", self.account_id, self.session_id, statement[:15])
        docs_of_interest = self.get_relevant_documents(context, statement)
        librarian_quotes: List[LibrarianAnswer] = []
        
        for doc in docs_of_interest:
            logging.info(
            "Running Librarian Quote Matcher with docId (%s -%s): %s", self.account_id, self.session_id, doc.metadata['id'])
            request = AmieLibrarianAgentRequest(quote=statement, doc_id=doc.metadata['id'], location=location)
            try:
                result = self.attempt_librarian_quote_match(request, doc)
                context.extend(result["context"])
                librarian_quotes.append(result["answer"])
            except Exception as e:
                logging.error(f"Error invoking librarian_quote_matcher: {str(e)}")
                librarian_quotes.append(LibrarianAnswer(quotes=[], hasError = True))
        if len(librarian_quotes) > 1:
            total_quotes = []
            total_errors = False
            for quotes in librarian_quotes:
                if quotes.hasError:
                    continue
                total_quotes.extend(quotes.quotes)
            return LibrarianAnswer(quotes=total_quotes, hasError=total_errors)
        return librarian_quotes[0] if len(librarian_quotes) == 1 else LibrarianAnswer(quotes=[], hasError=True)
    
    def get_relevant_documents(self, context: List[Document], statement: str) -> List[Document]:
        logging.info("Getting relevant documents for statement (%s - %s): %s", self.account_id, self.session_id, statement[:15])
        doc_ids = re.findall(quote_finder, 
                             statement)
        doc_ids = set([doc_id for doc_id in doc_ids if doc_id and len(doc_id.strip()) > 0])
        if not doc_ids or len(doc_ids) == 0:
            return []
        docs_of_interest = [
            doc for doc in context if doc.metadata['id'] in doc_ids]
        if not docs_of_interest or len(docs_of_interest) == 0:
            filter_statement = " or ".join(
                [f"id eq '{doc_id}'" for doc_id in doc_ids])
            try:
                docs_of_interest = self.vector_store.vector_search(
                    "*", filters=filter_statement)
                context.extend(docs_of_interest)
            except Exception as e:
                logging.error(f"Error retrieving documents for {str(doc_ids)}: {str(e)}")
                return []
        if not docs_of_interest or len(docs_of_interest) == 0:
            return []
        new_docs_of_interest = [doc for doc in docs_of_interest if analyze_docs(doc.page_content)]
        return deduplicate_sources(new_docs_of_interest)
    
    def attempt_librarian_quote_match(self, 
                                      request: AmieLibrarianAgentRequest, 
                                      doc: Document) -> LibrarianOutput:
        try:
            result = self.primary_agent.generate_response(request, context=[doc], law_retriever_provider=self.law_provider)
            if not result["answer"] or not result["answer"].quotes:
                raise Exception("No quotes found")
        except Exception as e:
            logging.error(f"Error invoking librarian_quote_matcher: {str(e)}.  Trying backup agent.")
            result = self.backup_agent.generate_response(request, context=[doc],  law_retriever_provider=self.law_provider)
            if not result["answer"] or not result["answer"].quotes:
                raise Exception("No quotes found")
            
        return result

    async def aattempt_librarian_quote_match(self, 
                                      request: AmieLibrarianAgentRequest, 
                                      doc: Document) -> LibrarianOutput:
        try:
            result = await self.primary_agent.agenerate_response(request, context=[doc])
            if not result["answer"] or not result["answer"].quotes:
                raise Exception("No quotes found")
        except Exception as e:
            logging.error(f"Error invoking librarian_quote_matcher: {str(e)}.  Trying backup agent.")
            result = await self.backup_agent.agenerate_response(request, context=[doc])
            if not result["answer"] or not result["answer"].quotes:
                raise Exception("No quotes found")
            
        return result

