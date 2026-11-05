import asyncio
import base64
import json

import pytest
from azure.cosmos import exceptions

from AIInteractionService.db.cosmosdb_checkpointer import CosmosDBSaver


class FakeContainer:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []
        self.read_calls = []
        self.reads = {}

    def query_items(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self.responses.pop(0) if self.responses else [])

    def read_item(self, item, partition_key):
        self.read_calls.append({"item": item, "partition_key": partition_key})
        return self.reads[item]


class AsyncItems:
    def __init__(self, items):
        self.items = list(items)
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


class FakeAsyncContainer:
    def __init__(self, container):
        self.container = container
        self.responses = []
        self.current_response = []

    async def read_item(self, item, partition_key):
        return self.container.read_item(item, partition_key)

    def query_items(self, **kwargs):
        self.current_response = self.responses.pop(0) if self.responses else []
        return self

    def by_page(self):
        return AsyncItems([AsyncItems(self.current_response)])


class FakeHandler:
    def __init__(self, container=None):
        self.container = container or FakeContainer()
        self.acontainer = FakeAsyncContainer(self.container)
        self.inserted = []
        self.updated = []

    def insert_or_ignore(self, item):
        self.inserted.append(item)

    def update_conversation(self, item):
        self.updated.append(item)

    async def ainsert_or_ignore(self, item):
        self.inserted.append(item)

    async def aupdate_conversation(self, item, no_response=False):
        self.updated.append(item)


def _encoded(serializer, value):
    type_, serialized = serializer.dumps_typed(value)
    return type_, base64.b64encode(serialized).decode("ascii")


def _checkpoint_doc(saver, checkpoint_id, *, checkpoint_ns="", parent_checkpoint_id=None):
    checkpoint_type, checkpoint = _encoded(
        saver.serde,
        {
            "id": checkpoint_id,
            "channel_values": {},
            "channel_versions": {},
            "versions_seen": {},
        },
    )
    metadata_type, metadata = _encoded(saver.serde, {"source": "unit"})
    doc = {
        "id": f"thread-1_{checkpoint_ns}_{checkpoint_id}",
        "account_id": "account-1",
        "thread_id": "thread-1",
        "checkpoint_ns": checkpoint_ns,
        "checkpoint_id": checkpoint_id,
        "checkpoint_type": checkpoint_type,
        "checkpoint": checkpoint,
        "metadata_type": metadata_type,
        "metadata": metadata,
        "type": "CHECKPOINT",
    }
    if parent_checkpoint_id:
        doc["parent_checkpoint_id"] = parent_checkpoint_id
    return doc


def _write_doc(saver, checkpoint_id, task_id, channel, value, channel_idx, *, checkpoint_ns=""):
    channel_type, encoded_value = _encoded(saver.serde, value)
    return {
        "account_id": "account-1",
        "thread_id": "thread-1",
        "checkpoint_ns": checkpoint_ns,
        "checkpoint_id": checkpoint_id,
        "task_id": task_id,
        "channel": channel,
        "channel_idx": channel_idx,
        "channel_type": channel_type,
        "value": encoded_value,
        "type": "WRITES",
    }


def _params(call):
    return {parameter["name"]: parameter["value"] for parameter in call["parameters"]}


def test_get_tuple_uses_latest_query_and_returns_checkpoint_without_writes():
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    checkpoint = _checkpoint_doc(saver, "checkpoint-2")
    handler.container.responses = [[checkpoint], []]

    result = saver.get_tuple({"configurable": {"thread_id": "thread-1", "account_id": "account-1"}})

    assert result is not None
    assert result.config["configurable"]["checkpoint_id"] == "checkpoint-2"
    assert result.pending_writes == []
    assert len(handler.container.calls) == 2
    assert "SELECT TOP 1" in handler.container.calls[0]["query"]
    assert handler.container.calls[0]["max_item_count"] == 1
    assert _params(handler.container.calls[1])["@checkpoint_id"] == "checkpoint-2"


def test_get_tuple_with_checkpoint_id_uses_point_read_for_checkpoint():
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    checkpoint = _checkpoint_doc(saver, "checkpoint-1")
    handler.container.reads["thread-1__checkpoint-1"] = checkpoint
    handler.container.responses = [[]]

    result = saver.get_tuple(
        {
            "configurable": {
                "thread_id": "thread-1",
                "account_id": "account-1",
                "checkpoint_id": "checkpoint-1",
            }
        }
    )

    assert result is not None
    assert handler.container.read_calls == [
        {"item": "thread-1__checkpoint-1", "partition_key": ("account-1", "thread-1")}
    ]
    assert len(handler.container.calls) == 1
    assert _params(handler.container.calls[0])["@checkpoint_id"] == "checkpoint-1"


