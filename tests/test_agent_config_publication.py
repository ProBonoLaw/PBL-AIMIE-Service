import importlib.util
import ast
import base64
import json
import os
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


publisher = load_script("agent_config_publisher", "publish-agent-configs.py")
settings_module = load_script("test_storage_settings", "configure-aks-test.py")


@pytest.fixture(autouse=True)
def synthetic_deployment_environment(monkeypatch):
    for name, value in {
        "TEST_AZURE_SUBSCRIPTION_ID": "11111111-1111-1111-1111-111111111111",
        "PROD_AZURE_SUBSCRIPTION_ID": "22222222-2222-2222-2222-222222222222",
        "TEST_STORAGE_ACCOUNT": "examplestorage",
        "PROD_STORAGE_ACCOUNT": "exampleprodstorage",
        "AKS_CLUSTER_RESOURCE_GROUP": "example-test-rg",
        "AKS_CLUSTER_NAME": "example-test-aks",
        "PROD_AKS_RESOURCE_GROUP": "example-prod-rg",
        "PROD_AKS_CLUSTER_NAME": "example-prod-aks",
        "TEST_FUNCTION_RESOURCE_GROUP": "example-test-function-rg",
        "TEST_FUNCTION_APP_NAME": "example-test-function",
        "PROD_FUNCTION_RESOURCE_GROUP": "example-prod-function-rg",
        "PROD_FUNCTION_APP_NAME": "example-prod-function",
        "TEST_KEYVAULT_NAME": "exampletestvault",
    }.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("code", ["AuthorizationFailure", "AuthorizationPermissionMismatch", None])
def test_azure_failure_reports_safe_code_without_cli_secrets(monkeypatch, code):
    stderr = f"ERROR: {code or 'UnknownFailure'}\nhttps://storage.example/?sig=private-token\nprivate prompt"
    monkeypatch.setattr(publisher.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=1, stderr=stderr,
    ))
    with pytest.raises(RuntimeError) as error:
        publisher.azure("storage", "container", "create")
    message = str(error.value)
    assert "storage container create failed" in message
    if code:
        assert f"({code})" in message
    assert "private-token" not in message
    assert "private prompt" not in message
    assert "UnknownFailure" not in message


@pytest.mark.parametrize("contents", ['{"prompt": "private prompt",', '[]'])
@pytest.mark.parametrize("via_aks", [False, True])
def test_invalid_batch_fails_before_any_upload(tmp_path, monkeypatch, contents, via_aks):
    (tmp_path / "a-valid.json").write_text('{"name": "valid"}')
    (tmp_path / "z-invalid.json").write_text(contents)
    calls = []
    monkeypatch.setattr(publisher, "azure", lambda *args: calls.append(args))
    monkeypatch.setattr(publisher, "publish_via_aks", lambda *args: calls.append(args))
    with pytest.raises(ValueError) as error:
        publisher.publish(tmp_path, via_aks=via_aks)
    assert not calls
    assert "private prompt" not in str(error.value)


