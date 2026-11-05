from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.cosmos import exceptions

from AIInteractionService.db import cosmosdb_handler


def test_credentials_are_configured_when_handler_is_created(monkeypatch):
    monkeypatch.setattr(cosmosdb_handler, "_global_default_credential", None)
    monkeypatch.setattr(cosmosdb_handler, "_global_async_default_credential", None)
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant")
    monkeypatch.setenv("AZURE_CLIENT_ID", "client")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "secret")

    default_credential = object()
    async_default_credential = object()
    database = MagicMock()
    async_database = MagicMock()
    client = MagicMock()
    async_client = MagicMock()
    client.get_database_client.return_value = database
    async_client.get_database_client.return_value = async_database

    with (
        patch.object(
            cosmosdb_handler,
            "DefaultAzureCredential",
            return_value=default_credential,
        ) as default_credential_factory,
        patch.object(
            cosmosdb_handler,
            "AsyncDefaultAzureCredential",
            return_value=async_default_credential,
        ) as async_default_credential_factory,
        patch.object(cosmosdb_handler, "CosmosClient", return_value=client),
        patch.object(cosmosdb_handler, "AsyncCosmosClient", return_value=async_client),
    ):
        handler = cosmosdb_handler.CosmosDBHandler("endpoint", "database", "container")

    default_credential_factory.assert_called_once_with(
        exclude_environment_credential=False,
    )
    async_default_credential_factory.assert_called_once_with(
        exclude_environment_credential=False,
    )
    assert handler.default_credential is default_credential
    assert handler.async_default_credential is async_default_credential


def _handler_without_initialization():
    handler = object.__new__(cosmosdb_handler.CosmosDBHandler)
    handler.container = MagicMock()
    handler.acontainer = MagicMock()
    handler.acontainer.create_item = AsyncMock()
    return handler


def test_insert_or_ignore_creates_without_reading():
    handler = _handler_without_initialization()
    item = {
        "id": "write-1",
        "account_id": "account-1",
        "thread_id": "thread-1",
    }

    handler.insert_or_ignore(item)

    handler.container.create_item.assert_called_once_with(
        body=item,
        priority="High",
        no_response=True,
    )
    handler.container.read_item.assert_not_called()
    handler.container.upsert_item.assert_not_called()


def test_insert_or_ignore_ignores_only_conflicts():
    handler = _handler_without_initialization()
    item = {
        "id": "write-1",
        "account_id": "account-1",
        "thread_id": "thread-1",
    }
    handler.container.create_item.side_effect = (
        exceptions.CosmosResourceExistsError(status_code=409, message="exists")
    )

    handler.insert_or_ignore(item)

    throttled = exceptions.CosmosHttpResponseError(
        status_code=429,
        message="throttled",
    )
    handler.container.create_item.side_effect = throttled
    with pytest.raises(exceptions.CosmosHttpResponseError) as raised:
        handler.insert_or_ignore(item)
    assert raised.value is throttled


@pytest.mark.asyncio
async def test_async_insert_or_ignore_creates_without_reading():
    handler = _handler_without_initialization()
    item = {
        "id": "write-1",
        "account_id": "account-1",
        "thread_id": "thread-1",
    }

    await handler.ainsert_or_ignore(item)

    handler.acontainer.create_item.assert_awaited_once_with(
        body=item,
        priority="High",
        no_response=True,
    )
    handler.acontainer.read_item.assert_not_called()
    handler.acontainer.upsert_item.assert_not_called()


@pytest.mark.asyncio
async def test_async_insert_or_ignore_ignores_only_conflicts():
    handler = _handler_without_initialization()
    item = {
        "id": "write-1",
        "account_id": "account-1",
        "thread_id": "thread-1",
    }
    handler.acontainer.create_item.side_effect = (
        exceptions.CosmosResourceExistsError(status_code=409, message="exists")
    )

    await handler.ainsert_or_ignore(item)

    throttled = exceptions.CosmosHttpResponseError(
        status_code=429,
        message="throttled",
    )
    handler.acontainer.create_item.side_effect = throttled
    with pytest.raises(exceptions.CosmosHttpResponseError) as raised:
        await handler.ainsert_or_ignore(item)
    assert raised.value is throttled
