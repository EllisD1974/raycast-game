"""Setting how tall a wall is: the map data, the world, the physics, the renderer and the editor."""
import json
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import main
import map_editor
import physics
from atlas import atlas_array, unpack_atlas
from constants import FOG_DIST, HEIGHT, MAX_DEPTH, WIDTH
from mapfile import DEFAULTS, FORMAT_VERSION, MAP_PATH, Level, load_level, save_level
from raykernel import render_scene
from world import World

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1920, 1009), pygame.RESIZABLE)
    yield
    pygame.quit()


def hall(width=14, height=9, ceiling=3.0):
    """An enclosed hall with a tall ceiling, so walls of any height can stand in it."""
    level = Level.blank(width, height)
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            level.set("ceil_h", x, y, ceiling)
    level.start_x, level.start_y = 2.5, height // 2 + 0.5
    return level


def with_wall(level, x, y, tile=1, height=0.0):
    level.set("walls", x, y, tile)
    level.set("wall_h", x, y, height)
    return level


# ------------------------------------------------------------------ the map data

def test_every_new_map_has_a_wall_height_grid_that_defaults_to_full_height():
    for level in (Level.blank(6, 5), Level.blank(6, 5, floors=3)):
        assert level.grids["wall_h"] == [[0.0] * 6 for _ in range(5)]
    assert DEFAULTS["wall_h"] == 0.0
    assert "wall_h" in Level.blank(4, 4).grid_names()


def test_wall_heights_survive_save_and_load_and_resize(tmp_path):
    level = hall()
    with_wall(level, 5, 4, height=0.5)
    with_wall(level, 6, 4, tile=2, height=1.25)
    path = str(tmp_path / "m.json")
    save_level(path, level)
    again = load_level(path)
    assert again.grids["wall_h"] == level.grids["wall_h"]
    assert again.grids["wall_h"][4][5] == 0.5 and again.grids["wall_h"][4][6] == 1.25
    again.resize(20, 12)                                          # new cells default to full
    assert again.grids["wall_h"][4][5] == 0.5 and again.grids["wall_h"][11][19] == 0.0
    assert json.load(open(path))["version"] == FORMAT_VERSION


def test_files_from_before_wall_heights_load_with_every_wall_full_height(tmp_path):
    level = hall()
    path = tmp_path / "old.json"
    save_level(str(path), level)
    data = json.load(open(path))
    del data["grids"]["wall_h"]                                   # what a version 4 file looks like
    data["version"] = 4
    json.dump(data, open(path, "w"))
    again = load_level(str(path))
    assert all(v == 0.0 for row in again.grids["wall_h"] for v in row)
    assert all(again.short_wall_top(x, y) is None for y in range(again.height) for x in range(again.width))


def test_the_real_map_file_loads_compiles_and_renders():
    """Whatever the author has put in map.json (short walls, transparent walls, ...) must work."""
    from atlas import transparent_tiles
    level = load_level(MAP_PATH)
    textures = atlas_array(unpack_atlas())
    world = World(level, len(textures), transparent_tiles(textures))
    player = physics.spawn(level, world)
    surface = main.Renderer(textures).draw(world, player)
    assert surface.get_size() == (WIDTH, HEIGHT)


def raise_around(level, x, y, height, diagonals=False):
    """Set the floor of the open cells beside (x, y)."""
    offsets = [(1, 0), (-1, 0), (0, 1), (0, -1)] + ([(1, 1), (1, -1), (-1, 1), (-1, -1)] if diagonals else [])
    for dx, dy in offsets:
        level.set("floor_h", x + dx, y + dy, height)


def test_short_wall_top_is_measured_up_from_the_floor_beside_the_wall():
    level = hall()
    assert level.short_wall_top(5, 4) is None                      # not a wall
    with_wall(level, 5, 4, height=0.0)
    assert level.short_wall_top(5, 4) is None                      # 0 = full height
    level.set("wall_h", 5, 4, 0.5)
    assert level.short_wall_top(5, 4) == pytest.approx(0.5)
    assert level.wall_base(5, 4) == 0.0
    raise_around(level, 5, 4, 1.0)                                  # a wall in the middle of a 1.0 platform
    assert level.wall_base(5, 4) == pytest.approx(1.0) and level.short_wall_top(5, 4) == pytest.approx(1.5)


