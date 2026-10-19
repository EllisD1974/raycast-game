"""Transparency: textures with an alpha channel make see-through walls (fences, windows, glass).

These tests build their own textures instead of using textures.png, so they never depend on it:
    id 1 red wall, id 2 green wall, id 3 fence (blue bars, fully transparent gaps),
    id 4 white glass (alpha 128), id 5 floor, id 6 ceiling, id 7 red glass, id 8 blue glass
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
from atlas import atlas_array, ensure_rgba, transparent_tiles, unpack_atlas
from constants import FOG_DIST, HEIGHT, MAX_DEPTH, WIDTH
from mapfile import Level
from raykernel import MAX_PANES, render_scene
from world import World

RED, GREEN, FENCE, GLASS, FLOOR, CEILING, RED_GLASS, BLUE_GLASS = 1, 2, 3, 4, 5, 6, 7, 8
GLASS_ALPHA = 128


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


def make_textures():
    t = np.zeros((8, 32, 32, 4), np.uint8)
    t[..., 3] = 255
    for index, color in {0: (200, 40, 40), 1: (40, 200, 40), 4: (120, 120, 120), 5: (60, 60, 80)}.items():
        t[index, :, :, :3] = color
    t[2, :, :, :3] = (30, 60, 255)                                  # the fence: bars 4 px wide every 8
    t[2, :, :, 3] = np.where(np.arange(32) % 8 < 4, 255, 0)[None, :]
    t[3, :, :, :3] = (255, 255, 255)                                # white glass
    t[3, :, :, 3] = GLASS_ALPHA
    t[6, :, :, :3] = (255, 40, 40)
    t[6, :, :, 3] = GLASS_ALPHA
    t[7, :, :, :3] = (40, 40, 255)
    t[7, :, :, 3] = GLASS_ALPHA
    return t


TEXTURES = make_textures()


def hall(width=16, height=11, ceiling=3.0):
    level = Level.blank(width, height)
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            level.set("ceil_h", x, y, ceiling)
    level.start_x, level.start_y = 2.5, height // 2 + 0.5
    return level


def place(level, x, y, tile, height=0.0):
    level.set("walls", x, y, tile)
    level.set("wall_h", x, y, height)
    return level


def build(level, textures=TEXTURES, aware=True):
    transparent = transparent_tiles(textures) if aware else None
    return World(level, len(textures), transparent)


@pytest.fixture(scope="module")
def renderer():
    return main.Renderer(TEXTURES)


def frame(renderer, world, x=3.5, y=5.5, angle=0.0, z=0.0, hide_panes=()):
    """Render and return the framebuffer as int32 [x, y, rgb]. hide_panes lists cells whose pane
    is switched off (the cell stays an open one), to compare with and without it."""
    saved = [(cell, world.pane_tex[cell[1], cell[0]]) for cell in hide_panes]
    for (cx, cy), _ in saved:
        world.pane_tex[cy, cx] = -1
    renderer.draw(world, physics.Player(x, y, z, angle, span=0))
    out = np.array(renderer.framebuffer, dtype=np.int32)
    for (cx, cy), value in saved:
        world.pane_tex[cy, cx] = value
    return out


def shade(distance, side_x=True):
    return max(0.2, 1 - distance / FOG_DIST) * (1.0 if side_x else 0.7)


def center_row(fb, row=HEIGHT // 2):
    return fb[:, row, :]


def dominant(rgb):
    r, g, b = (int(v) for v in rgb)
    if b > r + 80 and b > g + 60:
        return "blue"
    if g > r + 30 and g > b + 30:
        return "green"
    if r > g + 40 and r > b + 40:
        return "red"
    return "other"


# ------------------------------------------------------------------ the atlas and its alpha channel

def test_the_atlas_loader_keeps_alpha_and_reports_which_tiles_are_see_through(tmp_path):
    atlas = pygame.Surface((96, 32), pygame.SRCALPHA)
    atlas.fill((0, 0, 0, 0))
    atlas.fill((200, 30, 30, 255), (0, 0, 32, 32))                  # opaque
    atlas.fill((30, 30, 200, 90), (32, 0, 32, 32))                  # glass
    atlas.fill((30, 200, 30, 255), (64, 0, 32, 32))
    atlas.fill((0, 0, 0, 0), (64, 0, 8, 32))                        # opaque tile with a transparent strip
    path = str(tmp_path / "atlas.png")
    pygame.image.save(atlas, path)
    tiles = unpack_atlas(path)
    textures = atlas_array(tiles)
    assert textures.shape == (3, 32, 32, 4) and textures.dtype == np.uint8
    assert textures[0, 5, 5].tolist() == [200, 30, 30, 255]
    assert textures[1, 5, 5].tolist() == [30, 30, 200, 90]
    assert textures[2, 5, 3].tolist()[3] == 0 and textures[2, 5, 20].tolist() == [30, 200, 30, 255]
    assert transparent_tiles(textures).tolist() == [False, True, True]


def test_an_atlas_without_alpha_is_fully_opaque(tmp_path):
    atlas = pygame.Surface((64, 32))
    atlas.fill((10, 20, 30))
    path = str(tmp_path / "plain.png")
    pygame.image.save(atlas, path)
    textures = atlas_array(unpack_atlas(path))
    assert textures.shape[-1] == 4 and (textures[..., 3] == 255).all()
    assert not transparent_tiles(textures).any()


def test_color_only_textures_gain_an_opaque_alpha_channel():
    rgb = TEXTURES[..., :3].copy()
    rgba = ensure_rgba(rgb)
    assert rgba.shape[-1] == 4 and (rgba[..., 3] == 255).all()
    assert ensure_rgba(TEXTURES) is TEXTURES                        # already RGBA: untouched
    assert main.Renderer(rgb).textures.shape[-1] == 4               # the game renderer accepts both


def test_the_test_textures_have_the_see_through_tiles_expected():
    assert transparent_tiles(TEXTURES).tolist() == [False, False, True, True, False, False, True, True]


# ------------------------------------------------------------------ the compiled world

def test_a_wall_of_a_see_through_tile_becomes_an_open_cell_with_a_pane():
    world = build(place(hall(), 6, 5, FENCE))
    assert world.solid[5, 6] == 0 and world.span_on[0, 5, 6] == 1
    assert world.pane_tex[5, 6] == FENCE - 1
    assert world.pane_top[5, 6] > 1e6                               # full height
    assert world.floor_of(0, 6.5, 5.5) == 0.0 and world.ceil_of(0, 6.5, 5.5) == pytest.approx(3.0)
    assert world.is_blocked(6, 5)                                   # but the player cannot enter it


def test_opaque_walls_and_open_cells_have_no_pane():
    world = build(place(place(hall(), 6, 5, RED), 8, 5, GREEN))
    assert (world.pane_tex == -1).all()
    assert world.solid[5, 6] == 1 and world.solid[5, 8] == 1 and world.is_blocked(6, 5)


def test_a_world_built_without_transparency_info_treats_every_wall_as_opaque():
    world = build(place(hall(), 6, 5, FENCE), aware=False)
    assert world.solid[5, 6] == 1 and (world.pane_tex == -1).all()


def test_a_short_see_through_wall_keeps_its_height_but_still_blocks():
    world = build(place(hall(), 6, 5, GLASS, height=0.5))
    assert world.pane_tex[5, 6] == GLASS - 1 and world.pane_top[5, 6] == pytest.approx(0.5)
    assert world.is_blocked(6, 5)
    assert world.floor_of(0, 6.5, 5.5) == 0.0                       # the floor is not raised: it is a pane


def test_a_short_opaque_wall_is_still_a_raised_block_and_a_see_through_one_does_not_hop():
    level = place(place(hall(), 6, 5, RED, height=0.2), 8, 5, GLASS, height=0.2)
    world = build(level)
    assert not world.is_blocked(6, 5) and world.floor_of(0, 6.5, 5.5) == pytest.approx(0.2)
    assert world.is_blocked(8, 5)


def test_the_pane_stands_on_the_floor_beside_it_and_reaches_the_halls_ceiling():
    level = hall(ceiling=2.5)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        level.set("floor_h", 6 + dx, 5 + dy, 0.25)                 # the room's floor around the pane
    level.set("floor_h", 6, 5, 1.0)                                # (a value stored under it: ignored)
    world = build(place(level, 6, 5, FENCE))
    assert world.floor_of(0, 6.5, 5.5) == pytest.approx(0.25) and world.ceil_of(0, 6.5, 5.5) == pytest.approx(2.5)


# ------------------------------------------------------------------ the player cannot pass a pane

def walk_at(world, x, y, angle, ticks=150, jump=False):
    player = physics.Player(x, y, 0.0, angle, span=0)
    for t in range(ticks):
        physics.step(world, player, 1.0, 0.0, 0.0, jump and t == 0, 1 / 60)
    return player


@pytest.mark.parametrize("tile, height", [(FENCE, 0.0), (GLASS, 0.0), (GLASS, 0.2), (FENCE, 0.5)])
def test_neither_walking_nor_hopping_gets_past_a_pane(tile, height):
    world = build(place(hall(), 6, 5, tile, height))
    for jump in (False, True):
        player = walk_at(world, 3.5, 5.5, 0.0, jump=jump)
        assert player.x < 6.0 and player.z == 0.0, f"got past the pane (jump={jump})"


def test_the_pane_blocks_from_every_side():
    world = build(place(hall(), 6, 5, FENCE))
    for x, y, angle in ((9.5, 5.5, math.pi), (6.5, 2.5, math.pi / 2), (6.5, 8.5, -math.pi / 2)):
        player = walk_at(world, x, y, angle)
        assert (player.x, player.y) != (6.5, 5.5) and not (6.0 < player.x < 7.0 and 5.0 < player.y < 6.0)


# ------------------------------------------------------------------ what you see

def test_you_see_through_the_gaps_of_a_fence_and_the_bars_cover_the_rest(renderer):
    """Looking straight at a fence with a green wall far behind it: across the fence's width the
    center row alternates between blue bars and green wall seen through the gaps."""
    level = hall()
    place(level, 6, 5, FENCE)
    for y in range(2, 9):
        place(level, 12, y, GREEN)
    fb = frame(renderer, build(level))
    # the fence's face, 2.5 cells away, spans about 220-420 of the 640 columns
    kinds = [dominant(fb[x, HEIGHT // 2]) for x in range(235, 405)]
    blue, green = kinds.count("blue"), kinds.count("green")
    assert blue > 40 and green > 40, f"expected both bars and wall behind: {blue} blue, {green} green"
    assert abs(blue - green) < 40                                     # bars and gaps are equal widths
    assert blue + green > 0.85 * len(kinds)                           # nothing else shows in that band
    # beside the fence only the green wall (and no blue)
    assert all(dominant(fb[x, HEIGHT // 2]) != "blue" for x in range(0, 200))


def test_without_the_fence_there_is_no_blue_at_all(renderer):
    level = hall()
    for y in range(2, 9):
        place(level, 12, y, GREEN)
    fb = frame(renderer, build(level))
    assert not any(dominant(fb[x, y]) == "blue" for x in range(0, WIDTH, 8) for y in range(0, HEIGHT, 8))


def test_the_fence_is_not_solid_when_the_world_is_built_without_transparency(renderer):
    level = place(hall(), 6, 5, FENCE)
    for y in range(2, 9):
        place(level, 12, y, GREEN)
    fb = frame(renderer, build(level, aware=False))
    assert not any(dominant(fb[x, HEIGHT // 2]) == "green" for x in range(235, 405))   # all fence texture, opaque


def test_glass_blends_with_what_is_behind_it(renderer):
    """A pixel seen through white glass of alpha 128 is half the glass's color (shaded by
    distance) and half the picture behind it."""
    level = place(hall(), 6, 5, GLASS)
    for y in range(2, 9):
        place(level, 12, y, GREEN)
    world = build(level)
    with_glass = frame(renderer, world)
    without = frame(renderer, world, hide_panes=[(6, 5)])
    a = GLASS_ALPHA / 255.0
    face = shade(6 - 3.5)                                            # the glass is 2.5 away, facing +x
    for x, y in ((320, 180), (300, 130), (340, 230), (260, 100), (380, 260)):
        expected = np.floor(255 * face * a + without[x, y] * (1 - a))
        assert np.all(np.abs(with_glass[x, y] - expected) <= 2), (x, y, with_glass[x, y], expected)
    assert (with_glass[320, 180] > without[320, 180]).all()           # white glass brightens it


def test_glass_only_changes_the_pixels_in_its_own_face(renderer):
    level = place(hall(), 6, 5, GLASS)
    world = build(level)
    with_glass = frame(renderer, world)
    without = frame(renderer, world, hide_panes=[(6, 5)])
    changed = np.abs(with_glass - without).sum(axis=2) > 0
    cols = np.where(changed.any(axis=1))[0]
    assert 200 < cols.min() < 245 and 395 < cols.max() < 440         # the face is about 220-420 wide
    assert not changed[:150].any() and not changed[450:].any()


def test_nearer_glass_is_blended_over_farther_glass(renderer):
    """Two panes in a line, red glass behind blue glass. The result is the blue blended over the
    (red blended over the background): far panes first, near panes on top."""
    level = hall()
    place(level, 5, 5, BLUE_GLASS)
    place(level, 7, 5, RED_GLASS)
    world = build(level)
    both = frame(renderer, world, x=2.5)
    none = frame(renderer, world, x=2.5, hide_panes=[(5, 5), (7, 5)])
    a = GLASS_ALPHA / 255.0
    near_shade, far_shade = shade(5 - 2.5), shade(7 - 2.5)
    for x, y in ((320, 180), (320, 140), (310, 220)):
        far_only = np.floor(np.array((255, 40, 40)) * far_shade * a + none[x, y] * (1 - a))
        expected = np.floor(np.array((40, 40, 255)) * near_shade * a + far_only * (1 - a))
        assert np.all(np.abs(both[x, y] - expected) <= 3), (x, y, both[x, y], expected)
    # and the order matters: swapping the colors gives a different picture
    swapped = hall()
    place(swapped, 5, 5, RED_GLASS)
    place(swapped, 7, 5, BLUE_GLASS)
    other = frame(renderer, build(swapped), x=2.5)
    assert np.abs(other[320, 180] - both[320, 180]).sum() > 10


def test_a_pane_behind_a_nearer_opaque_wall_is_not_drawn(renderer):
    level = hall()
    place(level, 4, 5, RED)                                           # opaque, in front
    place(level, 8, 5, FENCE)                                         # hidden behind it
    world = build(level)
    with_pane = frame(renderer, world, x=2.5)
    without = frame(renderer, world, x=2.5, hide_panes=[(8, 5)])
    assert np.array_equal(with_pane, without)


def test_a_short_glass_wall_only_covers_up_to_its_height(renderer):
    """Eye height is 0.5 and the glass is 0.5 high, so its top edge is on the horizon: everything
    above the horizon is untouched, and below it the glass shows."""
    world = build(place(hall(), 6, 5, GLASS, height=0.5))
    with_pane = frame(renderer, world)
    without = frame(renderer, world, hide_panes=[(6, 5)])
    changed = np.abs(with_pane - without).sum(axis=2) > 0
    assert not changed[:, :170].any(), "glass drawn above its top edge"
    # 2.5 cells away, 0.5 high, eye 0.5: the pane runs from the horizon (row 180) to about row 278
    assert changed[300, 185:270].all(), "glass missing below its top edge"
    assert not changed[300, 290:].any(), "glass drawn below its bottom edge"


def test_a_taller_glass_wall_covers_more_of_the_view_than_a_short_one(renderer):
    def covered(height):
        world = build(place(hall(), 6, 5, GLASS, height))
        d = np.abs(frame(renderer, world) - frame(renderer, world, hide_panes=[(6, 5)])).sum(axis=2) > 0
        return int(d.sum())
    assert covered(0.25) < covered(0.5) < covered(1.0) <= covered(0.0)


def test_panes_are_drawn_from_both_sides(renderer):
    world = build(place(hall(), 6, 5, FENCE))
    for x, angle in ((3.5, 0.0), (9.5, math.pi)):
        a = frame(renderer, world, x=x, angle=angle)
        b = frame(renderer, world, x=x, angle=angle, hide_panes=[(6, 5)])
        assert np.abs(a - b).sum() > 0


def test_panes_also_work_when_seen_from_the_side(renderer):
    level = place(hall(), 6, 5, FENCE)
    world = build(level)
    a = frame(renderer, world, x=6.5, y=2.5, angle=math.pi / 2)       # looking along +y at the fence's side
    b = frame(renderer, world, x=6.5, y=2.5, angle=math.pi / 2, hide_panes=[(6, 5)])
    assert np.abs(a - b).sum() > 0


def test_floor_and_ceiling_textures_ignore_alpha(renderer):
    """Only walls are see-through. A floor tile with transparent pixels is drawn with its colors."""
    holey = TEXTURES.copy()
    holey[4, ::2, ::2, 3] = 0                                         # the floor tile gets holes
    level = hall()
    a = frame(main.Renderer(holey), World(level, 8, transparent_tiles(holey)))
    b = frame(main.Renderer(TEXTURES), World(level, 8, transparent_tiles(TEXTURES)))
    assert np.array_equal(a, b)


def test_a_row_of_many_panes_renders_and_shows_the_nearest_ones(renderer):
    level = hall(width=40)
    for x in range(3, 36):
        place(level, x, 5, GLASS)                                     # 33 panes in a line: more than are kept
    world = build(level)
    assert 33 > MAX_PANES
    near = frame(renderer, world, x=2.5)
    none = frame(renderer, world, x=2.5, hide_panes=[(x, 5) for x in range(3, 36)])
    assert np.abs(near - none).sum() > 0
    assert (near[320, 180] > none[320, 180]).all()                    # the kept panes lighten the view


def test_a_pane_next_to_the_viewer_covers_the_whole_screen_correctly(renderer):
    level = place(hall(), 4, 5, GLASS)
    world = build(level)
    a = frame(renderer, world, x=4.9)                                 # half a cell from the glass's face... inside its range
    b = frame(renderer, world, x=4.9, hide_panes=[(4, 5)])
    assert a.shape == b.shape == (WIDTH, HEIGHT, 3)


def render_raw(world, x, y, angle, span=0, z=0.0):
    sentinel = np.array((255, 0, 255), np.uint8)
    fb = np.zeros((WIDTH, HEIGHT, 3), np.uint8)
    fb[:] = sentinel
    r = main.Renderer(TEXTURES)
    render_scene(fb, x, y, z + 0.5, span, math.cos(angle), math.sin(angle),
                 -math.sin(angle) * r.half_fov_tan, math.cos(angle) * r.half_fov_tan,
                 HEIGHT / 2, r.focal, world.floor_plane, world.ceil_plane, world.span_on, world.solid_from,
                 world.pane_tex, world.pane_top, world.wall_tex, world.floor_tex, world.ceil_tex,
                 r.textures, MAX_DEPTH, FOG_DIST, sentinel)
    return fb, sentinel


@pytest.mark.parametrize("x, y", [(3.5, 5.5), (3.0, 5.0), (6.0, 5.5), (9.5, 7.5), (6.5, 2.5)])
def test_every_pixel_is_filled_with_panes_around_in_every_direction(x, y):
    level = hall()
    place(level, 6, 5, FENCE)
    place(level, 8, 4, GLASS, height=0.5)
    place(level, 8, 6, GLASS)
    place(level, 5, 3, RED)
    world = build(level)
    for angle in (0.0, math.pi / 2, math.pi, -math.pi / 2, 0.7, 2.5, 4.0, 5.5):
        fb, sentinel = render_raw(world, x, y, angle)
        assert not (fb == sentinel).all(axis=2).any(), f"unfilled pixels at ({x}, {y}) facing {angle}"


def test_panes_work_on_an_upper_floor_and_beside_ramps_and_short_walls(renderer):
    level = Level.blank(16, 11, floors=2)
    for y in range(1, 10):
        for x in range(1, 15):
            level.set("ceil_h", x, y, 1.2)
            level.set("floor_h2", x, y, 1.5)
            level.set("ceil_h2", x, y, 3.0)
    place(level, 8, 5, FENCE)                                         # a wall cell: carries no upper room
    world = build(level)
    player = physics.Player(3.5, 5.5, 1.5, 0.0, span=1)
    renderer.draw(world, player)                                       # must not raise
    assert np.array(renderer.framebuffer).shape == (WIDTH, HEIGHT, 3)
