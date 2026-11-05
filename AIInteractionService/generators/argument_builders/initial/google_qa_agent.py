
from typing import Any, Dict, Type, Union


from ...common import AgentResult, AgentBaseType
from .base_qa_agent import BaseQaAgent
from ....utils.state import State, StateOpenAi

class AimieQaGoogleAgent(
        BaseQaAgent[State],
        metaclass=AgentBaseType,
        llm_type="google"
       ):
    def __init__(self, account_id: str,
                 session_id: str,
                 max_doc_count: int,
                 **kwargs: Any):
        if not kwargs:
            kwargs = {}
        if "name" not in kwargs:
            kwargs["name"] = "AIMIE"
        super().__init__(account_id, session_id, max_doc_count, **kwargs)

    def prepare_output(self, result: Dict[str, Any]) -> Union[AgentResult, StateOpenAi]:
        return AgentResult(
            answer=result["answer"],
            context=result["context"],
            sources=result["sources"],
            chat_history=result["chat_history"]
        )
