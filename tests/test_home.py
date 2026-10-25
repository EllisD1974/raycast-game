"""The home screen: hosting (a map, a password, the most players) and joining (an address and password)."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import main
import net
from game import Inputs
from home import Home
from mapfile import Level, save_level
from menu import MAX_PLAYERS, MIN_PLAYERS, GameSettings
from session import ClientSession, HostSession
from test_session import FIRST_CHARACTER, make_world, run

SIZE = (1280, 900)


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


@pytest.fixture
def folder(tmp_path):
    for name, width in (("arena", 10), ("castle", 14), ("dunes", 18)):
        save_level(str(tmp_path / f"{name}.json"), Level.blank(width, 8))
    return tmp_path


def buttons(home):
    return {item.label: item for item in home.items(SIZE) if item.action}


def click(home, label):
    item = next(i for i in home.items(SIZE) if i.action and i.label == label)
    return home.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=item.rect.center, button=1), SIZE)


def click_box(home, field):
    item = next(i for i in home.items(SIZE) if i.action == f"input:{field}")
    return home.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=item.rect.center, button=1), SIZE)


def type_text(home, text):
    for char in text:
        home.handle(pygame.event.Event(pygame.KEYDOWN, key=0, mod=0, unicode=char), SIZE)


def key(home, k):
    return home.handle(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""), SIZE)


# ------------------------------------------------------------------ the pages

def test_the_home_page_offers_host_join_settings_and_exit(folder):
    home = Home(GameSettings(), str(folder))
    assert list(buttons(home)) == ["Host game", "Join game", "Settings", "Exit"]
    assert click(home, "Exit") == "exit"
    click(home, "Settings")
    assert home.page == "settings" and any(i.kind == "slider" for i in home.items(SIZE))
    key(home, pygame.K_ESCAPE)
    assert home.page == "home"


def test_hosting_needs_a_password_and_lets_the_map_and_players_be_chosen(folder):
    settings = GameSettings()
    home = Home(settings, str(folder))
    click(home, "Host game")
    listed = buttons(home)
    assert {"arena", "castle", "dunes"} <= set(listed) and listed["arena"].selected      # the first, by default
    click(home, "castle")
    assert buttons(home)["castle"].selected and home.map_path() == str(folder / "castle.json")
    assert click(home, "Start hosting") is None and "password" in home.message           # none typed yet
    click_box(home, "host_password")
    type_text(home, "sesame")
    key(home, pygame.K_RETURN)
    assert home.host_password == "sesame"
    assert next(i for i in home.items(SIZE) if i.action == "input:host_password").label == "******"   # hidden
    click(home, "+")
    assert settings.max_players == 9
    for _ in range(30):
        click(home, "-") if buttons(home)["-"].enabled else None
    assert settings.max_players == MIN_PLAYERS and not buttons(home)["-"].enabled
    settings.max_players = MAX_PLAYERS
    assert not buttons(home)["+"].enabled
    assert click(home, "Start hosting") == "host" and settings.host_map == "castle.json"


def test_the_map_hosted_last_is_picked_again(folder):
    home = Home(GameSettings(host_map="dunes.json"), str(folder))
    assert home.host_map() == "dunes.json"
    assert Home(GameSettings(host_map="gone.json"), str(folder)).host_map() == "arena.json"


def test_joining_takes_an_ip_address_a_port_that_starts_at_7777_and_a_password(folder):
    home = Home(GameSettings(), str(folder))
    click(home, "Join game")
    boxes = {i.action: i.label for i in home.items(SIZE) if i.kind == "input"}
    assert boxes == {"input:address": "", "input:port": "7777", "input:join_password": ""}   # the IP starts empty
    assert click(home, "Join") is None and "IP address" in home.message
    click_box(home, "address")
    type_text(home, "192.168.1.20 :x!")
    key(home, pygame.K_RETURN)
    assert home.join_address == "192.168.1.20x"                         # (no spaces, colons or punctuation)
    click_box(home, "port")
    type_text(home, "8a0")
    assert home.typing == "77778"                                       # digits only, five at most (7777 was there)
    for _ in range(5):
        key(home, pygame.K_BACKSPACE)
    type_text(home, "99999")
    key(home, pygame.K_RETURN)
    assert home.join_port == "99999" and home.port() is None
    assert click(home, "Join") is None and "port" in home.message
    click_box(home, "port")
    for _ in range(5):
        key(home, pygame.K_BACKSPACE)
    type_text(home, "8000")
    key(home, pygame.K_RETURN)
    assert home.port() == 8000
    assert click(home, "Join") is None and "password" in home.message
    click_box(home, "join_password")
    type_text(home, "pw")
    assert click(home, "Join") == "join" and home.join_password == "pw"  # (clicking away kept what was typed)
    home.go("connecting")
    assert "192.168.1.20x:8000" in home.items(SIZE)[0].label
    assert list(buttons(home)) == ["Cancel"] and key(home, pygame.K_ESCAPE) == "cancel"


def test_a_new_join_page_starts_empty_with_port_7777(folder):
    home = Home(GameSettings(), str(folder))
    assert (home.join_address, home.join_port, home.port()) == ("", "7777", 7777)


def test_the_map_and_max_players_are_kept_but_never_a_password_or_address(tmp_path):
    path = str(tmp_path / "game.json")
    GameSettings(max_players=4, host_map="castle.json").save(path)
    again = GameSettings.load(path)
    assert (again.max_players, again.host_map) == (4, "castle.json")
    saved = open(path).read()
    assert "password" not in saved and "address" not in saved


def test_every_home_page_draws(folder):
    home = Home(GameSettings(), str(folder))
    for page in ("home", "settings", "host", "join", "connecting"):
        home.go(page)
        home.draw(pygame.Surface(SIZE, pygame.SRCALPHA), (0, 0), shade=False)
        assert all(home.panel(SIZE).contains(item.rect) for item in home.items(SIZE))


# ------------------------------------------------------------------ hosting and joining for real

@pytest.fixture
def graphics():
    g = main.Graphics()
    g.load(main.ATLAS_PATH)
    return g


def joiner(host, password="pw"):
    return ClientSession(net.Client("127.0.0.1", host.host.port, password), make_world, FIRST_CHARACTER)


def test_a_host_lets_in_only_as_many_players_as_it_allows(folder, graphics):
    host = main.start_host(graphics, str(folder / "castle.json"), "pw", port=0, bind="127.0.0.1", max_players=2)
    first, second = joiner(host), joiner(host)
    try:
        assert host.game.level.width == 14                              # the map picked
        run([host, first], until=lambda: first.ready)
        run([host, second], until=lambda: second.ended)
        assert "full" in second.ended and len(host.game.players) == 2
    finally:
        for s in (first, second, host):
            s.close()


def scripted(home_like, steps):
    """An event source for main.home_screen that plays `steps` (a list of functions of a shadow Home returning
    events), keeping the shadow Home in step so the clicks land where the real one draws its buttons."""
    pending = list(steps)

    def events():
        if not pending:
            return []
        out = pending.pop(0)(home_like)
        for event in out:
            home_like.handle(event, SIZE)
        return out
    return events


def press_label(label):
    def make(home):
        item = next(i for i in home.items(SIZE) if i.action and i.label == label)
        return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=item.rect.center, button=1)]
    return make


def press_box(field):
    def make(home):
        item = next(i for i in home.items(SIZE) if i.action == f"input:{field}")
        return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=item.rect.center, button=1)]
    return make


def typed(text):
    return lambda home: [pygame.event.Event(pygame.KEYDOWN, key=0, mod=0, unicode=c) for c in text] + \
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode="")]


def clear(count):
    return lambda home: [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, mod=0, unicode="")] * count


@pytest.fixture
def screen(monkeypatch, folder):
    monkeypatch.setattr(main, "MAP_PATH", str(folder / "arena.json"))      # the maps the home screen lists
    s = main.Screen("test", SIZE)
    yield s
    s.window.destroy()


def test_the_home_screen_starts_hosting_the_map_picked(screen, folder, graphics, monkeypatch):
    real_start = main.start_host
    monkeypatch.setattr(main, "start_host", lambda g, path, password, max_players: real_start(
        g, path, password, port=0, bind="127.0.0.1", max_players=max_players))
    settings = GameSettings(max_players=3)
    steps = [press_label("Host game"), press_label("dunes"), press_box("host_password"), typed("pw"),
             press_label("Start hosting")]
    started = main.home_screen(screen, pygame.time.Clock(), graphics, settings,
                               events=scripted(Home(GameSettings(max_players=3), str(folder)), steps))
    session, map_path = started
    try:
        assert isinstance(session, HostSession) and map_path == str(folder / "dunes.json")
        assert session.game.level.width == 18 and session.host.max_clients == 2 and session.host.password == "pw"
    finally:
        session.close()


def test_the_home_screen_joins_a_host_and_reports_a_wrong_password(screen, folder, graphics, monkeypatch):
    shown = []

    class Watched(main.Home):                                   # (to see what the real home screen says)
        def __init__(self, *args):
            super().__init__(*args)
            shown.append(self)
    monkeypatch.setattr(main, "Home", Watched)
    host = main.start_host(graphics, str(folder / "castle.json"), "pw", port=0, bind="127.0.0.1")

    def attempt(password, frames):
        """Run the home screen joining with `password`, the host playing along; it gives up after `frames`."""
        steps = [press_label("Join game"), press_box("address"), typed("127.0.0.1"), press_box("port"), clear(4),
                 typed(str(host.host.port)), press_box("join_password"), typed(password), press_label("Join")]
        source, count = scripted(Home(GameSettings(), str(folder)), steps), [0]

        def events():
            host.step(Inputs(), 1 / 60)
            count[0] += 1
            return source() if count[0] < frames else [pygame.event.Event(pygame.QUIT)]
        return main.home_screen(screen, pygame.time.Clock(), graphics, GameSettings(), events=events)

    try:
        assert attempt("nope", 300) is None                     # refused: still on the home screen at the end
        assert shown[-1].page == "join" and "wrong password" in shown[-1].message
        session, map_path = attempt("pw", 600)
        try:
            assert isinstance(session, ClientSession) and session.ready and map_path is None
            assert session.level.width == 14
        finally:
            session.close()
    finally:
        host.close()