def test_a_wall_stands_on_the_lowest_floor_beside_it():
    level = with_wall(hall(), 5, 4, height=0.5)
    level.set("floor_h", 4, 4, 1.0)                                 # a platform on one side, ground on the others
    assert level.wall_base(5, 4) == 0.0 and level.short_wall_top(5, 4) == pytest.approx(0.5)
    level.set("floor_h", 5, 3, -0.25)                               # a step down on another side
    assert level.wall_base(5, 4) == pytest.approx(-0.25) and level.short_wall_top(5, 4) == pytest.approx(0.25)


def test_the_floor_value_stored_under_a_wall_is_ignored():
    """The editor never shows it, and it is easy to leave there (a FloorH fill or a stairs drag
    over a wall cell). It must not change how tall the wall is."""
    level = with_wall(hall(ceiling=1.5), 5, 4, height=0.5)
    base = level.short_wall_top(5, 4)
    for stored in (0.25, 1.0, 2.0, -1.0):
        level.set("floor_h", 5, 4, stored)
        assert level.short_wall_top(5, 4) == base == pytest.approx(0.5), f"floor {stored} under the wall mattered"


def test_a_wall_with_no_open_cell_beside_it_uses_the_diagonals_and_then_its_own_floor():
    level = hall()
    for y in range(3, 6):
        for x in range(4, 7):
            level.set("walls", x, y, 1)                             # a 3x3 block of wall
    level.set("wall_h", 5, 4, 0.5)
    level.set("floor_h", 3, 3, 0.75)                                # the only open cells around the block...
    assert level.wall_base(5, 4) == 0.0                             # (the middle has no open neighbor at all
    level.set("floor_h", 5, 4, 0.4)                                 # so it falls back to its own floor value)
    assert level.wall_base(5, 4) == pytest.approx(0.4)
    assert level.wall_base(4, 4) == 0.0                             # an edge wall looks at the open cell beside it


def test_a_wall_with_a_stored_floor_under_it_is_still_a_short_wall_in_a_low_room():
    """The reported bug: a wall with height 0.5 in a 1.5 high room, with 1.0 stored as the floor
    under it, stayed full height (1.0 + 0.5 reached the ceiling) and looked like a red full wall."""
    level = hall(ceiling=1.5)
    for x, y in ((5, 4), (6, 4), (5, 5)):
        with_wall(level, x, y, tile=2, height=0.5)
        level.set("floor_h", x, y, 1.0)
    for x, y in ((5, 4), (6, 4), (5, 5)):
        assert level.short_wall_top(x, y) == pytest.approx(0.5)
    world = World(level, 256)
    for x, y in ((5, 4), (6, 4), (5, 5)):
        assert world.solid[y, x] == 0 and world.span_on[0, y, x] == 1
        assert world.floor_of(0, x + 0.5, y + 0.5) == pytest.approx(0.5)


def test_a_wall_that_reaches_the_ceiling_is_just_a_full_height_wall():
    level = with_wall(hall(ceiling=2.0), 5, 4, height=1.0)
    assert level.short_wall_top(5, 4) == pytest.approx(1.0)
    level.set("wall_h", 5, 4, 1.97)                                # within a hair of the ceiling
    assert level.short_wall_top(5, 4) is None
    level.set("wall_h", 5, 4, 5.0)                                 # taller than the room
    assert level.short_wall_top(5, 4) is None


def test_a_stale_height_on_an_open_cell_means_nothing():
    level = hall()
    level.set("wall_h", 5, 4, 0.5)
    assert level.short_wall_top(5, 4) is None


def test_the_ceiling_over_a_short_wall_is_the_highest_of_the_open_cells_around_it():
    level = with_wall(hall(ceiling=3.0), 5, 4, height=0.5)
    assert level.wall_ceiling(5, 4) == 3.0
    level.set("ceil_h", 4, 4, 2.0)
    level.set("ceil_h", 6, 4, 1.5)
    assert level.wall_ceiling(5, 4) == 3.0                         # (5,3) and (5,5) are still 3.0
    level.set("ceil_h", 5, 3, 2.5)
    level.set("ceil_h", 5, 5, 2.25)
    assert level.wall_ceiling(5, 4) == 2.5
    # a wall boxed in by other walls looks at the open cells diagonally, then at its own ceiling
    boxed = Level.blank(7, 7)
    for y in range(2, 5):
        for x in range(2, 5):
            boxed.set("walls", x, y, 1)
    boxed.set("ceil_h", 1, 1, 2.75)
    assert boxed.wall_ceiling(3, 3) == boxed.grids["ceil_h"][3][3]


