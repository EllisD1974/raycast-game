import json
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import physics
from atlas import atlas_array, unpack_atlas
from constants import FOG_DIST, HEIGHT, MAX_DEPTH, WIDTH
from main import Renderer
from mapfile import DEFAULTS, FORMAT_VERSION, Level, default_level, load_level, save_level
from raykernel import render_scene
from world import World


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


def corridor(width=12, floors=1):
    """Enclosed 1-cell-wide corridor along y = 1, tall enough (ceiling 3) for stairs."""
    level = Level.blank(width, 3, floors=floors)
    for x in range(1, width - 1):
        level.set("walls", x, 1, 0)
        level.set("ceil_h", x, 1, 3.0)
    level.start_x, level.start_y = 1.5, 1.5
    return level


def stacked():
    """Corridor with a ramp up to a second floor that lies directly above a lower floor.

    x 3-8: ramp rising east; x 9: lower span raised to 1.5 (top of the ramp);
    x 10-16: lower floor (ceiling 1.2) with an upper floor (1.5 to 3.0) over it;
    x 17-22: lower floor only (the upper floor ends, so you can step off it).
    """
    level = corridor(24, floors=2)
    for x in range(3, 9):
        level.set("ramp", x, 1, 1)
    level.set("floor_h", 9, 1, 1.5)
    for x in range(10, 17):
        level.set("ceil_h", x, 1, 1.2)
        level.set("floor_h2", x, 1, 1.5)
        level.set("ceil_h2", x, 1, 3.0)
    return level


def run(level, until, max_ticks=900):
    """Walk forward until `until(player)` is true; returns (world, player)."""
    world = World(level, 256)
    player = physics.spawn(level, world)
    for _ in range(max_ticks):
        if until(player):
            break
        physics.step(world, player, 1.0, 0.0, 0.0, False, 1 / 60)
    return world, player


def walk(level, ticks=240):
    return run(level, lambda p: False, ticks)


# ------------------------------------------------------------------ map file and checks

def test_save_load_roundtrip_all_layers(tmp_path):
    level = stacked()
    level.set("floor_tex", 4, 1, 3)
    level.set("floor_tex2", 11, 1, 2)
    level.start_span = 1
    level.start_x = 12.5
    path = str(tmp_path / "m.json")
    save_level(path, level)
    again = load_level(path)
    assert again.grids == level.grids
    assert (again.start_x, again.start_y, again.start_span) == (12.5, 1.5, 1)
    assert json.load(open(path))["version"] == FORMAT_VERSION


def test_older_files_still_load(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"version": 1, "cells": [[1, 1, 1], [1, 0, 1], [1, 1, 1]],
                                "start": {"x": 1.5, "y": 1.5, "angle": 0}}))
    level = load_level(str(path))
    assert level.walls == [[1, 1, 1], [1, 0, 1], [1, 1, 1]]
    assert level.grids["ceil_h"][1][1] == DEFAULTS["ceil_h"]
    assert not level.span_present(1, 1, 1) and level.start_span == 0
    assert level.problems() == []


def test_resize_and_fill_use_layer_defaults():
    level = Level.blank(6, 6, floors=2)
    assert level.flood_fill("floor_h", 2, 2, 0.5) == 36
    level.resize(8, 4)
    assert (level.width, level.height) == (8, 4)
    assert level.grids["floor_h"][1][7] == DEFAULTS["floor_h"]
    assert level.grids["ceil_h2"][3][7] == DEFAULTS["ceil_h2"]
    assert level.grids["floor_h"][1][1] == 0.5


def test_problems():
    level = default_level()
    assert level.problems() == []
    level.set("walls", 1, 4, 2)
    assert "inside a wall" in level.problems()[0]
    level.set("walls", 1, 4, 0)
    level.set("ceil_h", 1, 4, 0.5)                           # lower than the player
    assert "too low" in level.problems()[0]
    level.set("ceil_h", 1, 4, 1.0)
    level.set("ramp", 5, 3, 1)                               # (4,3) and (6,3) are open: a valid ramp
    assert level.problems() == []
    level.set("ramp", 3, 3, 1)                               # run now starts next to the wall at (2,3)
    assert "ramp" in level.problems()[0]


def test_stacked_level_is_valid_and_overlap_is_a_problem():
    level = stacked()
    assert level.problems() == []
    level.set("floor_h2", 12, 1, 1.0)                        # upper floor below the lower ceiling 1.2
    assert "is below the ceiling of" in level.problems()[0]


