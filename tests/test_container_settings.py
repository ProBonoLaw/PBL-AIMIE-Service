import importlib.util
import ast
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("start_functions", ROOT / "deploy/start_functions.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_function_app_local_modules_are_packaged_in_container():
    """A missing imported module prevents indexing every HTTP function."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    allowed = (ROOT / ".dockerignore").read_text().splitlines()
    copied = {
        source
        for line in dockerfile.splitlines()
        if line.startswith("COPY ")
        for source in line.split()[1:-1]
    }
    imports = set()
    for node in ast.walk(ast.parse((ROOT / "function_app.py").read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
    for name in imports:
        filename = f"{name}.py"
        if (ROOT / filename).is_file():
            assert filename in copied, f"Dockerfile does not copy {filename}"
            assert f"!{filename}" in allowed, f".dockerignore excludes {filename}"
        elif (ROOT / name).is_dir():
            assert name in copied, f"Dockerfile does not copy {name}"
            assert f"!{name}/" in allowed, f".dockerignore excludes {name}"
            assert f"!{name}/**" in allowed, f".dockerignore excludes files in {name}"


def test_mount_is_loaded_before_exec_and_identity_overrides_source_settings(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"API_KEY": 'literal $value `no-shell`\nsecond line', "AZURE_CLIENT_ID": "old"}))
    result = subprocess.run(
        [sys.executable, str(ROOT / "deploy/start_functions.py"), sys.executable, "-c",
         "import os,json; print(json.dumps([os.environ['API_KEY'],os.environ['AZURE_CLIENT_ID']]))"],
        env={"APPSETTINGS_FILE": str(settings), "AZURE_CLIENT_ID": "projected-identity"},
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == ['literal $value `no-shell`\nsecond line', "projected-identity"]


@pytest.mark.parametrize("payload", [[], {}, {"A": 1}, {"A": "a\0b"}, {"A=B": "value"}, {"A": "@Microsoft.KeyVault(SecretUri=private)"}])
def test_invalid_settings_fail_before_starting_host(tmp_path, payload):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        module.load_settings(settings, {})


def test_invalid_json_is_not_logged(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"API_KEY": "do-not-print-this-secret"')
    result = subprocess.run(
        [sys.executable, str(ROOT / "deploy/start_functions.py")],
        env={"APPSETTINGS_FILE": str(settings)}, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "do-not-print-this-secret" not in result.stdout + result.stderr
