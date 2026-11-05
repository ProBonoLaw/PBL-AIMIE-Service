from types import SimpleNamespace

from AIInteractionService.utils.token_types import (
    aggregate_message_token_usage,
    aggregate_token_usage,
    log_agent_token_usage,
)


def test_aggregate_message_token_usage_sums_agent_model_calls():
    messages = [
        SimpleNamespace(
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "output_token_details": {"reasoning": 8},
            }
        ),
        {
            "response_metadata": {
                "token_usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 10,
                    "total_tokens": 40,
                    "completion_tokens_details": {"reasoning_tokens": 4},
                }
            }
        },
    ]

    usage, available = aggregate_message_token_usage(messages)

    assert available is True
    assert usage.input_tokens == 130
    assert usage.output_tokens == 30
    assert usage.total_tokens == 160
    assert usage.output_token_details.reasoning == 12


def test_log_agent_token_usage_emits_account_session_and_operation(caplog):
    model = SimpleNamespace(model_name="test-model", _llm_type="test-provider")
    result = {
        "messages": [
            SimpleNamespace(
                usage_metadata={
                    "input_tokens": 12,
                    "output_tokens": 3,
                    "total_tokens": 15,
                }
            )
        ]
    }

    usage = log_agent_token_usage(
        result,
        account_id="account-1",
        session_id="session-1",
        operation="timeline",
        llm=model,
        variant=0,
    )

    record = next(record for record in caplog.records if record.message == "token_usage")
    assert usage.total_tokens == 15
    assert record.accountId == "account-1"
    assert record.sessionId == "session-1"
    assert record.operation == "timeline"
    assert record.totalTokens == 15
    assert record.model == "test-model"


def test_aggregate_token_usage_sums_callback_totals_by_model():
    usage, available = aggregate_token_usage([
        {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60},
        {"input_tokens": 25, "output_tokens": 5, "total_tokens": 30},
    ])

    assert available is True
    assert usage.input_tokens == 75
    assert usage.output_tokens == 15
    assert usage.total_tokens == 90
