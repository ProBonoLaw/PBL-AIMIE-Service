#!/usr/bin/env python3
"""Check cross-resource wiring and migration isolation in the rendered bundle."""

from pathlib import Path
import os
import sys

import yaml


def validate(path: Path, deployment_environment: str = "test") -> None:
    if deployment_environment not in {"test", "production"}:
        raise ValueError("Environment must be test or production")
    raw = path.read_text()
    if "<" in raw or ":latest" in raw:
        raise ValueError("Render identity placeholders and immutable image tags before validation")
    resources = list(yaml.safe_load_all(raw))
    indexed = {(resource["kind"], resource["metadata"]["name"]): resource for resource in resources}
    assert len(indexed) == len(resources) == 5, "Expected five distinct service-owned resources"
    assert all(resource["metadata"]["namespace"] == "aimie-operations" for resource in resources)
    deployment = indexed["Deployment", "aimie-service"]
    pod = deployment["spec"]["template"]
    assert pod["metadata"]["labels"]["azure.workload.identity/use"] == "true"
    assert ("ServiceAccount", pod["spec"]["serviceAccountName"]) in indexed
    volume = pod["spec"]["volumes"][0]["csi"]
    assert ("SecretProviderClass", volume["volumeAttributes"]["secretProviderClass"]) in indexed
    container = pod["spec"]["containers"][0]
    environment = {item["name"]: item["value"] for item in container["env"]}
    assert environment["AzureFunctionsJobHost__extensions__durableTask__hubName"] == (
        "AimieServiceAksTest" if deployment_environment == "test" else "AimieServiceAksProduction"
    )
    assert environment["AzureFunctionsWebHost__hostid"] == (
        "aimie-service-aks-test" if deployment_environment == "test" else "aimie-service-aks-production"
    )
    assert environment["WEBSITE_HOSTNAME"] == "aimie-service.aimie-operations.svc.cluster.local"
    assert environment["AzureWebJobsSecretStorageType"] == "blob"
    assert container["readinessProbe"]["httpGet"]["path"] == "/api/healthz"
    assert container["resources"]["requests"] == (
        {"cpu": "25m", "memory": "1Gi"} if deployment_environment == "test"
        else {"cpu": "500m", "memory": "2Gi"}
    )
    service = indexed["Service", "aimie-service"]
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["selector"] == deployment["spec"]["selector"]["matchLabels"]
    ingress_resource = indexed["Ingress", "aimie-service"]
    ingress = ingress_resource["spec"]
    assert ingress["ingressClassName"] == "webapprouting.kubernetes.azure.com"
    assert ingress["tls"][0]["hosts"] == [ingress["rules"][0]["host"]]
    if deployment_environment == "production":
        assert "test" not in ingress["rules"][0]["host"]
        test_registry = os.environ["TEST_ACR_LOGIN_SERVER"]
        assert not container["image"].startswith(test_registry + "/"), "Production must use a separate registry"
        provider = indexed["SecretProviderClass", "aimie-service-appsettings"]
        vault = provider["spec"]["parameters"]["keyvaultName"]
        assert vault != os.environ["TEST_KEYVAULT_NAME"], "Production must use a separate vault"
        certificate_uri = ingress_resource["metadata"]["annotations"]["kubernetes.azure.com/tls-cert-keyvault-uri"]
        assert certificate_uri.startswith(f"https://{vault}.vault.azure.net/certificates/")
    paths = ingress["rules"][0]["http"]["paths"]
    assert {route["path"] for route in paths} == {
        "/api/AIInteractionService", "/runtime/webhooks/durabletask", "/api/healthz",
    }
    for route in paths:
        backend = route["backend"]["service"]
        assert backend["name"] == "aimie-service" and backend["port"]["name"] == "http"
    print(f"Validated {len(resources)} AKS resources and Durable isolation settings")


if __name__ == "__main__":
    deployment_environment = sys.argv[2] if len(sys.argv) > 2 else "test"
    validate(Path(sys.argv[1]), deployment_environment)
