"""King of the Hill: the capture point, the two clocks, capturing, contesting, decay, overtime, respawning, rounds, and
playing it through a host (koth.py, with game.py, session.py and the map's site layer)."""
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
import net
from bomb import site_under
from game import Game, Inputs
from koth import BLU, HILL_TILES, RED, HillView, capture_rate, hill_cells
from mapfile import HILL_SITE, Gun, Level, MapSettings, Spawner, load_level, save_level
from session import ClientSession, HostSession
from test_session import FIRST_CHARACTER, make_world, run
from world import World

DT = 1 / 60
HILL = (10, 6)                          # a cell of the point
AWAY = (5, 2)                           # a cell off it


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


def quick(**rules):
    """Short timers, so a round plays out in a few seconds of game time."""
    base = dict(mode="koth", hill_time=5.0, unlock_time=1.0, capture_time=1.0, capture_bonus=2.0, decay_time=4.0,
                respawn_time=1.0, round_end_time=1.0, win_limit=2)
    base.update(rules)
    return MapSettings(**base)


def hill_level(**rules):
    """A 20 x 12 room: RED spawn points on the left, BLU on the right, the point in the middle around HILL."""
    level = Level.blank(20, 12)
    for y in range(5, 8):
        for x in range(9, 12):
            level.set("site", x, y, HILL_SITE)
    level.spawners = [Spawner(2.5, 6.5, team=RED), Spawner(2.5, 8.5, team=RED),
                      Spawner(17.5, 8.5, team=BLU), Spawner(17.5, 9.5, team=BLU)]
    level.guns = [Gun(name="Pistol")]
    level.settings = quick(**rules)
    return level


def hill_game(players=(0, 1), **rules):
    level = hill_level(**rules)
    game = Game(level, World(level, 32), random.Random(1))
    for pid in players:
        game.add_player(pid)
    return game


def play(game, seconds, inputs=None):
    for _ in range(round(seconds / DT)):
        game.tick(inputs or {}, DT)


def stand(game, pid, cell):
    body = game.players[pid].body
    body.x, body.y = cell[0] + 0.5, cell[1] + 0.5
    body.z, body.vz, body.on_ground = 0.0, 0.0, True


def unlock(game):
    play(game, game.level.settings.unlock_time + DT)
    assert game.round.phase == "live"


def red_and_blu(game):
    red = next(pid for pid, s in game.players.items() if s.team == RED)
    blu = next(pid for pid, s in game.players.items() if s.team == BLU)
    return red, blu


def capture(game, pid):
    """`pid` stands on the point alone until their team owns it."""
    team = game.players[pid].team
    stand(game, pid, HILL)
    for _ in range(round(10 / DT)):
        game.tick({}, DT)
        if game.round.owner == team:
            return
    raise AssertionError("no capture")


# ------------------------------------------------------------------ the settings and the map file

def test_the_defaults_are_team_fortress_2s():
    s = MapSettings()
    assert (s.hill_time, s.unlock_time, s.decay_time, s.win_limit) == (180.0, 30.0, 90.0, 2.0)
    assert s.capture_bonus > 0 and s.has_teams() is False
    assert MapSettings(mode="koth").has_teams()


def test_the_hill_and_the_settings_are_saved_with_the_map(tmp_path):
    level = hill_level(hill_time=120, capture_bonus=15)
    path = tmp_path / "koth.json"
    save_level(str(path), level)
    back = load_level(str(path))
    assert back.settings.mode == "koth" and back.settings.hill_time == 120 and back.settings.capture_bonus == 15
    assert back.get("site", *HILL) == HILL_SITE and len(hill_cells(back)) == 9


def test_settings_from_a_file_are_kept_in_range():
    s = MapSettings.from_dict({"mode": "koth", "hill_time": 1, "capture_time": "x", "win_limit": 500})
    assert s.hill_time == 10.0 and s.capture_time == 10.0 and s.win_limit == 99.0


def test_the_hill_is_not_a_bomb_site():
    game = hill_game()
    stand(game, 0, HILL)
    assert site_under(game.level, game.players[0].body) == 0


def test_more_players_capture_faster_as_in_team_fortress_2():
    assert capture_rate(0, 10) == 0
    assert capture_rate(1, 10) == pytest.approx(0.1)
    assert capture_rate(2, 10) == pytest.approx(0.15)
    assert capture_rate(3, 10) == pytest.approx((1 + 1 / 2 + 1 / 3) / 10)


# ------------------------------------------------------------------ capturing

def test_teams_are_red_and_blu_at_their_own_spawn_points():
    game = hill_game(players=(0, 1, 2, 3))
    assert sorted(s.team for s in game.players.values()) == [RED, RED, BLU, BLU]
    for state in game.players.values():
        assert (state.body.x < 10) == (state.team == RED)


def test_the_point_is_locked_until_the_unlock_time():
    game = hill_game()
    red, _ = red_and_blu(game)
    assert game.round.phase == "setup"
    stand(game, red, HILL)
    play(game, 0.9)
    assert game.round.phase == "setup" and game.round.progress == 0 and game.round.owner == 0
    play(game, 0.2)
    assert game.round.phase == "live" and game.round.progress > 0


