import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "resolve_aks_production_image",
    Path(__file__).resolve().parents[1] / "scripts/resolve_aks_production_image.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_latest_resolves_to_the_matching_commit_and_digest():
    old_tag = "sha-" + "1" * 40
    new_tag = "sha-" + "2" * 40
    old_digest = "sha256:" + "a" * 64
    new_digest = "sha256:" + "b" * 64
    rows = [
        {"name": old_tag, "digest": old_digest, "lastUpdateTime": "2026-01-01T00:00:00Z"},
        {"name": new_tag, "digest": new_digest, "lastUpdateTime": "2026-01-02T00:00:00Z"},
        {"name": "latest", "digest": new_digest, "lastUpdateTime": "2026-01-02T00:00:01Z"},
    ]
    assert module.resolve("latest", rows) == (new_tag, new_digest)
    assert module.resolve(old_tag, rows) == (old_tag, old_digest)


def test_latest_requires_a_matching_commit_tag():
    rows = [{"name": "latest", "digest": "sha256:" + "a" * 64}]
    with pytest.raises(ValueError, match="no matching immutable commit tag"):
        module.resolve("latest", rows)