def test_start_on_a_floor_that_does_not_exist_is_a_problem():
    level = stacked()
    level.start_span = 1
    level.start_x = 1.5                                      # no upper floor at x = 1
    assert "no floor" in level.problems()[0]


def test_ramp_without_open_ends_is_a_problem():
    level = corridor()
    level.set("ramp", 1, 1, 1)                               # run starts at x=1: the cell before is a wall
    assert any("ramp" in p for p in level.problems())


def test_ramp_planes_are_continuous():
    level = corridor()
    for x in range(3, 7):                                    # 4-cell ramp rising east
        level.set("ramp", x, 1, 1)
    for x in range(7, 11):
        level.set("floor_h", x, 1, 1.0)
    world = World(level, 256)
    assert world.floor_of(0, 3.0, 1.5) == pytest.approx(0.0, abs=1e-5)
    assert world.floor_of(0, 5.0, 1.5) == pytest.approx(0.5, abs=1e-5)
    assert world.floor_of(0, 6.999, 1.5) == pytest.approx(1.0, abs=1e-3)
    assert world.floor_z(5.0, 1.5) == float("inf")          # too high to step onto from z = 0
    assert world.floor_z(5.0, 1.5, z=0.4) == pytest.approx(0.5, abs=1e-5)


# ------------------------------------------------------------------ single floor physics

def test_walk_up_stairs():
    level = corridor()
    for i, x in enumerate(range(3, 7)):
        level.set("floor_h", x, 1, 0.25 * (i + 1))           # 0.25 steps up to 1.0
    for x in range(7, 11):
        level.set("floor_h", x, 1, 1.0)
    _, player = walk(level)
    assert player.on_ground and player.z == pytest.approx(1.0, abs=1e-3)


def test_walk_up_a_ramp():
    level = corridor(14)
    for x in range(3, 7):
        level.set("ramp", x, 1, 1)
    for x in range(7, 13):
        level.set("floor_h", x, 1, 1.0)
    _, player = walk(level, ticks=300)
    assert player.on_ground and player.z == pytest.approx(1.0, abs=1e-3)


def test_ledge_taller_than_a_step_blocks():
    level = corridor()
    level.set("floor_h", 4, 1, 0.5)                          # 0.5 > STEP_HEIGHT 0.3
    _, player = walk(level)
    assert player.x < 4.0 and player.z == 0.0


def test_low_ceiling_blocks():
    level = corridor()
    level.set("ceil_h", 5, 1, 0.7)                           # player is 0.8 tall
    _, player = walk(level)
    assert player.x < 5.0


def test_jump_and_land():
    level = corridor()
    world = World(level, 256)
    player = physics.spawn(level, world)
    physics.step(world, player, 0, 0, 0, True, 1 / 60)
    assert not player.on_ground and player.z > 0
    for _ in range(120):
        physics.step(world, player, 0, 0, 0, False, 1 / 60)
    assert player.on_ground and player.z == 0.0


def test_walk_off_a_ledge_falls():
    level = corridor()
    for x in range(1, 5):
        level.set("floor_h", x, 1, 1.0)                      # start on a 1.0 platform
    _, player = walk(level)
    assert player.on_ground and player.z == 0.0 and player.x > 5.0


# ------------------------------------------------------------------ a floor above a floor

def test_ramp_leads_up_onto_the_floor_above():
    world, player = run(stacked(), lambda p: p.x > 13.0)
    assert player.on_ground and player.z == pytest.approx(1.5, abs=1e-3)
    assert world.span_at(player.x, player.y, player.z) == 1       # standing on the upper floor


def test_walking_under_the_upper_floor_stays_on_the_lower_floor():
    level = stacked()
    level.start_x, level.start_angle = 20.5, math.pi              # lower floor, facing west
    world, player = run(level, lambda p: p.x < 11.0)
    assert 10.0 < player.x < 11.0
    assert player.on_ground and player.z == 0.0
    assert world.span_at(player.x, player.y, player.z) == 0       # beneath the slab, not on it


def test_cannot_walk_from_the_lower_floor_up_onto_the_slab():
    level = stacked()
    level.start_x, level.start_angle = 20.5, math.pi
    _, player = run(level, lambda p: False, 600)                  # keep walking west into the ramp top
    assert player.z == 0.0 and player.x >= 10.0                   # the 1.5 ledge at x = 9 blocks us


