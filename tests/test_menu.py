"""The in-game menu (Esc): its pages and buttons, the player's settings, and the host changing the map."""
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import main
import net
from game import Game, Inputs
from mapfile import Entity, Level, save_level
from menu import MAX_SENSITIVITY, MIN_SENSITIVITY, GameSettings, Menu
from session import ClientSession, HostSession
from test_session import FIRST_CHARACTER, make_world, run

SIZE = (1280, 800)


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def maps(tmp_path, *names):
    for name in names:
        save_level(str(tmp_path / f"{name}.json"), Level.blank(8 + len(name), 8))
    return str(tmp_path / f"{names[0]}.json")


def buttons(menu):
    return {item.label: item for item in menu.items(SIZE) if item.action}


def press(menu, label):
    item = buttons(menu)[label]
    return menu.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=item.rect.center, button=1), SIZE)


def escape(menu):
    return menu.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""), SIZE)


# ------------------------------------------------------------------ the pages

def test_the_main_page_has_resume_settings_and_exit_and_host_settings_only_for_the_host():
    assert list(buttons(Menu(GameSettings()))) == ["Resume", "Settings", "Exit game"]
    assert list(buttons(Menu(GameSettings(), is_host=True))) == ["Resume", "Settings", "Host settings", "Exit game"]
    menu = Menu(GameSettings())
    menu.show()
    assert press(menu, "Resume") == "resume" and press(menu, "Exit game") == "exit"
    assert escape(menu) == "resume"                                    # Esc on the main page closes the menu


def item(menu, kind):
    return next(i for i in menu.items(SIZE) if i.kind == kind)


def mouse(menu, kind, pos, button=1):
    if kind == pygame.MOUSEMOTION:
        return menu.handle(pygame.event.Event(kind, pos=pos, rel=(0, 0), buttons=(1, 0, 0)), SIZE)
    return menu.handle(pygame.event.Event(kind, pos=pos, button=button), SIZE)


def type_keys(menu, text):
    for char in text:
        menu.handle(pygame.event.Event(pygame.KEYDOWN, key=0, mod=0, unicode=char), SIZE)


def key(menu, k):
    return menu.handle(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""), SIZE)


