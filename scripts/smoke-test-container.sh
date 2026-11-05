#!/usr/bin/env bash
# Exercise the actual packaged host against disposable Azurite; no Azure account is used.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${IMAGE_TAG:?Set IMAGE_TAG}"
scratch=$(mktemp -d)
cleanup() {
  if [[ "$1" != 0 ]]; then docker logs aimie-smoke 2>&1 | tail -150 || true; fi
  docker rm -f aimie-smoke aimie-smoke-storage >/dev/null 2>&1 || true
  docker network rm aimie-smoke >/dev/null 2>&1 || true
  rm -rf "$scratch"
}
trap 'cleanup $?' EXIT
docker network create aimie-smoke >/dev/null
cat function_app.py tests/container/functions.py > "$scratch/function_app.py"
# This synthetic account key is only used by the disposable Azurite instance.
cat > "$scratch/appsettings.json" <<'JSON'
{
  "AzureWebJobsStorage": "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFeqCnf2LJ8bP2vK6r6BvP/0gTBDbE=;BlobEndpoint=http://aimie-smoke-storage:10000/devstoreaccount1;QueueEndpoint=http://aimie-smoke-storage:10001/devstoreaccount1;TableEndpoint=http://aimie-smoke-storage:10002/devstoreaccount1;",
  "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=http://127.0.0.1:9/",
  "TEXT_EMBEDDING_OPENAI_ENDPOINT": "https://example.openai.azure.com",
  "TEXT_EMBEDDING_API_KEY": "smoke-test",
  "OPENAI_API_VERSION": "2024-02-01"
}
JSON
# Configure the same synthetic account in Azurite.
docker run -d --name aimie-smoke-storage --network aimie-smoke \
  -e 'AZURITE_ACCOUNTS=devstoreaccount1:Eby8vdM02xNOcqFeqCnf2LJ8bP2vK6r6BvP/0gTBDbE=' \
  mcr.microsoft.com/azure-storage/azurite:3.35.0 \
  azurite --blobHost 0.0.0.0 --queueHost 0.0.0.0 --tableHost 0.0.0.0 --skipApiVersionCheck >/dev/null
docker run -d --name aimie-smoke --network aimie-smoke -p 127.0.0.1:18080:80 \
  --mount "type=bind,source=$scratch/appsettings.json,target=/mnt/keyvault/appsettings.json,readonly" \
  --mount "type=bind,source=$scratch/function_app.py,target=/home/site/wwwroot/function_app.py,readonly" \
  -e AzureFunctionsWebHost__hostid=aimie-service-smoke \
  -e WEBSITE_HOSTNAME=aimie-smoke:80 \
  -e AzureWebJobsSecretStorageType=blob \
  -e AzureFunctionsJobHost__extensions__durableTask__hubName=AimieServiceSmoke \
  -e AzureFunctionsJobHost__extensions__durableTask__httpSettings__useForwardedHost=true \
  -e ASPNETCORE_FORWARDEDHEADERS_ENABLED=true \
  "aimie-service:${IMAGE_TAG}" >/dev/null
python3 scripts/check-container-recovery.py
