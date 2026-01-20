"""Print server boundary tests.

These tests must be deterministic and CI-safe:
- Never write to privileged paths like /var/lib.
- Never rely on subprocess behavior.
- No xfail/skip markers.

The print server is intentionally independent of the main web app;
these tests focus on environment gating and safe imports.
"""

import importlib
import os
import sys
import pytest


def _fresh_import_print_server_app():
    """Import services.print_server.app with a clean module cache."""
    for mod in [
        "services.print_server.app",
        "services.print_server.__main__",
        "services.print_server",
    ]:
        sys.modules.pop(mod, None)
    return importlib.import_module("services.print_server.app")


def test_print_server_imports_in_dev(tmp_path, monkeypatch):
    """Dev mode should import cleanly and initialize inbox in a writable path."""
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("PRINT_SERVER_DEV_MODE", "1")
    monkeypatch.setenv("PRINT_INBOX_DIR", str(tmp_path))
    monkeypatch.delenv("PRINT_SERVER_TOKEN", raising=False)

    ps = _fresh_import_print_server_app()
    assert ps.app is not None
    assert os.path.isdir(str(tmp_path))


def test_print_server_requires_token_in_production(tmp_path, monkeypatch):
    """Production mode must fail fast if PRINT_SERVER_TOKEN is missing."""
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("PRINT_SERVER_DEV_MODE", "0")
    monkeypatch.setenv("PRINT_INBOX_DIR", str(tmp_path))
    monkeypatch.delenv("PRINT_SERVER_TOKEN", raising=False)

    with pytest.raises(ValueError) as exc:
        _fresh_import_print_server_app()

    assert "PRINT_SERVER_TOKEN" in str(exc.value)


def test_print_server_allows_token_in_production(tmp_path, monkeypatch):
    """Production mode should import when a non-dev token is provided."""
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("PRINT_SERVER_DEV_MODE", "0")
    monkeypatch.setenv("PRINT_INBOX_DIR", str(tmp_path))
    monkeypatch.setenv("PRINT_SERVER_TOKEN", "test-prod-token")

    ps = _fresh_import_print_server_app()
    assert ps.app is not None
