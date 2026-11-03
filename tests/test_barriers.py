"""Barriers (spawn protection): cells of the site layer on the ground floor that let one team's players and bullets
through and stop everyone and everything else (world.World.for_team, with physics, projectiles, game and session)."""
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
import net
from game import Game, Inputs, move_body
from mapfile import BARRIER_SITES, AmmoType, Gun, Level, MapSettings, Spawner, load_level, save_level
from physics import Player
from projectiles import Projectiles
from session import ClientSession, HostSession
from test_session import FIRST_CHARACTER, make_world, run
from world import BARRIER_TILES, World

DT = 1 / 60
WALL_X = 8                              # the barrier is the column of cells at this x
TEAM_1_BARRIER = next(v for v, team in BARRIER_SITES.items() if team == 1)


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


def barrier_level(value=TEAM_1_BARRIER, mode="teams"):
    """A 20 x 12 room cut in two by a barrier at x = WALL_X: team 1's spawn on the left, team 2's on the right."""
    level = Level.blank(20, 12)
    for y in range(1, 11):
        level.set("site", WALL_X, y, value)
    level.spawners = [Spawner(3.5, 5.5, team=1), Spawner(15.5, 5.5, team=2)]
    level.guns = [Gun(name="Pistol", damage=10, spread=0.0)]
    level.settings = MapSettings(mode=mode, start_gun="Pistol")
    return level


def walk(world, x, angle, seconds=3.0):
    """Where a player starting at (x, 5.5), walking along `angle`, gets to."""
    body = Player(x, 5.5, 0.0, angle=angle)
    for _ in range(round(seconds / DT)):
        move_body(world, body, Inputs(forward=1), DT)
    return body.x


def shoot(world, team, x=3.5, angle=0.0):
    """Fire a bullet along `angle` from (x, 5.5); returns where it struck something (None: it flew its range)."""
    bullets = Projectiles(random.Random(1))
    bullets.fire(Player(x, 5.5, 0.0, angle=angle), Gun(spread=0.0), AmmoType(speed=20.0, range=30.0), 0, team)
    for _ in range(200):
        for hit in bullets.update(world, DT):
            return hit.x
    return None


# ------------------------------------------------------------------ the world

def test_a_barrier_is_drawn_as_a_see_through_pane_of_its_team():
    level = barrier_level()
    world = World(level, 64)
    assert world.barrier[5, WALL_X] == 1 and world.pane_tex[5, WALL_X] == BARRIER_TILES[1]
    assert world.span_on[0, 5, WALL_X] and not world.solid[5, WALL_X]       # an open cell, not a wall
    assert World(level, 16).pane_tex[5, WALL_X] == -1                          # (no such tile in the atlas: not drawn)


def test_for_team_shares_the_worlds_arrays():
    world = World(barrier_level(), 64)
    view = world.for_team(1)
    assert view is world.for_team(1) and view.team == 1 and world.team is None
    assert view.barrier is world.barrier and view.floor_plane is world.floor_plane
    assert view.for_team(None) is world.for_team(None)


# ------------------------------------------------------------------ players

def test_only_the_barriers_team_walks_through_it():
    world = World(barrier_level(), 64)
    assert walk(world.for_team(1), 3.5, 0.0) > WALL_X + 1                  # team 1 walks out of its spawn
    assert walk(world.for_team(1), 15.5, 3.14159) < WALL_X                 # ... and back in
    assert walk(world.for_team(2), 15.5, 3.14159) == pytest.approx(WALL_X + 1 + 0.25, abs=0.05)   # team 2 cannot
    assert walk(world.for_team(0), 15.5, 3.14159) > WALL_X + 1             # nor anyone on no team


def test_a_team_2_barrier_lets_team_2_through():
    world = World(barrier_level(value=TEAM_1_BARRIER + 1), 64)
    assert walk(world.for_team(2), 15.5, 3.14159) < WALL_X
    assert walk(world.for_team(1), 3.5, 0.0) < WALL_X


# ------------------------------------------------------------------ bullets and blasts

