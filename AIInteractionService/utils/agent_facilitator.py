import asyncio
from datetime import datetime, timedelta
import os
import inspect
import logging
import time
from types import ModuleType
from typing import Any, List, Optional, Sequence, Type, TypeVar
from async_lru import alru_cache

from azure.storage.blob.aio import BlobServiceClient
from azure.identity.aio import DefaultAzureCredential
from pydantic import AliasChoices, BaseModel, Field

from ..generators.common.base_agent import BaseAgent
from .azure_credentials import default_azure_credential_options

class AgentInstanceConfig(BaseModel):
    """
    This class represents the configuration for an agent instance.
    It includes the agent's name, type, and any other relevant settings.
    """
    class_name: str = Field(...,
                            description="The class name of the agent instance",
                            validation_alias=AliasChoices("class_name", "className"))
    llm_type: Optional[str] = Field(default=None, validation_alias=AliasChoices("llm_type", "llmType"))
    kwargs: dict 

class AgentConfig(BaseModel):
    """
    This class represents the configuration for an agent.
    It includes the agent's name, type, and any other relevant settings.
    """
    name: str
    description: str
    primary_prompt: Optional[List[str]] = Field(None,
                                description="The primary prompt for the agent",
                                validation_alias=AliasChoices("primary_prompt", "primaryPrompt"))
    primary_agent: AgentInstanceConfig = Field(..., 
                                               description="Primary agent instance configuration", 
                                               validation_alias=AliasChoices("primary_agent", "primaryAgent"))
    backup_agents: Sequence[AgentInstanceConfig] = Field(...,
                                                         description="Backup agent instance configurations", 
                                                         validation_alias=AliasChoices("backup_agents", "backupAgents"))


T = TypeVar('T', bound=BaseAgent, covariant=True)
class AgentFacilitator[T]:
    """
    This class is responsible for managing the interaction between the user and the AI agent.
    It handles the initialization of the agent, the processing of user input, and the generation
    of responses from the agent.
    """

    def __init__(self, agentModule: ModuleType, **kwargs):
        self.agentModule = agentModule
        endpoint = os.getenv("CONFIG_STORAGE_ACCOUNT", None)
        if not endpoint:
            raise EnvironmentError("CONFIG_STORAGE_ACCOUNT environment variable is missing")
        self.endpoint = endpoint
        self.container_name = os.getenv("CONFIG_STORAGE_ACCOUNT_CONTAINER", "agents")
        if not hasattr(agentModule, "module_identifier"):
            raise EnvironmentError("Agent module does not have a module identifier")
        self.module_identifier:str = getattr(agentModule, "module_identifier")
        self.agent_configuration: Optional[AgentConfig] = None
        
    
    @alru_cache(ttl=120)
    async def __get_agent_configurations(self, module_identifier: str) -> AgentConfig:
        """
        Load agent configurations from Azure Blob Storage.
        """
        if self.agent_configuration:
            return self.agent_configuration
        try:
            async with DefaultAzureCredential(**default_azure_credential_options()) as default_credential:
                async with BlobServiceClient(account_url=self.endpoint, credential=default_credential) as blob_service_client:
                    async with blob_service_client.get_container_client(self.container_name) as container_client:
                        # Assuming the agent configuration is stored in a specific blob
                        async with container_client.get_blob_client(f"{module_identifier}.json") as blob_client:
                            if not await blob_client.exists():
                                raise FileNotFoundError(f"Blob {module_identifier}.json does not exist in container {self.container_name}")
                            config_data = await blob_client.download_blob()
                            self.agent_configuration = AgentConfig.model_validate_json(await config_data.readall())
                            return self.agent_configuration
        except Exception as e:
            raise RuntimeError(f"Failed to load agent configurations: {e}")


    async def get_agent_config(self) -> AgentConfig:
        return await self.__get_agent_configurations(self.module_identifier)


    async def get_agent_variant_config(self, index: int) -> AgentInstanceConfig:
        agent_config = await self.__get_agent_configurations(self.module_identifier)
        if index == 0:
            return agent_config.primary_agent
        if index <= len(agent_config.backup_agents):
            return agent_config.backup_agents[index - 1]
        raise ValueError("Invalid agent index")


    async def get_agent_variant_instance(self, 
                                 index: int, 
                                 account_id: str, 
                                 session_id: str, 
                                 max_doc_count: int = 10, 
                                 **kwargs: Any) -> T:
        """
        Process the user input and generate a response from the agent.
        """
        agent_config = await self.__get_agent_configurations(self.module_identifier)
        
        if index == 0:
            agent_instance_config = agent_config.primary_agent
        elif index <= len(agent_config.backup_agents):
            agent_instance_config = agent_config.backup_agents[index - 1]
        else:
            raise ValueError("Invalid agent index")
        agent_class = getattr(self.agentModule, agent_instance_config.class_name)
        
        merged_kwargs = agent_instance_config.kwargs.copy()
        if "primary_prompt" not in kwargs:
            merged_kwargs["primary_prompt"] = agent_config.primary_prompt
        merged_kwargs.update(kwargs)
        
        try:
            if inspect.signature(agent_class.__init__).parameters.get("max_doc_count") is not None:
                instance = agent_class(
                    account_id=account_id, # type: ignore
                    session_id=session_id, # type: ignore
                    max_doc_count=max_doc_count, # type: ignore
                    **merged_kwargs)
            else:
                instance = agent_class(
                    account_id=account_id, # type: ignore
                    session_id=session_id, # type: ignore
                    **merged_kwargs)
            return instance
        except Exception as e:
            logging.error(f"Error creating agent instance: {e}")
            raise RuntimeError(f"Failed to create agent instance: {e}")
    
    async def get_agent_variant_count(self) -> int:
        """
        Get the number of backup agents.
        """
        agentConfig = await self.__get_agent_configurations(self.module_identifier)
        return len(agentConfig.backup_agents) + 1
    