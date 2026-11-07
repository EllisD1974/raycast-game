"""The death camera: who a knocked-out player may watch (the map's settings), the host only sending what that allows,
and what a joiner is shown of the player they watch (game.py, session.py, mapfile.py and the editor)."""
import json
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
import net
from game import Game, next_watch, watchable_ids
from mapfile import CT_TEAM, T_TEAM, MapSettings, level_text, parse_level
from session import ClientSession, HostSession, LocalSession
from test_bomb import bomb_level
from test_session import FIRST_CHARACTER, make_world, run
from world import World


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


# ------------------------------------------------------------------ the rules

def test_teammates_only_by_default_and_the_other_team_after_them_with_all_teams():
    teams = {0: T_TEAM, 1: CT_TEAM, 2: T_TEAM, 3: CT_TEAM, 4: T_TEAM}
    alive = {0, 1, 2, 3}                                            # (4 is out too)
    assert watchable_ids(MapSettings(mode="bomb"), 4, T_TEAM, alive, teams) == [0, 2]
    assert watchable_ids(MapSettings(mode="bomb", death_cam_who="all"), 4, T_TEAM, alive, teams) == [0, 2, 1, 3]
    assert watchable_ids(MapSettings(mode="bomb", death_cam=False), 4, T_TEAM, alive, teams) == []
    assert watchable_ids(MapSettings(mode="bomb"), 4, T_TEAM, {1, 3}, teams) == []     # no teammate left


def test_clicking_goes_round_and_moves_on_when_the_watched_player_is_out():
    assert next_watch([], 3, 1) is None
    assert next_watch([0, 2, 5], None) == 0
    assert next_watch([0, 2, 5], 2, 1) == 5 and next_watch([0, 2, 5], 5, 1) == 0
    assert next_watch([0, 2, 5], 0, -1) == 5
    assert next_watch([0, 5], 2) == 0                               # 2 was knocked out: the first one left


def test_the_settings_are_saved_and_older_maps_get_the_defaults():
    level = bomb_level(death_cam=False, death_cam_who="all")
    back = parse_level(json.loads(level_text(level)), "test")
    assert back.settings.death_cam is False and back.settings.death_cam_who == "all"
    old = MapSettings.from_dict({"mode": "bomb"})
    assert old.death_cam is True and old.death_cam_who == "team"
    assert MapSettings.from_dict({"death_cam_who": "everyone"}).death_cam_who == "team"


def test_the_map_settings_show_the_death_camera_in_bomb_defusal_and_koth(tmp_path):
    ed = map_editor.Editor(str(tmp_path / "m.json"))
    assert "death_cam" not in [f.key for f in ed.rules_fields()]
    for mode in ("bomb", "koth"):
        ed.level.settings.mode = mode
        keys = [f.key for f in ed.rules_fields()]
        assert "death_cam" in keys and "death_cam_who" in keys
    ed.set_rule("death_cam", False)
    assert "death_cam_who" not in [f.key for f in ed.rules_fields()]
    assert "no death cam" in ed.rules_summary()


# ------------------------------------------------------------------ playing alone or hosting

def test_the_local_player_only_watches_teammates():
    level = bomb_level()
    session = LocalSession(Game(level, World(level, 32), random.Random(1)))      # player 0, T
    for pid in (1, 2):                                              # 1: CT, 2: T
        session.game.add_player(pid)
    session.game.hurt(0, 1000, 1)
    assert [pid for pid, _body, _name in session.watchable()] == [2]
    assert session.watched(2) is session.game.players[2]
    session.game.hurt(2, 1000, 1)
    assert session.watchable() == []


# ------------------------------------------------------------------ through a host

def host_and_joiners(level, count):
    host = HostSession(Game(level, World(level, 32), random.Random(1)), net.Host("pw", port=0))
    clients = [ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
               for _ in range(count)]
    run([host] + clients, lambda: all(c.ready and c.round is not None for c in clients))
    return host, clients


def close(host, clients):
    for c in clients:
        c.close()
    host.close()


def test_a_joiner_with_no_teammate_left_is_not_sent_where_the_others_are():
    host, clients = host_and_joiners(bomb_level(), 1)               # host: T, joiner: CT
    client = clients[0]
    try:
        assert client.me.team == CT_TEAM and 0 in client.history
        host.game.hurt(client.id, 1000, 0)
        run([host, client], lambda: client.id not in client.round.alive and 0 not in client.history)
        assert client.watchable() == []
    finally:
        close(host, clients)


def test_with_the_death_camera_off_a_joiner_watches_nobody():
    host, clients = host_and_joiners(bomb_level(death_cam=False, death_cam_who="all"), 1)
    client = clients[0]
    try:
        host.game.hurt(client.id, 1000, 0)
        run([host, client], lambda: client.id not in client.round.alive and 0 not in client.history)
        assert client.watchable() == []
    finally:
        close(host, clients)


def test_a_joiner_watching_a_teammate_gets_their_hud_and_where_they_look():
    host, clients = host_and_joiners(bomb_level(), 2)               # host: T, joiners: CT and T
    teammate = next(c for c in clients if c.me.team == T_TEAM)
    try:
        host.game.players[0].body.pitch = 0.3
        host.game.players[0].stats.health = 42
        host.game.players[0].inventory.give_gun(host.game.level.guns[0])
        host.game.hurt(teammate.id, 1000, 0)
        run([host] + clients, lambda: teammate.id not in teammate.round.alive)
        others = teammate.watchable()
        assert [pid for pid, _body, _name in others] == [0]         # not the other team's joiner
        teammate.watch(0)
        run([host] + clients, lambda: teammate.watched(0) is not None)
        shown = teammate.watched(0)
        assert shown.stats.health == 42 and [g.gun.name for g in shown.inventory.guns] == ["Pistol"]
        run([host] + clients, lambda: teammate.watchable()[0][1].pitch == pytest.approx(0.3))
    finally:
        close(host, clients)


def test_the_host_ignores_a_joiner_asking_to_watch_the_other_team():
    host, clients = host_and_joiners(bomb_level(), 2)
    teammate = next(c for c in clients if c.me.team == T_TEAM)
    opponent = next(c for c in clients if c.me.team == CT_TEAM)
    try:
        host.game.hurt(teammate.id, 1000, 0)
        run([host] + clients, lambda: teammate.id not in teammate.round.alive)
        teammate.watch(opponent.id)                                 # (a modified client)
        run([host] + clients, lambda: host.watching.get(teammate.id) == opponent.id)
        for _ in range(10):
            run([host] + clients, lambda: True)
        assert teammate.watched_state is None
    finally:
        close(host, clients)
