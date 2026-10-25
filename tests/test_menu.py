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
from menu import MAX_SENSITIVITY, GameSettings, Menu
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


def test_settings_change_the_sensitivity_and_fullscreen_and_back_returns():
    settings = GameSettings()
    menu = Menu(settings)
    press(menu, "Settings")
    assert menu.page == "settings"
    assert press(menu, "More") == "settings" and settings.sensitivity == 1.25
    assert press(menu, "Less") == "settings" and press(menu, "Less") == "settings" and settings.sensitivity == 0.75
    assert press(menu, "Fullscreen: off") == "settings" and settings.fullscreen
    for _ in range(40):
        menu.press("sensitivity+")
    assert settings.sensitivity == MAX_SENSITIVITY and not buttons(menu)["More"].enabled
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