def test_wall_region_is_the_connected_wall_whatever_its_texture():
    level = hall()
    for x, tile in ((4, 1), (5, 2), (6, 3)):
        level.set("walls", x, 4, tile)
    level.set("walls", 9, 4, 1)                                    # a separate wall
    region = set(level.wall_region(5, 4))
    assert region == {(4, 4), (5, 4), (6, 4)}
    assert level.wall_region(2, 2) == []                           # open cell


# ------------------------------------------------------------------ the compiled world

def test_a_short_wall_becomes_a_raised_block_wearing_the_walls_texture():
    level = with_wall(hall(), 6, 4, tile=2, height=0.5)
    world = World(level, 256)
    assert world.solid[4, 6] == 0 and world.span_on[0, 4, 6] == 1
    assert world.floor_of(0, 6.5, 4.5) == pytest.approx(0.5)
    assert world.ceil_of(0, 6.5, 4.5) == pytest.approx(3.0)        # the hall's ceiling over it
    assert world.floor_tex[0, 4, 6] == world.wall_tex[4, 6] == 1   # tile id 2 is atlas index 1
    assert not world.is_blocked(6, 4)


def test_full_height_walls_are_untouched_and_still_solid():
    level = hall()
    with_wall(level, 6, 4, height=0.0)
    with_wall(level, 7, 4, height=0.5)
    world = World(level, 256)
    assert world.solid[4, 6] == 1 and world.span_on[0, 4, 6] == 0 and world.is_blocked(6, 4)
    assert world.solid[4, 7] == 0 and world.span_on[0, 4, 7] == 1   # only the short wall became a block


def test_there_is_no_room_above_a_short_wall():
    level = Level.blank(14, 9, floors=2)
    for y in range(1, 8):
        for x in range(1, 13):
            level.set("ceil_h", x, y, 1.2)
    with_wall(level, 6, 4, height=0.5)
    level.set("floor_h2", 6, 4, 1.5)
    level.set("ceil_h2", 6, 4, 3.0)
    world = World(level, 256)
    assert world.span_on[1, 4, 6] == 0                             # walls carry no rooms, short or not


# ------------------------------------------------------------------ walking into, onto and over them

def stand(world, x, y, z=0.0, angle=0.0):
    return physics.Player(x, y, z, angle, span=0)


def run(world, player, ticks, forward=1.0, jump_at=None):
    for t in range(ticks):
        physics.step(world, player, forward, 0.0, 0.0, jump_at == t, DT)
    return player


def test_a_tall_short_wall_blocks_the_player_like_any_wall():
    world = World(with_wall(hall(), 6, 4, height=1.0), 256)
    player = run(world, stand(world, 2.5, 4.5), 200)
    assert player.x < 6.0 and player.z == 0.0                      # stopped at the wall's face


def test_a_low_curb_can_simply_be_walked_onto():
    world = World(with_wall(hall(), 6, 4, height=0.2), 256)
    player = run(world, stand(world, 2.5, 4.5), 100)
    assert player.x > 6.0 and player.on_ground


def hop_at_wall(height):
    """Jump at a wall one cell wide while walking at it; returns every state from the jump until
    the player has crossed the wall, so we can see whether they were ever standing on top of it."""
    world = World(with_wall(hall(), 6, 4, height=height), 256)
    player = stand(world, 5.0, 4.5)
    states = []
    for tick in range(120):
        physics.step(world, player, 1.0, 0.0, 0.0, tick == 0, DT)
        states.append((player.x, player.z, player.on_ground))
    return states


def test_the_player_can_hop_onto_a_waist_high_wall():
    states = hop_at_wall(0.5)
    on_top = [s for s in states if s[2] and 6.0 < s[0] < 7.0 and s[1] == pytest.approx(0.5, abs=1e-3)]
    assert on_top, "the player never landed on top of the 0.5 high wall"


def test_a_taller_wall_cannot_be_hopped_onto_and_stops_the_player():
    states = hop_at_wall(0.9)
    assert not [s for s in states if s[0] > 6.0 - 0.2 + 1e-6]       # never got past the wall's face
    assert all(s[1] <= 0.4 for s in states)                         # and never stood on it


