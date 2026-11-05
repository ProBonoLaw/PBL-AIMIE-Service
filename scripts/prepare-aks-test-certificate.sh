#!/usr/bin/env bash
# Generate a private key and CSR for the portal-facing AKS Test ingress.
# The ProBonoLaw Test Internal Root CA must sign this CSR before Key Vault import.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${TEST_INGRESS_HOST:?Set TEST_INGRESS_HOST}"
[[ "$TEST_INGRESS_HOST" =~ ^[a-z0-9.-]+\.[a-z]{2,}$ ]] || { echo 'Invalid Test ingress hostname' >&2; exit 1; }
umask 077
output_dir=${CERT_OUTPUT_DIR:-.local}
mkdir -p "$output_dir"
key="$output_dir/aimie-service-test-server.key"
csr="$output_dir/aimie-service-test-server.csr"
if [[ -e "$key" || -e "$csr" ]]; then
  echo 'Certificate key or CSR already exists; refusing to replace it' >&2
  exit 1
fi
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$key"
openssl req -new -key "$key" -out "$csr" \
  -subj "/CN=${TEST_INGRESS_HOST:?Set TEST_INGRESS_HOST}" \
  -addext "subjectAltName=DNS:${TEST_INGRESS_HOST}"
chmod 600 "$key" "$csr"
printf 'CSR: %s\nPrivate key: %s (keep private)\n' "$csr" "$key"