def test_list_applies_limit_and_batches_write_lookup():
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    checkpoint_2 = _checkpoint_doc(saver, "checkpoint-2")
    checkpoint_1 = _checkpoint_doc(saver, "checkpoint-1")
    write_2 = _write_doc(saver, "checkpoint-2", "task-b", "channel", {"value": 2}, 0)
    write_1 = _write_doc(saver, "checkpoint-1", "task-a", "channel", {"value": 1}, 0)
    handler.container.responses = [[checkpoint_2, checkpoint_1], [write_2, write_1]]

    results = list(
        saver.list(
            {
                "configurable": {
                    "thread_id": "thread-1",
                    "account_id": "account-1",
                    "checkpoint_id": "checkpoint-2",
                }
            },
            limit=2,
        )
    )

    assert [item.config["configurable"]["checkpoint_id"] for item in results] == [
        "checkpoint-2",
        "checkpoint-1",
    ]
    assert results[0].pending_writes == [("task-b", "channel", {"value": 2})]
    assert results[1].pending_writes == [("task-a", "channel", {"value": 1})]
    assert len(handler.container.calls) == 2
    assert "SELECT TOP 2 *" in handler.container.calls[0]["query"]
    assert "c.checkpoint_id = @checkpoint_id" not in handler.container.calls[0]["query"]
    assert "c.checkpoint_ns = @checkpoint_ns" in handler.container.calls[0]["query"]
    assert "@checkpoint_id" not in _params(handler.container.calls[0])
    assert _params(handler.container.calls[0])["@checkpoint_ns"] == ""
    assert "c.checkpoint_id IN" in handler.container.calls[1]["query"]
    assert _params(handler.container.calls[1])["@checkpoint_id_0"] == "checkpoint-1"
    assert _params(handler.container.calls[1])["@checkpoint_id_1"] == "checkpoint-2"


def test_put_writes_accepts_task_path_and_includes_task_id_in_document_id():
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    config = {
        "configurable": {
            "thread_id": "thread-1",
            "account_id": "account-1",
            "checkpoint_ns": "ns",
            "checkpoint_id": "checkpoint-1",
        }
    }

    saver.put_writes(config, [("channel", "first")], "task-a", task_path="node-a")
    saver.put_writes(config, [("channel", "second")], "task-b", task_path="node-b")

    assert [doc["id"] for doc in handler.inserted] == [
        "thread-1_ns_checkpoint-1_task-a_0",
        "thread-1_ns_checkpoint-1_task-b_0",
    ]
    assert [doc["task_path"] for doc in handler.inserted] == ["node-a", "node-b"]


def test_large_write_is_chunked_and_reassembled(monkeypatch):
    monkeypatch.setattr(CosmosDBSaver, "max_payload_chars", 64)
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    config = {
        "configurable": {
            "thread_id": "thread-1",
            "account_id": "account-1",
            "checkpoint_ns": "ns",
            "checkpoint_id": "checkpoint-1",
        }
    }
    value = {"content": "large-tool-result-" * 40}

    saver.put_writes(config, [("channel", value)], "task-a")

    manifest = next(doc for doc in handler.inserted if doc["type"] == "WRITES")
    chunks = [doc for doc in handler.inserted if doc["type"] == "WRITES_CHUNK"]
    assert manifest["payload_chunked"] is True
    assert manifest["value_chunk_count"] == len(chunks)
    assert "value" not in manifest
    assert all(len(doc["value"]) <= 64 for doc in chunks)

    checkpoint = _checkpoint_doc(saver, "checkpoint-1", checkpoint_ns="ns")
    handler.container.reads[checkpoint["id"]] = checkpoint
    for chunk in chunks:
        handler.container.reads[chunk["id"]] = chunk
    handler.container.responses = [[manifest]]

    result = saver.get_tuple({
        "configurable": {
            "thread_id": "thread-1",
            "account_id": "account-1",
            "checkpoint_ns": "ns",
            "checkpoint_id": "checkpoint-1",
        }
    })

    assert result is not None
    assert result.pending_writes == [("task-a", "channel", value)]


