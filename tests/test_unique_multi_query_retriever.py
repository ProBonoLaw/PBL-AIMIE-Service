import sys
from pathlib import Path

import pytest
from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    BaseCallbackHandler,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda
from pydantic import PrivateAttr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from AIInteractionService.utils.unique_multi_query_retriever import UniqueMultiQueryRetriever


class RecordingRetriever(BaseRetriever):
    _queries: list[str] = PrivateAttr(default_factory=list)

    @property
    def queries(self) -> list[str]:
        return self._queries

    def _get_relevant_documents(
            self,
            query: str,
            *,
            run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        self._queries.append(query)
        return [Document(page_content=f"doc for {query}", metadata={"id": query, "score": 1})]

    async def _aget_relevant_documents(
            self,
            query: str,
            *,
            run_manager: AsyncCallbackManagerForRetrieverRun) -> list[Document]:
        self._queries.append(query)
        return [Document(page_content=f"doc for {query}", metadata={"id": query, "score": 1})]


class RecordingChainCallbackHandler(BaseCallbackHandler):
    def __init__(self):
        self.chain_outputs = []

    def on_chain_end(self, outputs, **kwargs):
        self.chain_outputs.append(outputs)


class FailingRetriever(BaseRetriever):
    def _get_relevant_documents(
            self,
            query: str,
            *,
            run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        raise RuntimeError("retriever failed")


def _failing_llm_chain() -> RunnableLambda:
    def raise_error(_):
        raise RuntimeError("llm failed")

    return RunnableLambda(raise_error)


def test_falls_back_to_original_query_when_llm_generation_fails():
    retriever = RecordingRetriever()
    mq_retriever = UniqueMultiQueryRetriever(
        retriever=retriever,
        llm_chain=_failing_llm_chain(),
    )

    docs = mq_retriever.invoke("What happened?")

    assert retriever.queries == ["What happened?"]
    assert docs == [
        Document(page_content="doc for What happened?", metadata={"id": "What happened?", "score": 1})
    ]


@pytest.mark.asyncio
async def test_async_falls_back_to_original_query_when_llm_generation_fails():
    retriever = RecordingRetriever()
    mq_retriever = UniqueMultiQueryRetriever(
        retriever=retriever,
        llm_chain=_failing_llm_chain(),
    )

    docs = await mq_retriever.ainvoke("What happened?")

    assert retriever.queries == ["What happened?"]
    assert docs == [
        Document(page_content="doc for What happened?", metadata={"id": "What happened?", "score": 1})
    ]


def test_retriever_failures_are_not_swallowed_by_llm_fallback():
    mq_retriever = UniqueMultiQueryRetriever(
        retriever=FailingRetriever(),
        llm_chain=RunnableLambda(lambda _: ["generated query"]),
    )

    with pytest.raises(RuntimeError, match="retriever failed"):
        mq_retriever.invoke("What happened?")


def test_query_generation_does_not_forward_parent_callbacks_to_parser_chain():
    callback_handler = RecordingChainCallbackHandler()
    retriever = RecordingRetriever()
    mq_retriever = UniqueMultiQueryRetriever(
        retriever=retriever,
        llm_chain=RunnableLambda(lambda _: ["generated query"]),
    )

    docs = mq_retriever.invoke("What happened?", config={"callbacks": [callback_handler]})

    assert retriever.queries == ["generated query"]
    assert docs == [
        Document(page_content="doc for generated query", metadata={"id": "generated query", "score": 1})
    ]
    assert callback_handler.chain_outputs == []


def test_raw_string_query_generation_is_split_before_adding_original_query():
    retriever = RecordingRetriever()
    mq_retriever = UniqueMultiQueryRetriever(
        retriever=retriever,
        llm_chain=RunnableLambda(lambda _: "generated query one\n\ngenerated query two"),
        include_original=True,
    )

    docs = mq_retriever.invoke("What happened?")

    assert retriever.queries == ["generated query one", "generated query two", "What happened?"]
    assert docs == [
        Document(page_content="doc for generated query one", metadata={"id": "generated query one", "score": 1}),
        Document(page_content="doc for generated query two", metadata={"id": "generated query two", "score": 1}),
        Document(page_content="doc for What happened?", metadata={"id": "What happened?", "score": 1}),
    ]


def test_text_dict_query_generation_is_split_before_adding_original_query():
    retriever = RecordingRetriever()
    mq_retriever = UniqueMultiQueryRetriever(
        retriever=retriever,
        llm_chain=RunnableLambda(lambda _: {"text": "generated query one\n\ngenerated query two"}),
        include_original=True,
    )

    docs = mq_retriever.invoke("What happened?")

    assert retriever.queries == ["generated query one", "generated query two", "What happened?"]
    assert docs == [
        Document(page_content="doc for generated query one", metadata={"id": "generated query one", "score": 1}),
        Document(page_content="doc for generated query two", metadata={"id": "generated query two", "score": 1}),
        Document(page_content="doc for What happened?", metadata={"id": "What happened?", "score": 1}),
    ]


def test_dict_query_generation_is_unwrapped_before_adding_original_query():
    retriever = RecordingRetriever()
    mq_retriever = UniqueMultiQueryRetriever(
        retriever=retriever,
        llm_chain=RunnableLambda(lambda _: {"queries": ["generated query"]}),
        include_original=True,
    )

    docs = mq_retriever.invoke("What happened?")

    assert retriever.queries == ["generated query", "What happened?"]
    assert docs == [
        Document(page_content="doc for generated query", metadata={"id": "generated query", "score": 1}),
        Document(page_content="doc for What happened?", metadata={"id": "What happened?", "score": 1}),
    ]


@pytest.mark.asyncio
async def test_async_text_dict_query_generation_is_split_before_adding_original_query():
    retriever = RecordingRetriever()
    mq_retriever = UniqueMultiQueryRetriever(
        retriever=retriever,
        llm_chain=RunnableLambda(lambda _: {"text": "generated query one\n\ngenerated query two"}),
        include_original=True,
    )

    docs = await mq_retriever.ainvoke("What happened?")

    assert retriever.queries == ["generated query one", "generated query two", "What happened?"]
    assert docs == [
        Document(page_content="doc for generated query one", metadata={"id": "generated query one", "score": 1}),
        Document(page_content="doc for generated query two", metadata={"id": "generated query two", "score": 1}),
        Document(page_content="doc for What happened?", metadata={"id": "What happened?", "score": 1}),
    ]
