import logging
from threading import Lock

from azure.cosmos import CosmosClient, exceptions, PartitionKey
from azure.cosmos.aio import CosmosClient as AsyncCosmosClient
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential

from AIInteractionService.utils.azure_credentials import default_azure_credential_options

_global_default_credential = None
_global_async_default_credential = None
_default_credential_lock = Lock()
logger = logging.getLogger(__name__)


def _get_default_credentials():
    global _global_default_credential, _global_async_default_credential

    if _global_default_credential is None or _global_async_default_credential is None:
        with _default_credential_lock:
            if _global_default_credential is None or _global_async_default_credential is None:
                credential_options = default_azure_credential_options()
                default_credential = DefaultAzureCredential(**credential_options)
                async_default_credential = AsyncDefaultAzureCredential(**credential_options)
                _global_default_credential = default_credential
                _global_async_default_credential = async_default_credential

    return _global_default_credential, _global_async_default_credential


class CosmosDBHandler(object):
    
    def __init__(self, endpoint, database_name, collection):
        self.default_credential, self.async_default_credential = _get_default_credentials()
        self.client = CosmosClient(endpoint, self.default_credential)
        self.aclient = AsyncCosmosClient(endpoint, self.async_default_credential, connection_mode="Direct", connection_protocol="Tcp")
        self.database_name = database_name
        self.container_name = collection

        try:
            self.database = self.client.get_database_client(self.database_name)
        except exceptions.CosmosResourceNotFoundError:
            self.database = self.client.create_database(self.database_name)
        self.adatabase = self.aclient.get_database_client(self.database_name)

        try:
            self.container = self.database.get_container_client(self.container_name)
        except exceptions.CosmosResourceNotFoundError:
            self.container = self.database.create_container(
                id=self.container_name, partition_key=PartitionKey(path=['/account_id', '/thread_id'])
            )
        except exceptions.CosmosHttpResponseError as exc:
            logger.exception("Failed to create Cosmos container",
                              extra={'cosmos_container': self.container_name, 'cosmos_database': self.database_name})
        self.acontainer = self.adatabase.get_container_client(self.container_name)

    def __enter__(self):
        return self

    def __exit__(self, endpoint, collection, traceback):
        self.client = None


    def update_conversation(self, item):
        self.container.upsert_item(body=item)
    
    async def aupdate_conversation(self, item, no_response= False):
        await self.acontainer.upsert_item(body=item, priority="High", no_response=no_response)

    def insert_or_ignore(self, item):
        try:
            self.container.create_item(body=item, priority="High", no_response=True)
        except exceptions.CosmosResourceExistsError:
            pass
    
    async def ainsert_or_ignore(self, item):
        try:
            await self.acontainer.create_item(
                body=item,
                priority="High",
                no_response=True,
            )
        except exceptions.CosmosResourceExistsError:
            pass
    