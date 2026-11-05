from enum import Enum
from typing import Optional
from pydantic import AliasChoices, Field

from ...common.base_agent import BaseRequestModel

class VerbosityLevel(str, Enum):
    DEFAULT = "default"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class QARequest(BaseRequestModel):
    use_enhanced_retriever: bool = Field(default=True,
                                         serialization_alias="useEnhancedRetriever",
                                         validation_alias=AliasChoices(
                                             "use_enhanced_retriever", "useEnhancedRetriever", "UseEnhancedRetriever"),
                                         description="Whether to enhance retrieval with multi-query expansion")
    input: str
    aimies_client: str
    aimies_filing_role: str
    opposition: str
    opposition_role: str
    verbosity_level: Optional[VerbosityLevel] = Field(default=VerbosityLevel.DEFAULT,
                                                      serialization_alias="verbosityLevel",
                                                      validation_alias=AliasChoices(
                                                          "verbosity_level", "verbosityLevel", "VerbosityLevel"),
                                                      description="The verbosity level of the answer")
