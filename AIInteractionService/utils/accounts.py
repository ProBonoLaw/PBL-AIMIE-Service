
import os
from typing import Hashable, List, Optional
from async_lru import alru_cache
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
import logging

from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential

from .azure_credentials import default_azure_credential_options

class PersonalInformation(BaseModel, Hashable):
    first_name: Optional[str] = Field(
        default_factory=lambda: None,
        description="The first name of the party",
        serialization_alias="firstName",
        validation_alias=AliasChoices('firstName', 'first_name', 'FirstName'),
    )
    last_name: Optional[str] = Field(
        default_factory=lambda: None,
        description="The last name of the party",
        serialization_alias="lastName",
        validation_alias=AliasChoices('lastName', 'last_name', 'LastName'),
    )
    middle_name: Optional[str] = Field(
        default_factory=lambda: None,
        description="The middle name of the party",
        serialization_alias="middleInitial",
        validation_alias=AliasChoices('middleName', 'middle_name', 'MiddleName', 'middleInitial', 'middle_initial', 'MiddleInitial'),
    )
    email_address: Optional[str] = Field(
        default_factory=lambda: None,
        description="The email address of the party",
        serialization_alias="emailAddress",
        validation_alias=AliasChoices('emailAddress', 'email_address', 'EmailAddress'),
    )
    phone_number: Optional[str] = Field(
        default_factory=lambda: None,
        description="The phone number of the party",
        serialization_alias="phoneNumber",
        validation_alias=AliasChoices('phoneNumber', 'phone_number', 'PhoneNumber'),
    )
    organization: Optional[str] = Field(
        default_factory=lambda: None,
        description="The organization of the party",
        serialization_alias="organization",
        validation_alias=AliasChoices('organization', 'Organization'),
    )

    model_config = {
        "frozen": True
    }

    def __hash__(self):
        return hash((self.first_name, self.last_name, self.middle_name, self.email_address, self.phone_number, self.organization))
    
    def __eq__(self, other):
        if not isinstance(other, PersonalInformation):
            return NotImplemented
        return (self.first_name == other.first_name and
                self.last_name == other.last_name and
                self.middle_name == other.middle_name and
                self.email_address == other.email_address and
                self.phone_number == other.phone_number and
                self.organization == other.organization)

class AttorneyInformation(PersonalInformation, Hashable):
    firm_name: Optional[str] = Field(
        default_factory=lambda: None,
        description="The firm name of the attorney",
        serialization_alias="firmName",
        validation_alias=AliasChoices('firmName', 'firm_name', 'FirmName'),
    )
    isCurrent: bool = Field(
        ...,
        description="Whether the attorney is current",
        serialization_alias="isCurrent",
        validation_alias=AliasChoices('isCurrent', 'is_current', 'IsCurrent')
    )

    model_config = {
        "frozen": True
    }

    def __hash__(self):
        return hash((self.first_name, self.last_name, self.middle_name, self.email_address, self.phone_number, self.organization, self.firm_name, self.isCurrent))
    
    def __eq__(self, other):
        if not isinstance(other, AttorneyInformation):
            return NotImplemented
        return (super().__eq__(other) and
                self.firm_name == other.firm_name and
                self.isCurrent == other.isCurrent)

class OppositionParty(PersonalInformation, Hashable):
    filing_role: str = Field(
        ...,
        description="The role of the account in the case",
        serialization_alias="filingRole",
        validation_alias=AliasChoices('filingRole', 'filing_role', 'FilingRole'),
    )
    attorney_information: List[AttorneyInformation] = Field(
        ...,
        description="The attorney information of the opposition party",
        serialization_alias="attorneyInformation",
        validation_alias=AliasChoices('attorneyInformation', 'attorney_information', 'AttorneyInformation'),
    )

    model_config = {
        "frozen": True
    }

    def __hash__(self):
        return hash((
            self.first_name,
            self.last_name,
            self.middle_name,
            self.email_address,
            self.phone_number,
            self.organization,
            self.filing_role,
            tuple(self.attorney_information),
        ))
    
    def __eq__(self, other):
        if not isinstance(other, OppositionParty):
            return NotImplemented
        return (super().__eq__(other) and
                self.filing_role == other.filing_role and
                self.attorney_information == other.attorney_information)

