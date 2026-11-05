from AIInteractionService.utils.azure_credentials import default_azure_credential_options


def test_environment_credential_is_excluded_when_service_principal_is_incomplete(monkeypatch):
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant")
    monkeypatch.setenv("AZURE_CLIENT_ID", "client")
    monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)

    assert default_azure_credential_options() == {
        "exclude_environment_credential": True,
    }


def test_environment_credential_is_enabled_when_service_principal_is_complete(monkeypatch):
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant")
    monkeypatch.setenv("AZURE_CLIENT_ID", "client")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "secret")

    assert default_azure_credential_options() == {
        "exclude_environment_credential": False,
    }