def test_large_checkpoint_is_chunked_and_reassembled(monkeypatch):
    monkeypatch.setattr(CosmosDBSaver, "max_payload_chars", 64)
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    config = {
        "configurable": {
            "thread_id": "thread-1",
            "account_id": "account-1",
            "checkpoint_ns": "ns",
        }
    }
    checkpoint = {
        "id": "checkpoint-1",
        "channel_values": {"messages": "large-checkpoint-" * 40},
        "channel_versions": {},
        "versions_seen": {},
    }

    saver.put(config, checkpoint, {"source": "unit"}, {})

    manifest = next(doc for doc in handler.updated if doc["type"] == "CHECKPOINT")
    chunks = [doc for doc in handler.updated if doc["type"] == "CHECKPOINT_CHUNK"]
    assert manifest["payload_chunked"] is True
    assert chunks
    assert "checkpoint" not in manifest
    assert all(len(doc["value"]) <= 64 for doc in chunks)

    for doc in handler.updated:
        handler.container.reads[doc["id"]] = doc
    handler.container.responses = [[]]
    result = saver.get_tuple({
        "configurable": {
            "thread_id": "thread-1",
            "account_id": "account-1",
            "checkpoint_ns": "ns",
            "checkpoint_id": "checkpoint-1",
        }
    })

    assert result is not None
    assert result.checkpoint["channel_values"] == checkpoint["channel_values"]


@pytest.mark.asyncio
async def test_async_large_write_uses_size_safe_cosmos_documents():
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    config = {
        "configurable": {
            "thread_id": "thread-1",
            "account_id": "account-1",
            "checkpoint_ns": "timeline",
            "checkpoint_id": "checkpoint-1",
        }
    }

    await saver.aput_writes(
        config,
        [("channel", {"content": "x" * 2_000_000})],
        "task-a",
    )

    assert any(doc["type"] == "WRITES_CHUNK" for doc in handler.inserted)
    assert any(doc["type"] == "WRITES" for doc in handler.inserted)
    assert all(len(json.dumps(doc).encode("utf-8")) < 2_000_000 for doc in handler.inserted)


@pytest.mark.asyncio
async def test_async_checkpoint_writes_for_independent_threads_overlap(monkeypatch):
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    started = 0
    both_started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_update(item, no_response=False):
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await release.wait()
        handler.updated.append(item)

    monkeypatch.setattr(handler, "aupdate_conversation", blocked_update)

    def config(thread_id):
        return {
            "configurable": {
                "thread_id": thread_id,
                "account_id": "account-1",
                "checkpoint_ns": "timeline",
            }
        }

    def checkpoint(checkpoint_id):
        return {
            "id": checkpoint_id,
            "channel_values": {},
            "channel_versions": {},
            "versions_seen": {},
        }

    tasks = [
        asyncio.create_task(
            saver.aput(
                config("thread-1"),
                checkpoint("checkpoint-1"),
                {"source": "unit"},
                {},
            )
        ),
        asyncio.create_task(
            saver.aput(
                config("thread-2"),
                checkpoint("checkpoint-2"),
                {"source": "unit"},
                {},
            )
        ),
    ]
    try:
        await asyncio.wait_for(both_started.wait(), timeout=1)
    finally:
        release.set()
        await asyncio.gather(*tasks)

    assert started == 2


@pytest.mark.asyncio
async def test_async_chunk_writes_overlap_and_manifest_is_written_last(monkeypatch):
    monkeypatch.setattr(CosmosDBSaver, "max_payload_chars", 32)
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    chunk_calls = 0
    two_chunks_started = asyncio.Event()
    release_chunks = asyncio.Event()
    completed_types = []

    async def blocked_update(item, no_response=False):
        nonlocal chunk_calls
        if item["type"] == "CHECKPOINT_CHUNK":
            chunk_calls += 1
            if chunk_calls == 2:
                two_chunks_started.set()
            await release_chunks.wait()
        completed_types.append(item["type"])

    monkeypatch.setattr(handler, "aupdate_conversation", blocked_update)
    write_task = asyncio.create_task(saver.aput(
        {
            "configurable": {
                "thread_id": "thread-1",
                "account_id": "account-1",
                "checkpoint_ns": "timeline",
            }
        },
        {
            "id": "checkpoint-1",
            "channel_values": {"messages": "large-checkpoint-" * 40},
            "channel_versions": {},
            "versions_seen": {},
        },
        {"source": "unit"},
        {},
    ))
    try:
        await asyncio.wait_for(two_chunks_started.wait(), timeout=1)
        assert "CHECKPOINT" not in completed_types
    finally:
        release_chunks.set()
        await write_task

    assert chunk_calls > 1
    assert completed_types[-1] == "CHECKPOINT"