def test_empty_directory_fails_without_azure_changes(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(publisher, "azure", lambda *args: calls.append(args))
    with pytest.raises(ValueError, match="No agent JSON"):
        publisher.publish(tmp_path)
    assert not calls


@pytest.mark.parametrize("environment,account,subscription", [
    ("test", "examplestorage", "11111111-1111-1111-1111-111111111111"),
    ("production", "exampleprodstorage", "22222222-2222-2222-2222-222222222222"),
])
def test_publication_uses_login_and_preserves_unmanaged_blobs(tmp_path, monkeypatch, environment, account, subscription):
    (tmp_path / "timeline.json").write_text('{"name": "timeline"}')
    (tmp_path / "notes.txt").write_text("not configuration")
    calls = []
    monkeypatch.setattr(publisher, "azure", lambda *args: calls.append(args))
    publisher.publish(tmp_path, environment=environment)
    assert len(calls) == 2
    assert calls[0][:3] == ("storage", "container", "create")
    assert calls[0][-2:] == ("--public-access", "off")
    upload = calls[1]
    assert upload[:3] == ("storage", "blob", "upload")
    assert upload[upload.index("--name") + 1] == "timeline.json"
    assert upload[upload.index("--content-type") + 1] == "application/json"
    assert upload[upload.index("--overwrite") + 1] == "true"
    for args in calls:
        assert args[args.index("--auth-mode") + 1] == "login"
        assert args[args.index("--account-name") + 1] == account
        assert args[args.index("--subscription") + 1] == subscription


@pytest.mark.parametrize("environment", ["test", "production"])
@pytest.mark.parametrize("via_aks", [False, True])
def test_dry_run_never_contacts_azure(tmp_path, monkeypatch, environment, via_aks):
    (tmp_path / "timeline.json").write_text('{"name": "timeline"}')
    calls = []
    monkeypatch.setattr(publisher, "azure", lambda *args: calls.append(args))
    monkeypatch.setattr(publisher, "publish_via_aks", lambda *args: calls.append(args))
    publisher.publish(tmp_path, dry_run=True, environment=environment, via_aks=via_aks)
    assert not calls


@pytest.mark.parametrize("returncode", [0, 1])
@pytest.mark.parametrize("environment,account,subscription,group,cluster", [
    ("test", "examplestorage", "11111111-1111-1111-1111-111111111111",
     "example-test-rg", "example-test-aks"),
    ("production", "exampleprodstorage", "22222222-2222-2222-2222-222222222222",
     "example-prod-rg", "example-prod-aks"),
])
def test_aks_attachment_preserves_blob_bytes_and_propagates_failure(tmp_path, monkeypatch, returncode, environment, account, subscription, group, cluster):
    contents = '{"name": "Test", "prompt": "é \\n $() `literal`"}\n'.encode()
    (tmp_path / "agent.json").write_bytes(contents)
    attachments = []

    # A Production call must ignore the caller's inherited Test subscription
    # and generic Test cluster settings.
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("AKS_CLUSTER_RESOURCE_GROUP", "example-test-rg")
    monkeypatch.setenv("AKS_CLUSTER_NAME", "example-test-aks")
    monkeypatch.setenv("PROD_AKS_RESOURCE_GROUP", "example-prod-rg")
    monkeypatch.setenv("PROD_AKS_CLUSTER_NAME", "example-prod-aks")

    def run(command, env):
        assert env["AZURE_SUBSCRIPTION_ID"] == subscription
        assert env["AKS_CLUSTER_RESOURCE_GROUP"] == group
        assert env["AKS_CLUSTER_NAME"] == cluster
        assert command[:2] == ["bash", str(ROOT / "scripts/aks-run-command.sh")]
        attachment = Path(command[2])
        assert attachment.stat().st_mode & 0o777 == 0o600
        script = attachment.read_text()
        compile(script, str(attachment), "exec")
        tree = ast.parse(script)
        call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name) and node.func.id == "publish_from_workload_identity")
        payload = ast.literal_eval(call.args[0])
        assert payload["account_url"] == f"https://{account}.blob.core.windows.net"
        assert payload["container"] == "agents"
        assert base64.b64decode(payload["files"]["agent.json"]) == contents
        assert "-c functions -- python - < agent-config-publication.py" in command[3]
        attachments.append(attachment)
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(publisher.subprocess, "run", run)
    monkeypatch.setattr(publisher, "azure", lambda *args: pytest.fail("AKS uploads must not call local storage CLI"))
    if returncode:
        with pytest.raises(RuntimeError, match="AKS agent configuration publication failed"):
            publisher.publish(tmp_path, environment=environment, via_aks=True)
    else:
        publisher.publish(tmp_path, environment=environment, via_aks=True)
    assert len(attachments) == 1
    assert not attachments[0].exists()


def test_production_aks_publication_uses_production_cluster_overrides(tmp_path, monkeypatch):
    (tmp_path / "agent.json").write_text('{"name": "agent"}')
    monkeypatch.setenv("PROD_AKS_RESOURCE_GROUP", "custom-production-group")
    monkeypatch.setenv("PROD_AKS_CLUSTER_NAME", "custom-production-cluster")
    calls = []

    def run(command, env):
        calls.append(env)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(publisher.subprocess, "run", run)
    publisher.publish(tmp_path, environment="production", via_aks=True)
    assert len(calls) == 1
    assert calls[0]["AZURE_SUBSCRIPTION_ID"] == "22222222-2222-2222-2222-222222222222"
    assert calls[0]["AKS_CLUSTER_RESOURCE_GROUP"] == "custom-production-group"
    assert calls[0]["AKS_CLUSTER_NAME"] == "custom-production-cluster"