def test_one_player_captures_in_the_capture_time_and_only_the_owners_clock_runs():
    game = hill_game()
    red, _ = red_and_blu(game)
    unlock(game)
    stand(game, red, HILL)
    play(game, 0.5)
    assert game.round.capper == RED and game.round.progress == pytest.approx(0.5, abs=0.03)
    play(game, 0.55)
    assert game.round.owner == RED and game.round.progress == 0
    play(game, 1.0)
    assert game.round.clocks[RED] == pytest.approx(4.0, abs=0.1) and game.round.clocks[BLU] == 5.0


def test_a_capture_adds_the_bonus_to_the_capturing_teams_clock_up_to_the_full_time():
    game = hill_game(players=(0, 1))
    red, blu = red_and_blu(game)
    unlock(game)
    capture(game, red)
    assert game.round.clocks[RED] == pytest.approx(5.0, abs=0.05)  # (already full: no more)
    play(game, 2.0)                                                 # RED's clock runs down to about 3
    stand(game, red, AWAY)
    capture(game, blu)
    assert game.round.clocks[BLU] == pytest.approx(5.0, abs=0.05)
    left = game.round.clocks[RED]
    stand(game, blu, AWAY)
    capture(game, red)
    assert game.round.clocks[RED] == pytest.approx(left + 2.0, abs=0.05)
    assert "RED captured the point" in game.round.message


def test_both_teams_on_the_point_contest_it():
    game = hill_game()
    red, blu = red_and_blu(game)
    unlock(game)
    stand(game, red, HILL)
    play(game, 0.5)
    progress = game.round.progress
    stand(game, blu, (HILL[0] + 1, HILL[1]))
    play(game, 1.0)
    assert game.round.contested and game.round.progress == pytest.approx(progress) and game.round.owner == 0


def test_progress_drains_away_with_nobody_on_the_point():
    game = hill_game()
    red, _ = red_and_blu(game)
    unlock(game)
    stand(game, red, HILL)
    play(game, 0.5)
    stand(game, red, AWAY)
    play(game, 1.0)                                                 # decay_time 4: a quarter of a capture a second
    assert game.round.progress == pytest.approx(0.25, abs=0.03)
    play(game, 1.1)
    assert game.round.progress == 0 and game.round.capper == 0


def test_on_a_neutral_point_a_team_first_pushes_back_the_others_progress():
    game = hill_game()
    red, blu = red_and_blu(game)
    unlock(game)
    stand(game, red, HILL)
    play(game, 0.5)
    stand(game, red, AWAY)
    stand(game, blu, HILL)
    play(game, 0.3)
    assert game.round.capper == RED and game.round.progress == pytest.approx(0.2, abs=0.03)
    play(game, 0.3)
    assert game.round.capper == BLU


def test_the_owners_push_the_others_capture_back():
    game = hill_game()
    red, blu = red_and_blu(game)
    unlock(game)
    capture(game, red)
    stand(game, red, AWAY)
    stand(game, blu, HILL)
    play(game, 0.5)
    assert game.round.capper == BLU
    stand(game, blu, AWAY)
    stand(game, red, HILL)
    play(game, 0.6)
    assert game.round.progress == 0 and game.round.owner == RED


# ------------------------------------------------------------------ winning

def test_the_owner_wins_when_its_clock_runs_out_and_a_new_round_starts():
    game = hill_game()
    red, _ = red_and_blu(game)
    unlock(game)
    capture(game, red)
    play(game, 5.1)
    assert game.round.phase == "over" and game.round.winner == RED and game.round.score[RED] == 1
    assert "RED wins the round" in game.round.message
    play(game, 1.1)
    assert game.round.phase == "setup" and game.round.number == 2 and game.round.owner == 0
    assert game.round.clocks == {RED: 5.0, BLU: 5.0}
    assert game.players[red].body.x < 10                            # back at RED's spawn points


def test_the_match_is_won_at_the_win_limit_and_starts_over():
    game = hill_game(win_limit=1)
    red, _ = red_and_blu(game)
    unlock(game)
    capture(game, red)
    play(game, 5.1)
    assert "RED wins the match 1-0" in game.round.message
    play(game, 1.1)
    assert game.round.score == {RED: 0, BLU: 0}


def test_overtime_while_the_other_team_has_progress():
    game = hill_game()
    red, blu = red_and_blu(game)
    unlock(game)
    capture(game, red)
    play(game, 4.8)
    stand(game, red, AWAY)
    stand(game, blu, HILL)
    play(game, 0.5)                                                 # RED's clock runs out with BLU capturing
    assert game.round.phase == "live" and game.round.overtime and game.round.clocks[RED] == 0
    stand(game, blu, AWAY)                                          # BLU leaves: the progress drains six times
    play(game, 0.5)                                                 # faster, and RED wins once it is gone
    assert game.round.phase == "over" and game.round.winner == RED


def test_a_capture_in_overtime_takes_the_point():
    game = hill_game()
    red, blu = red_and_blu(game)
    unlock(game)
    capture(game, red)
    play(game, 4.8)
    stand(game, red, AWAY)
    capture(game, blu)
    assert game.round.phase == "live" and game.round.owner == BLU and not game.round.overtime