def test_walking_off_the_end_of_the_upper_floor_falls_to_the_lower_floor():
    level = stacked()
    level.start_span, level.start_x = 1, 15.5
    world = World(level, 256)
    player = physics.spawn(level, world)
    assert player.z == pytest.approx(1.5)
    for _ in range(240):
        physics.step(world, player, 1.0, 0.0, 0.0, False, 1 / 60)
    assert player.x > 17.0 and player.on_ground and player.z == 0.0


def test_jumping_cannot_pierce_the_slab():
    level = stacked()
    level.start_x = 13.5                                          # lower floor under the slab
    world = World(level, 256)
    player = physics.spawn(level, world)
    assert player.z == 0.0
    top = 0.0
    for i in range(200):
        physics.step(world, player, 0, 0, 0, i % 30 == 0, 1 / 60)
        top = max(top, player.z)
    assert top <= 1.2 - 0.8 + 1e-6 and world.span_at(player.x, player.y, player.z) == 0


# ------------------------------------------------------------------ renderer

def draw(world, renderer, x, angle, z=None, span=None):
    sentinel = np.array((255, 0, 255), np.uint8)
    fb = np.zeros((WIDTH, HEIGHT, 3), np.uint8)
    fb[:] = sentinel
    z = world.floor_of(0, x, 1.5) if z is None else z      # default: standing on the lower floor
    player = physics.Player(x, 1.5, z, angle)
    if span is None:
        span = max(0, world.span_at(player.x, player.y, player.z))
    render_scene(fb, player.x, player.y, player.eye_z, span, np.cos(angle), np.sin(angle),
                 -np.sin(angle) * renderer.half_fov_tan, np.cos(angle) * renderer.half_fov_tan,
                 HEIGHT / 2, renderer.focal, world.floor_plane, world.ceil_plane, world.span_on,
                 world.solid_from, world.pane_tex, world.pane_top, world.wall_tex, world.floor_tex, world.ceil_tex, renderer.textures,
                 MAX_DEPTH, FOG_DIST, sentinel)
    return fb, sentinel


@pytest.fixture(scope="module")
def renderer():
    return Renderer(atlas_array(unpack_atlas()))


def test_renderer_draws_every_pixel_with_stairs_ramps_and_height_changes(renderer):
    level = corridor()
    for x in range(3, 6):
        level.set("ramp", x, 1, 1)
    for x in range(6, 9):
        level.set("floor_h", x, 1, 0.75)
    level.set("ceil_h", 9, 1, 1.5)
    world = World(level, 6)
    for x, angle in ((1.5, 0.0), (4.5, 0.0), (8.5, 3.14159), (7.0, 0.3)):
        fb, sentinel = draw(world, renderer, x, angle)
        assert not (fb == sentinel).all(axis=2).any(), f"unfilled pixels from x={x}, angle={angle}"


@pytest.mark.parametrize("x, angle, z", [
    (1.5, 0.0, 0.0),            # start of the ramp, looking along it
    (6.0, 0.0, None),           # halfway up the ramp
    (13.5, 0.0, 0.0),           # under the slab looking east (slab underside, then open ground)
    (13.5, math.pi, 0.0),       # under the slab looking west (blocked by the ramp top)
    (12.5, 0.0, 1.5),           # on top of the slab looking east: the upper floor ends ahead
    (15.5, math.pi, 1.5),       # on the slab looking back toward the ramp
    (20.5, math.pi, 0.0),       # on open ground looking at the slab's end face
])
def test_renderer_draws_every_pixel_with_a_floor_above_a_floor(renderer, x, angle, z):
    world = World(stacked(), 256)
    fb, sentinel = draw(world, renderer, x, angle, z=z)
    assert not (fb == sentinel).all(axis=2).any()


def test_the_upper_floor_changes_what_you_see(renderer):
    with_upper = World(stacked(), 256)
    flat = stacked()
    for x in range(10, 17):
        flat.set("ceil_h", x, 1, 3.0)
        flat.set("ceil_h2", x, 1, 0.0)
        flat.set("floor_h2", x, 1, 0.0)
    without_upper = World(flat, 256)
    a, _ = draw(with_upper, renderer, 20.5, math.pi, z=0.0)
    b, _ = draw(without_upper, renderer, 20.5, math.pi, z=0.0)
    assert not np.array_equal(a, b)


# ------------------------------------------------------------------ any number of named floors

