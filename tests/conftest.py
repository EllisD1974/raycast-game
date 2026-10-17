"""Shared test setup: the editor's 3D view is off by default so tests of the map area, clicks and
zoom see the layout they were written for; tests of the view itself switch it on."""
import os
import sys

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import map_editor  # noqa: E402
import preview  # noqa: E402


@pytest.fixture(autouse=True)
def quiet_editor_defaults(monkeypatch):
    monkeypatch.setattr(map_editor, "DEFAULT_SHOW_PREVIEW", False)
    monkeypatch.setattr(preview, "REBUILD_INTERVAL", 0.0)
