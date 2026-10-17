"""Jumping over a hole in a floor keeps the player's horizontal momentum.

Regression: over a hole in the second floor the player's floor flipped to the one below, whose
ceiling at the far side of the hole is inside the slab being jumped onto. The jump was stopped
dead and the player fell straight down.
"""
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import physics
from mapfile import Level
from test_world_and_physics import slot_over_ramp
from world import World

DT = 1 / 60


def jump(world, x, y, angle, span, z, sprint=False, hold_keys=True, ticks=200):
    """Jump at once, holding forward (or releasing it after takeoff). Returns the final player,
    plus the list of per-tick (vx, vy) while airborne and whether the box always fit."""
    player = physics.Player(x, y, z, angle, span=span)
    air, always_fit = [], True
    for tick in range(ticks):
        forward = 1.0 if (hold_keys or tick == 0) else 0.0
        physics.step(world, player, forward, 0.0, 0.0, tick == 0, DT, sprint)
        if not player.on_ground:
            air.append((player.vx, player.vy, player.y))
        always_fit &= physics.can_stand(world, player.x, player.y, player.z, player.span, player.on_ground)
        if tick > 5 and player.on_ground:
            break
    return player, air, always_fit


# The slot in slot_over_ramp() is row y = 2 (cells y 2-3), x 8-12; floor 2 is solid ground around it.

@pytest.mark.parametrize("sprint", [False, True])
@pytest.mark.parametrize("hold_keys", [True, False])
@pytest.mark.parametrize("x", [9.0, 10.5, 11.9])
def test_jumping_across_a_hole_in_floor_2_lands_on_the_far_side(x, hold_keys, sprint):
    world = World(slot_over_ramp(), 256)
    player, air, fit = jump(world, x, 1.8, math.pi / 2, 1, 1.75, sprint, hold_keys)   # south across the slot
    assert player.on_ground and player.span == 1 and player.z == pytest.approx(1.75, abs=1e-3)
    assert player.y > 3.0, f"fell into the hole instead of crossing it (y={player.y})"
    assert fit


def test_the_horizontal_velocity_survives_the_whole_jump_over_the_hole():
    world = World(slot_over_ramp(), 256)
    far_wall = 4.0 - physics.PLAYER_RADIUS          # the test room ends at y = 4
    for sprint, speed in ((False, physics.MOVE_SPEED), (True, physics.MOVE_SPEED * physics.SPRINT_MULTIPLIER)):
        player, air, _ = jump(world, 10.5, 1.8, math.pi / 2, 1, 1.75, sprint)
        assert len(air) > 20
        # The speed is never lost mid-air, until the far wall of the room is reached.
        assert all(vy == pytest.approx(speed) for _vx, vy, y in air if y < far_wall - 0.2)


@pytest.mark.parametrize("x", [9.0, 10.5, 11.9])
def test_and_back_across_in_the_other_direction(x):
    world = World(slot_over_ramp(), 256)
    player, _air, fit = jump(world, x, 3.2, -math.pi / 2, 1, 1.75)           # north across the slot
    assert player.on_ground and player.span == 1 and player.y < 2.0 and fit


def test_a_hole_too_wide_to_jump_still_swallows_the_player():
    level = slot_over_ramp()
    for y in (2, 3):                                           # widen the hole to two cells
        for x in range(8, 13):
            level.set("floor_h2", x, y, 0.0)
            level.set("ceil_h2", x, y, 0.0)
            level.set("ceil_h", x, y, 4.0)
    world = World(level, 256)
    player, _air, _fit = jump(world, 10.5, 1.8, math.pi / 2, 1, 1.75)
    assert player.on_ground and player.span == 0 and player.z < 1.75 and player.y < 4.0


def test_jumping_over_a_pit_in_a_single_floor_still_works():
    level = Level.blank(20, 5)
    for y in range(1, 4):
        for x in range(1, 19):
            level.set("ceil_h", x, y, 4.0)
        level.set("floor_h", 8, y, -2.0)                       # a one-cell-wide pit across the room
    world = World(level, 256)
    player, _air, fit = jump(world, 7.8, 2.5, 0.0, 0, 0.0)
    assert player.on_ground and player.z == 0.0 and player.x > 9.0 and fit


def test_the_player_is_not_pushed_into_the_slab_while_jumping_along_the_hole():
    """Jumping lengthwise down the slot must still be blocked by its side walls, not pass through."""
    world = World(slot_over_ramp(), 256)
    player = physics.Player(8.5, 2.5, 1.75, 0.0, span=1)       # on the slot's edge cell, heading east
    for tick in range(120):
        physics.step(world, player, 1.0, 0.0, 0.0, tick == 0, DT)
        assert physics.can_stand(world, player.x, player.y, player.z, player.span, player.on_ground)


# ------------------------------------------------------------------ which floor a point is on, in the air

def test_in_the_air_a_point_belongs_to_the_floor_whose_room_holds_the_feet():
    world = World(slot_over_ramp(), 256)
    over_slab = (10.5, 3.5)                                      # floor 2 here, with floor 1 (ceiling 1.5) below
    over_hole = (10.5, 2.5)                                      # the hole: only floor 1
    # Feet at 1.9: inside floor 2's room, above floor 1's whole room.
    assert world.span_at(*over_slab, 1.9, current=0, grounded=False) == 1
    assert world.span_at(*over_slab, 1.9, current=1, grounded=False) == 1
    assert world.span_at(*over_hole, 1.9, current=1, grounded=False) == 0
    # Down on the ground floor, the floor below stays the floor.
    assert world.span_at(*over_slab, 0.2, current=0, grounded=False) == 0
    # Grounded behaviour is unchanged: keep your own floor while it is still there.
    assert world.span_at(*over_slab, 1.75, current=1, grounded=True) == 1
