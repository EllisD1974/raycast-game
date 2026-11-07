"""The respawn delay of free for all, two teams and co-op (respawn.py, with game.py, session.py and the editor)."""
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
from game import Game, Inputs
from mapfile import Level, MapSettings, Spawner, level_text, parse_level
from respawn import RespawnView, Respawns
from session import ClientSession, HostSession, LocalSession
from test_session import FIRST_CHARACTER, make_world, run
from world import World

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


def respawn_level(mode="teams", **rules):
    level = Level.blank(20, 12)
    level.spawners = [Spawner(2.5, 6.5, team=1), Spawner(17.5, 6.5, team=2)]
    level.settings = MapSettings(mode=mode, **rules)
    return level


def respawn_game(players=(0, 1, 2), mode="teams", **rules):
    level = respawn_level(mode, **rules)
    game = Game(level, World(level, 32), random.Random(1))
    for pid in players:
        game.add_player(pid)
    return game


def play(game, seconds, inputs=None):
    for _ in range(round(seconds / DT)):
        game.tick(inputs or {}, DT)


def test_without_a_delay_players_come_straight_back_as_before():
    game = respawn_game()
    assert game.round is None
    game.hurt(1, 1000, 0)
    assert game.players[1].alive and game.players[1].stats.health == 100


def test_with_a_delay_a_knocked_out_player_waits_then_comes_back_at_a_spawn_point():
    game = respawn_game(respawn_delay=3.0)
    assert isinstance(game.round, Respawns)
    state = game.players[1]                                         # team 2
    state.stats.health = 50
    game.hurt(1, 1000, 0)
    assert not state.alive and game.round.view().respawns == {1: 3.0}
    where = (state.body.x, state.body.y)
    game.hurt(1, 10, 0)                                             # (nothing reaches them meanwhile)
    play(game, 1.0, {1: Inputs(forward=1)})                         # held still, can look around
    assert (state.body.x, state.body.y) == where and not state.alive
    assert len(game.labels(0)) == 1                                 # (only player 2 is drawn)
    play(game, 2.1)
    assert state.alive and state.stats.health == 100
    assert (state.body.x, state.body.y) == pytest.approx((17.5, 6.5))   # their team's spawn point


def test_the_setting_is_saved_kept_in_range_and_older_maps_have_none():
    level = respawn_level(respawn_delay=4.0)
    assert parse_level(json.loads(level_text(level)), "test").settings.respawn_delay == 4.0
    assert MapSettings.from_dict({"mode": "teams"}).respawn_delay == 0.0
    assert MapSettings.from_dict({"respawn_delay": 500}).respawn_delay == 60.0
    assert MapSettings.from_dict({"respawn_delay": "x"}).respawn_delay == 0.0


def test_the_view_goes_through_a_message_and_rejects_junk():
    game = respawn_game(respawn_delay=3.0)
    game.hurt(1, 1000, 0)
    view = game.round.view()
    back = RespawnView.from_dict(view.to_dict(), view.teams)
    assert back.alive == view.alive and back.respawns == view.respawns and not back.may_move(1, None, False, None)
    assert RespawnView.from_dict({"alive": "nope"}) is None


def test_the_death_camera_watches_teammates_in_two_teams_and_anyone_in_free_for_all():
    level = respawn_level(respawn_delay=3.0)
    session = LocalSession(Game(level, World(level, 32), random.Random(1)))      # player 0, team 1
    for pid in (1, 2):                                              # 1: team 2, 2: team 1
        session.game.add_player(pid)
    session.game.hurt(0, 1000, 1)
    assert [pid for pid, _body, _name in session.watchable()] == [2]
    level = respawn_level("ffa", respawn_delay=3.0)
    session = LocalSession(Game(level, World(level, 32), random.Random(1)))
    for pid in (1, 2):
        session.game.add_player(pid)
    session.game.hurt(0, 1000, 1)
    assert [pid for pid, _body, _name in session.watchable()] == [1, 2]


def test_a_joiner_waits_to_respawn_and_is_held_still_meanwhile():
    level = respawn_level(respawn_delay=1.0)
    host = HostSession(Game(level, World(level, 32), random.Random(1)), net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
    try:
        run([host, client], lambda: client.ready and isinstance(client.round, RespawnView))
        host.game.hurt(client.id, 1000, 0)
        run([host, client], lambda: not client.me.alive)
        assert client.round.respawns[client.id] > 0
        x = client.me.body.x
        for _ in range(10):
            host.step(Inputs(), DT)
            client.step(Inputs(forward=1), DT)
        assert client.me.body.x == pytest.approx(x)
        run([host, client], lambda: client.me.alive, timeout=4.0)
    finally:
        client.close()
        host.close()


def test_the_map_settings_show_the_respawn_time_and_then_the_death_camera(tmp_path):
    ed = map_editor.Editor(str(tmp_path / "m.json"))
    ed.level.settings.mode = "teams"
    keys = [f.key for f in ed.rules_fields()]
    assert "respawn_delay" in keys and "death_cam" not in keys     # (straight back: nothing to watch)
    ed.set_rule("respawn_delay", 5.0)
    keys = [f.key for f in ed.rules_fields()]
    assert "death_cam" in keys and "death_cam_who" in keys and "respawn 5s" in ed.rules_summary()
    ed.level.settings.mode = "ffa"
    keys = [f.key for f in ed.rules_fields()]
    assert "death_cam" in keys and "death_cam_who" not in keys and "death cam: everyone" in ed.rules_summary()
    ed.level.settings.mode = "koth"
    assert "respawn_delay" not in [f.key for f in ed.rules_fields()]
