from typing import Any, Optional, Sequence
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages.base import BaseMessage, message_to_dict
from pydantic import BaseModel, Field
from langchain_core.messages.utils import messages_from_dict
from uuid import uuid4
import os
import logging
from azure.cosmos import CosmosClient, DatabaseProxy, ContainerProxy

class CosmosDbMessageHistoryProcessor(BaseChatMessageHistory, BaseModel):
    def __init__(self, account_id: str, session_id: Optional[str] = None, max_message_count: int = 10):
        if session_id is None:
            self.__dict__['session_id'] = str(uuid4())
        else:
            self.__dict__['session_id'] = session_id
        self.__dict__['max_message_count'] = max_message_count
        self.__dict__['account_id'] = account_id
        url = os.environ['COSMOS_MESSAGE_HISTORY_ENDPOINT']
        key = os.environ['AZ_COSMOS_ACCOUNT_KEY']
        self.__dict__['client'] = CosmosClient(url, credential=key)
        self.__dict__['db_client'] = self.client.get_database_client('db_conversation_history')
        self.__dict__['container_client'] = self.db_client.get_container_client('messages')

    @property
    def session_id(self) -> str:
        return self.__dict__['session_id']
    
    @property
    def account_id(self) -> str:
        return self.__dict__['account_id']
    
    @property
    def max_message_count(self) -> int:
        return self.__dict__['max_message_count']
    
    @property
    def client(self) -> CosmosClient:
        return self.__dict__['client']
    
    @property
    def db_client(self) -> DatabaseProxy:
        return self.__dict__['db_client']
    
    @property
    def container_client(self) -> ContainerProxy:
        return self.__dict__['container_client']

    @property
    def messages(self) -> list[BaseMessage]:
        response = self.container_client.query_items(f"SELECT * FROM c WHERE c.sessionId = '{self.session_id}' ORDER BY c._ts ASC",partition_key=[self.account_id, self.session_id])
        messages = messages_from_dict([item for item in response])
        logging.info('Pulled %s entries for account: %s, session: %s', len(messages), self.account_id, self.session_id)
        return messages

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        for message in messages:
            if message.id is None:
                message.id = str(uuid4())
            document = message_to_dict(message)
            document['sessionId'] = self.session_id
            document['accountId'] = self.account_id
            document['id'] = message.id
            self.container_client.create_item(document)
            
    def clear(self):
        self.container_client.delete_all_items_by_partition_key(partition_key=[self.account_id, self.session_id])