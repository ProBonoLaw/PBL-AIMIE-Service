from typing import List
from orchestrators import Progress_Status

def update_progress(activity_context, actions: List, actions_completed: int, actions_remaining: int, increment=1) -> Progress_Status:
    if (increment < 1 or increment > len(actions)):
        raise ValueError("Increment must be between 1 and the number of actions remaining.")
    for _ in range(increment):
        actions.pop(0)
    actions_completed += increment
    actions_remaining -= increment
    activity_context.set_custom_status({'actionsCompleted': actions_completed, 'actionsRemaining': actions_remaining, 'actionsToComplete': actions })
    return actions_completed, actions_remaining