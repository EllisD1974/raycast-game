"""The game and the map editor open maximized."""
import os
import sys
import time
import types

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
import window
from mapfile import Level


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1280, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(20, 12)
    editor.fit_view()
    return editor


def fake_pygame(from_display_module):
    """A stand-in for the `pygame` name inside window.py (pygame.Window is a built-in type)."""
    return types.SimpleNamespace(Window=types.SimpleNamespace(from_display_module=from_display_module))


def test_maximize_asks_the_window_to_maximize_and_reports_it(monkeypatch):
    calls = []

    class FakeWindow:
        def maximize(self):
            calls.append("maximize")

    monkeypatch.setattr(window, "pygame", fake_pygame(lambda: FakeWindow()))
    assert window.maximize() is True and calls == ["maximize"]


def test_maximize_is_harmless_where_it_cannot_work(monkeypatch):
    def refuse():
        raise pygame.error("no window")

    monkeypatch.setattr(window, "pygame", fake_pygame(refuse))
    assert window.maximize() is False                         # no exception: the window just stays as it is


def test_maximize_with_the_real_window_api_does_not_raise():
    assert window.maximize() in (True, False)


def resize_to(width, height):
    pygame.display.set_mode((width, height), pygame.RESIZABLE)
    return pygame.event.Event(pygame.VIDEORESIZE, size=(width, height), w=width, h=height)


def test_the_editor_asks_for_maximize_and_opens_a_refit_window(ed, monkeypatch):
    calls = []
    monkeypatch.setattr(map_editor, "maximize", lambda: calls.append(1) or True)
    before = time.time()
    assert ed.start_maximized() is True and calls == [1]
    assert before < ed.refit_until <= time.time() + map_editor.REFIT_SECONDS + 0.01


def test_resizes_right_after_startup_refit_the_map_to_the_bigger_window(ed):
    ed.start_maximized()
    small_zoom = ed.zoom
    ed.handle_event(resize_to(1920, 1009))                    # what maximizing does
    area = ed.map_area()
    assert ed.zoom > small_zoom
    assert ed.pan[0] >= 0 and ed.pan[1] >= 0
    assert ed.pan[0] + ed.level.width * ed.zoom <= area.w and ed.pan[1] + ed.level.height * ed.zoom <= area.h
    ed.handle_event(resize_to(1280, 860))                     # and every resize inside the window refits
    assert ed.zoom == small_zoom


def test_a_resize_after_the_startup_window_never_undoes_the_users_view(ed):
    ed.start_maximized()
    ed.refit_until = time.time() - 1                          # the startup window has passed
    ed.pan[0] += 40
    ed.zoom += 8
    view = (ed.zoom, tuple(ed.pan))
    ed.handle_event(resize_to(1500, 900))
    assert (ed.zoom, tuple(ed.pan)) == view


def test_without_start_maximized_a_resize_does_not_touch_the_view(ed):
    ed.pan[0] += 25
    view = (ed.zoom, tuple(ed.pan))
    ed.handle_event(resize_to(1500, 900))
    assert (ed.zoom, tuple(ed.pan)) == view


def test_the_editor_still_draws_after_a_resize(ed):
    ed.start_maximized()
    ed.handle_event(resize_to(1920, 1009))
    ed.draw(pygame.display.get_surface())
