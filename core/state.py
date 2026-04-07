from typing import TypedDict, List, Annotated
from langchain_core.messages import BaseMessage

def manage_history_reducer(left: list, right: list):
    """Custom reducer that appends messages, or completely wipes history if signaled."""
    if not right:
        return left
    if hasattr(right[0], "additional_kwargs") and right[0].additional_kwargs.get("action") == "WIPE_HISTORY":
        return right[1:]
    return left + right

class HypervisorState(TypedDict):
    messages: Annotated[List[BaseMessage], manage_history_reducer]
    active_agent: str
    sender: str
    episodic_summary: str
    turn_count: int