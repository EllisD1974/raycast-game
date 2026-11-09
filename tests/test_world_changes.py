"""Cells that change during a game (world.World.close_cells, open_cells, set_blocks, for_enemies): doors that close
a cell for everyone, and cells that stop only players or only enemies (a boarded-up window)."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from constants import MOVE_SPEED
from game import Inputs, move_body
from lighting import LightSystem
from mapfile import AmmoType, Gun, Level
from physics import Player, step
from projectiles import Projectiles
from world import World

DT = 1 / 60
DOOR = [(8, y) for y in range(1, 11)]          # a column of cells across the whole room


def room():
    return World(Level.blank(20, 12), 64)


def walk(world, seconds=3.0):
    """How far east a player starting at (3.5, 5.5) gets."""
    body = Player(3.5, 5.5, 0.0)
    for _ in range(round(seconds / DT)):
        move_body(world, body, Inputs(forward=1), DT)
    return body.x


def shot_lands(world):
    """Where a bullet fired east from (3.5, 5.5) strikes something (the room's far wall is at 19)."""
    bullets = Projectiles(random.Random(1))
    bullets.fire(Player(3.5, 5.5, 0.0), Gun(spread=0.0), AmmoType(speed=20.0, range=30.0), 0)
    for _ in range(200):
        for hit in bullets.update(world, DT):
            return hit.x
    return None


def test_a_closed_cell_stops_walking_bullets_and_sight():
    world = room()
    assert walk(world) > 9.0
    world.close_cells(DOOR, 5)
    assert walk(world) < 8.0
    assert shot_lands(world) < 8.0
    assert not world.line_clear((3.5, 5.5, 0.5), (12.5, 5.5, 0.5))
    assert world.solid[5, 8] and world.wall_tex[5, 8] == 5 and world.is_closed(8, 5)


def test_opening_a_cell_puts_back_what_the_level_made():
    world = room()
    before = {name: getattr(world, name).copy() for name in
              ("solid", "wall_tex", "blocked", "solid_from", "wall_sides", "pane_tex", "light_occluder")}
    world.close_cells(DOOR, 5)
    world.open_cells(DOOR)
    for name, array in before.items():
        assert np.array_equal(getattr(world, name), array), name
    assert walk(world) > 9.0 and not world.is_closed(8, 5)


def test_closing_again_and_opening_twice_do_nothing_more():
    world = room()
    world.close_cells(DOOR, 5)
    world.close_cells(DOOR, 7)                  # (already closed: keeps what it saved the first time)
    world.open_cells(DOOR)
    world.open_cells(DOOR)
    assert not world.solid[5, 8] and walk(world) > 9.0


def test_every_change_counts_a_revision():
    world = room()
    start = int(world.revision[0])
    world.close_cells(DOOR, 5)
    world.open_cells(DOOR)
    world.set_blocks(DOOR, enemies=True)
    assert int(world.revision[0]) == start + 3
    assert world.for_team(1).revision is world.revision and world.for_enemies().revision is world.revision


def test_a_door_casts_a_shadow():
    world = room()
    lights = LightSystem(Level.blank(20, 12), world)
    world.close_cells(DOOR, 5)
    assert lights.occluder[5, 8] == 1
    world.open_cells(DOOR)
    assert lights.occluder[5, 8] == 0


def test_an_enemy_block_stops_enemies_only():
    world = room()
    world.set_blocks(DOOR, enemies=True)
    assert walk(world) > 9.0                    # players go through
    assert walk(world.for_enemies()) < 8.0
    assert shot_lands(world) > 18.0             # and so do bullets


def test_a_player_block_stops_players_only():
    world = room()
    world.set_blocks(DOOR, players=True)
    assert walk(world) < 8.0
    assert walk(world.for_team(1)) < 8.0        # whatever their team
    assert walk(world.for_enemies()) > 9.0
    world.set_blocks(DOOR, players=False)
    assert walk(world) > 9.0


def test_blocks_are_per_floor():
    level = Level.blank(20, 12, floors=2)
    world = World(level, 64)
    world.set_blocks(DOOR, players=True, floor=1)
    assert walk(world) > 9.0                    # (the ground floor is open)


def test_walking_at_a_speed_of_its_own():
    world = room()
    slow, fast = Player(3.5, 5.5, 0.0), Player(3.5, 3.5, 0.0)
    for _ in range(30):
        step(world, slow, 1, 0, 0, False, DT, speed=1.0)
        step(world, fast, 1, 0, 0, False, DT)
    assert math.isclose(slow.x - 3.5, 0.5, abs_tol=1e-6)
    assert math.isclose(fast.x - 3.5, MOVE_SPEED * 0.5, abs_tol=1e-6)