def test_the_sensitivity_slider_follows_a_click_and_a_drag_and_is_saved_when_let_go():
    settings = GameSettings()
    menu = Menu(settings)
    press(menu, "Settings")
    slider = item(menu, "slider").rect
    start, end = menu.track(slider)
    assert mouse(menu, pygame.MOUSEBUTTONDOWN, (start, slider.centery)) is None
    assert settings.sensitivity == MIN_SENSITIVITY                     # the far left: the least
    assert mouse(menu, pygame.MOUSEMOTION, (end + 50, slider.centery)) is None
    assert settings.sensitivity == MAX_SENSITIVITY                     # (dragged past the end: the most)
    mouse(menu, pygame.MOUSEMOTION, ((start + end) // 2, slider.centery + 40))   # off the slider still drags
    assert settings.sensitivity == pytest.approx((MIN_SENSITIVITY + MAX_SENSITIVITY) / 2, abs=0.05)
    assert round(settings.sensitivity / 0.05, 6).is_integer()          # in steps of 0.05
    assert mouse(menu, pygame.MOUSEBUTTONUP, ((start + end) // 2, slider.centery)) == "settings"
    assert not menu.dragging


def test_the_sensitivity_can_be_typed_and_is_held_to_the_range():
    settings = GameSettings()
    menu = Menu(settings)
    menu.page = "settings"
    box = item(menu, "input")
    assert box.label == "1"
    mouse(menu, pygame.MOUSEBUTTONDOWN, box.rect.center)
    assert menu.typing == "1"
    key(menu, pygame.K_BACKSPACE)
    type_keys(menu, "2.5x.5")                                          # (only digits and one point are taken)
    assert menu.typing == "2.55"
    assert key(menu, pygame.K_RETURN) == "settings" and settings.sensitivity == 2.55 and menu.typing is None
    mouse(menu, pygame.MOUSEBUTTONDOWN, box.rect.center)
    type_keys(menu, "99")
    assert key(menu, pygame.K_ESCAPE) is None and settings.sensitivity == 2.55     # Esc forgets what was typed
    assert menu.page == "settings"                                     # ... and stays on the page
    mouse(menu, pygame.MOUSEBUTTONDOWN, box.rect.center)
    key(menu, pygame.K_BACKSPACE)
    key(menu, pygame.K_BACKSPACE)
    key(menu, pygame.K_BACKSPACE)
    key(menu, pygame.K_BACKSPACE)
    type_keys(menu, "9")
    assert key(menu, pygame.K_RETURN) == "settings" and settings.sensitivity == MAX_SENSITIVITY
    mouse(menu, pygame.MOUSEBUTTONDOWN, box.rect.center)
    for _ in range(4):
        key(menu, pygame.K_BACKSPACE)
    type_keys(menu, ".")
    assert key(menu, pygame.K_RETURN) is None and settings.sensitivity == MAX_SENSITIVITY and menu.message
    mouse(menu, pygame.MOUSEBUTTONDOWN, box.rect.center)
    for _ in range(4):
        key(menu, pygame.K_BACKSPACE)
    type_keys(menu, "0.75")
    assert mouse(menu, pygame.MOUSEBUTTONDOWN, (5, 5)) == "settings"    # clicking away keeps it
    assert settings.sensitivity == 0.75


def test_fullscreen_toggles_and_back_returns():
    settings = GameSettings()
    menu = Menu(settings)
    press(menu, "Settings")
    assert press(menu, "Fullscreen: off") == "settings" and settings.fullscreen
    assert escape(menu) is None and menu.page == "main"                # Esc goes back a page


def test_settings_are_kept_between_runs(tmp_path):
    path = str(tmp_path / "settings" / "game.json")
    assert GameSettings.load(path) == GameSettings()                   # none yet: the defaults
    GameSettings(1.75, True).save(path)
    assert GameSettings.load(path) == GameSettings(1.75, True)
    with open(path, "w") as f:
        f.write("{ broken")
    assert GameSettings.load(path) == GameSettings()


def test_the_host_page_shows_the_players_and_lists_the_maps_to_change_to(tmp_path):
    current = maps(tmp_path, "arena", "castle", "dunes")
    (tmp_path / "notes.txt").write_text("not a map")
    menu = Menu(GameSettings(), is_host=True, map_path=current, players=lambda: 3)
    press(menu, "Host settings")
    labels = [item.label for item in menu.items(SIZE)]
    assert "3 players in the game" in labels and "Map: arena.json" in labels
    press(menu, "Change map")
    listed = buttons(menu)
    assert set(listed) == {"arena  (playing)", "castle", "dunes", "Back"}
    assert not listed["arena  (playing)"].enabled                      # (already playing it)
    assert press(menu, "castle") == "map:" + str(tmp_path / "castle.json")
    escape(menu)
    assert menu.page == "host"


def test_a_long_list_of_maps_scrolls(tmp_path):
    current = maps(tmp_path, *(f"map{i:02}" for i in range(20)))
    menu = Menu(GameSettings(), is_host=True, map_path=current)
    menu.page = "maps"
    assert "map07" in buttons(menu) and "map08" not in buttons(menu)
    menu.handle(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-5), SIZE)
    assert "map05" in buttons(menu) and "map12" in buttons(menu) and "map04" not in buttons(menu)
    menu.handle(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-50), SIZE)
    assert "map19" in buttons(menu)                                    # (it stops at the end)


def test_every_page_draws_and_the_buttons_fit_in_the_panel(tmp_path):
    menu = Menu(GameSettings(), is_host=True, map_path=maps(tmp_path, "arena", "castle"))
    for page in ("main", "settings", "host", "maps"):
        menu.page = page
        first = next(iter(buttons(menu).values()))
        menu.draw(pygame.Surface(SIZE, pygame.SRCALPHA), first.rect.center)
        box = menu.panel(SIZE)
        assert all(box.contains(item.rect) for item in menu.items(SIZE))
    menu.say("Could not load it", warn=True)
    menu.draw(pygame.Surface(SIZE, pygame.SRCALPHA))


# ------------------------------------------------------------------ the game window and the mouse

def test_the_menu_is_drawn_over_the_picture_in_place_of_the_crosshair():
    for without_gpu in (False, True):
        screen = main.Screen("test", (800, 450))
        try:
            if without_gpu:                                            # (a window without a GPU renderer)
                screen.gpu = screen.texture = None
            frame = pygame.Surface((main.WIDTH, main.HEIGHT))
            frame.fill((200, 40, 40))
            overlay = pygame.Surface((800, 450), pygame.SRCALPHA)
            overlay.fill((0, 0, 255, 255), (0, 0, 100, 100))
            screen.show(frame, overlay)
            shown = screen.window.get_surface() if without_gpu else screen.gpu.to_surface()
            assert tuple(shown.get_at((50, 50)))[:3] == (0, 0, 255)
            assert tuple(shown.get_at((400, 225)))[:3] == (200, 40, 40)   # no crosshair under the menu
        finally:
            screen.window.destroy()


def test_the_sensitivity_setting_scales_mouse_look():
    look = main.MouseLook(sensitivity=main.MOUSE_SENSITIVITY * 2)
    look.set_captured(True)
    look.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(0, 0), rel=(10, 0), buttons=(0, 0, 0)))
    assert look.take()[0] == pytest.approx(10 * main.MOUSE_SENSITIVITY * 2)
    look.set_captured(False)


# ------------------------------------------------------------------ the host changing the map

def test_the_host_changing_the_map_moves_every_joiner_to_it(tmp_path):
    first = maps(tmp_path, "arena")
    castle = Level.blank(20, 9)
    castle.entities = [Entity(5.5, 5.5)]
    save_level(str(tmp_path / "castle.json"), castle)
    graphics = main.Graphics()
    graphics.load(main.ATLAS_PATH)
    level = main.load_or_default(first)
    host = HostSession(Game(level, graphics.make_world(level), random.Random(1), character_tile=graphics.character_tile),
                       net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
    try:
        run([host, client], until=lambda: client.ready or client.ended)
        main.reload_game(host, graphics, str(tmp_path / "castle.json"))
        run([host, client], until=lambda: client.loads == 2 and client.ready and client.level.width == 20)
        assert host.game.level.width == 20 and len(client.items.items) == 1
        run([host, client], until=lambda: host.game.players[1].body.x > 2.0, inputs={client: Inputs(forward=1)})
    finally:
        host.close()
        client.close()
