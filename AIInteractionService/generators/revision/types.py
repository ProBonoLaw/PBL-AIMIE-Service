from enum import Enum
from typing import Optional
from pydantic import AliasChoices, Field

from ..common.base_agent import BaseRequestModel

class VerbosityLevel(str, Enum):
    DEFAULT = "default"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class RevisionRequest(BaseRequestModel):
    statement: str = Field(
        ...,
        description="The statement to be validated.",
        serialization_alias='statement',
        validation_alias=AliasChoices('statement')
    )
    feedback: str = Field(
        ...,
        description="The feedback to be considered.",
        serialization_alias='feedback',
        validation_alias=AliasChoices('feedback')
    )
    use_retrievers: bool = Field(
        True,
        description="Whether to use context from previous interactions.",
        serialization_alias='use_retrievers',
        validation_alias=AliasChoices('use_retrievers', 'useRetrievers', 'UseRetrievers')
    )
    verbosity_level: Optional[VerbosityLevel] = Field(default=VerbosityLevel.DEFAULT,
                                                      serialization_alias="verbosityLevel",
                                                      validation_alias=AliasChoices(
                                                          "verbosity_level", "verbosityLevel", "VerbosityLevel"),
                                                      description="The verbosity level of the answer")

