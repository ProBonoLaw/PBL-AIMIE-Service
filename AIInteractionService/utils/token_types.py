import logging
from collections.abc import Iterable, Mapping
from typing import Any, Dict, Optional

from pydantic import AliasChoices, BaseModel, Field


class InputTokenDetails(BaseModel):
    audio: int = Field(default=0,
                        serialization_alias="audio",
                        validation_alias=AliasChoices('audio_tokens', 'prompt_audio_tokens', 'audio'))
    cache_read: int | None = Field(default=None,
                                    serialization_alias="cache_read",
                                    validation_alias=AliasChoices('prompt_cache_read_tokens', 'prompt_cache_read', 'prompt_cache', 'cache_tokens', 'cache_read'))


class OutputTokenDetails(BaseModel):
    audio: int = Field(default=0,
                        serialization_alias="audio",
                        validation_alias=AliasChoices('audio_tokens', 'completion_audio_tokens', 'audio'))
    reasoning: int | None = Field(default=None,
                                   serialization_alias="reasoning",
                                   validation_alias=AliasChoices('completion_reasoning_tokens', 'reasoning_tokens', 'reasoning'))


class TokenUsage(BaseModel):
    input_tokens: int = Field(
        default=0,
        serialization_alias="input_tokens",
        validation_alias=AliasChoices('prompt_tokens', 'input_tokens'))
    output_tokens: int = Field(
        default=0,
        serialization_alias="output_tokens",
        validation_alias=AliasChoices('completion_tokens', 'output_tokens'))
    total_tokens: Optional[int] = Field(
        default=None,
        serialization_alias="total_tokens",
        validation_alias=AliasChoices('total_tokens'))
    input_token_details: Optional[InputTokenDetails] = Field(
        default=None,
        serialization_alias="input_token_details",
        validation_alias=AliasChoices('prompt_tokens_details', 'input_token_details'))
    output_token_details: Optional[OutputTokenDetails] = Field(
        default=None,
        serialization_alias="output_token_details",
        validation_alias=AliasChoices('completion_tokens_details', 'output_token_details'))


def parse_token_usage(data: Dict) -> TokenUsage:
    try:
        result = TokenUsage.model_validate(data, extra="ignore")
        if result.total_tokens is None:
            result.total_tokens = result.input_tokens + result.output_tokens
        return result
    except Exception as error:
        logging.warning(f"Failed to parse token usage data: {error}")
        return TokenUsage(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            input_token_details=None,
            output_token_details=None,
        )


def aggregate_token_usage(usages: Iterable[Mapping[str, Any]]) -> tuple[TokenUsage, bool]:
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    reasoning_tokens = 0
    usage_available = False

    for usage in usages:
        parsed = parse_token_usage(dict(usage))
        input_tokens += parsed.input_tokens
        output_tokens += parsed.output_tokens
        total_tokens += parsed.total_tokens or 0
        if parsed.output_token_details is not None:
            reasoning_tokens += parsed.output_token_details.reasoning or 0
        usage_available = True

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        output_token_details=OutputTokenDetails(reasoning=reasoning_tokens),
    ), usage_available


def aggregate_message_token_usage(messages: Iterable[Any]) -> tuple[TokenUsage, bool]:
    usages: list[Mapping[str, Any]] = []
    for message in messages:
        if isinstance(message, Mapping):
            usage = message.get("usage_metadata")
            response_metadata = message.get("response_metadata")
        else:
            usage = getattr(message, "usage_metadata", None)
            response_metadata = getattr(message, "response_metadata", None)

        if not usage and isinstance(response_metadata, Mapping):
            usage = response_metadata.get("token_usage") or response_metadata.get("usage")
        if isinstance(usage, Mapping):
            usages.append(usage)

    return aggregate_token_usage(usages)


def log_agent_token_usage(
    result: Any,
    *,
    account_id: str,
    session_id: str,
    operation: str,
    llm: Any = None,
    variant: int | None = None,
    usage_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> TokenUsage:
    if usage_metadata:
        tokens, usage_available = aggregate_token_usage(usage_metadata.values())
    else:
        messages = result.get("messages", []) if isinstance(result, Mapping) else []
        tokens, usage_available = aggregate_message_token_usage(messages)
    llm_type = getattr(llm, "_llm_type", None)
    if callable(llm_type):
        llm_type = llm_type()
    model = (
        getattr(llm, "model", None)
        or getattr(llm, "model_name", None)
        or getattr(llm, "model_id", None)
    )
    lc_id = ",".join(llm.lc_id()) if llm is not None and hasattr(llm, "lc_id") else None

    logging.warning(
        "token_usage",
        extra={
            "microsoft.custom_event.name": "token_usage",
            "accountId": account_id,
            "sessionId": session_id,
            "operation": operation,
            "variant": variant,
            "inputTokens": tokens.input_tokens,
            "outputTokens": tokens.output_tokens,
            "totalTokens": tokens.total_tokens,
            "reasoningTokens": tokens.output_token_details.reasoning if tokens.output_token_details else 0,
            "usageAvailable": usage_available,
            "isSecondaryLLM": False,
            "type": llm_type,
            "model": model,
            "lc_id": lc_id,
        },
    )
    return tokens