@pytest.mark.parametrize("subscription,wrong_subscription", [
    ("22222222-2222-2222-2222-222222222222", "11111111-1111-1111-1111-111111111111"),
    ("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"),
])
def test_aks_helper_rejects_cluster_from_wrong_subscription_before_getting_tokens(tmp_path, subscription, wrong_subscription):
    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    fake_az = bin_path / "az"
    fake_az.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['TASK_AZ_LOG'], 'a') as log:\n"
        "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "print(os.environ['TASK_CLUSTER_ID'])\n"
    )
    fake_az.chmod(0o700)
    attachment = tmp_path / "attachment.py"
    attachment.write_text("# no publication\n")
    log = tmp_path / "az-calls.jsonl"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/aks-run-command.sh"), str(attachment), "true"],
        env={**os.environ, "PATH": f"{bin_path}:{os.environ['PATH']}",
             "AZURE_SUBSCRIPTION_ID": subscription, "TASK_AZ_LOG": str(log),
             "TASK_CLUSTER_ID": f"/subscriptions/{wrong_subscription}/resourceGroups/example/providers/Microsoft.ContainerService/managedClusters/example"},
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "AKS cluster is outside the requested subscription" in result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(calls) == 1
    assert calls[0][:2] == ["aks", "show"]
    assert calls[0][calls[0].index("--subscription") + 1] == subscription


@pytest.mark.parametrize("existing_container", [False, True])
def test_workload_upload_creates_container_and_preserves_unmanaged_blobs(monkeypatch, existing_container):
    from azure.core.exceptions import ResourceExistsError
    from azure.identity import WorkloadIdentityCredential
    import azure.identity
    import azure.storage.blob
    from unittest.mock import MagicMock

    credential = MagicMock(spec=WorkloadIdentityCredential)
    service = MagicMock()
    container = service.__enter__.return_value.get_container_client.return_value
    if existing_container:
        container.create_container.side_effect = ResourceExistsError("exists")
    monkeypatch.setattr(azure.identity, "WorkloadIdentityCredential", lambda: credential)
    monkeypatch.setattr(azure.storage.blob, "BlobServiceClient", lambda *args, **kwargs: service)
    contents = b'{"name":"agent"}'
    publisher.publish_from_workload_identity({
        "account_url": "https://example.blob.core.windows.net",
        "container": "agents", "files": {"agent.json": base64.b64encode(contents).decode()},
    })
    container.create_container.assert_called_once_with()
    args, kwargs = container.upload_blob.call_args
    assert args == ("agent.json", contents)
    assert kwargs["overwrite"] is True
    assert kwargs["content_settings"].content_type == "application/json"
    container.delete_blob.assert_not_called()
    container.list_blobs.assert_not_called()


def test_upload_failure_stops_remaining_uploads(tmp_path, monkeypatch):
    for name in ["a.json", "b.json"]:
        (tmp_path / name).write_text("{}")
    calls = []

    def azure(*args):
        calls.append(args)
        if args[:3] == ("storage", "blob", "upload"):
            raise RuntimeError("Upload failed")

    monkeypatch.setattr(publisher, "azure", azure)
    with pytest.raises(RuntimeError, match="Upload failed"):
        publisher.publish(tmp_path)
    assert len(calls) == 2


def test_consolidation_writes_private_file_without_logging_credentials(tmp_path, monkeypatch, capsys):
    settings = {name: "configured" for name in settings_module.REQUIRED}
    settings["AzureWebJobsStorage"] = "AccountName=old;AccountKey=private-key"
    settings["CONFIG_STORAGE_ACCOUNT"] = "https://exampleold.blob.core.windows.net"
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(settings))
    def azure(*args):
        pytest.fail("Identity-based storage preparation must not retrieve account keys")

    monkeypatch.setattr(settings_module, "azure", azure)
    monkeypatch.setattr(sys, "argv", ["configure-aks-test.py", "consolidate-storage", "--file", str(path)])
    settings_module.main()
    prepared = json.loads(path.read_text())
    assert prepared["CONFIG_STORAGE_ACCOUNT"] == "https://examplestorage.blob.core.windows.net"
    assert prepared["CONFIG_STORAGE_ACCOUNT_CONTAINER"] == "agents"
    assert prepared["AzureWebJobsStorage__accountName"] == "examplestorage"
    assert "AzureWebJobsStorage" not in prepared
    assert "AzureWebJobsStorage__credential" not in prepared
    assert "AzureWebJobsStorage__clientId" not in prepared
    assert prepared["AZURE_OPENAI_API_KEY"] == settings["AZURE_OPENAI_API_KEY"]
    assert path.stat().st_mode & 0o777 == 0o600
    assert "private-key" not in capsys.readouterr().out


