#!/usr/bin/env python3
"""Publish repository agent JSON configurations using Azure CLI login/OIDC."""

import argparse
import base64
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"test": "TEST", "production": "PROD"}
CONTAINER = "agents"


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Set {name} in the private deployment environment")
    return value


def target(environment):
    if environment not in TARGETS:
        raise ValueError(f"Unknown deployment environment: {environment}")
    prefix = TARGETS[environment]
    subscription = required_env(f"{prefix}_AZURE_SUBSCRIPTION_ID")
    account = required_env(f"{prefix}_STORAGE_ACCOUNT")
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", subscription):
        raise ValueError(f"{prefix}_AZURE_SUBSCRIPTION_ID must be a GUID")
    if not re.fullmatch(r"[a-z0-9]{3,24}", account):
        raise ValueError(f"{prefix}_STORAGE_ACCOUNT must be an Azure Storage account name")
    return subscription, account


def configuration_files(directory):
    files = sorted(directory.glob("*.json"))
    if not files:
        raise ValueError(f"No agent JSON configurations found in {directory}")
    # Validate the whole batch before making any Azure changes.
    for path in files:
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            raise ValueError(f"Invalid JSON configuration: {path.name}") from None
        if not isinstance(config, dict):
            raise ValueError(f"Agent configuration must be a JSON object: {path.name}")
    return files


def azure(*args):
    result = subprocess.run(
        ["az", *args, "--only-show-errors", "--output", "none"],
        capture_output=True, text=True,
    )
    if result.returncode:
        # Surface only recognized error codes, never raw CLI output: it can
        # contain tokens, signed URLs, or configuration contents.
        code = re.search(
            r"\b(AuthorizationFailure|AuthorizationPermissionMismatch|"
            r"AuthenticationFailed|InvalidAuthenticationInfo|ContainerNotFound|"
            r"AccountIsDisabled|PublicAccessNotPermitted)\b",
            result.stderr,
        )
        detail = f" ({code.group(0)})" if code else ""
        raise RuntimeError(
            f"Azure CLI {' '.join(args[:3])} failed{detail}; check login, storage networking and "
            "Storage Blob Data Contributor access to the agents container"
        )


def publish_from_workload_identity(payload):
    """Run inside the AIMIE pod, which has storage routing and data roles."""
    import base64
    import sys
    sys.path.insert(0, "/home/site/wwwroot/.python_packages/lib/site-packages")
    from azure.core.exceptions import ResourceExistsError
    from azure.identity import WorkloadIdentityCredential
    from azure.storage.blob import BlobServiceClient, ContentSettings

    with WorkloadIdentityCredential() as credential:
        with BlobServiceClient(payload["account_url"], credential=credential) as service:
            container = service.get_container_client(payload["container"])
            try:
                container.create_container()
            except ResourceExistsError:
                pass
            for name, contents in payload["files"].items():
                container.upload_blob(
                    name, base64.b64decode(contents), overwrite=True,
                    content_settings=ContentSettings(content_type="application/json"),
                )
                print(f"Published {name}", flush=True)


def publish_via_aks(files, storage_account, environment):
    group_variable, name_variable = (
        ("PROD_AKS_RESOURCE_GROUP", "PROD_AKS_CLUSTER_NAME") if environment == "production"
        else ("AKS_CLUSTER_RESOURCE_GROUP", "AKS_CLUSTER_NAME")
    )
    command_environment = {
        **os.environ,
        "AZURE_SUBSCRIPTION_ID": target(environment)[0],
        "AKS_CLUSTER_RESOURCE_GROUP": required_env(group_variable),
        "AKS_CLUSTER_NAME": required_env(name_variable),
    }
    payload = {
        "account_url": f"https://{storage_account}.blob.core.windows.net",
        "container": CONTAINER,
        "files": {path.name: base64.b64encode(path.read_bytes()).decode("ascii") for path in files},
    }
    # Attach the validated batch through ARM. Only publication status is logged;
    # the pod uses its projected workload identity token, never account keys.
    with tempfile.TemporaryDirectory(prefix="agent-config-publication-") as scratch:
        script = Path(scratch) / "agent-config-publication.py"
        script.write_text(
            inspect.getsource(publish_from_workload_identity)
            + "\ntry:\n    publish_from_workload_identity(" + repr(payload) + ")\n"
            + "except Exception as error:\n"
            + "    code = getattr(error, 'error_code', None)\n"
            + "    safe_codes = ('AuthorizationFailure', 'AuthorizationPermissionMismatch', "
            + "'AuthenticationFailed', 'ContainerNotFound')\n"
            + "    detail = code if code in safe_codes else type(error).__name__\n"
            + "    raise SystemExit('AKS agent configuration publication failed: ' + detail) from None\n",
            encoding="utf-8",
        )
        script.chmod(0o600)
        result = subprocess.run([
            "bash", str(ROOT / "scripts/aks-run-command.sh"), str(script),
            "kubectl exec -i -n aimie-operations deployment/aimie-service "
            "-c functions -- python - < agent-config-publication.py",
        ], env=command_environment)
        if result.returncode:
            raise RuntimeError(
                "AKS agent configuration publication failed; check the running AIMIE pod, "
                "workload identity storage permissions and private endpoint connectivity"
            )


def publish(directory, dry_run=False, environment="test", via_aks=False):
    if environment not in TARGETS:
        raise ValueError(f"Unknown deployment environment: {environment}")
    subscription, storage_account = target(environment)
    files = configuration_files(directory)
    destination = f"{storage_account}/{CONTAINER}"
    for path in files:
        print(f"{path.name} -> {destination}/{path.name}", flush=True)
    if dry_run:
        print(f"Validated {len(files)} configurations; no Azure changes made")
        return
    if via_aks:
        publish_via_aks(files, storage_account, environment)
        print(f"Published {len(files)} configurations to {destination}")
        return
    connection = ("--account-name", storage_account, "--auth-mode", "login", "--subscription", subscription)
    azure("storage", "container", "create", *connection,
          "--name", CONTAINER, "--public-access", "off")
    for path in files:
        azure("storage", "blob", "upload", *connection,
              "--container-name", CONTAINER, "--name", path.name, "--file", str(path),
              "--overwrite", "true", "--content-type", "application/json")
    print(f"Published {len(files)} configurations to {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs-dir", type=Path, default=ROOT / "configs")
    parser.add_argument("--environment", choices=sorted(TARGETS), default="test")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--via-aks", action="store_true",
                        help="Upload through the selected environment's AIMIE pod using workload identity and private networking")
    args = parser.parse_args()
    publish(args.configs_dir, args.dry_run, args.environment, args.via_aks)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