def test_the_losers_cannot_shoot_until_the_next_round():
    game = hill_game()
    red, blu = red_and_blu(game)
    unlock(game)
    capture(game, red)
    play(game, 5.1)
    assert game.round.phase == "over"
    assert not game.round.act(blu, Inputs(fire=True, forward=1), DT).fire
    assert game.round.act(blu, Inputs(fire=True, forward=1), DT).forward == 1
    assert game.round.act(red, Inputs(fire=True), DT).fire


# ------------------------------------------------------------------ respawning

def test_a_knocked_out_player_respawns_after_the_respawn_time():
    game = hill_game()
    red, blu = red_and_blu(game)
    unlock(game)
    stand(game, blu, HILL)
    game.hurt(blu, 1000, red)
    assert not game.players[blu].alive and blu not in game.round.view().alive
    assert game.round.view().respawns[blu] == pytest.approx(1.0)
    play(game, 0.5)
    assert not game.players[blu].alive and game.round.on_point()[BLU] == 0
    play(game, 0.6)
    state = game.players[blu]
    assert state.alive and state.body.x > 10 and state.stats.health == state.stats.max_health


def test_a_respawn_time_of_zero_brings_them_straight_back():
    game = hill_game(respawn_time=0)
    red, blu = red_and_blu(game)
    game.hurt(blu, 1000, red)
    assert game.players[blu].alive and game.players[blu].stats.health == game.players[blu].stats.max_health


# ------------------------------------------------------------------ the view and the marker

def test_the_view_goes_through_a_dict():
    game = hill_game()
    red, _ = red_and_blu(game)
    unlock(game)
    stand(game, red, HILL)
    play(game, 0.3)
    view = game.round.view()
    back = HillView.from_dict(view.to_dict(), view.teams)
    assert back.to_dict() == view.to_dict() and back.teams == view.teams and back.spot is not None
    assert HillView.from_dict({"mode": "koth"}) is None


def test_the_marker_floats_over_the_point_in_its_owners_color():
    game = hill_game()
    red, _ = red_and_blu(game)
    (marker,) = game.round.sprites(0.0)
    assert 9 <= marker[0] <= 12 and 5 <= marker[1] <= 8 and marker[4] == HILL_TILES[0]
    unlock(game)
    capture(game, red)
    assert game.round.sprites(0.0)[0][4] == HILL_TILES[RED]
    assert any(s[4] == HILL_TILES[RED] for s in game.sprites(red))


def test_a_map_without_a_point_has_no_marker():
    level = Level.blank(10, 10)
    level.settings = quick()
    game = Game(level, World(level, 32), random.Random(1))
    game.add_player(0)
    assert game.round.sprites(0.0) == [] and game.round.view().spot is None


# ------------------------------------------------------------------ through a host

def test_a_joiner_sees_the_hill_round_and_waits_to_respawn():
    level = hill_level(unlock_time=0.0, respawn_time=2.0)
    host = HostSession(Game(level, World(level, 32), random.Random(1)), net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
    try:
        run([host, client], lambda: client.ready and isinstance(client.round, HillView))
        assert client.round.phase == "live" and client.id in client.round.alive and client.me.team in (RED, BLU)
        assert any(s[4] in HILL_TILES.values() for s in client.sprites())
        host.game.hurt(client.id, 1000, 0)
        run([host, client], lambda: client.id not in client.round.alive)
        assert not client.me.alive and client.round.respawns[client.id] > 0
        x = client.me.body.x
        for _ in range(10):                                         # held still by its own prediction too
            host.step(Inputs(), DT)
            client.step(Inputs(forward=1), DT)
        assert client.me.body.x == pytest.approx(x)
        run([host, client], lambda: client.id in client.round.alive, timeout=4.0)
    finally:
        client.close()
        host.close()


# ------------------------------------------------------------------ the editor

def test_the_sites_layer_paints_the_hill_too(tmp_path):
    ed = map_editor.Editor(str(tmp_path / "m.json"))
    ed.do("layer:site")
    ed.do("dir")
    ed.do("dir")
    assert ed.brush_value() == HILL_SITE
    ed.begin_edit()
    ed.paint_at(3, 3)
    assert ed.level.get("site", 3, 3) == HILL_SITE
    ed.do("dir")
    assert ed.brush_value() == HILL_SITE + 1                        # R goes on from the hill to the barriers


def test_the_map_settings_show_the_hill_settings_only_in_king_of_the_hill(tmp_path):
    ed = map_editor.Editor(str(tmp_path / "m.json"))
    assert "hill_time" not in [f.key for f in ed.rules_fields()]
    ed.level.settings.mode = "koth"
    keys = [f.key for f in ed.rules_fields()]
    assert {"hill_time", "unlock_time", "capture_time", "capture_bonus", "decay_time", "respawn_time",
            "win_limit", "round_end_time"} <= set(keys)
    assert ed.spawn_team_label(RED) == "RED" and ed.buy_team_labels()[BLU] == "BLU only"