def test_floors_can_be_added_renamed_and_removed():
    level = Level.blank(8, 6)
    assert level.floor_count == 1 and level.names == ["Floor 1"]
    assert level.add_floor() == 1 and level.add_floor("Roof") == 2
    assert level.names == ["Floor 1", "Floor 2", "Roof"]
    assert set(level.grids) >= {"floor_h2", "ceil_h3", "ramp3", "floor_tex3"}
    assert level.rename_floor(1, "Mezzanine") == "Mezzanine"
    assert level.rename_floor(1, "Roof") == "Roof 2"             # names stay unique
    assert level.rename_floor(1, "   ") == "Roof 2"              # an empty name changes nothing
    assert level.rename_floor(0, "x" * 80) == "x" * 24           # long names are trimmed

    level.set("floor_h3", 2, 2, 5.0)
    level.set("ceil_h2", 3, 3, 2.0)
    level.start_span = 2
    level.remove_floor(1)                                        # the Roof moves down to index 1
    assert level.names == ["x" * 24, "Roof"] and level.floor_count == 2
    assert level.grids["floor_h2"][2][2] == 5.0 and "floor_h3" not in level.grids
    assert level.grids["ceil_h2"][3][3] == 0.0                   # the removed floor's data is gone
    assert level.start_span == 1                                 # still on the Roof
    with pytest.raises(ValueError):
        level.remove_floor(0)                                    # the ground floor stays


def test_removing_the_floor_you_start_on_moves_the_start_to_the_ground():
    level = Level.blank(8, 6, floors=3)
    level.start_span = 1
    level.remove_floor(1)
    assert level.start_span == 0


def test_floor_names_and_all_floors_survive_save_and_load(tmp_path):
    level = Level.blank(8, 6, floors=4)
    level.rename_floor(0, "Ground")
    level.rename_floor(2, "Attic")
    level.set("floor_h4", 3, 3, 4.5)
    level.set("ceil_h4", 3, 3, 6.0)
    path = str(tmp_path / "m.json")
    save_level(path, level)
    again = load_level(path)
    assert again.names == ["Ground", "Floor 2", "Attic", "Floor 4"]
    assert again.grids == level.grids and again.span_present(3, 3, 3)


def test_files_from_before_named_floors_still_load(tmp_path):
    level = Level.blank(6, 5, floors=2)
    path = str(tmp_path / "v3.json")
    save_level(path, level)
    data = json.load(open(path))
    del data["floors"]                                           # what a version 3 file looks like
    data["version"] = 3
    json.dump(data, open(path, "w"))
    again = load_level(path)
    assert again.names == ["Floor 1", "Floor 2"] and again.floor_count == 2


def three_floors():
    """Corridor that climbs by ramp to a second floor, then by a second ramp to a third floor.

    x 3-8: ramp; x 9: ground raised to 1.5; x 10: floor 2 room; x 11-13: ramp on floor 2;
    x 14: floor 2 raised to 3.0; x 15-20: floor 3 room. Floor 1 runs underneath everything.
    """
    level = corridor(24, floors=3)
    for x in range(3, 9):
        level.set("ramp", x, 1, 1)
    level.set("floor_h", 9, 1, 1.5)
    for x in range(10, 21):
        level.set("ceil_h", x, 1, 1.25)                          # ground floor under the others
    for x in range(10, 15):
        level.set("floor_h2", x, 1, 1.5)
        level.set("ceil_h2", x, 1, 4.5)
    for x in range(11, 14):
        level.set("ramp2", x, 1, 1)
    level.set("floor_h2", 14, 1, 3.0)
    for x in range(15, 21):
        level.set("floor_h3", x, 1, 3.0)
        level.set("ceil_h3", x, 1, 4.5)
    return level


def test_three_floor_level_is_valid():
    assert three_floors().problems() == []


def test_a_floor_below_the_one_under_it_is_reported_by_name():
    level = three_floors()
    level.rename_floor(2, "Attic")
    level.set("floor_h3", 17, 1, 1.0)                            # attic floor under the ground ceiling
    assert any("Attic floor is below the ceiling of" in p for p in level.problems())


def test_climbing_ramps_up_through_three_floors():
    level = three_floors()
    world, player = run(level, lambda p: p.x > 17.0)
    assert player.on_ground and player.z == pytest.approx(3.0, abs=1e-3)
    assert world.span_at(player.x, player.y, player.z) == 2      # on the third floor


def test_walking_under_three_stacked_floors_stays_on_the_ground_floor():
    level = three_floors()
    level.start_x, level.start_angle = 20.5, math.pi
    world = World(level, 256)
    player = physics.spawn(level, world)                         # span 0: the ground floor
    for _ in range(300):
        physics.step(world, player, 1.0, 0.0, 0.0, False, 1 / 60)
    assert 10.0 < player.x < 11.0 and player.z == 0.0
    assert world.span_at(player.x, player.y, player.z) == 0


