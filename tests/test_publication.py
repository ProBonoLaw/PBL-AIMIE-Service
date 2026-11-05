import importlib.util
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load("publication_check_test", "scripts/check-publication.py")
exporter = load("publication_export_test", "scripts/export-public-snapshot.py")
example = load("source_example", "test.py")


@pytest.mark.parametrize("content", [
    "https://tenant" + ".sharepoint.com/sites/private/document.pdf",
    "https://private" + ".blob.core.windows.net",
    "12345678-1234-1234-1234-" + "123456789abc",
    "someone@" + "private.invalid",
    "-----BEGIN " + "PRIVATE KEY-----",
    "172.28." + "1.2",
])
def test_identifier_check_reports_location_without_value(content):
    findings = list(check.inspect_text("safe line\n" + content))
    assert findings and all(line == 2 for line, _ in findings)
    assert content not in str(findings)


def test_synthetic_values_and_environment_references_are_allowed():
    text = 'https://example.blob.core.windows.net\n${{ vars.SHAREPOINT_EXAMPLE_DOCUMENT_URL }}'
    assert not list(check.inspect_text(text))


def test_export_uses_working_tree_without_history_or_ignored_data(tmp_path):
    source, output = tmp_path / "source", tmp_path / "public"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / ".gitignore").write_text(".local/\n")
    (source / "code.py").write_text("old = True\n")
    (source / "deleted.txt").write_text("retired example\n")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    (source / "deleted.txt").unlink()
    (source / "code.py").write_text("sanitized = True\n")
    (source / "new.txt").write_text("new source\n")
    (source / ".local").mkdir()
    (source / ".local/private.txt").write_text("private input\n")
    exporter.export(source, output)
    assert (output / "code.py").read_text() == "sanitized = True\n"
    assert (output / "new.txt").exists()
    assert not (output / ".git").exists()
    assert not (output / ".local").exists()
    assert not (output / "deleted.txt").exists()
    with pytest.raises(ValueError, match="already exists"):
        exporter.export(source, output)


def test_export_rejects_symlinks_and_private_files(tmp_path):
    source, output = tmp_path / "source", tmp_path / "public"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    private = tmp_path / "private.txt"
    private.write_text("private content")
    (source / "link.txt").symlink_to(private)
    with pytest.raises(ValueError, match="Publication check failed"):
        exporter.export(source, output)
    assert not output.exists()


def test_source_example_uses_configuration_without_private_defaults(monkeypatch):
    monkeypatch.delenv("SHAREPOINT_EXAMPLE_DOCUMENT_URL", raising=False)
    assert "example.invalid" in example.example_payload()["context"][0]["metadata"]["source"]
    url = "https://example.invalid/configured-document.pdf"
    monkeypatch.setenv("SHAREPOINT_EXAMPLE_DOCUMENT_URL", url)
    assert example.example_payload()["context"][0]["metadata"]["source"] == url
    monkeypatch.setenv("SHAREPOINT_EXAMPLE_DOCUMENT_URL", url + "?sig=example")
    with pytest.raises(ValueError, match="without credentials"):
        example.example_payload()