def test_production_export_consolidates_storage_without_test_account(tmp_path, monkeypatch):
    production = load_script("production_storage_settings", "configure-aks-production.py")
    settings = {name: "configured" for name in settings_module.REQUIRED}
    settings["CONFIG_STORAGE_ACCOUNT"] = "https://exampleproduction.blob.core.windows.net"
    settings["AzureWebJobsStorage"] = "AccountName=production;AccountKey=private-key"
    monkeypatch.setattr(production, "azure", lambda *args: [
        {"name": key, "value": value} for key, value in settings.items()
    ])
    path = tmp_path / "production.json"
    monkeypatch.setattr(sys, "argv", ["configure-aks-production.py", "export", "--file", str(path)])
    production.main()
    exported = json.loads(path.read_text())
    expected = {
        **{key: value for key, value in settings.items() if key != "AzureWebJobsStorage"},
        "AzureWebJobsStorage__accountName": "exampleprodstorage",
        "CONFIG_STORAGE_ACCOUNT": "https://exampleprodstorage.blob.core.windows.net",
        "CONFIG_STORAGE_ACCOUNT_CONTAINER": "agents",
    }
    assert exported == expected


def test_existing_production_settings_consolidate_privately_without_publication(tmp_path, monkeypatch, capsys):
    production = load_script("production_durable_settings", "configure-aks-production.py")
    settings = {name: "configured" for name in settings_module.REQUIRED}
    settings["AzureWebJobsStorage"] = "AccountName=old;AccountKey=private-key"
    path = tmp_path / "production.json"
    path.write_text(json.dumps(settings))
    monkeypatch.setattr(production, "azure", lambda *args: pytest.fail("Preparation must not publish"))
    monkeypatch.setattr(sys, "argv", ["configure-aks-production.py", "consolidate-storage", "--file", str(path)])
    production.main()
    prepared = json.loads(path.read_text())
    assert prepared["AzureWebJobsStorage__accountName"] == "exampleprodstorage"
    assert prepared["CONFIG_STORAGE_ACCOUNT"] == "https://exampleprodstorage.blob.core.windows.net"
    assert prepared["CONFIG_STORAGE_ACCOUNT_CONTAINER"] == "agents"
    assert "AzureWebJobsStorage" not in prepared
    assert "AzureWebJobsStorage__credential" not in prepared
    assert "AzureWebJobsStorage__clientId" not in prepared
    assert prepared["AZURE_OPENAI_API_KEY"] == settings["AZURE_OPENAI_API_KEY"]
    assert path.stat().st_mode & 0o777 == 0o600
    assert "private-key" not in capsys.readouterr().out


@pytest.mark.parametrize("environment,workflow_environment", [("test", "test"), ("production", "production")])
def test_deployment_publishes_configs_before_applying_manifests(environment, workflow_environment):
    workflow = (ROOT / f".github/workflows/deploy-aks-{workflow_environment}.yml").read_text()
    assert workflow.index("azure/login@") < workflow.index("scripts/publish-agent-configs.py")
    assert workflow.index("scripts/publish-agent-configs.py") < workflow.index(f"bash scripts/deploy-aks-{workflow_environment}.sh")
    assert f"scripts/publish-agent-configs.py --environment {environment}" in workflow


@pytest.mark.parametrize("storage", [
    {"AzureWebJobsStorage__accountName": "examplestorage"},
    {f"AzureWebJobsStorage__{service}ServiceUri": f"https://example.{service}.core.windows.net"
     for service in ("blob", "queue", "table")},
    {"AzureWebJobsStorage": "AccountName=production;AccountKey=private-key"},
])
def test_storage_validation_accepts_complete_connections(storage):
    settings_module.validate({**{name: "configured" for name in settings_module.REQUIRED}, **storage})