def test_a_player_standing_on_a_short_wall_walks_off_the_far_side_and_falls():
    world = World(with_wall(hall(), 6, 4, height=0.5), 256)
    player = stand(world, 5.0, 4.5)
    run(world, player, 250, jump_at=0)                             # hop up and keep walking east
    assert player.x > 7.0 and player.z == 0.0 and player.on_ground


def test_a_full_height_wall_cannot_be_hopped_onto():
    world = World(with_wall(hall(), 6, 4, height=0.0), 256)
    player = stand(world, 5.0, 4.5)
    run(world, player, 90, jump_at=0)
    assert player.x < 6.0 and player.z == 0.0


# ------------------------------------------------------------------ what you see

@pytest.fixture(scope="module")
def renderer():
    return main.Renderer(atlas_array(unpack_atlas()))


def view(renderer, world, x, y, angle, z=0.0):
    player = physics.Player(x, y, z, angle, span=0)
    renderer.draw(world, player)
    return np.array(renderer.framebuffer)


def center_pixel(frame):
    return tuple(int(v) for v in frame[WIDTH // 2, HEIGHT // 2])


def is_reddish(rgb):
    return rgb[0] > rgb[1] + 35 and rgb[0] > rgb[2] + 35           # the brick wall is red; stone is gray-green


def reddish_near_center(frame, half=14):
    """Fraction of reddish pixels in a block around the middle of the view (mortar lines between
    the bricks are gray, so one pixel would not tell)."""
    cx, cy = WIDTH // 2, HEIGHT // 2
    block = [tuple(int(v) for v in frame[x, y])
             for x in range(cx - half, cx + half) for y in range(cy - half, cy + half)]
    return sum(is_reddish(p) for p in block) / len(block)


def test_you_can_see_over_a_short_wall_but_not_over_a_full_one(renderer):
    """Looking along +x at eye height 0.5 with a brick wall (tile 1) in front and a stone wall
    (tile 2) behind it at the end of the hall. Over a 0.2 high brick wall the stone one shows."""
    def scene(wall_height):
        level = hall(width=16, height=7)
        with_wall(level, 6, 3, tile=1, height=wall_height)
        for y in range(1, 6):
            level.set("walls", 14, y, 2)                            # the far stone wall
        return World(level, 256)

    full = view(renderer, scene(0.0), 3.0, 3.5, 0.0)
    short = view(renderer, scene(0.2), 3.0, 3.5, 0.0)
    assert reddish_near_center(full) > 0.5, "a full-height wall hides what is behind it"
    assert reddish_near_center(short) < 0.1, "over a short wall the far wall shows"
    assert not np.array_equal(full, short)


def test_the_top_and_the_front_of_a_short_wall_are_drawn(renderer):
    level = hall(width=16, height=7)
    with_wall(level, 6, 3, tile=1, height=0.2)
    world = World(level, 256)
    frame = view(renderer, world, 3.0, 3.5, 0.0)
    # the brick wall is red; some of the picture must be brick: its front and its top
    reds = sum(1 for x in range(0, WIDTH, 4) for y in range(0, HEIGHT, 4) if is_reddish(tuple(int(v) for v in frame[x, y])))
    assert reds > 30


def test_the_renderer_fills_every_pixel_with_short_walls_of_every_height(renderer):
    level = hall(width=16, height=9)
    for i, height in enumerate((0.1, 0.25, 0.5, 1.0, 2.0, 2.9)):
        with_wall(level, 4 + i, 4, tile=1 + i % 3, height=height)
    world = World(level, 256)
    sentinel = np.array((255, 0, 255), np.uint8)
    for x, y, angle, z in ((2.5, 4.5, 0.0, 0.0), (11.5, 4.5, math.pi, 0.0), (6.5, 6.5, -math.pi / 2, 0.0),
                           (6.5, 2.5, math.pi / 2, 0.0)):
        player = physics.Player(x, y, z, angle, span=0)
        fb = np.zeros((WIDTH, HEIGHT, 3), np.uint8)
        fb[:] = sentinel
        render_scene(fb, player.x, player.y, player.eye_z, 0, math.cos(angle), math.sin(angle),
                     -math.sin(angle) * renderer.half_fov_tan, math.cos(angle) * renderer.half_fov_tan,
                     HEIGHT / 2, renderer.focal, world.floor_plane, world.ceil_plane, world.span_on,
                     world.solid_from, world.pane_tex, world.pane_top, world.wall_tex, world.wall_sides, world.floor_tex, world.ceil_tex, renderer.textures,
                     MAX_DEPTH, FOG_DIST, sentinel)
        assert not (fb == sentinel).all(axis=2).any(), f"unfilled pixels from ({x}, {y}) facing {angle}"


# ------------------------------------------------------------------ the editor

def make_editor(tmp_path, size=(1920, 1009)):
    pygame.display.set_mode(size, pygame.RESIZABLE)
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = hall(width=12, height=9)
    editor.mouse = (0, 0)
    editor.fit_view()
    editor.draw(pygame.display.get_surface())
    return editor


@pytest.fixture
def ed(tmp_path):
    return make_editor(tmp_path)


def click(editor, x, y, button=1):
    pos = editor.cell_rect(x, y).center
    editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
    editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))


