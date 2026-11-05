from AIInteractionService.generators.common.agent_base import AgentBaseType
from AIInteractionService.generators.timelines.agent import build_timeline_model
from AIInteractionService.utils.agent_facilitator import AgentInstanceConfig


def test_timeline_config_accepts_explicit_provider_type():
    config = AgentInstanceConfig.model_validate({
        'className': 'AzureOpenAiTimelineAgent',
        'llmType': 'azureOpenAI',
        'kwargs': {},
    })
    assert config.llm_type == 'azureOpenAI'


def test_provider_type_can_be_inferred_from_existing_agent_class_names():
    assert AgentBaseType.llm_type_for_class_name('AzureOpenAiTimelineAgent') == 'azureopenai'
    assert AgentBaseType.llm_type_for_class_name('AnthropicTimelineAgent') == 'anthropic'
    assert AgentBaseType.llm_type_for_class_name('OpenAiTimelineAgent') == 'openai'
    assert AgentBaseType.llm_type_for_class_name('AzureAnthropicTimelineAgent') == 'azureanthropic'
    assert AgentBaseType.llm_type_for_class_name('AnthropicFoundryTimelineAgent') == 'azureanthropic'


def test_timeline_model_uses_shared_model_factory(monkeypatch):
    calls = []

    def build_model(provider, kwargs):
        calls.append((provider, kwargs))
        return 'model'

    monkeypatch.setattr(AgentBaseType, 'build_model', build_model)
    assert build_timeline_model('AzureOpenAiTimelineAgent', {'timeout': 5}) == 'model'
    assert calls == [('azureopenai', {'timeout': 5})]