@pytest.mark.parametrize("storage", [
    {},
    {"AzureWebJobsStorage__blobServiceUri": "https://example.blob.core.windows.net"},
    {"AzureWebJobsStorage": "AccountName=example;AccountKey=private-key",
     "AzureWebJobsStorage__accountName": "example"},
    {"AzureWebJobsStorage__accountName": "https://example.blob.core.windows.net"},
    {"AzureWebJobsStorage__accountName": "example", "AzureWebJobsStorage__credential": "workloadidentity"},
    {"AzureWebJobsStorage__accountName": "example", "AzureWebJobsStorage__clientId": "client-id",
     "AzureWebJobsStorage__managedIdentityResourceId": "/subscriptions/example"},
    {"AzureWebJobsStorage": "UseDevelopmentStorage=true"},
    {f"AzureWebJobsStorage__{service}ServiceUri": f"http://example.{service}.core.windows.net"
     for service in ("blob", "queue", "table")},
])
def test_storage_validation_rejects_missing_or_conflicting_connections(storage):
    with pytest.raises(ValueError):
        settings_module.validate({**{name: "configured" for name in settings_module.REQUIRED}, **storage})


def test_consolidation_removes_previous_identity_selectors(monkeypatch):
    settings = {name: "configured" for name in settings_module.REQUIRED}
    settings.update({
        "AzureWebJobsStorage__accountName": "oldstorage",
        "AzureWebJobsStorage__credential": "managedidentity",
        "AzureWebJobsStorage__clientId": "old-function-app-identity",
    })
    monkeypatch.setattr(settings_module, "azure", lambda *args: pytest.fail("Unexpected Azure call"))
    settings_module.consolidate_storage(settings)
    assert {key: value for key, value in settings.items() if key.startswith("AzureWebJobsStorage")} == {
        "AzureWebJobsStorage__accountName": "examplestorage"
    }


def test_existing_production_settings_can_be_prepared_without_publishing(tmp_path, monkeypatch, capsys):
    production = load_script("production_agent_settings", "configure-aks-production.py")
    settings = {name: "configured" for name in settings_module.REQUIRED}
    settings["AzureWebJobsStorage"] = "AccountName=production;AccountKey=private-key"
    path = tmp_path / "production.json"
    path.write_text(json.dumps(settings))
    monkeypatch.setattr(production, "azure", lambda *args: pytest.fail("Preparation must not publish to Azure"))
    monkeypatch.setattr(sys, "argv", ["configure-aks-production.py", "configure-agents", "--file", str(path)])
    production.main()
    prepared = json.loads(path.read_text())
    assert prepared == {
        **settings,
        "CONFIG_STORAGE_ACCOUNT": "https://exampleprodstorage.blob.core.windows.net",
        "CONFIG_STORAGE_ACCOUNT_CONTAINER": "agents",
    }
    assert path.stat().st_mode & 0o777 == 0o600
    assert "private-key" not in capsys.readouterr().out


def test_invalid_environment_fails_before_any_azure_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(publisher, "azure", lambda *args: pytest.fail("Unexpected Azure call"))
    with pytest.raises(ValueError, match="Unknown deployment environment"):
        publisher.publish(tmp_path, environment="unknown")


@pytest.mark.parametrize("environment,missing", [
    ("test", "TEST_AZURE_SUBSCRIPTION_ID"), ("test", "TEST_STORAGE_ACCOUNT"),
    ("production", "PROD_AZURE_SUBSCRIPTION_ID"), ("production", "PROD_STORAGE_ACCOUNT"),
])
def test_missing_target_fails_before_any_upload(tmp_path, monkeypatch, environment, missing):
    (tmp_path / "agent.json").write_text("{}")
    monkeypatch.delenv(missing)
    monkeypatch.setattr(publisher, "azure", lambda *args: pytest.fail("Unexpected Azure call"))
    with pytest.raises(ValueError, match=missing):
        publisher.publish(tmp_path, environment=environment)


def test_production_never_falls_back_to_generic_test_cluster(tmp_path, monkeypatch):
    (tmp_path / "agent.json").write_text("{}")
    monkeypatch.delenv("PROD_AKS_CLUSTER_NAME")
    monkeypatch.setattr(publisher.subprocess, "run", lambda *args, **kwargs: pytest.fail("Unexpected Azure call"))
    with pytest.raises(ValueError, match="PROD_AKS_CLUSTER_NAME"):
        publisher.publish(tmp_path, environment="production", via_aks=True)
