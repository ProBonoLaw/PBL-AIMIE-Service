#!/usr/bin/env python3
"""Sign the AIMIE Test CSR with the existing CA key without exporting that key."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID


ROOT = Path(__file__).resolve().parent.parent
CSR_PATH = ROOT / ".local/aimie-service-test-server.csr"
KEY_PATH = ROOT / ".local/aimie-service-test-server.key"
OUTPUT_PATH = ROOT / ".local/aimie-service-test-server.crt"



def azure_json(*args: str) -> dict:
    return json.loads(subprocess.check_output(["az", *args, "--output", "json"], text=True))


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class KeyVaultRSAPrivateKey(rsa.RSAPrivateKey):
    """Cryptography signing adapter; only the digest goes to Key Vault."""

    def __init__(self, public_key: rsa.RSAPublicKey, key_id: str, token: str):
        self._public_key = public_key
        self._key_id = key_id
        self._token = token

    @property
    def key_size(self) -> int:
        return self._public_key.key_size

    def public_key(self) -> rsa.RSAPublicKey:
        return self._public_key

    def sign(self, data: bytes, padding_alg: object, algorithm: object) -> bytes:
        if not isinstance(padding_alg, padding.PKCS1v15) or not isinstance(
            algorithm, hashes.SHA256
        ):
            raise ValueError("Only RS256 X.509 signatures are supported")
        digest = hashlib.sha256(data).digest()
        body = json.dumps({"alg": "RS256", "value": b64url(digest)}).encode()
        request = urllib.request.Request(
            f"{self._key_id}/sign?api-version=7.4",
            data=body,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                signature = json.load(response)["value"]
        except urllib.error.HTTPError as error:
            raise RuntimeError(
                f"Key Vault refused signing (HTTP {error.code}); check Key Vault Crypto User access"
            ) from error
        return base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))

    def decrypt(self, ciphertext: bytes, padding_alg: object) -> bytes:
        raise NotImplementedError("The CA key cannot be used for decryption here")

    def private_numbers(self) -> rsa.RSAPrivateNumbers:
        raise NotImplementedError("The CA private key remains in Key Vault")

    def private_bytes(self, encoding: object, format: object, encryption_algorithm: object) -> bytes:
        raise NotImplementedError("The CA private key remains in Key Vault")

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


def main() -> None:
    hostname, ca_vault, ca_name = [os.environ[name] for name in ("TEST_INGRESS_HOST", "TEST_CA_VAULT_NAME", "TEST_CA_CERT_NAME")]
    if OUTPUT_PATH.exists():
        raise RuntimeError(f"Refusing to overwrite existing certificate: {OUTPUT_PATH}")
    csr = x509.load_pem_x509_csr(CSR_PATH.read_bytes())
    if not csr.is_signature_valid:
        raise RuntimeError("CSR signature is invalid")
    san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    if san.get_values_for_type(x509.DNSName) != [hostname]:
        raise RuntimeError(f"CSR must request exactly DNS:{hostname}")
    server_key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    if csr.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    ) != server_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    ):
        raise RuntimeError("CSR does not match the AIMIE server private key")

    ca_record = azure_json(
        "keyvault", "certificate", "show", "--vault-name", ca_vault, "--name", ca_name
    )
    ca_cert = x509.load_der_x509_certificate(base64.b64decode(ca_record["cer"]))
    ca_public_key = ca_cert.public_key()
    if not isinstance(ca_public_key, rsa.RSAPublicKey):
        raise RuntimeError("The Test CA key must be RSA")
    if not ca_cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise RuntimeError("The issuer certificate is not a CA")

    token = azure_json("account", "get-access-token", "--resource", "https://vault.azure.net")[
        "accessToken"
    ]
    now = datetime.now(timezone.utc)
    expires = min(now + timedelta(days=395), ca_cert.not_valid_after_utc - timedelta(days=1))
    if expires <= now:
        raise RuntimeError("The Test CA expires too soon to issue a server certificate")
    builder = (
        x509.CertificateBuilder()
        .subject_name(csr.subject)
        .issuer_name(ca_cert.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(expires)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(san, critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(csr.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_public_key), critical=False
        )
    )
    certificate = builder.sign(
        private_key=KeyVaultRSAPrivateKey(ca_public_key, ca_record["kid"], token),
        algorithm=hashes.SHA256(),
    )
    ca_public_key.verify(
        certificate.signature,
        certificate.tbs_certificate_bytes,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    OUTPUT_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with OUTPUT_PATH.open("xb") as output:
        output.write(certificate.public_bytes(serialization.Encoding.PEM))
    OUTPUT_PATH.chmod(0o600)
    print(f"Signed AIMIE server certificate: {OUTPUT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
