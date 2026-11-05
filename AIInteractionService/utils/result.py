from typing import Any, Dict


def get_answer(result: Dict[str, Any]):
    if 'answer' in result:
        answer = result["answer"]
    else:
        answer = result
    if "parsed" in answer:
        return answer["parsed"]
    return answer