@pytest.mark.parametrize("x, angle, z", [
    (1.5, 0.0, 0.0),            # the first ramp
    (12.0, 0.0, 1.5 + 0.25),    # on the second ramp, heading for the third floor
    (17.5, 0.0, 3.0),           # on the third floor
    (17.5, math.pi, 3.0),       # on the third floor looking back at the ramp
    (13.5, 0.0, 0.0),           # on the ground floor beneath two floors
    (22.5, math.pi, 0.0),       # outside, facing the tower's end face of three slabs
])
def test_renderer_draws_every_pixel_with_three_floors(renderer, x, angle, z):
    world = World(three_floors(), 256)
    assert world.floors == 3
    fb, sentinel = draw(world, renderer, x, angle, z=z)
    assert not (fb == sentinel).all(axis=2).any()


# ------------------------------------------------------------------ a ramp under another floor's room

def overlapping_ramp():
    """A ramp whose cells also have a room of the floor above, overlapping it in height.

    That is invalid (the editor warns), but it is easy to make by accident: the upper floor's
    floor (1.75) is inside the lower room (ceiling 4.0) above the ramp, which climbs from 0 to 1.75.
    """
    level = corridor(24, floors=2)
    for x in range(11, 17):
        level.set("ramp", x, 1, 1)
    level.set("floor_h", 17, 1, 1.75)                            # the top of the ramp, flush with floor 2
    for x in range(10, 13):
        level.set("ceil_h", x, 1, 1.5)
    for x in range(13, 18):
        level.set("ceil_h", x, 1, 4.0)                           # headroom above the ramp: overlaps floor 2
    for x in range(18, 23):
        level.set("ceil_h", x, 1, 1.5)                           # normal ground floor under floor 2
    for x in range(10, 23):
        level.set("floor_h2", x, 1, 1.75)
        level.set("ceil_h2", x, 1, 4.0)
    return level


def test_the_overlapping_ramp_is_reported_and_its_cells_are_marked():
    level = overlapping_ramp()
    assert any("Floor 2 floor is below the ceiling of Floor 1" in p for p in level.problems())
    cells = level.problem_cells()
    assert {(13, 1), (16, 1), (17, 1)} <= cells and (2, 1) not in cells


def test_walking_down_a_ramp_that_has_another_floor_overhead():
    level = overlapping_ramp()
    world = World(level, 256)
    player = physics.Player(17.5, 1.5, 1.75, math.pi, span=0)    # at the top, on the lower floor
    seen = []
    for _ in range(200):
        physics.step(world, player, 1.0, 0.0, 0.0, False, 1 / 60)
        seen.append((player.x, player.z))
    assert player.span == 0 and player.on_ground
    assert player.z == pytest.approx(0.0, abs=1e-3)              # it reaches the bottom
    for x, z in seen:                                            # and follows the ramp the whole way down
        if 11.0 < x < 16.9:
            assert z == pytest.approx(world.floor_of(0, x, 1.5), abs=0.02)


def test_walking_up_that_ramp_and_onto_the_upper_floor():
    level = overlapping_ramp()
    level.start_x = 10.5                                         # at the bottom of the ramp
    world = World(level, 256)
    player = physics.spawn(level, world)
    for _ in range(400):
        physics.step(world, player, 1.0, 0.0, 0.0, False, 1 / 60)
        if player.x > 19.0:
            break
    assert player.x > 19.0 and player.z == pytest.approx(1.75, abs=1e-3)
    assert player.span == 1                                      # stepped onto the upper floor at the top


def test_a_player_keeps_their_own_floor_when_another_floor_is_within_a_step():
    world = World(overlapping_ramp(), 256)
    x, y = 16.5, 1.5                                             # ramp floor is ~1.60, upper floor 1.75
    ramp_z = world.floor_of(0, x, y)
    assert 0 < 1.75 - ramp_z < 0.3                               # the upper floor is within a step
    assert world.span_at(x, y, ramp_z, current=0) == 0           # on the ramp: stay on it
    assert world.span_at(x, y, 1.75, current=1) == 1             # on the upper floor: stay on it
    assert world.span_at(x, y, ramp_z) == 1                      # no current floor: highest reachable


# ------------------------------------------------------------------ falling off the second floor onto a ramp

