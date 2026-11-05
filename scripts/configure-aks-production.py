#!/usr/bin/env python3
"""Prepare Production Function settings for the future AKS Key Vault secret."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = ROOT / ".local" / "appsettings.aks-production.json"

# Test and Production preserve the same application settings contract.
spec = importlib.util.spec_from_file_location("aks_test_settings", ROOT / "scripts/configure-aks-test.py")
test_settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_settings)


def azure(*args):
    result = subprocess.run(
        ["az", *args, "--subscription", test_settings.required_env("PROD_AZURE_SUBSCRIPTION_ID"), "--output", "json", "--only-show-errors"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(f"Azure CLI {args[0]} {args[1]} failed; check production access")
    return json.loads(result.stdout)


def configure_agents(settings):
    account = test_settings.required_env("PROD_STORAGE_ACCOUNT")
    settings["CONFIG_STORAGE_ACCOUNT"] = f"https://{account}.blob.core.windows.net"
    settings["CONFIG_STORAGE_ACCOUNT_CONTAINER"] = "agents"
    test_settings.validate(settings)


def consolidate_storage(settings):
    test_settings.consolidate_storage(settings, test_settings.required_env("PROD_STORAGE_ACCOUNT"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "validate", "configure-agents", "consolidate-storage", "publish"])
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--vault-name", help="Production AKS Key Vault; required for publish")
    args = parser.parse_args()
    if args.action == "export":
        items = azure(
            "functionapp", "config", "appsettings", "list", "--resource-group", test_settings.required_env("PROD_FUNCTION_RESOURCE_GROUP"),
            "--name", test_settings.required_env("PROD_FUNCTION_APP_NAME"),
        )
        settings = {
            item["name"]: item["value"] for item in items
            if item["name"] in test_settings.REQUIRED | test_settings.OPTIONAL
        }
        consolidate_storage(settings)
        args.file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(settings, handle, indent=2)
            handle.write("\n")
        print(f"Exported {len(settings)} production settings to {args.file}; values were not printed")
        return

    settings = json.loads(args.file.read_text())
    test_settings.validate(settings)
    if args.action in ("configure-agents", "consolidate-storage"):
        if args.action == "consolidate-storage":
            consolidate_storage(settings)
        else:
            configure_agents(settings)
        temporary = args.file.with_name(args.file.name + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(settings, handle, indent=2)
                handle.write("\n")
            os.replace(temporary, args.file)
        finally:
            temporary.unlink(missing_ok=True)
        print("Prepared production storage settings; publish separately")
        return
    print(f"Validated {len(settings)} production settings in {args.file}; values were not printed")
    if args.action == "publish":
        if not args.vault_name:
            raise ValueError("--vault-name is required to publish production settings")
        if args.vault_name == test_settings.required_env("TEST_KEYVAULT_NAME"):
            raise ValueError("Refusing to publish production settings to the Test AKS vault")
        azure("keyvault", "show", "--name", args.vault_name)
        azure(
            "keyvault", "secret", "set", "--vault-name", args.vault_name,
            "--name", "aimie-service-appsettings", "--file", str(args.file),
            "--encoding", "utf-8",
        )
        print(f"Published aimie-service-appsettings to production vault {args.vault_name}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, RuntimeError) as error:
        if isinstance(error, json.JSONDecodeError):
            raise SystemExit("Invalid JSON settings file") from None
        raise SystemExit(str(error)) from None
