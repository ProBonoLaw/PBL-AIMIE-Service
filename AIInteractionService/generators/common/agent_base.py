from abc import ABCMeta
import os
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from .azure_anthropic import AzureChatAnthropic


class AgentBaseType(ABCMeta):
    """
    A metaclass for creating agent classes that can be used with the AgentFacilitator.
    This class ensures that the agent has a `prepare_output` method and an `output_class_type` method.
    """

    def __new__(cls, name, bases, attrs, **kwargs):
        llm_type = kwargs.get("llm_type")
        if llm_type is None:
            raise ValueError(f"Agent {name} must define a llm_type attribute.")
        llm_type = llm_type.lower()
        if llm_type not in ["openai", "anthropic", "google", "azureopenai", "azureanthropic"]:
            raise ValueError(f"Agent {name} has an invalid llm_type: {llm_type}. "
                             "Valid types are: 'openai', 'anthropic', 'google', 'azureopenai', 'azureanthropic'.")
        if llm_type == "openai":
            attrs["instantiate_llm"] = cls.__instantiate_open_ai_llm
        elif llm_type == "anthropic":
            attrs["instantiate_llm"] = cls.__instantiate_anthropic_llm
        elif llm_type == "google":
            attrs["instantiate_llm"] = cls.__instantiate_google_llm
        elif llm_type == "azureopenai":
            attrs["instantiate_llm"] = cls.__instantiate_azure_open_ai_llm
        elif llm_type == "azureanthropic":
            attrs["instantiate_llm"] = cls.__instantiate_azure_anthropic_llm
        
        return super().__new__(cls, name, bases, attrs)

    @staticmethod
    def build_model(llm_type: str, kwargs: dict):
        constructors = {
            "openai": AgentBaseType.__instantiate_open_ai_llm,
            "anthropic": AgentBaseType.__instantiate_anthropic_llm,
            "google": AgentBaseType.__instantiate_google_llm,
            "azureopenai": AgentBaseType.__instantiate_azure_open_ai_llm,
            "azureanthropic": AgentBaseType.__instantiate_azure_anthropic_llm,
        }
        try:
            return constructors[llm_type.lower()](None, kwargs)
        except KeyError as error:
            raise ValueError(f"Unsupported LLM type: {llm_type}") from error

    @staticmethod
    def llm_type_for_class_name(class_name: str) -> str:
        normalized = class_name.lower()
        if "azureopenai" in normalized:
            return "azureopenai"
        if "azureanthropic" in normalized or "anthropicfoundry" in normalized:
            return "azureanthropic"
        if "anthropic" in normalized:
            return "anthropic"
        if "google" in normalized:
            return "google"
        if "openai" in normalized:
            return "openai"
        raise ValueError(f"Cannot infer LLM type from agent class: {class_name}")

    @staticmethod
    def __instantiate_azure_open_ai_llm(_, kwargs: dict) -> ChatOpenAI:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        if not endpoint:
            raise EnvironmentError("AZURE_OPENAI_ENDPOINT environment variable is missing")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("AZURE_OPENAI_API_KEY environment variable is missing")

        reasoning = dict(kwargs.get("reasoning", {}))
        effort = kwargs.get("reasoning_effort") or os.getenv("AZURE_OPENAI_REASONING_EFFORT")
        mode = kwargs.get("reasoning_mode") or os.getenv("AZURE_OPENAI_REASONING_MODE")
        if effort and "effort" not in reasoning:
            reasoning["effort"] = effort
        if mode and "mode" not in reasoning:
            reasoning["mode"] = mode

        return ChatOpenAI(
            base_url=f"{endpoint.rstrip('/')}/openai/v1/",
            model=kwargs.get("model") or kwargs.get("azure_deployment", "gpt-4o-law-2"),
            api_key=SecretStr(api_key),
            timeout=kwargs.get("timeout", 120),
            use_responses_api=True,
            verbosity=kwargs.get("verbosity", None),
            reasoning=reasoning or None,
            disable_streaming=True,
            logit_bias=kwargs.get("logit_bias", None),
        )

    @staticmethod
    def __instantiate_anthropic_llm(_, kwargs: dict) -> ChatAnthropic:
        temperature = kwargs.get("temperature", 1.0)
        max_tokens_to_sample = kwargs.get("max_tokens_to_sample", 4096)
        top_p = kwargs.get("top_p", None)
        model_name = kwargs.get("model_name", "claude-3-opus-20240229")
        timeout = kwargs.get("timeout", None)
        stop = kwargs.get("stop", None)
        thinking = kwargs.get("thinking", None)
        return ChatAnthropic(
            temperature=temperature,
            cache=False,
            top_p=top_p,
            model_name=model_name,
            timeout=timeout,
            stop=stop,
            max_tokens_to_sample=max_tokens_to_sample,
            thinking=thinking,
            disable_streaming=True)

    @staticmethod
    def __instantiate_azure_anthropic_llm(_, kwargs: dict) -> AzureChatAnthropic:
        api_key = os.getenv("ANTHROPIC_FOUNDRY_API_KEY") or os.getenv("AZURE_ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_FOUNDRY_API_KEY or AZURE_ANTHROPIC_API_KEY environment variable is missing"
            )
        base_url = os.getenv("ANTHROPIC_FOUNDRY_BASE_URL")
        if not base_url:
            endpoint = os.getenv("AZURE_ANTHROPIC_ENDPOINT")
            resource = os.getenv("ANTHROPIC_FOUNDRY_RESOURCE")
            if endpoint:
                base_url = endpoint.rstrip("/")
                if not base_url.endswith("/anthropic"):
                    base_url = f"{base_url}/anthropic"
            elif resource:
                base_url = f"https://{resource}.services.ai.azure.com/anthropic"
            else:
                raise EnvironmentError(
                    "ANTHROPIC_FOUNDRY_BASE_URL, ANTHROPIC_FOUNDRY_RESOURCE, or "
                    "AZURE_ANTHROPIC_ENDPOINT environment variable is missing"
                )
        return AzureChatAnthropic(
            model_name=kwargs.get("model") or kwargs.get("model_name", "claude-sonnet-4-5"),
            api_key=SecretStr(api_key), base_url=f"{base_url.rstrip('/')}/",
            default_headers={"api-key": api_key},
            temperature=kwargs.get("temperature"), top_p=kwargs.get("top_p"),
            top_k=kwargs.get("top_k"),
            max_tokens_to_sample=kwargs.get("max_tokens", kwargs.get("max_tokens_to_sample", 4096)),
            timeout=kwargs.get("timeout", 120), max_retries=kwargs.get("max_retries", 2),
            stop=kwargs.get("stop"), thinking=kwargs.get("thinking"),
            effort=kwargs.get("effort"), disable_streaming=True,
        )

    @staticmethod
    def __instantiate_google_llm(_, kwargs: dict) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=kwargs.get("model", "gemini-1.5-pro-001"),
            temperature=kwargs.get("temperature", None),
            top_p=kwargs.get("top_p", None),
            n=kwargs.get("n", 1),
            max_output_tokens=kwargs.get("max_output_tokens", 4000),
            timeout=kwargs.get("timeout", 200),
            thinking_budget=kwargs.get("thinking_budget", 2000),
            disable_streaming=True,
        )

    @staticmethod
    def __instantiate_open_ai_llm(_, kwargs: dict) -> ChatOpenAI:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY environment variable is missing")

        reasoning = dict(kwargs.get("reasoning", {}))
        effort = kwargs.get("reasoning_effort") or os.getenv("OPENAI_REASONING_EFFORT")
        mode = kwargs.get("reasoning_mode") or os.getenv("OPENAI_REASONING_MODE")
        if effort and "effort" not in reasoning:
            reasoning["effort"] = effort
        if mode and "mode" not in reasoning:
            reasoning["mode"] = mode

        return ChatOpenAI(
            model=kwargs.get("model", "gpt-5"),
            api_key=SecretStr(api_key),
            timeout=kwargs.get("timeout", 120),
            use_responses_api=True,
            disable_streaming=True,
            verbosity=kwargs.get("verbosity", None),
            reasoning=reasoning or None,
            logit_bias=kwargs.get("logit_bias", None),
        )
