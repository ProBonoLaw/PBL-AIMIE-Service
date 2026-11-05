#!/usr/bin/env python3
"""Export Test Function settings to a private file; optionally publish that file to Key Vault."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = ROOT / ".local" / "appsettings.aks-test.json"
CONFIG_CONTAINER = "agents"
REQUIRED = {
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "ACCOUNT_COSMOS_ENDPOINT", "ACCOUNT_COSMOS_DATABASE", "ACCOUNT_COSMOS_CONTAINER",
    "COSMOS_MESSAGE_HISTORY_ENDPOINT", "COSMOS_MESSAGE_HISTORY_DATABASE", "COSMOS_MESSAGE_HISTORY_CONTAINER",
    "CONFIG_STORAGE_ACCOUNT", "TEXT_EMBEDDING_OPENAI_ENDPOINT", "TEXT_EMBEDDING_API_KEY",
    "OPENAI_API_VERSION", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY",
    "AZURE_COGNITIVE_SERVICE_ENDPOINT", "AZURE_COGNITIVE_SERVICE_KEY",
}
STORAGE_SETTINGS = {
    "AzureWebJobsStorage", "AzureWebJobsStorage__accountName",
    "AzureWebJobsStorage__blobServiceUri", "AzureWebJobsStorage__queueServiceUri",
    "AzureWebJobsStorage__tableServiceUri", "AzureWebJobsStorage__credential",
    "AzureWebJobsStorage__clientId", "AzureWebJobsStorage__managedIdentityResourceId",
}
# Provider variants are configured in Blob Storage; retain their settings without exposing values.
OPTIONAL = {
    "ANTHROPIC_API_KEY", "ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_BASE_URL",
    "ANTHROPIC_FOUNDRY_RESOURCE", "AZURE_ANTHROPIC_API_KEY", "AZURE_ANTHROPIC_ENDPOINT",
    "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENAI_ORGANIZATION", "SEMANTIC_CONFIGURATION_NAME",
    "CONFIG_STORAGE_ACCOUNT_CONTAINER", "TEXT_EMBEDDING_AZURE_DEPLOYMENT_NAME",
    "TEXT_EMBEDDING_AZURE_MODEL_NAME", "AZ_COSMOS_ACCOUNT_KEY", "EVENT_QUERY_TIMEOUT_SECONDS",
    "AZURE_OPENAI_REASONING_EFFORT", "AZURE_OPENAI_REASONING_MODE",
    "OPENAI_REASONING_EFFORT", "OPENAI_REASONING_MODE",
    "AZURESEARCH_FIELDS_ID", "AZURESEARCH_FIELDS_CONTENT", "AZURESEARCH_FIELDS_CONTENT_VECTOR",
    "AZURESEARCH_FIELDS_TAG",
} | STORAGE_SETTINGS


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Set {name} in the private deployment environment")
    return value


def azure(*args):
    result = subprocess.run(
        ["az", *args, "--subscription", required_env("TEST_AZURE_SUBSCRIPTION_ID"), "--output", "json", "--only-show-errors"],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(f"Azure CLI {args[0]} {args[1]} failed; check login and resource permissions")
    return json.loads(result.stdout)


def validate(settings):
    if not isinstance(settings, dict):
        raise ValueError("Settings must be a JSON object")
    missing = REQUIRED - settings.keys()
    if missing:
        raise ValueError(f"Missing required setting names: {', '.join(sorted(missing))}")
    unknown = settings.keys() - REQUIRED - OPTIONAL
    if unknown:
        raise ValueError(f"Unexpected setting names: {', '.join(sorted(unknown))}; extend the allowlist if needed")
    for name, value in settings.items():
        if not isinstance(value, str) or not value.strip() or "\0" in value:
            raise ValueError(f"Setting {name} must be a nonempty string without NUL characters")
        if value.startswith("@Microsoft.KeyVault("):
            raise ValueError(f"Resolve the App Service Key Vault reference for {name} before publishing")
    identity_settings = STORAGE_SETTINGS - {"AzureWebJobsStorage"}
    if "AzureWebJobsStorage" in settings:
        if identity_settings & settings.keys():
            raise ValueError("Use either AzureWebJobsStorage or its identity-based settings, not both")
        if settings["AzureWebJobsStorage"].lower() == "usedevelopmentstorage=true":
            raise ValueError("AKS requires durable Azure Storage, not Azurite")
    else:
        account_name = settings.get("AzureWebJobsStorage__accountName")
        uri_keys = {f"AzureWebJobsStorage__{service}ServiceUri" for service in ("blob", "queue", "table")}
        if account_name:
            if not re.fullmatch(r"[a-z0-9]{3,24}", account_name):
                raise ValueError("AzureWebJobsStorage__accountName must be a valid Azure Storage account name")
            if uri_keys & settings.keys():
                raise ValueError("Use either AzureWebJobsStorage__accountName or all three service URIs")
        elif not uri_keys <= settings.keys():
            raise ValueError("Storage requires AzureWebJobsStorage, AzureWebJobsStorage__accountName, or all three service URIs")
        for key in uri_keys & settings.keys():
            uri = urlsplit(settings[key])
            if uri.scheme != "https" or not uri.hostname or uri.username or uri.password or uri.query or uri.fragment:
                raise ValueError(f"{key} must be an HTTPS storage service URI without credentials or query parameters")
        credential = settings.get("AzureWebJobsStorage__credential")
        if credential and credential != "managedidentity":
            raise ValueError("AzureWebJobsStorage__credential must be managedidentity when specified")
        if {"AzureWebJobsStorage__clientId", "AzureWebJobsStorage__managedIdentityResourceId"} <= settings.keys():
            raise ValueError("Specify only one storage managed identity selector")


def consolidate_storage(settings, storage_account=None):
    """Prepare storage settings without publishing or moving workflow state."""
    storage_account = storage_account or required_env("TEST_STORAGE_ACCOUNT")
    for key in STORAGE_SETTINGS:
        settings.pop(key, None)
    # Leave credential/clientId unset: DefaultAzureCredential uses the projected
    # AKS workload identity token, or the Azure CLI identity during local runs.
    settings["AzureWebJobsStorage__accountName"] = storage_account
    settings["CONFIG_STORAGE_ACCOUNT"] = f"https://{storage_account}.blob.core.windows.net"
    settings["CONFIG_STORAGE_ACCOUNT_CONTAINER"] = CONFIG_CONTAINER
    validate(settings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "validate", "consolidate-storage", "publish"])
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    args = parser.parse_args()
    if args.action == "export":
        items = azure("functionapp", "config", "appsettings", "list", "--resource-group", required_env("TEST_FUNCTION_RESOURCE_GROUP"),
                      "--name", required_env("TEST_FUNCTION_APP_NAME"))
        settings = {item["name"]: item["value"] for item in items if item["name"] in REQUIRED | OPTIONAL}
        consolidate_storage(settings)
        validate(settings)
        args.file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Refuse to silently overwrite a previously prepared configuration.
        fd = os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(settings, handle, indent=2)
            handle.write("\n")
        print(f"Exported {len(settings)} settings to {args.file}; values were not printed")
        return
    settings = json.loads(args.file.read_text())
    validate(settings)
    if args.action == "consolidate-storage":
        consolidate_storage(settings)
        # Replace the private file atomically; storage credentials never enter logs.
        temporary = args.file.with_name(args.file.name + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(settings, handle, indent=2)
                handle.write("\n")
            os.replace(temporary, args.file)
        finally:
            temporary.unlink(missing_ok=True)
        print("Prepared Test storage and configuration container; publish separately")
        return
    print(f"Validated {len(settings)} settings in {args.file}; values were not printed")
    if args.action == "publish":
        azure("keyvault", "secret", "set", "--vault-name", required_env("TEST_KEYVAULT_NAME"),
              "--name", "aimie-service-appsettings", "--file", str(args.file), "--encoding", "utf-8")
        print("Published appsettings to the configured Test vault; restart pods to load updates")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, RuntimeError) as error:
        # JSON parser messages can contain source fragments; never print those.
        if isinstance(error, json.JSONDecodeError):
            raise SystemExit("Invalid JSON settings file") from None
        raise SystemExit(str(error)) from None
