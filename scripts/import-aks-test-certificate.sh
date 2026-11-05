#!/usr/bin/env bash
# Validate and import the signed AIMIE ingress certificate into the AKS Key Vault.
set -euo pipefail

cd "$(dirname "$0")/.."
umask 077

usage() {
  cat <<'EOF'
Usage: bash scripts/import-aks-test-certificate.sh --cert SIGNED_LEAF_PEM [options]

Options:
  --key PATH      Matching private key (default: .local/aimie-service-test-server.key)
  --ca-cert PATH  Issuing root CA PEM (default: download public cert from TEST_CA_VAULT_NAME)
  --dry-run       Validate without importing into Key Vault
  --help          Show this help

The signed leaf certificate must be for TEST_INGRESS_HOST.
Do not pass the CSR or the root CA certificate as --cert.
EOF
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

cert_file=
key_file=.local/aimie-service-test-server.key
ca_file=
dry_run=false

while (($#)); do
  case "$1" in
    --cert|--key|--ca-cert)
      (($# >= 2)) || fail "$1 requires a path"
      case "$1" in
        --cert) cert_file=$2 ;;
        --key) key_file=$2 ;;
        --ca-cert) ca_file=$2 ;;
      esac
      shift 2
      ;;
    --dry-run) dry_run=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ -n "$cert_file" ]] || { usage >&2; fail '--cert is required'; }
if [[ "$cert_file" == /absolute/path/to/* || "$cert_file" == /path/to/* ]]; then
  fail "$cert_file is an example path; replace it with the real location of the signed server certificate"
fi
[[ -f "$cert_file" ]] || fail "signed certificate not found: $cert_file"
[[ -f "$key_file" ]] || fail "private key not found: $key_file"
[[ -z "$ca_file" || -f "$ca_file" ]] || fail "CA certificate not found: $ca_file"
command -v openssl >/dev/null || fail 'openssl is required'
if [[ -z "$ca_file" || "$dry_run" == false ]]; then
  command -v az >/dev/null || fail 'Azure CLI is required'
fi

tmp_dir=$(mktemp -d)
trap 'rm -r -- "$tmp_dir"' EXIT
leaf_file=$tmp_dir/leaf.pem
bundle_file=$tmp_dir/import.pfx
hostname=${TEST_INGRESS_HOST:?Set TEST_INGRESS_HOST}

# Extract the first certificate as the leaf. This also rejects a CSR or a PFX.
openssl x509 -in "$cert_file" -out "$leaf_file" 2>/dev/null || \
  fail '--cert must be a signed X.509 certificate in PEM format (not a CSR or PFX)'

cert_key_hash=$(openssl x509 -in "$leaf_file" -pubkey -noout |
  openssl pkey -pubin -outform DER 2>/dev/null | openssl dgst -sha256)
private_key_hash=$(openssl pkey -in "$key_file" -pubout -outform DER 2>/dev/null |
  openssl dgst -sha256) || fail "cannot read private key: $key_file"
[[ "$cert_key_hash" == "$private_key_hash" ]] || \
  fail "certificate public key does not match $key_file; have the CA sign the CSR created from this key, or supply its matching key with --key"

openssl x509 -in "$leaf_file" -noout -ext subjectAltName |
  tr ',' '\n' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' |
  grep -Fxq "DNS:$hostname" || fail "certificate SAN must contain DNS:$hostname"
openssl x509 -in "$leaf_file" -checkend 0 -noout >/dev/null || \
  fail 'certificate is expired or otherwise not currently valid'

if [[ -z "$ca_file" ]]; then
  ca_file=$tmp_dir/ca.pem
  az keyvault certificate download \
    --vault-name "${TEST_CA_VAULT_NAME:?Set TEST_CA_VAULT_NAME}" \
    --name "${TEST_CA_CERT_NAME:?Set TEST_CA_CERT_NAME}" \
    --file "$ca_file" --encoding PEM --output none
fi
openssl verify -CAfile "$ca_file" "$leaf_file" >/dev/null || \
  fail 'certificate is not trusted by the ProBonoLaw Test Internal Root CA'

printf 'Validated certificate, private key, hostname, validity, and CA chain.\n'
if [[ "$dry_run" == true ]]; then
  printf 'Dry run complete; nothing was uploaded.\n'
  exit 0
fi

# Match the PKCS#12 format used by the working Markdown Converter certificate.
# The temporary PFX has an empty password and is deleted on exit.
openssl pkcs12 -export \
  -in "$leaf_file" -inkey "$key_file" -certfile "$ca_file" \
  -out "$bundle_file" -passout pass:
openssl pkcs12 -in "$bundle_file" -passin pass: -noout
az keyvault certificate import \
  --vault-name "${TEST_KEYVAULT_NAME:?Set TEST_KEYVAULT_NAME}" \
  --name "${TEST_TLS_CERT_NAME:?Set TEST_TLS_CERT_NAME}" \
  --file "$bundle_file" --output none
printf 'Imported certificate into the configured Test vault.\n'
