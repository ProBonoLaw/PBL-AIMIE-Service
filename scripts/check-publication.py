#!/usr/bin/env python3
"""Check candidate source files for identifiers that should be private configuration.

This is a regression check, not a substitute for secret scanning and human review.
Only paths and line numbers are reported; matching values are never printed.
"""

import argparse
from pathlib import Path
import re
import subprocess
import sys

UUID = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.I)
# Synthetic fixture UUIDs and Microsoft's documented Cosmos role / AKS audience.
PUBLIC_UUIDS = {
    "00000000-0000-0000-0000-000000000000",
    "11111111-1111-1111-1111-111111111111",
    "22222222-2222-2222-2222-222222222222",
    "00000000-0000-0000-0000-000000000002",
    "6dae42f8-4368-4678-94ff-3960e28e3630",
}
CLOUD_HOST = re.compile(
    r"\b([a-z0-9][a-z0-9.-]*\.(?:azurewebsites\.net|azurecr\.io|"
    r"vault\.azure\.net|(?:blob|queue|table)\.core\.windows\.net|"
    r"documents\.azure\.com|search\.windows\.net|openai\.azure\.com|"
    r"cognitiveservices\.azure\.com|sharepoint\.com|onmicrosoft\.com))\b", re.I,
)
EMAIL = re.compile(r"[a-z0-9_.+\[\]-]+@([a-z0-9.-]+\.[a-z]{2,})", re.I)
SAFE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "example.invalid", "users.noreply.github.com"}
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")
PRIVATE_IP = re.compile(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))(?:\.\d{1,3}){2,3}\b")


def candidate_files(root):
    """Include tracked edits and nonignored new files, but never .git or ignored data."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True, capture_output=True,
    )
    return sorted({Path(name.decode()) for name in result.stdout.split(b"\0") if name})


def inspect_text(text):
    for number, line in enumerate(text.splitlines(), 1):
        if any(match.group().lower() not in PUBLIC_UUIDS for match in UUID.finditer(line)):
            yield number, "non-example UUID: use configuration"
        for match in CLOUD_HOST.finditer(line):
            hostname = match.group().lower()
            if hostname.endswith((".sharepoint.com", ".onmicrosoft.com")) or not hostname.startswith("example"):
                yield number, "literal cloud/tenant hostname: use configuration"
                break
        if any(match.group(1).lower() not in SAFE_EMAIL_DOMAINS for match in EMAIL.finditer(line)):
            yield number, "non-example email address"
        if PRIVATE_KEY.search(line):
            yield number, "private key material"
        if PRIVATE_IP.search(line):
            yield number, "private network address: use configuration"


def inspect_files(root, files):
    for relative in files:
        path = root / relative
        if not path.exists() and not path.is_symlink():
            continue  # Deleted tracked files are absent from the candidate snapshot.
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            yield relative, 0, "symlinks and nonregular files require manual review"
            continue
        if (relative.parts[0] in {".git", ".local", "public-export"}
                or relative.name in {"local.settings.json", "appsettings.json"}
                or (relative.name.startswith(".env") and relative.name != ".env.example")
                or relative.suffix.lower() in {".pem", ".key", ".pfx", ".p12", ".csr"}
                or relative.parts[:2] in {("tests", "test1"), ("tests", "test2")}):
            yield relative, 0, "private configuration, key, or retired case-fixture path"
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            yield relative, 0, "binary file requires manual publication review"
            continue
        for number, message in inspect_text(text):
            yield relative, number, message


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    files = candidate_files(args.root)
    findings = list(inspect_files(args.root, files))
    for path, line, message in findings:
        print(f"{path}:{line}: {message}", file=sys.stderr)
    if findings:
        return 1
    print(f"Publication identifier check passed for {len(files)} candidate paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