@pytest.mark.asyncio
async def test_async_get_tuple_reassembles_chunked_write(monkeypatch):
    monkeypatch.setattr(CosmosDBSaver, "max_payload_chars", 64)
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    config = {
        "configurable": {
            "thread_id": "thread-1",
            "account_id": "account-1",
            "checkpoint_ns": "ns",
            "checkpoint_id": "checkpoint-1",
        }
    }
    value = {"content": "async-large-tool-result-" * 40}
    saver.put_writes(config, [("channel", value)], "task-a")

    manifest = next(doc for doc in handler.inserted if doc["type"] == "WRITES")
    checkpoint = _checkpoint_doc(saver, "checkpoint-1", checkpoint_ns="ns")
    handler.container.reads[checkpoint["id"]] = checkpoint
    for doc in handler.inserted:
        handler.container.reads[doc["id"]] = doc
    handler.acontainer.responses = [[manifest]]

    result = await saver.aget_tuple(config)

    assert result is not None
    assert result.pending_writes == [("task-a", "channel", value)]


@pytest.mark.asyncio
async def test_async_checkpoint_write_retries_cosmos_429(monkeypatch):
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    attempts = 0

    async def throttled_update(item, no_response=False):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise exceptions.CosmosHttpResponseError(
                status_code=429,
                message='throttled',
            )
        handler.updated.append(item)

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(handler, 'aupdate_conversation', throttled_update)
    monkeypatch.setattr(
        'AIInteractionService.db.cosmosdb_checkpointer.asyncio.sleep',
        no_sleep,
    )

    await saver.aput(
        {
            'configurable': {
                'thread_id': 'thread-1',
                'account_id': 'account-1',
                'checkpoint_ns': 'timeline',
            }
        },
        {
            'id': 'checkpoint-1',
            'channel_values': {},
            'channel_versions': {},
            'versions_seen': {},
        },
        {'source': 'unit'},
        {},
    )

    assert attempts == 2
    assert len(handler.updated) == 1


def test_sync_checkpoint_write_paths_retry_cosmos_429(monkeypatch):
    handler = FakeHandler()
    saver = CosmosDBSaver(handler)
    attempts = {"update": 0, "insert": 0}
    retried_update_ids: set[str] = set()
    retried_insert_ids: set[str] = set()

    def throttled_update(item):
        attempts["update"] += 1
        if item["id"] not in retried_update_ids:
            retried_update_ids.add(item["id"])
            raise exceptions.CosmosHttpResponseError(
                status_code=429,
                message="throttled",
            )
        handler.updated.append(item)

    def throttled_insert(item):
        attempts["insert"] += 1
        if item["id"] not in retried_insert_ids:
            retried_insert_ids.add(item["id"])
            raise exceptions.CosmosHttpResponseError(
                status_code=429,
                message="throttled",
            )
        handler.inserted.append(item)

    monkeypatch.setattr(handler, "update_conversation", throttled_update)
    monkeypatch.setattr(handler, "insert_or_ignore", throttled_insert)
    monkeypatch.setattr(
        "AIInteractionService.db.cosmosdb_checkpointer.time.sleep",
        lambda _delay: None,
    )

    saver.put(
        {
            "configurable": {
                "thread_id": "thread-1",
                "account_id": "account-1",
            }
        },
        {
            "id": "checkpoint-1",
            "channel_values": {},
            "channel_versions": {},
            "versions_seen": {},
        },
        {"source": "unit"},
        {},
    )

    config = {
        "configurable": {
            "thread_id": "thread-1",
            "account_id": "account-1",
            "checkpoint_ns": "timeline",
            "checkpoint_id": "checkpoint-1",
        }
    }

    saver.put_writes(
        config,
        [("channel", "value"), ("__error__", "value")],
        "task-1",
    )

    assert attempts == {"update": 4, "insert": 2}
    assert len(retried_update_ids) == 2
    assert len(handler.updated) == 2
    assert len(handler.inserted) == 1