def press(editor, key):
    editor.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def test_wall_height_is_the_seventh_layer_with_its_own_key_and_button(ed):
    assert map_editor.EDIT_LAYERS[-1] == "wall_h" and map_editor.LAYER_LABELS["wall_h"] == "WallH"
    press(ed, pygame.K_7)
    assert ed.layer == "wall_h"
    assert any(a == "layer:wall_h" for _r, _l, a in ed.layout())
    assert any(a == "val+" for _r, _l, a in ed.layout())            # the height brush buttons show
    assert ed.brush("wall_h") == 0.5                                # a waist-high wall to start with
    for name, key in (("walls", pygame.K_1), ("ramp", pygame.K_6)):  # the other layers' keys are unchanged
        press(ed, key)
        assert ed.layer == name


def test_painting_a_height_sets_walls_and_ignores_open_cells(ed):
    with_wall(ed.level, 5, 4)
    ed.do("layer:wall_h")
    click(ed, 5, 4)
    assert ed.level.grids["wall_h"][4][5] == 0.5 and ed.level.short_wall_top(5, 4) == pytest.approx(0.5)
    click(ed, 3, 3)                                                 # an open cell
    assert ed.level.grids["wall_h"][3][3] == 0.0 and not ed.level.walls[3][3]


def test_the_brush_adjusts_in_steps_and_never_goes_below_the_smallest_height(ed):
    ed.do("layer:wall_h")
    press(ed, pygame.K_RIGHTBRACKET)
    assert ed.brush("wall_h") == 0.75
    for _ in range(10):
        press(ed, pygame.K_LEFTBRACKET)
    assert ed.brush("wall_h") == map_editor.VALUE_STEP              # 0 would mean "full": use Erase for that
    for _ in range(80):
        ed.do("val+")
    assert ed.brush("wall_h") == 8.0


def test_erasing_a_height_puts_the_wall_back_to_full_height(ed):
    with_wall(ed.level, 5, 4, height=0.75)
    ed.do("layer:wall_h")
    click(ed, 5, 4, button=3)
    assert ed.level.grids["wall_h"][4][5] == 0.0 and ed.level.walls[4][5] == 1
    assert ed.level.short_wall_top(5, 4) is None


def test_fill_sets_the_height_of_the_whole_connected_wall(ed):
    for x, tile in ((3, 1), (4, 2), (5, 3)):
        with_wall(ed.level, x, 4, tile=tile)
    with_wall(ed.level, 8, 4)                                       # a separate wall
    ed.do("layer:wall_h")
    ed.do("tool:fill")
    click(ed, 4, 4)
    assert [ed.level.grids["wall_h"][4][x] for x in (3, 4, 5)] == [0.5, 0.5, 0.5]
    assert ed.level.grids["wall_h"][4][8] == 0.0                    # not connected: untouched
    assert ed.level.grids["wall_h"][5][4] == 0.0                    # no heights written on open cells
    click(ed, 6, 6)                                                 # filling an open cell does nothing
    assert "Click a wall" in ed.message
    ed.do("undo")
    assert ed.level.grids["wall_h"][4][4] == 0.0                    # the fill is one undo step