def test_azure_openai_uses_responses_api_chat_openai(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT', 'https://example.cognitiveservices.azure.com/')
    monkeypatch.setenv('AZURE_OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr('AIInteractionService.generators.common.agent_base.ChatOpenAI', FakeChatOpenAI)

    AgentBaseType.build_model('azureOpenAI', {
        'model': 'gpt-5.6-luna',
        'reasoning': {'effort': 'max', 'mode': 'standard'},
    })

    assert captured['base_url'] == 'https://example.cognitiveservices.azure.com/openai/v1/'
    assert captured['model'] == 'gpt-5.6-luna'
    assert captured['use_responses_api'] is True
    assert captured['reasoning'] == {'effort': 'max', 'mode': 'standard'}


def test_openai_uses_the_current_responses_api_configuration(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr('AIInteractionService.generators.common.agent_base.ChatOpenAI', FakeChatOpenAI)

    AgentBaseType.build_model('openai', {
        'model': 'gpt-5.6-luna',
        'reasoning': {'effort': 'low', 'mode': 'standard'},
        'timeout': 300,
    })

    assert captured['model'] == 'gpt-5.6-luna'
    assert captured['timeout'] == 300
    assert captured['use_responses_api'] is True
    assert captured['reasoning'] == {'effort': 'low', 'mode': 'standard'}
    assert 'n' not in captured
    assert 'extra_body' not in captured
    assert 'model_kwargs' not in captured


def test_timeline_configuration_keeps_its_system_prompt_in_json():
    from pathlib import Path
    from AIInteractionService.utils.agent_facilitator import AgentConfig

    config = AgentConfig.model_validate_json(
        Path('configs/timeline.json').read_text(encoding='utf-8')
    )
    assert config.primary_prompt
    assert (
        'evidence-focused legal and investigative timeline builder'
        in config.primary_prompt[0]
    )


def test_timeline_configuration_has_azure_anthropic_backup():
    from pathlib import Path
    from AIInteractionService.utils.agent_facilitator import AgentConfig

    config = AgentConfig.model_validate_json(
        Path('configs/timeline.json').read_text(encoding='utf-8')
    )
    assert config.primary_agent.llm_type == 'azureOpenAI'
    assert config.primary_agent.kwargs['azure_deployment'] == 'gpt-5.6-luna'
    assert 'model' not in config.primary_agent.kwargs
    assert len(config.backup_agents) == 1
    backup = config.backup_agents[0]
    assert backup.class_name == 'AzureAnthropicTimelineAgent'
    assert backup.llm_type == 'azureAnthropic'
    assert backup.kwargs['model'] == 'claude-opus-5'
    assert backup.kwargs['thinking'] == {'type': 'adaptive'}
    assert backup.kwargs['effort'] == 'medium'



def test_event_query_configuration_has_azure_anthropic_backup():
    from pathlib import Path
    from AIInteractionService.utils.agent_facilitator import AgentConfig

    config = AgentConfig.model_validate_json(
        Path('configs/event_query.json').read_text(encoding='utf-8')
    )
    assert len(config.backup_agents) == 1
    backup = config.backup_agents[0]
    assert backup.class_name == 'AzureAnthropicEventQueryAgent'
    assert backup.llm_type == 'azureAnthropic'
    assert backup.kwargs['model'] == 'claude-haiku-4-5'
    assert backup.kwargs['thinking'] == {'type': 'disabled'}
    assert 'effort' not in backup.kwargs


def test_azure_anthropic_uses_foundry_resource(monkeypatch):
    captured = {}
    class FakeAzureChatAnthropic:
        def __init__(self, **kwargs): captured.update(kwargs)
    monkeypatch.setenv('ANTHROPIC_FOUNDRY_RESOURCE', 'example-resource')
    monkeypatch.setenv('ANTHROPIC_FOUNDRY_API_KEY', 'test-key')
    monkeypatch.delenv('ANTHROPIC_FOUNDRY_BASE_URL', raising=False)
    monkeypatch.delenv('AZURE_ANTHROPIC_ENDPOINT', raising=False)
    monkeypatch.setattr('AIInteractionService.generators.common.agent_base.AzureChatAnthropic', FakeAzureChatAnthropic)
    AgentBaseType.build_model('azureAnthropic', {'model': 'claude-sonnet-4-5', 'max_tokens': 8192, 'effort': 'high'})
    assert captured['base_url'] == 'https://example-resource.services.ai.azure.com/anthropic/'
    assert captured['model_name'] == 'claude-sonnet-4-5'
    assert captured['max_tokens_to_sample'] == 8192
    assert captured['effort'] == 'high'
    assert captured['default_headers'] == {'api-key': 'test-key'}
    assert captured['api_key'].get_secret_value() == 'test-key'
    assert captured['disable_streaming'] is True


def test_azure_anthropic_accepts_azure_endpoint_aliases(monkeypatch):
    captured = {}
    class FakeAzureChatAnthropic:
        def __init__(self, **kwargs): captured.update(kwargs)
    monkeypatch.delenv('ANTHROPIC_FOUNDRY_RESOURCE', raising=False)
    monkeypatch.delenv('ANTHROPIC_FOUNDRY_API_KEY', raising=False)
    monkeypatch.delenv('ANTHROPIC_FOUNDRY_BASE_URL', raising=False)
    monkeypatch.setenv('AZURE_ANTHROPIC_ENDPOINT', 'https://example.services.ai.azure.com/')
    monkeypatch.setenv('AZURE_ANTHROPIC_API_KEY', 'azure-key')
    monkeypatch.setattr('AIInteractionService.generators.common.agent_base.AzureChatAnthropic', FakeAzureChatAnthropic)
    AgentBaseType.build_model('azureAnthropic', {'model_name': 'claude-opus-4-1'})
    assert captured['base_url'] == 'https://example.services.ai.azure.com/anthropic/'
    assert captured['model_name'] == 'claude-opus-4-1'


def test_azure_anthropic_reports_a_distinct_provider_to_deepagents():
    from pydantic import SecretStr
    from deepagents._models import get_model_provider
    from AIInteractionService.generators.common.azure_anthropic import AzureChatAnthropic

    model = AzureChatAnthropic(
        model_name='claude-test',
        api_key=SecretStr('test-key'),
        base_url='https://example.invalid/anthropic/',
        max_tokens_to_sample=256,
    )

    assert get_model_provider(model) == 'azure_anthropic'