def slot_over_ramp():
    """A slot cut through the second floor above a ramp (the layout that got a player stuck).

    Row y = 2: ramp x 6-11 rising east to a raised ground cell at x = 12. Floor 2 (1.75 to 4.0)
    covers everything except the slot x 8-12 of that row, so walking off its edge drops you onto
    the ramp. Where Floor 2 remains over the ramp's low end (x 6-7) the ground ceiling is 1.5.
    """
    level = Level.blank(20, 5, floors=2)
    for y in range(1, 4):
        for x in range(1, 19):
            level.set("ceil_h", x, y, 1.5)
            level.set("floor_h2", x, y, 1.75)
            level.set("ceil_h2", x, y, 4.0)
    for x in range(6, 12):
        level.set("ramp", x, 2, 1)
    level.set("floor_h", 12, 2, 1.75)
    for x in range(8, 13):
        level.set("ceil_h", x, 2, 4.0)
        level.set("floor_h2", x, 2, 0.0)                         # the slot: no room on floor 2
        level.set("ceil_h2", x, 2, 0.0)
    level.start_x, level.start_y = 3.5, 2.5
    return level


def test_the_slot_layout_is_valid():
    assert slot_over_ramp().problems() == []


@pytest.mark.parametrize("name, x, y, angle", [
    ("north edge, heading south", 10.5, 1.5, math.pi / 2),
    ("south edge, heading north", 10.5, 3.5, -math.pi / 2),
    ("west end, heading east", 7.5, 2.5, 0.0),
])
def test_walking_off_the_second_floor_onto_the_ramp_never_leaves_the_player_stuck(name, x, y, angle):
    world = World(slot_over_ramp(), 256)
    for walk_ticks in range(0, 60, 2):                           # many timings, to hit every edge position
        player = physics.Player(x, y, 1.75, angle, span=1)
        for tick in range(240):
            forward = 1.0 if tick < walk_ticks else 0.0          # walk, then stand still and fall
            physics.step(world, player, forward, 0.0, 0.0, False, 1 / 60)
            assert physics.can_stand(world, player.x, player.y, player.z, player.span, player.on_ground), \
                f"{name}: box inside the geometry after {walk_ticks} ticks walking, tick {tick}: {player}"
        assert player.on_ground, f"{name}: still in the air after {walk_ticks} ticks walking"
        floor, ceiling = world.floor_of(player.span, player.x, player.y), world.ceil_of(player.span, player.x, player.y)
        assert player.z == pytest.approx(floor, abs=1e-3) or player.z == pytest.approx(1.75, abs=1e-3), \
            f"{name}: floating at {player.z}, floor {floor}"   # on the ramp, or still up on the ledge
        assert player.z + 0.8 <= ceiling + 1e-6


def test_a_player_hanging_half_over_the_ledge_stays_up_until_fully_off_it():
    world = World(slot_over_ramp(), 256)
    player = physics.Player(10.5, 1.5, 1.75, math.pi / 2, span=1)
    seen_held = False
    for _ in range(40):
        physics.step(world, player, 1.0, 0.0, 0.0, False, 1 / 60)
        if player.y > 2.0 and player.z == pytest.approx(1.75, abs=1e-6):
            seen_held = True                                     # center is over the slot, body still on the ledge
            assert player.y < 2.0 + 0.2 + 0.01                   # ... but never further than the half-width of the box
    assert seen_held and player.z < 1.75                         # and it did fall once fully off


def test_a_player_standing_exactly_at_the_edge_does_not_hang_in_the_air():
    world = World(slot_over_ramp(), 256)
    player = physics.Player(10.5, 2.0 + physics.PLAYER_RADIUS, 1.75, math.pi / 2, span=1)  # box edge on the ledge edge
    for _ in range(60):
        physics.step(world, player, 0.0, 0.0, 0.0, False, 1 / 60)
    assert player.z < 1.75 and player.on_ground                  # it dropped to the ramp


def test_the_ramp_still_works_both_ways_after_falling_onto_it():
    world = World(slot_over_ramp(), 256)
    player = physics.Player(10.5, 1.5, 1.75, math.pi / 2, span=1)
    for _ in range(60):
        physics.step(world, player, 1.0 if player.y < 2.5 else 0.0, 0.0, 0.0, False, 1 / 60)
    assert player.span == 0 and player.on_ground and player.z > 0.9      # landed on the ramp
    player.angle = math.pi                                       # walk down it, west
    for _ in range(200):
        physics.step(world, player, 1.0, 0.0, 0.0, False, 1 / 60)
    assert player.z == pytest.approx(0.0, abs=1e-3)


# ------------------------------------------------------------------ horizontal momentum