def test_pick_takes_a_walls_height_as_the_brush(ed):
    with_wall(ed.level, 5, 4, height=1.5)
    with_wall(ed.level, 6, 4, height=0.0)
    ed.do("layer:wall_h")
    ed.do("tool:pick")
    click(ed, 5, 4)
    assert ed.brush("wall_h") == 1.5 and ed.tool == "paint"
    ed.do("tool:pick")
    click(ed, 6, 4)                                                 # a full wall has no height to pick
    assert ed.brush("wall_h") == 1.5


def test_a_new_wall_starts_full_height_and_an_erased_wall_forgets_its_height(ed):
    with_wall(ed.level, 5, 4, height=0.5)
    ed.do("layer:walls")
    ed.do("tool:erase")
    click(ed, 5, 4)
    assert not ed.level.walls[4][5] and ed.level.grids["wall_h"][4][5] == 0.0
    ed.level.set("wall_h", 6, 4, 0.75)                              # a stale height left on an open cell
    ed.do("tool:paint")
    click(ed, 6, 4)
    assert ed.level.walls[4][6] and ed.level.grids["wall_h"][4][6] == 0.0     # the new wall is full height


def test_repainting_a_walls_texture_keeps_its_height(ed):
    with_wall(ed.level, 5, 4, tile=1, height=0.5)
    ed.selection = {2}                                              # a different wall tile
    ed.do("layer:walls")
    click(ed, 5, 4)
    assert ed.level.walls[4][5] == 3 and ed.level.grids["wall_h"][4][5] == 0.5


def test_wall_heights_can_be_undone_and_redone(ed):
    with_wall(ed.level, 5, 4)
    ed.do("layer:wall_h")
    click(ed, 5, 4)
    ed.do("undo")
    assert ed.level.grids["wall_h"][4][5] == 0.0
    ed.do("redo")
    assert ed.level.grids["wall_h"][4][5] == 0.5


def test_wall_height_is_shared_by_every_floor(tmp_path):
    editor = make_editor(tmp_path)
    editor.level = Level.blank(12, 9, floors=2)
    with_wall(editor.level, 5, 4)
    editor.do("layer:wall_h")
    editor.do("floor:1")
    click(editor, 5, 4)
    assert editor.gname("wall_h") == "wall_h" and editor.level.grids["wall_h"][4][5] == 0.5
    editor.do("floor:0")
    assert editor.level.grids["wall_h"][4][5] == 0.5


def test_hover_text_describes_a_walls_height(ed):
    with_wall(ed.level, 5, 4, height=0.5)
    with_wall(ed.level, 6, 4, height=0.0)
    with_wall(ed.level, 7, 4, height=9.0)
    for x, expect in ((5, "short: 0.5 high"), (6, "full height"), (7, "reaches the ceiling")):
        ed.mouse = ed.cell_rect(x, 4).center
        assert expect in ed.hover_info()


def test_the_wall_height_layer_and_short_wall_marks_draw(ed):
    with_wall(ed.level, 5, 4, height=0.5)
    with_wall(ed.level, 6, 4, height=0.0)
    surface = pygame.display.get_surface()
    ed.do("layer:walls")
    ed.draw(surface)
    cell = ed.cell_rect(5, 4)
    assert surface.get_at((cell.centerx, cell.bottom - 6))[:3] == map_editor.SHORT_WALL    # the cyan bar
    full = ed.cell_rect(6, 4)
    assert surface.get_at((full.centerx, full.bottom - 6))[:3] != map_editor.SHORT_WALL
    ed.do("layer:wall_h")
    ed.draw(surface)
    assert surface.get_at((full.left + 2, full.top + 2))[:3] == map_editor.WALL_FULL      # full walls
    assert surface.get_at((cell.left + 2, cell.top + 2))[:3] != map_editor.WALL_FULL      # short ones: by height
    open_cell = ed.cell_rect(3, 3)
    assert surface.get_at((open_cell.centerx, open_cell.centery))[:3] == map_editor.EMPTY_CELL


