from pathlib import Path

import pytest

from src.utils.config import config


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests that download/load ML models (deselect with '-m \"not slow\"')",
    )


@pytest.fixture(autouse=True)
def allow_tmp_workspaces(tmp_path_factory, monkeypatch):
    """Automatically allow pytest temporary directories as valid workspaces."""
    basetemp = tmp_path_factory.getbasetemp().resolve()
    monkeypatch.setattr(config, "ALLOWED_WORKSPACES", [basetemp, Path.cwd().resolve()])
    monkeypatch.chdir(basetemp)