def platform_level():
    """Open ground (ceiling 4) with a 1.0 high platform on x 2-5 to walk off of."""
    level = Level.blank(24, 7)
    for y in range(1, 6):
        for x in range(1, 23):
            level.set("ceil_h", x, y, 4.0)
    for y in range(1, 6):
        for x in range(2, 6):
            level.set("floor_h", x, y, 1.0)
    return level


def platform_world():
    return World(platform_level(), 256)


def drop_off_platform(release_after_leaving, jump=False):
    """Walk east along the platform and off its end; returns (x where the feet left, final player)."""
    world = platform_world()
    player = physics.Player(3.0, 3.5, 1.0, 0.0, span=0)
    left_at, released = None, False
    for _ in range(240):
        was_grounded = player.on_ground
        forward = 0.0 if (released and release_after_leaving) else 1.0
        physics.step(world, player, forward, 0.0, 0.0, jump and was_grounded and player.x > 3.0 and left_at is None, 1 / 60)
        if was_grounded and not player.on_ground and left_at is None:
            left_at, released = player.x, True
    return left_at, player


def test_walking_off_a_ledge_keeps_the_horizontal_speed_even_if_you_let_go():
    left_at, held = drop_off_platform(release_after_leaving=False)
    _, released = drop_off_platform(release_after_leaving=True)
    assert left_at is not None and left_at > 5.0
    assert held.on_ground and released.on_ground and released.z == 0.0
    # Letting go of the keys in the air changes nothing: the momentum carries the player on.
    assert released.x > left_at + 0.5


def test_the_fall_is_an_arc_not_a_drop_straight_down():
    world = platform_world()
    player = physics.Player(4.0, 3.5, 1.0, 0.0, span=0)
    xs, in_air = [], False
    for _ in range(120):
        physics.step(world, player, 1.0 if player.on_ground else 0.0, 0.0, 0.0, False, 1 / 60)
        if not player.on_ground:
            in_air = True
            xs.append(player.x)
    assert in_air and len(xs) >= 5
    assert all(b > a for a, b in zip(xs, xs[1:]))                # keeps moving every tick of the fall
    assert xs[-1] - xs[0] >= 0.5


def test_a_running_jump_goes_farther_than_a_standing_jump():
    world = platform_world()

    def jump_distance(speed_keys):
        player = physics.Player(10.0, 3.5, 0.0, 0.0, span=0)
        physics.step(world, player, speed_keys, 0.0, 0.0, True, 1 / 60)     # jump on the first tick
        start = player.x
        for _ in range(60):
            physics.step(world, player, 0.0, 0.0, 0.0, False, 1 / 60)       # keys released in the air
            if player.on_ground:
                break
        return player.x - start

    assert jump_distance(0.0) == pytest.approx(0.0, abs=1e-6)
    assert jump_distance(1.0) > 0.8                              # momentum carried through the jump


def test_the_player_can_steer_in_the_air_but_not_faster_than_walking():
    world = platform_world()
    player = physics.Player(4.5, 3.5, 1.0, 0.0, span=0)
    physics.step(world, player, 1.0, 0.0, 0.0, True, 1 / 60)     # jump heading east
    vx_before = player.vx
    for _ in range(20):
        physics.step(world, player, 0.0, 1.0, 0.0, False, 1 / 60)           # strafe right (+y) in the air
        assert math.hypot(player.vx, player.vy) <= physics.MOVE_SPEED * 1.0001
    assert player.vy > 0.5 and player.vx < vx_before             # it bent toward the keys


def test_momentum_stops_at_a_wall_and_is_reset_on_landing():
    world = platform_world()
    player = physics.Player(21.0, 3.5, 0.0, 0.0, span=0)
    physics.step(world, player, 1.0, 0.0, 0.0, True, 1 / 60)     # running jump straight at the east wall
    for _ in range(90):
        physics.step(world, player, 0.0, 0.0, 0.0, False, 1 / 60)
    assert player.on_ground and player.x < 23.0 - physics.PLAYER_RADIUS + 1e-6   # never through the wall
    assert player.vx == 0.0                                      # the wall took the speed away
    landed_at = player.x
    for _ in range(30):
        physics.step(world, player, 0.0, 0.0, 0.0, False, 1 / 60)
    assert player.x == landed_at                                 # and on the ground it stands still again


def test_momentum_does_not_carry_the_player_through_the_slab_beside_an_opening():
    world = World(slot_over_ramp(), 256)
    player = physics.Player(10.5, 1.5, 1.75, math.pi / 2, span=1)
    for tick in range(240):
        physics.step(world, player, 1.0 if tick < 30 else 0.0, 0.0, 0.0, False, 1 / 60)
        assert physics.can_stand(world, player.x, player.y, player.z, player.span, player.on_ground)


