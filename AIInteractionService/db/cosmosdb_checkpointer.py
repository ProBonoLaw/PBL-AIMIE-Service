import asyncio
import base64
import logging
import random
import time
from collections import defaultdict
from contextlib import AbstractContextManager
from threading import Lock
from types import TracebackType
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, Iterator, List, Optional, Self, Sequence, Tuple
from weakref import WeakValueDictionary

from azure.cosmos import exceptions
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    PendingWrite,
    WRITES_IDX_MAP,
    get_checkpoint_id,
)
from langgraph.checkpoint.serde.base import SerializerProtocol
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from AIInteractionService.db.cosmosdb_handler import CosmosDBHandler


class CosmosDBSaver(AbstractContextManager, BaseCheckpointSaver):
    """A checkpoint saver that stores checkpoints in an Azure Cosmos DB database."""

    serde = JsonPlusSerializer()
    max_payload_chars = 64_000
    max_write_attempts = 5
    max_concurrent_writes = 8

    handler: CosmosDBHandler

    def __init__(
        self,
        handler: CosmosDBHandler,
        *,
        serde: Optional[SerializerProtocol] = None,
        allowed_msgpack_modules: Optional[Sequence[Tuple[str, str]]] = None,
    ) -> None:
        if serde is not None and allowed_msgpack_modules is not None:
            raise ValueError("Specify either serde or allowed_msgpack_modules, not both.")
        if serde is None and allowed_msgpack_modules is not None:
            serde = JsonPlusSerializer(allowed_msgpack_modules=list(allowed_msgpack_modules))
        BaseCheckpointSaver.__init__(self, serde=serde)
        self.handler = handler
        self._async_write_locks: WeakValueDictionary[
            Tuple[str, str, str], asyncio.Lock
        ] = WeakValueDictionary()
        self._async_write_locks_guard = Lock()
        self._async_write_semaphore = asyncio.Semaphore(self.max_concurrent_writes)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        __exc_type: Optional[type[BaseException]],
        __exc_value: Optional[BaseException],
        __traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        return None

    @staticmethod
    def __checkpoint_doc_id(thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> str:
        return f"{thread_id}_{checkpoint_ns}_{checkpoint_id}"

    @staticmethod
    def __write_doc_id(
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        task_id: str,
        channel_idx: int,
    ) -> str:
        return f"{thread_id}_{checkpoint_ns}_{checkpoint_id}_{task_id}_{channel_idx}"

    @staticmethod
    def __payload_chunk_doc_id(doc_id: str, payload_name: str, chunk_index: int) -> str:
        return f"{doc_id}_{payload_name}_chunk_{chunk_index}"

    @classmethod
    def __split_payload(cls, payload: str) -> List[str]:
        return [
            payload[offset:offset + cls.max_payload_chars]
            for offset in range(0, len(payload), cls.max_payload_chars)
        ] or [""]

    @classmethod
    def __chunked_payload_docs(
        cls,
        doc: Dict[str, Any],
        payload_names: Sequence[str],
    ) -> List[Dict[str, Any]]:
        payloads = {name: doc[name] for name in payload_names}
        if sum(len(value) for value in payloads.values()) <= cls.max_payload_chars:
            return [doc]

        manifest = {key: value for key, value in doc.items() if key not in payload_names}
        manifest["payload_chunked"] = True
        chunk_docs: List[Dict[str, Any]] = []
        for payload_name, payload in payloads.items():
            chunks = cls.__split_payload(payload)
            manifest[f"{payload_name}_chunk_count"] = len(chunks)
            for chunk_index, chunk in enumerate(chunks):
                chunk_docs.append({
                    "id": cls.__payload_chunk_doc_id(doc["id"], payload_name, chunk_index),
                    "account_id": doc["account_id"],
                    "thread_id": doc["thread_id"],
                    "type": f"{doc['type']}_CHUNK",
                    "parent_id": doc["id"],
                    "payload_name": payload_name,
                    "chunk_index": chunk_index,
                    "value": chunk,
                })
        return [*chunk_docs, manifest]

    def __hydrate_payload_doc(
        self,
        doc: Dict[str, Any],
        payload_names: Sequence[str],
    ) -> Dict[str, Any]:
        if not doc.get("payload_chunked"):
            return doc
        hydrated = dict(doc)
        for payload_name in payload_names:
            chunks = []
            for chunk_index in range(doc[f"{payload_name}_chunk_count"]):
                chunk_doc = self.handler.container.read_item(
                    item=self.__payload_chunk_doc_id(doc["id"], payload_name, chunk_index),
                    partition_key=(doc["account_id"], doc["thread_id"]),
                )
                chunks.append(chunk_doc["value"])
            hydrated[payload_name] = "".join(chunks)
        return hydrated

    async def __ahydrate_payload_doc(
        self,
        doc: Dict[str, Any],
        payload_names: Sequence[str],
    ) -> Dict[str, Any]:
        if not doc.get("payload_chunked"):
            return doc
        hydrated = dict(doc)
        for payload_name in payload_names:
            chunks = []
            for chunk_index in range(doc[f"{payload_name}_chunk_count"]):
                chunk_doc = await self.handler.acontainer.read_item(
                    item=self.__payload_chunk_doc_id(doc["id"], payload_name, chunk_index),
                    partition_key=(doc["account_id"], doc["thread_id"]),
                )
                chunks.append(chunk_doc["value"])
            hydrated[payload_name] = "".join(chunks)
        return hydrated

    @staticmethod
    def __retry_delay_seconds(error: exceptions.CosmosHttpResponseError, attempt: int) -> float:
        response = getattr(error, "response", None)
        headers = getattr(error, "headers", None) or getattr(response, "headers", None) or {}
        retry_after_ms = (
            headers.get("x-ms-retry-after-ms")
            or headers.get("retry-after-ms")
            or getattr(error, "retry_after_in_milliseconds", None)
        )
        try:
            server_delay = float(retry_after_ms) / 1000 if retry_after_ms else 0.0
        except (TypeError, ValueError):
            server_delay = 0.0
        return max(server_delay, min(0.25 * (2 ** attempt), 5.0))

    def __write_with_retry(
        self,
        operation: Callable[[], Any],
        doc_id: str,
    ) -> None:
        for attempt in range(self.max_write_attempts):
            try:
                operation()
                return
            except exceptions.CosmosHttpResponseError as error:
                if error.status_code != 429 or attempt + 1 >= self.max_write_attempts:
                    raise
                delay = self.__retry_delay_seconds(error, attempt)
                logging.warning(
                    "Cosmos throttled checkpoint document %s; retrying in %.3f seconds",
                    doc_id,
                    delay,
                )
                time.sleep(delay)

    def __async_write_lock_for(
        self,
        payload_docs: Sequence[Dict[str, Any]],
    ) -> asyncio.Lock:
        logical_doc = payload_docs[-1]
        key = (
            str(logical_doc["account_id"]),
            str(logical_doc["thread_id"]),
            str(logical_doc["id"]),
        )
        with self._async_write_locks_guard:
            lock = self._async_write_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._async_write_locks[key] = lock
            return lock

    async def __awrite_with_retry(
        self,
        operation: Callable[[], Awaitable[Any]],
        doc_id: str,
    ) -> None:
        for attempt in range(self.max_write_attempts):
            try:
                async with self._async_write_semaphore:
                    await operation()
                return
            except exceptions.CosmosHttpResponseError as error:
                if error.status_code != 429 or attempt + 1 >= self.max_write_attempts:
                    raise
                delay = self.__retry_delay_seconds(error, attempt)
                logging.warning(
                    "Cosmos throttled checkpoint document %s; retrying in %.3f seconds",
                    doc_id,
                    delay,
                )
                await asyncio.sleep(delay)

    async def __awrite_payload_doc(
        self,
        payload_doc: Dict[str, Any],
        *,
        insert_only: bool,
    ) -> None:
        if insert_only:
            operation = lambda: self.handler.ainsert_or_ignore(payload_doc)
        else:
            operation = lambda: self.handler.aupdate_conversation(
                payload_doc,
                no_response=True,
            )
        await self.__awrite_with_retry(operation, payload_doc["id"])

    async def __awrite_payload_docs_concurrently(
        self,
        payload_docs: Sequence[Dict[str, Any]],
        *,
        insert_only: bool,
    ) -> None:
        results = await asyncio.gather(
            *(
                self.__awrite_payload_doc(
                    payload_doc,
                    insert_only=insert_only,
                )
                for payload_doc in payload_docs
            ),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result

    async def __awrite_payload_docs(
        self,
        payload_docs: Sequence[Dict[str, Any]],
        *,
        insert_only: bool,
    ) -> None:
        if not payload_docs:
            return

        async with self.__async_write_lock_for(payload_docs):
            if payload_docs[-1].get("payload_chunked"):
                await self.__awrite_payload_docs_concurrently(
                    payload_docs[:-1],
                    insert_only=insert_only,
                )
                await self.__awrite_payload_doc(
                    payload_docs[-1],
                    insert_only=insert_only,
                )
            else:
                await self.__awrite_payload_docs_concurrently(
                    payload_docs,
                    insert_only=insert_only,
                )

    @staticmethod
    def __partition_kwargs(account_id: Optional[str], thread_id: Optional[str]) -> Dict[str, Any]:
        if account_id is not None and thread_id is not None:
            return {"partition_key": (account_id, thread_id)}
        return {"enable_cross_partition_query": True}

    @staticmethod
    def __query_parameter(name: str, value: Any) -> Dict[str, Any]:
        return {"name": name, "value": value}

    @staticmethod
    def __checkpoint_ns_from_config(configurable: Dict[str, Any]) -> str:
        return configurable.get("checkpoint_ns") or ""

    @staticmethod
    def __config_from_doc(doc: Dict[str, Any], checkpoint_id: Optional[str] = None) -> RunnableConfig:
        return {
            "configurable": {
                "thread_id": doc["thread_id"],
                "account_id": doc["account_id"],
                "checkpoint_ns": doc.get("checkpoint_ns", ""),
                "checkpoint_id": checkpoint_id or doc["checkpoint_id"],
            }
        }

    @staticmethod
    def __write_group_key(doc: Dict[str, Any]) -> Tuple[str, str, str, str]:
        return (
            doc["account_id"],
            doc["thread_id"],
            doc.get("checkpoint_ns", ""),
            doc["checkpoint_id"],
        )

    def __checkpoint_tuple_from_doc(
        self,
        doc: Dict[str, Any],
        writes: List[Dict[str, Any]],
    ) -> CheckpointTuple:
        parent_checkpoint_id = doc.get("parent_checkpoint_id")
        return CheckpointTuple(
            self.__config_from_doc(doc),
            self.serde.loads_typed(
                (
                    doc["checkpoint_type"],
                    base64.b64decode(doc["checkpoint"], validate=False),
                )
            ),
            self.serde.loads_typed(
                (
                    doc.get("metadata_type", "bytes"),
                    base64.b64decode(doc["metadata"], validate=False),
                )
            ),
            (
                self.__config_from_doc(doc, parent_checkpoint_id)
                if parent_checkpoint_id
                else None
            ),
            self.__convert_to_tuple(writes),
        )

    def __read_checkpoint_doc(
        self,
        account_id: str,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> Optional[Dict[str, Any]]:
        try:
            doc = self.handler.container.read_item(
                item=self.__checkpoint_doc_id(thread_id, checkpoint_ns, checkpoint_id),
                partition_key=(account_id, thread_id),
            )
            return self.__hydrate_payload_doc(doc, ("checkpoint", "metadata"))
        except exceptions.CosmosResourceNotFoundError:
            return None

    async def __aread_checkpoint_doc(
        self,
        account_id: str,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> Optional[Dict[str, Any]]:
        try:
            doc = await self.handler.acontainer.read_item(
                item=self.__checkpoint_doc_id(thread_id, checkpoint_ns, checkpoint_id),
                partition_key=(account_id, thread_id),
            )
            return await self.__ahydrate_payload_doc(doc, ("checkpoint", "metadata"))
        except exceptions.CosmosResourceNotFoundError:
            return None

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Get a checkpoint from the database."""
        configurable = config.get("configurable", {})
        thread_id = configurable["thread_id"]
        account_id = configurable["account_id"]
        checkpoint_ns = self.__checkpoint_ns_from_config(configurable)

        if checkpoint_id := get_checkpoint_id(config):
            doc = self.__read_checkpoint_doc(account_id, thread_id, checkpoint_ns, checkpoint_id)
        else:
            query = (
                "SELECT TOP 1 * FROM c WHERE c.type = @type "
                "AND c.account_id = @account_id "
                "AND c.thread_id = @thread_id "
                "AND c.checkpoint_ns = @checkpoint_ns "
                "ORDER BY c.checkpoint_id DESC"
            )
            items = self.handler.container.query_items(
                query=query,
                parameters=[
                    self.__query_parameter("@type", "CHECKPOINT"),
                    self.__query_parameter("@account_id", account_id),
                    self.__query_parameter("@thread_id", thread_id),
                    self.__query_parameter("@checkpoint_ns", checkpoint_ns),
                ],
                priority="High",
                max_item_count=1,
                partition_key=(account_id, thread_id),
            )
            doc = next(iter(items), None)

        if not doc:
            return None
        if "checkpoint" not in doc:
            doc = self.__hydrate_payload_doc(doc, ("checkpoint", "metadata"))

        doc_config = self.__config_from_doc(doc)
        writes = self.__get_writes_for_checkpoint(doc_config)
        return self.__checkpoint_tuple_from_doc(doc, writes)

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Get a checkpoint from the database."""
        logging.info("Getting checkpoint tuple with config: %s", config)
        configurable = config.get("configurable", {})
        thread_id = configurable["thread_id"]
        account_id = configurable["account_id"]
        checkpoint_ns = self.__checkpoint_ns_from_config(configurable)

        if checkpoint_id := get_checkpoint_id(config):
            doc = await self.__aread_checkpoint_doc(account_id, thread_id, checkpoint_ns, checkpoint_id)
        else:
            query = (
                "SELECT TOP 1 * FROM c WHERE c.type = @type "
                "AND c.account_id = @account_id "
                "AND c.thread_id = @thread_id "
                "AND c.checkpoint_ns = @checkpoint_ns "
                "ORDER BY c.checkpoint_id DESC"
            )
            result_iterable = self.handler.acontainer.query_items(
                query=query,
                parameters=[
                    self.__query_parameter("@type", "CHECKPOINT"),
                    self.__query_parameter("@account_id", account_id),
                    self.__query_parameter("@thread_id", thread_id),
                    self.__query_parameter("@checkpoint_ns", checkpoint_ns),
                ],
                priority="High",
                max_item_count=1,
                partition_key=(account_id, thread_id),
            )
            doc = None
            async for page in result_iterable.by_page():
                async for item in page:
                    doc = item
                    break
                if doc:
                    break

        if not doc:
            logging.info("No checkpoint found for config: %s", config)
            return None
        if "checkpoint" not in doc:
            doc = await self.__ahydrate_payload_doc(doc, ("checkpoint", "metadata"))

        doc_config = self.__config_from_doc(doc)
        writes = await self.__aget_writes_for_checkpoint(doc_config)
        logging.info("Found checkpoint for config: %s", config)
        return self.__checkpoint_tuple_from_doc(doc, writes)

    def __get_writes_for_checkpoint(self, config: Optional[RunnableConfig]) -> List[Dict[str, Any]]:
        if config is None:
            return []

        configurable = config.get("configurable", {})
        checkpoint_id = get_checkpoint_id(config)
        if not checkpoint_id:
            return []

        thread_id = configurable["thread_id"]
        account_id = configurable["account_id"]
        checkpoint_ns = self.__checkpoint_ns_from_config(configurable)
        query = (
            "SELECT c.id, c.account_id, c.thread_id, c.checkpoint_ns, c.checkpoint_id, "
            "c.task_id, c.channel, c.channel_idx, c.channel_type, c['value'], "
            "c.payload_chunked, c.value_chunk_count "
            "FROM c WHERE c.type = @type "
            "AND c.account_id = @account_id "
            "AND c.thread_id = @thread_id "
            "AND c.checkpoint_ns = @checkpoint_ns "
            "AND c.checkpoint_id = @checkpoint_id "
            "ORDER BY c.task_id ASC"
        )
        items = self.handler.container.query_items(
            query=query,
            parameters=[
                self.__query_parameter("@type", "WRITES"),
                self.__query_parameter("@account_id", account_id),
                self.__query_parameter("@thread_id", thread_id),
                self.__query_parameter("@checkpoint_ns", checkpoint_ns),
                self.__query_parameter("@checkpoint_id", checkpoint_id),
            ],
            partition_key=(account_id, thread_id),
        )
        hydrated = [self.__hydrate_payload_doc(doc, ("value",)) for doc in items]
        return sorted(hydrated, key=lambda x: (x["task_id"], x["channel_idx"]))

    async def __aget_writes_for_checkpoint(self, config: Optional[RunnableConfig]) -> List[Dict[str, Any]]:
        logging.info("Getting writes for checkpoint with config: %s", config)
        if config is None:
            logging.info("No config provided, returning empty writes list")
            return []

        configurable = config.get("configurable", {})
        checkpoint_id = get_checkpoint_id(config)
        if not checkpoint_id:
            return []

        thread_id = configurable["thread_id"]
        account_id = configurable["account_id"]
        checkpoint_ns = self.__checkpoint_ns_from_config(configurable)
        query = (
            "SELECT c.id, c.account_id, c.thread_id, c.checkpoint_ns, c.checkpoint_id, "
            "c.task_id, c.channel, c.channel_idx, c.channel_type, c['value'], "
            "c.payload_chunked, c.value_chunk_count "
            "FROM c WHERE c.type = @type "
            "AND c.account_id = @account_id "
            "AND c.thread_id = @thread_id "
            "AND c.checkpoint_ns = @checkpoint_ns "
            "AND c.checkpoint_id = @checkpoint_id "
            "ORDER BY c.task_id ASC"
        )
        items = self.handler.acontainer.query_items(
            query=query,
            parameters=[
                self.__query_parameter("@type", "WRITES"),
                self.__query_parameter("@account_id", account_id),
                self.__query_parameter("@thread_id", thread_id),
                self.__query_parameter("@checkpoint_ns", checkpoint_ns),
                self.__query_parameter("@checkpoint_id", checkpoint_id),
            ],
            partition_key=(account_id, thread_id),
        )
        list_items = [doc async for page in items.by_page() async for doc in page]
        list_items = [
            await self.__ahydrate_payload_doc(doc, ("value",))
            for doc in list_items
        ]
        list_items.sort(key=lambda x: (x["task_id"], x["channel_idx"]))
        logging.info("Found %d writes for checkpoint", len(list_items))
        return list_items

    def __get_writes_for_checkpoints(
        self,
        checkpoint_docs: Sequence[Dict[str, Any]],
    ) -> Dict[Tuple[str, str, str, str], List[Dict[str, Any]]]:
        if not checkpoint_docs:
            return {}

        checkpoint_ids = sorted({doc["checkpoint_id"] for doc in checkpoint_docs})
        id_parameter_names = [f"@checkpoint_id_{idx}" for idx in range(len(checkpoint_ids))]
        parameters = [self.__query_parameter("@type", "WRITES")]
        parameters.extend(
            self.__query_parameter(name, checkpoint_id)
            for name, checkpoint_id in zip(id_parameter_names, checkpoint_ids)
        )
        conditions = ["c.type = @type", f"c.checkpoint_id IN ({', '.join(id_parameter_names)})"]

        account_ids = {doc["account_id"] for doc in checkpoint_docs}
        thread_ids = {doc["thread_id"] for doc in checkpoint_docs}
        if len(account_ids) == 1:
            account_id = next(iter(account_ids))
            conditions.append("c.account_id = @account_id")
            parameters.append(self.__query_parameter("@account_id", account_id))
        else:
            account_id = None

        if len(thread_ids) == 1:
            thread_id = next(iter(thread_ids))
            conditions.append("c.thread_id = @thread_id")
            parameters.append(self.__query_parameter("@thread_id", thread_id))
        else:
            thread_id = None

        checkpoint_namespaces = {doc.get("checkpoint_ns", "") for doc in checkpoint_docs}
        if len(checkpoint_namespaces) == 1:
            checkpoint_ns = next(iter(checkpoint_namespaces))
            conditions.append("c.checkpoint_ns = @checkpoint_ns")
            parameters.append(self.__query_parameter("@checkpoint_ns", checkpoint_ns))

        query = (
            "SELECT c.id, c.account_id, c.thread_id, c.checkpoint_ns, c.checkpoint_id, "
            "c.task_id, c.channel, c.channel_idx, c.channel_type, c['value'], "
            "c.payload_chunked, c.value_chunk_count "
            f"FROM c WHERE {' AND '.join(conditions)} ORDER BY c.task_id ASC"
        )
        query_kwargs = self.__partition_kwargs(account_id, thread_id)
        items = self.handler.container.query_items(
            query=query,
            parameters=parameters,
            **query_kwargs,
        )
        write_docs = [self.__hydrate_payload_doc(doc, ("value",)) for doc in items]
        return self.__group_writes(checkpoint_docs, write_docs)

    async def __aget_writes_for_checkpoints(
        self,
        checkpoint_docs: Sequence[Dict[str, Any]],
    ) -> Dict[Tuple[str, str, str, str], List[Dict[str, Any]]]:
        if not checkpoint_docs:
            return {}

        checkpoint_ids = sorted({doc["checkpoint_id"] for doc in checkpoint_docs})
        id_parameter_names = [f"@checkpoint_id_{idx}" for idx in range(len(checkpoint_ids))]
        parameters = [self.__query_parameter("@type", "WRITES")]
        parameters.extend(
            self.__query_parameter(name, checkpoint_id)
            for name, checkpoint_id in zip(id_parameter_names, checkpoint_ids)
        )
        conditions = ["c.type = @type", f"c.checkpoint_id IN ({', '.join(id_parameter_names)})"]

        account_ids = {doc["account_id"] for doc in checkpoint_docs}
        thread_ids = {doc["thread_id"] for doc in checkpoint_docs}
        if len(account_ids) == 1:
            account_id = next(iter(account_ids))
            conditions.append("c.account_id = @account_id")
            parameters.append(self.__query_parameter("@account_id", account_id))
        else:
            account_id = None

        if len(thread_ids) == 1:
            thread_id = next(iter(thread_ids))
            conditions.append("c.thread_id = @thread_id")
            parameters.append(self.__query_parameter("@thread_id", thread_id))
        else:
            thread_id = None

        checkpoint_namespaces = {doc.get("checkpoint_ns", "") for doc in checkpoint_docs}
        if len(checkpoint_namespaces) == 1:
            checkpoint_ns = next(iter(checkpoint_namespaces))
            conditions.append("c.checkpoint_ns = @checkpoint_ns")
            parameters.append(self.__query_parameter("@checkpoint_ns", checkpoint_ns))

        query = (
            "SELECT c.id, c.account_id, c.thread_id, c.checkpoint_ns, c.checkpoint_id, "
            "c.task_id, c.channel, c.channel_idx, c.channel_type, c['value'], "
            "c.payload_chunked, c.value_chunk_count "
            f"FROM c WHERE {' AND '.join(conditions)} ORDER BY c.task_id ASC"
        )
        query_kwargs = self.__partition_kwargs(account_id, thread_id)
        items = self.handler.acontainer.query_items(
            query=query,
            parameters=parameters,
            **query_kwargs,
        )
        list_items = [doc async for page in items.by_page() async for doc in page]
        list_items = [
            await self.__ahydrate_payload_doc(doc, ("value",))
            for doc in list_items
        ]
        return self.__group_writes(checkpoint_docs, list_items)

    def __group_writes(
        self,
        checkpoint_docs: Sequence[Dict[str, Any]],
        write_docs: Sequence[Dict[str, Any]],
    ) -> Dict[Tuple[str, str, str, str], List[Dict[str, Any]]]:
        selected_keys = {self.__write_group_key(doc) for doc in checkpoint_docs}
        grouped: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        for write_doc in write_docs:
            key = self.__write_group_key(write_doc)
            if key in selected_keys:
                grouped[key].append(write_doc)

        for writes in grouped.values():
            writes.sort(key=lambda x: (x["task_id"], x["channel_idx"]))
        return grouped

    def __convert_to_tuple(self, writes: List[Dict[str, Any]]) -> List[PendingWrite]:
        result = []
        for entry in writes:
            try:
                channel_value = self.serde.loads_typed(
                    (entry["channel_type"], base64.b64decode(entry["value"], validate=False))
                )
                result.append((entry["task_id"], entry["channel"], channel_value))
            except ValueError as e:
                logging.error("Unable to decode %s - %s", entry["value"], str(e))

        return result

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints from the database."""
        if limit is not None and limit <= 0:
            return

        query, parameters, query_kwargs = self.__checkpoint_list_query(config, filter, before, limit)
        items = self.handler.container.query_items(
            query=query,
            parameters=parameters,
            priority="High",
            **query_kwargs,
        )
        checkpoint_docs = list(items)
        writes_by_checkpoint = self.__get_writes_for_checkpoints(checkpoint_docs)

        for doc in checkpoint_docs:
            hydrated_doc = self.__hydrate_payload_doc(doc, ("checkpoint", "metadata"))
            yield self.__checkpoint_tuple_from_doc(
                hydrated_doc,
                writes_by_checkpoint.get(self.__write_group_key(doc), []),
            )

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[CheckpointTuple, None]:
        """List checkpoints from the database."""
        logging.info("Listing checkpoints with config: %s, filter: %s, before: %s", config, filter, before)
        if limit is not None and limit <= 0:
            return

        query, parameters, query_kwargs = self.__checkpoint_list_query(config, filter, before, limit)
        items = self.handler.acontainer.query_items(
            query=query,
            parameters=parameters,
            priority="High",
            **query_kwargs,
        )
        checkpoint_docs = [doc async for page in items.by_page() async for doc in page]
        writes_by_checkpoint = await self.__aget_writes_for_checkpoints(checkpoint_docs)

        hydrated_docs = [
            await self.__ahydrate_payload_doc(doc, ("checkpoint", "metadata"))
            for doc in checkpoint_docs
        ]
        for doc, hydrated_doc in zip(checkpoint_docs, hydrated_docs):
            yield self.__checkpoint_tuple_from_doc(
                hydrated_doc,
                writes_by_checkpoint.get(self.__write_group_key(doc), []),
            )
        logging.info("Completed listing checkpoints")

    def __checkpoint_list_query(
        self,
        config: Optional[RunnableConfig],
        filter: Optional[Dict[str, Any]],
        before: Optional[RunnableConfig],
        limit: Optional[int],
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        conditions = ["c.type = @type"]
        parameters = [self.__query_parameter("@type", "CHECKPOINT")]
        configurable = config.get("configurable", {}) if config else {}
        account_id = configurable.get("account_id")
        thread_id = configurable.get("thread_id")

        if config is not None:
            conditions.append("c.thread_id = @thread_id")
            conditions.append("c.account_id = @account_id")
            parameters.append(self.__query_parameter("@thread_id", thread_id))
            parameters.append(self.__query_parameter("@account_id", account_id))

            checkpoint_ns = self.__checkpoint_ns_from_config(configurable)
            conditions.append("c.checkpoint_ns = @checkpoint_ns")
            parameters.append(self.__query_parameter("@checkpoint_ns", checkpoint_ns))

        if filter:
            for idx, (key, value) in enumerate(filter.items()):
                parameter_name = f"@filter_{idx}"
                conditions.append(f"c.metadata.{key} = {parameter_name}")
                parameters.append(self.__query_parameter(parameter_name, value))

        if before is not None and (before_checkpoint_id := get_checkpoint_id(before)):
            conditions.append("c.checkpoint_id < @before_checkpoint_id")
            parameters.append(self.__query_parameter("@before_checkpoint_id", before_checkpoint_id))

        top = f"TOP {limit} " if limit is not None else ""
        query = f"SELECT {top}* FROM c WHERE {' AND '.join(conditions)} ORDER BY c.checkpoint_id DESC"
        query_kwargs = self.__partition_kwargs(account_id, thread_id)
        if limit is not None:
            query_kwargs["max_item_count"] = limit
        return query, parameters, query_kwargs

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Save a checkpoint to the database."""
        configurable = config.get("configurable", {})
        checkpoint_id = checkpoint["id"]
        checkpoint_ns = self.__checkpoint_ns_from_config(configurable)
        thread_id = configurable["thread_id"]
        account_id = configurable["account_id"]
        type_, serialized_checkpoint = self.serde.dumps_typed(checkpoint)
        metadata_type_, serialized_metadata = self.serde.dumps_typed(metadata)
        doc = {
            "id": self.__checkpoint_doc_id(thread_id, checkpoint_ns, checkpoint_id),
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "account_id": account_id,
            "checkpoint_id": checkpoint_id,
            "checkpoint": base64.b64encode(serialized_checkpoint).decode("ascii"),
            "checkpoint_type": type_,
            "metadata": base64.b64encode(serialized_metadata).decode("ascii"),
            "metadata_type": metadata_type_,
            "type": "CHECKPOINT",
        }
        if configurable.get("checkpoint_id"):
            doc["parent_checkpoint_id"] = configurable.get("checkpoint_id")

        for payload_doc in self.__chunked_payload_docs(doc, ("checkpoint", "metadata")):
            self.__write_with_retry(
                lambda payload_doc=payload_doc: self.handler.update_conversation(payload_doc),
                payload_doc["id"],
            )
        return {
            "configurable": {
                "thread_id": thread_id,
                "account_id": account_id,
                "checkpoint_id": checkpoint_id,
                "checkpoint_ns": checkpoint_ns,
            }
        }

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Save a checkpoint to the database."""
        configurable = config.get("configurable", {})
        checkpoint_id = checkpoint["id"]
        checkpoint_ns = self.__checkpoint_ns_from_config(configurable)
        thread_id = configurable["thread_id"]
        account_id = configurable["account_id"]
        type_, serialized_checkpoint = self.serde.dumps_typed(checkpoint)
        metadata_type_, serialized_metadata = self.serde.dumps_typed(metadata)
        doc = {
            "id": self.__checkpoint_doc_id(thread_id, checkpoint_ns, checkpoint_id),
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "account_id": account_id,
            "checkpoint_id": checkpoint_id,
            "checkpoint": base64.b64encode(serialized_checkpoint).decode("ascii"),
            "checkpoint_type": type_,
            "metadata": base64.b64encode(serialized_metadata).decode("ascii"),
            "metadata_type": metadata_type_,
            "type": "CHECKPOINT",
        }
        if configurable.get("checkpoint_id"):
            doc["parent_checkpoint_id"] = configurable.get("checkpoint_id")
        logging.info("Checkpoint %s saving for thread %s in namespace %s", checkpoint_id, thread_id, checkpoint_ns)
        payload_docs = self.__chunked_payload_docs(doc, ("checkpoint", "metadata"))
        await self.__awrite_payload_docs(payload_docs, insert_only=False)
        logging.info("Checkpoint %s saved for thread %s in namespace %s", checkpoint_id, thread_id, checkpoint_ns)
        return {
            "configurable": {
                "thread_id": thread_id,
                "account_id": account_id,
                "checkpoint_id": checkpoint_id,
                "checkpoint_ns": checkpoint_ns,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        configurable = config.get("configurable", {})
        checkpoint_ns = self.__checkpoint_ns_from_config(configurable)
        thread_id = configurable["thread_id"]
        checkpoint_id = configurable["checkpoint_id"]
        account_id = configurable["account_id"]
        for idx, (channel, value) in enumerate(writes):
            type_, value_encoded = self.serde.dumps_typed(value)
            channel_idx = WRITES_IDX_MAP.get(channel, idx)
            doc = {
                "id": self.__write_doc_id(thread_id, checkpoint_ns, checkpoint_id, task_id, channel_idx),
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "account_id": account_id,
                "task_id": task_id,
                "task_path": task_path,
                "checkpoint_id": checkpoint_id,
                "channel": channel,
                "channel_idx": channel_idx,
                "type": "WRITES",
                "channel_type": type_,
                "value": base64.b64encode(value_encoded).decode("ascii"),
            }
            for payload_doc in self.__chunked_payload_docs(doc, ("value",)):
                if channel_idx >= 0:
                    self.__write_with_retry(
                        lambda payload_doc=payload_doc: self.handler.insert_or_ignore(payload_doc),
                        payload_doc["id"],
                    )
                else:
                    self.__write_with_retry(
                        lambda payload_doc=payload_doc: self.handler.update_conversation(payload_doc),
                        payload_doc["id"],
                    )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        configurable = config.get("configurable", {})
        checkpoint_ns = self.__checkpoint_ns_from_config(configurable)
        thread_id = configurable["thread_id"]
        checkpoint_id = configurable["checkpoint_id"]
        account_id = configurable["account_id"]
        saved_doc_count = 0
        write_batches: List[Tuple[Sequence[Dict[str, Any]], bool]] = []
        logging.info("Writing %d writes for task %s in thread %s and namespace %s", len(writes), task_id, thread_id, checkpoint_ns)
        for idx, (channel, value) in enumerate(writes):
            type_, value_encoded = self.serde.dumps_typed(value)
            channel_idx = WRITES_IDX_MAP.get(channel, idx)
            doc = {
                "id": self.__write_doc_id(thread_id, checkpoint_ns, checkpoint_id, task_id, channel_idx),
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "account_id": account_id,
                "task_id": task_id,
                "task_path": task_path,
                "checkpoint_id": checkpoint_id,
                "channel": channel,
                "channel_idx": channel_idx,
                "type": "WRITES",
                "channel_type": type_,
                "value": base64.b64encode(value_encoded).decode("ascii"),
            }
            payload_docs = self.__chunked_payload_docs(doc, ("value",))
            write_batches.append((payload_docs, channel_idx >= 0))
            saved_doc_count += len(payload_docs)

        await asyncio.gather(*(
            self.__awrite_payload_docs(
                payload_docs,
                insert_only=insert_only,
            )
            for payload_docs, insert_only in write_batches
        ))

        logging.info("Completed %d writes for task %s in thread %s and namespace %s", saved_doc_count, task_id, thread_id, checkpoint_ns)

    def get_next_version(self, current: Optional[str], channel: None) -> str:
        """Generate the next version ID for a channel.

        This method creates a new version identifier for a channel based on its current version.

        Args:
            current (Optional[str]): The current version identifier of the channel.
            channel: Deprecated argument retained for LangGraph compatibility.

        Returns:
            str: The next version identifier, which is guaranteed to be monotonically increasing.
        """
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(current.split(".")[0])
        next_v = current_v + 1
        next_h = random.random()
        return f"{next_v:032}.{next_h:016}"
