"""Load the CSI-mounted settings before starting either the host or Python worker."""

import json
import os
from pathlib import Path
import re
import sys


def load_settings(path: Path, environment: dict[str, str]) -> dict[str, str]:
    settings = json.loads(path.read_text())
    if not isinstance(settings, dict) or not settings:
        raise ValueError("Appsettings must be a nonempty JSON object")
    for key, value in settings.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("Appsettings contains an invalid environment variable name")
        if not isinstance(value, str) or "\0" in value:
            raise ValueError(f"Appsetting {key} must be a string without NUL characters")
        if value.startswith("@Microsoft.KeyVault("):
            raise ValueError(f"Appsetting {key} contains an unresolved App Service Key Vault reference")
    # Deployment settings and projected workload identity take precedence over the source app.
    return {**settings, **environment}


def main() -> None:
    try:
        path = Path(os.environ.get("APPSETTINGS_FILE", "/mnt/keyvault/appsettings.json"))
        environment = load_settings(path, dict(os.environ))
    except (OSError, ValueError) as error:
        # Do not echo JSON content or credentials in startup logs.
        print(f"Cannot load Functions appsettings ({type(error).__name__}); check the mounted JSON file", file=sys.stderr)
        raise SystemExit(1) from None
    command = sys.argv[1:] or ["/opt/startup/start_nonappservice.sh"]
    os.execvpe(command[0], command, environment)


if __name__ == "__main__":
    main()