# ------------------------------------------------------------------ a ramp used along its edge

@pytest.mark.parametrize("y", [2.0, 2.02, 2.05, 2.1, 2.15, 2.2, 2.5, 2.8, 2.85, 2.9, 2.95, 2.99])
def test_walking_up_the_ramp_along_either_edge_is_not_a_dead_end(y):
    world = World(slot_over_ramp(), 256)
    player = physics.Player(5.5, y, 0.0, 0.0, span=0)
    for _ in range(420):
        physics.step(world, player, 1.0, 0.0, 0.0, False, 1 / 60)
    assert player.x > 15.0 and player.z == pytest.approx(1.75, abs=1e-3) and player.span == 1
    assert 2.0 + physics.PLAYER_RADIUS - 0.01 <= player.y <= 3.0 - physics.PLAYER_RADIUS + 0.01 or player.x > 13.0


@pytest.mark.parametrize("angle", [-0.35, -0.15, 0.15, 0.35])
@pytest.mark.parametrize("y", [2.1, 2.5, 2.9])
def test_walking_up_the_ramp_at_an_angle_slides_along_the_walls(angle, y):
    """Higher up the ramp (z above 0.7) the cells beside it have no room for the player, so
    walking at an angle runs into their edge; the player must slide along it to the top."""
    world = World(slot_over_ramp(), 256)
    x = 9.0
    player = physics.Player(x, y, world.floor_of(0, x, y), angle, span=0)
    assert player.z > 0.8
    for _ in range(300):
        physics.step(world, player, 1.0, 0.0, 0.0, False, 1 / 60)
    assert player.x > 12.5 and player.z > 1.5                    # got up the ramp, not wedged on it


def test_below_the_ramps_sides_the_player_can_simply_walk_off_it():
    world = World(slot_over_ramp(), 256)
    player = physics.Player(5.5, 2.5, 0.0, -0.35, span=0)         # heading up and to the side
    for _ in range(300):
        physics.step(world, player, 1.0, 0.0, 0.0, False, 1 / 60)
    assert player.y < 2.0 and player.z == 0.0 and player.x > 12.0  # left the ramp low down, kept walking


def test_the_player_is_never_left_wedged_in_an_invalid_spot_for_long():
    """A random walk over the ramp, its slot and the floors around it: the box may only fail to
    fit for a few ticks at a time (while being slid out of a ceiling edge), never stay that way."""
    import random
    rng = random.Random(7)
    world = World(slot_over_ramp(), 256)
    worst = 0
    for _ in range(25):
        player = physics.Player(rng.uniform(4, 6), rng.uniform(1.4, 3.6), 0.0, rng.uniform(0, math.tau), span=0)
        streak = 0
        for tick in range(600):
            if tick % 40 == 0:
                keys = (rng.choice((0.0, 1.0, 1.0)), rng.choice((-1.0, 0.0, 1.0)), rng.uniform(-0.05, 0.05))
            physics.step(world, player, keys[0], keys[1], keys[2], rng.random() < 0.01, 1 / 60)
            fits = physics.can_stand(world, player.x, player.y, player.z, player.span, player.on_ground)
            streak = 0 if fits or not player.on_ground else streak + 1
            worst = max(worst, streak)
    assert worst <= 8, f"the player stayed in a spot where the box does not fit for {worst} ticks"


def test_strafing_in_the_air_from_a_standing_jump_reaches_full_sideways_speed_quickly():
    world = platform_world()
    player = physics.Player(4.5, 3.5, 1.0, 0.0, span=0)
    physics.step(world, player, 0.0, 0.0, 0.0, True, 1 / 60)     # straight up
    for _ in range(15):
        physics.step(world, player, 0.0, 1.0, 0.0, False, 1 / 60)
    assert not player.on_ground and player.vy == pytest.approx(physics.MOVE_SPEED)


def test_turning_in_the_air_does_not_swing_the_momentum():
    world = platform_world()
    player = physics.Player(4.5, 3.5, 1.0, 0.0, span=0)
    physics.step(world, player, 1.0, 0.0, 0.0, True, 1 / 60)     # jump east
    physics.step(world, player, 0.0, 0.0, 1.0, False, 1 / 60)    # turn while airborne, no keys
    assert player.vx == pytest.approx(physics.MOVE_SPEED) and player.vy == pytest.approx(0.0)
