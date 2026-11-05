
from typing_extensions import List, TypedDict, Optional

from ..common import BaseRequestModel
from .topic_questions import DiscoveryTopicQuestionsWriterOutput
from ...utils.common_types import Source

class DiscoveryRequestWriterAgentRequest(BaseRequestModel):
    input: str
    location: str
    hearing_type: str
    target: str
    questions: List[DiscoveryTopicQuestionsWriterOutput]


class DiscoveryRequestWriterOutput(BaseRequestModel):
    discovery_order: str

class TopicQuestions(TypedDict):
    topic: str
    questions: List[str]
    sources: Optional[List[Source]]


class DiscoveryBuilderOutput(TypedDict):
    discovery_order: str
    questions_by_topic: List[TopicQuestions]
    has_error: Optional[bool]