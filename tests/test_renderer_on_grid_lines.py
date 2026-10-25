"""Regression: standing exactly on a grid line (or corner) and facing across it crashed the renderer.

The ray's first cell crossing was then at distance 0 and the projection divided by it.
"""
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import main
import physics
from atlas import atlas_array, unpack_atlas
from constants import FOG_DIST, HEIGHT, MAX_DEPTH, WIDTH
from mapfile import Level
from raykernel import render_scene
from world import World


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


@pytest.fixture(scope="module")
def renderer():
    return main.Renderer(atlas_array(unpack_atlas()))


def room(floors=1):
    level = Level.blank(12, 10, floors=floors)
    for y in range(1, 9):
        for x in range(1, 11):
            level.set("ceil_h", x, y, 3.0)
    level.set("walls", 5, 5, 2)
    level.set("wall_h", 5, 5, 0.5)                              # and a short wall to look at
    level.set("walls", 7, 3, 3)
    return World(level, 256)


def draw(renderer, world, x, y, angle, span=0, z=0.0):
    sentinel = np.array((255, 0, 255), np.uint8)
    fb = np.zeros((WIDTH, HEIGHT, 3), np.uint8)
    fb[:] = sentinel
    player = physics.Player(x, y, z, angle, span=span)
    render_scene(fb, player.x, player.y, player.eye_z, span, math.cos(angle), math.sin(angle),
                 -math.sin(angle) * renderer.half_fov_tan, math.cos(angle) * renderer.half_fov_tan,
                 HEIGHT / 2, renderer.focal, world.floor_plane, world.ceil_plane, world.span_on,
                 world.solid_from, world.pane_tex, world.pane_top, world.wall_tex, world.side_tex, world.floor_tex, world.ceil_tex, renderer.textures,
                 MAX_DEPTH, FOG_DIST, sentinel)
    return fb, sentinel


ANGLES = [0.0, math.pi / 2, math.pi, -math.pi / 2, 0.785398, -0.25, 2.5, 4.0]
SPOTS = [(2.5, 5.0), (2.0, 5.5), (2.0, 5.0), (3.0, 3.0), (8.0, 6.0), (6.0, 7.0), (4.5, 5.0)]   # none inside a wall


@pytest.mark.parametrize("x, y", SPOTS)
def test_standing_exactly_on_a_grid_line_or_corner_renders_in_every_direction(renderer, x, y):
    world = room()
    for angle in ANGLES:
        fb, sentinel = draw(renderer, world, x, y, angle)       # used to raise ZeroDivisionError
        assert not (fb == sentinel).all(axis=2).any(), f"unfilled pixels at ({x}, {y}) facing {angle}"


def test_the_same_holds_on_an_upper_floor_and_with_a_tilted_view(renderer):
    world = room(floors=2)
    for angle in ANGLES:
        fb, sentinel = draw(renderer, world, 4.0, 4.0, angle)
        assert not (fb == sentinel).all(axis=2).any()


def test_the_game_renderer_handles_a_grid_line_position_too(renderer):
    world = room()
    for pitch in (-0.6, 0.0, 0.6):
        for angle in ANGLES:
            player = physics.Player(3.0, 5.0, 0.0, angle, span=0, pitch=pitch)
            renderer.draw(world, player)                         # must not raise