def test_the_key_explains_the_short_wall_bar_and_the_wall_height_colors(ed):
    kinds = lambda: [k for k, _t in ed.legend_entries()]
    assert "short_wall" not in kinds()                              # no short walls yet
    with_wall(ed.level, 5, 4, height=0.5)
    ed.revision += 1
    assert "short_wall" in kinds() and "wall_dim" not in kinds()    # on the Walls layer walls aren't dimmed
    ed.do("layer:floor_tex")
    assert {"short_wall", "wall_dim"} <= set(kinds())
    ed.do("layer:wall_h")
    assert "short_wall" not in kinds() and "wall_full" in kinds() and "heat" in kinds()
    assert "wall_dim" not in kinds()
    surface = pygame.display.get_surface()
    ed.do("layer:floor_tex")
    ed.draw(surface)
    rect, columns, _docked = ed.legend_layout()
    entries = ed.legend_entries()
    per_column = (len(entries) + columns - 1) // columns
    i = [k for k, _t in entries].index("short_wall")
    column, row = divmod(i, per_column)
    box = pygame.Rect(rect.x + 10 + column * (rect.w // columns),
                      rect.y + map_editor.LEGEND_TITLE + row * map_editor.LEGEND_ROW
                      + (map_editor.LEGEND_ROW - map_editor.LEGEND_ICON) // 2,
                      map_editor.LEGEND_ICON, map_editor.LEGEND_ICON)
    colors = {tuple(surface.get_at((x, y)))[:3] for x in range(box.left, box.right) for y in range(box.top, box.bottom)}
    assert map_editor.SHORT_WALL in colors                         # the same bar as on the map


def test_every_layer_draws_with_short_walls_on_every_floor(tmp_path):
    editor = make_editor(tmp_path)
    editor.level = Level.blank(12, 9, floors=3)
    with_wall(editor.level, 5, 4, height=0.5)
    with_wall(editor.level, 6, 4, height=2.5)
    surface = pygame.display.get_surface()
    for floor in range(3):
        editor.do(f"floor:{floor}")
        for name in map_editor.EDIT_LAYERS:
            editor.do(f"layer:{name}")
            editor.draw(surface)


# ------------------------------------------------------------------ walls at the edge of the map

def test_the_outer_border_walls_take_a_height_like_any_other_wall(tmp_path):
    editor = make_editor(tmp_path)
    editor.do("layer:wall_h")
    editor.do("tool:fill")
    for cell in ((0, 4), (11, 4), (5, 0), (5, 8)):                # left, right, top and bottom borders
        pos = editor.cell_rect(*cell).center
        editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
        editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
    # the border is one connected wall, so Fill set all of it
    level = editor.level
    border = [(x, y) for y in range(level.height) for x in range(level.width)
              if x in (0, level.width - 1) or y in (0, level.height - 1)]
    assert all(level.grids["wall_h"][y][x] == 0.5 for x, y in border)
    assert all(level.short_wall_top(x, y) == pytest.approx(0.5) for x, y in border)   # corners too
    world = World(level, 256)
    assert all(world.solid[y, x] == 0 and world.floor_of(0, x + 0.5, y + 0.5) == pytest.approx(0.5)
               for x, y in border)


def test_painting_a_height_on_one_left_border_wall_changes_only_that_wall(tmp_path):
    editor = make_editor(tmp_path)
    editor.do("layer:wall_h")
    click(editor, 0, 4)
    heights = {(x, y): editor.level.grids["wall_h"][y][x] for y in range(9) for x in range(12)}
    assert heights[(0, 4)] == 0.5
    assert all(v == 0.0 for cell, v in heights.items() if cell != (0, 4))
    assert editor.level.short_wall_top(0, 4) == pytest.approx(0.5)
    assert editor.level.short_wall_top(0, 3) is None                  # its neighbors stay full height
    editor.draw(pygame.display.get_surface())
    rect = editor.cell_rect(0, 4)
    assert pygame.display.get_surface().get_at((rect.left + 3, rect.top + 3))[:3] != map_editor.WALL_FULL


def test_a_stored_floor_height_under_an_edge_wall_does_not_make_it_full(tmp_path):
    editor = make_editor(tmp_path)
    editor.level = hall(width=12, height=9, ceiling=1.5)
    for y in range(9):
        editor.level.set("floor_h", 0, y, 1.0)                    # e.g. left over from a FloorH fill
    editor.do("layer:wall_h")
    click(editor, 0, 4)
    assert editor.level.short_wall_top(0, 4) == pytest.approx(0.5)
    editor.draw(pygame.display.get_surface())
    rect = editor.cell_rect(0, 4)
    assert pygame.display.get_surface().get_at((rect.left + 3, rect.top + 3))[:3] != map_editor.WALL_FULL
