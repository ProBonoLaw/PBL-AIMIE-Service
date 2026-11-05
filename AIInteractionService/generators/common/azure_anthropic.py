from typing import Any

from langchain_anthropic import ChatAnthropic


class AzureChatAnthropic(ChatAnthropic):
    """Anthropic chat model routed through Azure AI Foundry."""

    @property
    def _llm_type(self) -> str:
        return "azure-anthropic-chat"

    def _get_ls_params(
        self,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Identify Azure AI Foundry separately from Anthropic's direct API.

        DeepAgents uses this provider value when selecting harness profiles.
        Treating the Azure-hosted integration as direct Anthropic causes it to
        add Anthropic prompt-cache controls, which Azure AI Foundry rejects.
        """
        params = super()._get_ls_params(stop=stop, **kwargs)
        return {**params, 'ls_provider': 'azure_anthropic'}

