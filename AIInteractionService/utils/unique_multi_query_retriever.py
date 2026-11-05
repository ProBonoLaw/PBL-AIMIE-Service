import logging
from collections.abc import Mapping, Sequence
from typing import Any, Optional

from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_classic.retrievers import MultiQueryRetriever
from langchain_core.documents import Document

from .formatters import get_unique_docs

logger = logging.getLogger(__name__)


class UniqueMultiQueryRetriever(MultiQueryRetriever):
    max_doc_count: Optional[int] = None

    async def _aget_relevant_documents(
            self,
            query: str,
            *,
            run_manager: AsyncCallbackManagerForRetrieverRun) -> list[Document]:
        try:
            queries = await self.agenerate_queries(query, run_manager)
            if self.include_original:
                queries.append(query)
        except Exception:
            logger.warning(
                "Multi-query generation failed; falling back to the original query.",
                exc_info=True,
                extra={"query": query},
            )
            queries = [query]

        documents = await self.aretrieve_documents(queries, run_manager)
        return self.unique_union(documents)

    async def agenerate_queries(
            self,
            question: str,
            run_manager: AsyncCallbackManagerForRetrieverRun) -> list[str]:
        response = await self.llm_chain.ainvoke(
            {"question": question},
            config={"callbacks": []},
        )
        queries = self._normalize_generated_queries(response)
        if self.verbose:
            logger.info("Generated queries: %s", queries)
        return queries

    def _get_relevant_documents(
            self,
            query: str,
            *,
            run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        try:
            queries = self.generate_queries(query, run_manager)
            if self.include_original:
                queries.append(query)
        except Exception:
            logger.warning(
                "Multi-query generation failed; falling back to the original query.",
                exc_info=True,
                extra={"query": query},
            )
            queries = [query]

        documents = self.retrieve_documents(queries, run_manager)
        return self.unique_union(documents)

    def generate_queries(
            self,
            question: str,
            run_manager: CallbackManagerForRetrieverRun) -> list[str]:
        response = self.llm_chain.invoke(
            {"question": question},
            config={"callbacks": []},
        )
        queries = self._normalize_generated_queries(response)
        if self.verbose:
            logger.info("Generated queries: %s", queries)
        return queries

    def _normalize_generated_queries(self, generated_queries: Any) -> list[str]:
        if isinstance(generated_queries, str):
            return [query.strip() for query in generated_queries.splitlines() if query.strip()]

        if isinstance(generated_queries, Mapping):
            for key in (self.parser_key, "lines", "queries", "text", "output"):
                if key in generated_queries:
                    return self._normalize_generated_queries(generated_queries[key])
            if len(generated_queries) == 1:
                return self._normalize_generated_queries(next(iter(generated_queries.values())))
            raise ValueError(f"Unable to extract generated queries from keys: {list(generated_queries.keys())}")

        if isinstance(generated_queries, Sequence):
            return [str(query).strip() for query in generated_queries if str(query).strip()]

        raise ValueError(f"Unable to normalize generated queries from {type(generated_queries).__name__}")

    def unique_union(self, documents: list[Document]) -> list[Document]:
        return get_unique_docs(documents, max_doc_count=self.max_doc_count)