class AccountInfo(BaseModel, Hashable):
    id: str = Field(
        ...,
        description="The unique identifier of the account",
        serialization_alias="id",
        validation_alias=AliasChoices('id', 'ID', 'Id'),
    )
    account_id: str = Field(
        ...,
        description="The unique identifier of the account",
        serialization_alias="accountId",
        validation_alias=AliasChoices('accountId', 'account_id', 'AccountId'),
    )
    case_number: str = Field(
        default='',
        description="The unique identifier of the case",
        serialization_alias="caseNumber",
        validation_alias=AliasChoices('caseNumber', 'case_number', 'CaseNumber'),
    )
    filing_role: str = Field(
        default='',
        description="The role of the account in the case",
        serialization_alias="filingRole",
        validation_alias=AliasChoices('filingRole', 'filing_role', 'FilingRole'),
    )
    state: str = Field(
        default='',
        description="The state of the account",
        serialization_alias="state",
        validation_alias=AliasChoices('state', 'State'),
    )
    county: str = Field(
        default='',
        description="The county of the account",
        serialization_alias="county",
        validation_alias=AliasChoices('county', 'County'),
    )
    description: str = Field(
        default='',
        description="The description of the account",
        serialization_alias="description",
        validation_alias=AliasChoices('description', 'Description'),
    )
    data_source_id: str = Field(
        ...,
        description="The data source ID of the account",
        serialization_alias="dataSourceId",
        validation_alias=AliasChoices('dataSourceId', 'data_source_id', 'DataSourceId'),
    )
    type: str = Field(
        ...,
        description="The type of the account",
        serialization_alias="type",
        validation_alias=AliasChoices('type', 'Type'),
    )
    person_information: Optional[PersonalInformation] = Field(
        default=None,
        description="The person information of the account",
        serialization_alias="personInformation",
        validation_alias=AliasChoices('personInformation', 'person_information', 'PersonInformation'),
    )
    opposition: Optional[OppositionParty] = Field(
        default=None,
        description="The opposition party information of the account",
        serialization_alias="opposition",
        validation_alias=AliasChoices('opposition', 'Opposition'),
    )
    attorney_information: Optional[List[AttorneyInformation]] = Field(
        default=None,
        description="The attorney information of the account",
        serialization_alias="attorneyInformation",
        validation_alias=AliasChoices('attorneyInformation', 'attorney_information', 'AttorneyInformation'),
    )
    is_web_site:bool = Field(
        default=False,
        description="Whether the account is a website",
        serialization_alias="isWebSite",
        validation_alias=AliasChoices('isWebSite', 'is_web_site', 'IsWebSite')
    )
    is_shared_resource: bool = Field(
        default=False,
        description="Whether the account is a shared resource",
        serialization_alias="isSharedResource",
        validation_alias=AliasChoices('isSharedResource', 'is_shared_resource', 'IsSharedResource')
    )
    search_endpoint: Optional[str] = Field(
        default=None,
        description="The search endpoint of the account",
        serialization_alias="searchEndpoint",
        validation_alias=AliasChoices('searchEndpoint', 'search_endpoint', 'SearchEndpoint'),
    )

    model_config = {
        "frozen": True
    }

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, AccountInfo):
            return NotImplemented

        return (
            self.id == other.id and
            self.account_id == other.account_id and
            self.case_number == other.case_number and
            self.filing_role == other.filing_role and
            self.state == other.state and
            self.county == other.county and
            self.description == other.description and
            self.data_source_id == other.data_source_id and
            self.type == other.type and
            self.person_information == other.person_information and
            self.opposition == other.opposition and
            self.attorney_information == other.attorney_information and
            self.is_web_site == other.is_web_site and
            self.is_shared_resource == other.is_shared_resource and
            self.search_endpoint == other.search_endpoint
        )

@alru_cache(ttl=300)
async def aget_account_info(account_id: str) -> AccountInfo:
    logging.info("Getting account info for {0}".format(account_id))
    cosmos_endpoint = os.getenv("ACCOUNT_COSMOS_ENDPOINT", None)
    database_name = os.getenv(
        "ACCOUNT_COSMOS_DATABASE", "db_conversation_history")
    container_name = os.getenv("ACCOUNT_COSMOS_CONTAINER", "accounts")
    if not cosmos_endpoint:
        raise EnvironmentError("ACCOUNT_COSMOS_ENDPOINT environment variable is missing")
    async with DefaultAzureCredential(**default_azure_credential_options()) as default_credential:
        async with CosmosClient(cosmos_endpoint, default_credential) as cosmos_client:
            database = cosmos_client.get_database_client(database_name)
            container = database.get_container_client(container_name)
            aresults = container.query_items(
                    "SELECT * FROM c WHERE c.type = 'ACCOUNT_DETAILS'",
                    partition_key=[account_id],
                    max_item_count=1)
            results = [item async for item in aresults]
            if len(results) == 0:
                raise FileNotFoundError(
                    "Missing general index for {0}".format(account_id))
            logging.info("Found account info for {0}".format(account_id))
            return AccountInfo.model_validate(results[0])