def test_only_the_barriers_teams_bullets_fly_through_it():
    world = World(barrier_level(), 64)
    assert shoot(world, 1) is None or shoot(world, 1) > WALL_X + 1          # team 1 shoots out of its spawn
    assert WALL_X + 1 <= shoot(world, 2, x=15.5, angle=3.14159) <= WALL_X + 1.2     # team 2 cannot shoot in
    assert shoot(world, None, x=15.5, angle=3.14159) >= WALL_X + 1


def test_blasts_do_not_go_through_a_barrier():
    world = World(barrier_level(), 64)
    assert not world.line_clear((15.5, 5.5, 0.4), (3.5, 5.5, 0.4))
    assert world.for_team(1).line_clear((15.5, 5.5, 0.4), (3.5, 5.5, 0.4))


# ------------------------------------------------------------------ in a game, and through a host

def teams_game():
    level = barrier_level()
    game = Game(level, World(level, 64), random.Random(1))
    for pid in (0, 1):
        game.add_player(pid)
    return game


def test_in_a_game_the_other_team_cannot_get_in_or_shoot_in():
    game = teams_game()
    one = next(pid for pid, s in game.players.items() if s.team == 1)
    two = next(pid for pid, s in game.players.items() if s.team == 2)
    game.players[two].body.angle = 3.14159
    for _ in range(round(3 / DT)):
        game.tick({two: Inputs(forward=1)}, DT)
    assert game.players[two].body.x > WALL_X + 1                          # held outside team 1's spawn
    a, b = game.players[one], game.players[two]
    a.body.x, a.body.angle = 4.5, 0.0
    b.body.x, b.body.angle = WALL_X + 1.6, 3.14159
    game.tick({two: Inputs(fire=True)}, DT)
    play_out = round(1.0 / DT)
    for _ in range(play_out):
        game.tick({}, DT)
    assert a.stats.health == a.stats.max_health                             # the barrier stopped team 2's bullet
    game.tick({one: Inputs(fire=True)}, DT)
    for _ in range(play_out):
        game.tick({}, DT)
    assert b.stats.health < b.stats.max_health                              # team 1's went through it


def test_a_barrier_painted_on_an_upper_floor_does_nothing():
    level = Level.blank(20, 12, floors=2)
    for y in range(1, 11):
        level.set("site2", WALL_X, y, TEAM_1_BARRIER)
    world = World(level, 64)
    assert not world.barrier.any() and walk(world.for_team(2), 15.5, 3.14159) < WALL_X


def test_a_joiner_predicts_the_barrier_too():
    level = barrier_level()
    host = HostSession(Game(level, World(level, 64), random.Random(1)), net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), lambda lvl: World(lvl, 64), FIRST_CHARACTER)
    try:
        run([host, client], lambda: client.ready and client.me.team == 2)
        client.me.body.angle = 3.14159
        for _ in range(round(2 / DT)):
            host.step(Inputs(), DT)
            client.step(Inputs(forward=1), DT)
        assert client.me.body.x > WALL_X + 1
    finally:
        client.close()
        host.close()


# ------------------------------------------------------------------ the map file and the editor

def test_barriers_are_saved_with_the_map(tmp_path):
    path = tmp_path / "b.json"
    save_level(str(path), barrier_level())
    assert load_level(str(path)).get("site", WALL_X, 5) == TEAM_1_BARRIER


def test_the_sites_layer_paints_barriers_on_the_ground_floor_only(tmp_path):
    ed = map_editor.Editor(str(tmp_path / "m.json"))
    ed.do("layer:site")
    while ed.brush_value() != TEAM_1_BARRIER:
        ed.do("dir")
    ed.begin_edit()
    ed.paint_at(3, 3)
    assert ed.level.get("site", 3, 3) == TEAM_1_BARRIER
    ed.do("dir")
    assert ed.brush_value() == TEAM_1_BARRIER + 1
    ed.do("dir")
    assert ed.brush_value() == 1                                           # R goes round A, B, the hill, the barriers
