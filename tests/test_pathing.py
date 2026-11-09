"""Finding the way for enemies (pathing.py): flow fields over every floor, around walls, up ramps and through doors."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapfile import Level
from pathing import DIAGONAL, STRAIGHT, Pathing
from physics import Player, spawn_at, step
from test_world_and_physics import corridor, stacked
from world import World

DT = 1 / 60


def room(width=20, height=12):
    return Level.blank(width, height)


def chase(pathing, body, goal, seconds=20.0, speed=3.0):
    """Walk `body` along the way to `goal` (a body) until it gets there; returns the seconds it took, or None."""
    for tick in range(round(seconds / DT)):
        if math.hypot(goal.x - body.x, goal.y - body.y) < 0.3:
            return tick * DT
        point = pathing.steer(body, goal)
        if point is None:
            return None
        body.angle = math.atan2(point[1] - body.y, point[0] - body.x)
        step(pathing.world, body, 1, 0, 0, False, DT, speed=speed)
    return None


def test_distances_in_an_open_room():
    paths = Pathing(World(room(), 64))
    field = paths.field((0, 10, 5))
    assert field.at(0, 10, 5) == 0
    assert field.at(0, 5, 5) == 5 * STRAIGHT
    assert field.at(0, 7, 2) == 3 * DIAGONAL
    assert not field.reachable(0, 0, 0)         # the border wall


def test_the_way_goes_round_a_wall():
    level = room()
    for y in range(1, 10):
        level.set("walls", 10, y, 1)            # a wall with a gap at the bottom (y = 10)
    paths = Pathing(World(level, 64))
    field = paths.field((0, 15, 2))
    assert field.at(0, 5, 2) > 15 * STRAIGHT    # far more than the 10 cells straight across
    body, goal = Player(5.5, 2.5, 0.0), Player(15.5, 2.5, 0.0)
    assert chase(paths, body, goal) is not None


def test_no_cutting_corners():
    level = room()
    level.set("walls", 6, 5, 1)
    paths = Pathing(World(level, 64))
    paths.refresh()
    out = [to for to, _cost in paths.moves[(0, 5, 5)]]
    assert (0, 6, 4) not in out and (0, 6, 6) not in out        # the diagonals past the wall's corners
    assert (0, 4, 4) in out and (0, 5, 4) in out


def test_a_closed_door_and_an_opened_one():
    level = room()
    for y in range(1, 11):
        level.set("walls", 10, y, 1)
    level.set("walls", 10, 5, 0)                # a doorway at (10, 5)
    world = World(level, 64)
    paths = Pathing(world)
    assert paths.field((0, 15, 5)).reachable(0, 5, 5)
    world.close_cells([(10, 5)], 1)
    assert not paths.field((0, 15, 5)).reachable(0, 5, 5)
    world.open_cells([(10, 5)])
    assert paths.field((0, 15, 5)).reachable(0, 5, 5)


def test_enemy_blocks_stop_the_enemies_way_not_the_players():
    level = room()
    for y in range(1, 11):
        level.set("walls", 10, y, 1)
    level.set("walls", 10, 5, 0)
    world = World(level, 64)
    world.set_blocks([(10, 5)], enemies=True)
    assert not Pathing(world.for_enemies()).field((0, 15, 5)).reachable(0, 5, 5)
    assert Pathing(world).field((0, 15, 5)).reachable(0, 5, 5)
    world.set_blocks([(10, 5)], players=True, enemies=False)
    assert Pathing(world.for_enemies()).field((0, 15, 5)).reachable(0, 5, 5)


def test_up_a_ramp_to_the_floor_above():
    level = stacked()
    world = World(level, 256)
    paths = Pathing(world)
    field = paths.field((1, 13, 1))             # on the upper floor, over the lower one
    assert field.reachable(0, 1, 1)             # from the start, by the ramp
    body = spawn_at(world, 1.5, 1.5, 0, 0.0)
    goal = spawn_at(world, 13.5, 1.5, 1, 0.0)
    assert chase(paths, body, goal) is not None
    assert body.span == 1


def test_down_a_ledge_but_not_back_up():
    level = corridor()
    for x in range(6, 12):
        level.set("floor_h", x, 1, 0.6)         # a ledge twice as high as a step
    paths = Pathing(World(level, 64))
    assert paths.field((0, 3, 1)).reachable(0, 8, 1)        # off the ledge: fine
    assert not paths.field((0, 8, 1)).reachable(0, 3, 1)    # up it: no


def test_too_low_to_fit():
    level = corridor()
    level.set("ceil_h", 5, 1, 0.7)
    assert Pathing(World(level, 64)).field((0, 8, 1)).reachable(0, 3, 1) is False
    assert Pathing(World(level, 64), height=0.5).field((0, 8, 1)).reachable(0, 3, 1)


def test_fields_are_kept_until_the_world_changes():
    world = World(room(), 64)
    paths = Pathing(world)
    first = paths.field((0, 10, 5))
    assert paths.field((0, 10, 5)) is first
    world.set_blocks([(3, 3)], enemies=True)
    assert paths.field((0, 10, 5)) is not first


def test_straight_at_a_target_in_sight():
    paths = Pathing(World(room(), 64))
    body, goal = Player(5.5, 5.5, 0.0), Player(7.2, 6.1, 0.0)
    assert paths.steer(body, goal) == (7.2, 6.1)
