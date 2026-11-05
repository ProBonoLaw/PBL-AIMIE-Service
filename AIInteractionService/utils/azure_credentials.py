import os
from typing import Any


_ENVIRONMENT_CREDENTIAL_VARIABLES = (
    "AZURE_TENANT_ID",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
)


def default_azure_credential_options() -> dict[str, Any]:
    environment_credential_configured = all(
        (os.getenv(name) or "").strip()
        for name in _ENVIRONMENT_CREDENTIAL_VARIABLES
    )
    return {
        "exclude_environment_credential": not environment_credential_configured,
    }
