"""Setting the ceiling over a wall that is not full height (a short wall or a see-through one)."""
import json
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
from atlas import transparent_tiles
from constants import HEIGHT, WIDTH
from mapfile import DEFAULTS, FORMAT_VERSION, MAP_PATH, Level, load_level, save_level
from world import World

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1920, 1009), pygame.RESIZABLE)
    yield
    pygame.quit()


def hall(width=14, height=9, ceiling=3.0):
    level = Level.blank(width, height)
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            level.set("ceil_h", x, y, ceiling)
    level.start_x, level.start_y = 2.5, height // 2 + 0.5
    return level


def short_wall(level, x, y, height=0.5, tile=1):
    level.set("walls", x, y, tile)
    level.set("wall_h", x, y, height)
    return level


# ------------------------------------------------------------------ the map data

def test_every_map_has_a_wall_ceiling_grid_that_starts_automatic():
    for level in (Level.blank(6, 5), Level.blank(6, 5, floors=3)):
        assert level.grids["wall_ceil"] == [[0.0] * 6 for _ in range(5)]
    assert DEFAULTS["wall_ceil"] == 0.0 and "wall_ceil" in Level.blank(4, 4).grid_names()


def test_the_ceiling_over_a_wall_is_automatic_until_one_is_set():
    level = short_wall(hall(ceiling=3.0), 5, 4)
    assert level.wall_ceiling(5, 4) == 3.0 and level.auto_wall_ceiling(5, 4) == 3.0
    assert not level.has_explicit_wall_ceiling(5, 4)
    level.set("wall_ceil", 5, 4, 1.5)
    assert level.wall_ceiling(5, 4) == 1.5 and level.has_explicit_wall_ceiling(5, 4)
    assert level.auto_wall_ceiling(5, 4) == 3.0                     # still what automatic would give
    level.set("wall_ceil", 5, 4, 0.0)
    assert level.wall_ceiling(5, 4) == 3.0 and not level.has_explicit_wall_ceiling(5, 4)


def test_the_ceiling_stored_under_a_wall_by_other_tools_is_never_used():
    level = short_wall(hall(ceiling=3.0), 5, 4)
    for stored in (0.5, 1.0, 2.0, 9.0):
        level.set("ceil_h", 5, 4, stored)                          # e.g. left by a CeilH fill or default
        assert level.wall_ceiling(5, 4) == 3.0, f"ceil_h {stored} under the wall mattered"


def test_a_set_ceiling_decides_whether_the_wall_counts_as_short():
    level = short_wall(hall(ceiling=3.0), 5, 4, height=1.0)
    assert level.short_wall_top(5, 4) == pytest.approx(1.0)
    level.set("wall_ceil", 5, 4, 1.0)                              # no room above the wall: it reaches the ceiling
    assert level.short_wall_top(5, 4) is None
    level.set("wall_ceil", 5, 4, 2.0)
    assert level.short_wall_top(5, 4) == pytest.approx(1.0)


def test_wall_ceilings_survive_save_load_and_resize(tmp_path):
    level = short_wall(hall(), 5, 4)
    level.set("wall_ceil", 5, 4, 1.75)
    path = str(tmp_path / "m.json")
    save_level(path, level)
    again = load_level(path)
    assert again.grids["wall_ceil"] == level.grids["wall_ceil"] and again.wall_ceiling(5, 4) == 1.75
    assert json.load(open(path))["version"] == FORMAT_VERSION
    again.resize(20, 12)
    assert again.grids["wall_ceil"][4][5] == 1.75 and again.grids["wall_ceil"][11][19] == 0.0


def test_files_from_before_wall_ceilings_load_with_every_ceiling_automatic(tmp_path):
    level = short_wall(hall(), 5, 4)
    path = tmp_path / "old.json"
    save_level(str(path), level)
    data = json.load(open(path))
    del data["grids"]["wall_ceil"]                                 # what a version 5 file looks like
    data["version"] = 5
    json.dump(data, open(path, "w"))
    again = load_level(str(path))
    assert all(v == 0.0 for row in again.grids["wall_ceil"] for v in row)
    assert again.wall_ceiling(5, 4) == 3.0


def test_the_real_map_file_still_loads():
    level = load_level(MAP_PATH)
    assert len(level.grids["wall_ceil"]) == level.height


# ------------------------------------------------------------------ the world and the player

def test_the_world_uses_the_set_ceiling_for_short_walls_and_for_panes():
    level = short_wall(hall(ceiling=3.0), 5, 4)
    level.set("wall_ceil", 5, 4, 1.5)
    short_wall(level, 8, 4, tile=2)                                 # a see-through wall (tile 2 below)
    level.set("wall_h", 8, 4, 0.0)
    level.set("wall_ceil", 8, 4, 2.0)
    transparent = np.array([False, True])
    world = World(level, 2, transparent)
    assert world.ceil_of(0, 5.5, 4.5) == pytest.approx(1.5)         # over the short wall
    assert world.ceil_of(0, 8.5, 4.5) == pytest.approx(2.0)         # inside the pane's cell
    assert world.ceil_of(0, 4.5, 4.5) == pytest.approx(3.0)         # open cells beside them unchanged


def test_a_low_ceiling_over_a_short_wall_stops_the_player_hopping_onto_it():
    def hop(wall_ceiling):
        level = short_wall(hall(), 6, 4, height=0.5)
        level.set("wall_ceil", 6, 4, wall_ceiling)
        world = World(level, 256)
        player = physics.Player(5.0, 4.5, 0.0, 0.0, span=0)
        on_top = False
        for tick in range(120):
            physics.step(world, player, 1.0, 0.0, 0.0, tick == 0, DT)
            on_top |= player.on_ground and 6.0 < player.x < 7.0 and player.z == pytest.approx(0.5, abs=1e-3)
        return on_top
    assert hop(0.0)                                                 # automatic (3.0): plenty of headroom
    assert hop(2.0)
    assert not hop(1.0)                                             # 0.5 wall + 0.5 left: the player won't fit


# ------------------------------------------------------------------ what you see

@pytest.fixture(scope="module")
def renderer():
    from atlas import atlas_array, unpack_atlas
    return main.Renderer(atlas_array(unpack_atlas()))


def frame(renderer, world, x, y, angle, z=0.0):
    renderer.draw(world, physics.Player(x, y, z, angle, span=0))
    return np.array(renderer.framebuffer, dtype=np.int32)


def test_the_ceiling_over_a_short_wall_shows_when_you_look_up_at_it(renderer):
    def view(wall_ceiling):
        level = short_wall(hall(width=14, height=9, ceiling=3.0), 6, 4, height=0.5)
        level.set("wall_ceil", 6, 4, wall_ceiling)
        return frame(renderer, World(level, 256), 3.5, 4.5, 0.0)
    auto, low = view(0.0), view(1.0)
    assert not np.array_equal(auto, low)                            # a lower ceiling over the wall is visible
    # the cell's ceiling is lower, so the hall's ceiling now steps down above the wall
    assert np.abs(auto - low).sum(axis=2).any()


# ------------------------------------------------------------------ the editor

def make_editor(tmp_path, size=(1920, 1009)):
    pygame.display.set_mode(size, pygame.RESIZABLE)
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = hall(width=12, height=9, ceiling=3.0)
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


def test_painting_the_ceiling_layer_on_a_short_wall_sets_the_ceiling_over_it(ed):
    short_wall(ed.level, 5, 4)
    stored_before = ed.level.grids["ceil_h"][4][5]                  # whatever is stored under the wall
    ed.do("layer:ceil_h")
    ed.value["ceil_h"] = 1.5
    click(ed, 5, 4)
    assert ed.level.grids["wall_ceil"][4][5] == 1.5 and ed.level.wall_ceiling(5, 4) == 1.5
    assert World(ed.level, 256).ceil_of(0, 5.5, 4.5) == pytest.approx(1.5)
    assert ed.level.grids["ceil_h"][4][5] == stored_before          # the value under the wall was not written
    assert ed.level.grids["ceil_h"][4][4] == 3.0                    # and the open cells are untouched


def test_painting_the_ceiling_layer_on_open_cells_still_sets_their_ceiling(ed):
    ed.do("layer:ceil_h")
    ed.value["ceil_h"] = 2.25
    click(ed, 4, 3)
    assert ed.level.grids["ceil_h"][3][4] == 2.25 and ed.level.grids["wall_ceil"][3][4] == 0.0


def test_erasing_a_walls_ceiling_puts_it_back_to_automatic(ed):
    short_wall(ed.level, 5, 4)
    ed.level.set("wall_ceil", 5, 4, 1.5)
    ed.do("layer:ceil_h")
    click(ed, 5, 4, button=3)
    assert ed.level.grids["wall_ceil"][4][5] == 0.0 and ed.level.wall_ceiling(5, 4) == 3.0


def test_pick_takes_the_ceiling_over_a_wall_as_the_brush(ed):
    short_wall(ed.level, 5, 4)
    ed.level.set("wall_ceil", 5, 4, 1.75)
    ed.do("layer:ceil_h")
    ed.do("tool:pick")
    click(ed, 5, 4)
    assert ed.brush("ceil_h") == 1.75
    short_wall(ed.level, 6, 4)
    ed.do("tool:pick")
    click(ed, 6, 4)                                                 # automatic: the ceiling it has now
    assert ed.brush("ceil_h") == 3.0


def test_a_ceiling_over_a_full_height_wall_is_stored_with_an_explanation(ed):
    ed.level.set("walls", 5, 4, 1)                                  # full height
    ed.do("layer:ceil_h")
    ed.value["ceil_h"] = 1.5
    click(ed, 5, 4)
    assert ed.level.grids["wall_ceil"][4][5] == 1.5
    assert "full-height wall reaches the ceiling anyway" in ed.message
    assert ed.level.short_wall_top(5, 4) is None                    # and the wall is still full height


def test_shortening_the_wall_afterwards_uses_the_ceiling_that_was_set(ed):
    ed.level.set("walls", 5, 4, 1)
    ed.do("layer:ceil_h")
    ed.value["ceil_h"] = 2.0
    click(ed, 5, 4)
    ed.do("layer:wall_h")
    click(ed, 5, 4)                                                 # height 0.5
    assert ed.level.short_wall_top(5, 4) == pytest.approx(0.5) and ed.level.wall_ceiling(5, 4) == 2.0


def test_erasing_a_wall_forgets_its_height_and_its_ceiling(ed):
    short_wall(ed.level, 5, 4)
    ed.level.set("wall_ceil", 5, 4, 1.5)
    ed.do("layer:walls")
    ed.do("tool:erase")
    click(ed, 5, 4)
    assert not ed.level.walls[4][5]
    assert ed.level.grids["wall_h"][4][5] == 0.0 and ed.level.grids["wall_ceil"][4][5] == 0.0


def test_wall_ceilings_can_be_undone_and_redone(ed):
    short_wall(ed.level, 5, 4)
    ed.do("layer:ceil_h")
    ed.value["ceil_h"] = 1.5
    click(ed, 5, 4)
    ed.do("undo")
    assert ed.level.grids["wall_ceil"][4][5] == 0.0
    ed.do("redo")
    assert ed.level.grids["wall_ceil"][4][5] == 1.5


def test_on_an_upper_floor_the_ceiling_layer_does_not_touch_wall_ceilings(tmp_path):
    editor = make_editor(tmp_path)
    editor.level = Level.blank(12, 9, floors=2)
    short_wall(editor.level, 5, 4)
    editor.do("floor:1")
    editor.do("layer:ceil_h")
    assert not editor.edits_wall_ceiling(5, 4)
    click(editor, 5, 4)
    assert editor.level.grids["wall_ceil"][4][5] == 0.0


def test_the_ceiling_layer_shows_the_ceiling_over_short_walls_set_or_automatic(ed):
    short_wall(ed.level, 5, 4)                                      # automatic
    short_wall(ed.level, 7, 4)
    ed.level.set("wall_ceil", 7, 4, 1.5)                            # set
    ed.level.set("walls", 9, 4, 1)                                  # a full wall: nothing to show
    ed.revision += 1
    surface = pygame.display.get_surface()
    ed.do("layer:ceil_h")
    ed.draw(surface)
    auto, explicit, full = ed.cell_rect(5, 4), ed.cell_rect(7, 4), ed.cell_rect(9, 4)
    heat_auto = map_editor.heat(3.0, *map_editor.HEIGHT_RANGE["ceil_h"])
    heat_set = map_editor.heat(1.5, *map_editor.HEIGHT_RANGE["ceil_h"])
    assert surface.get_at((auto.left + 3, auto.top + 3))[:3] == tuple(c * 2 // 3 for c in heat_auto)   # duller: automatic
    assert surface.get_at((explicit.left + 3, explicit.top + 3))[:3] == heat_set                     # full color: set
    assert surface.get_at((full.left + 3, full.top + 3))[:3] not in (heat_auto, heat_set)            # a plain dimmed wall
    ed.do("layer:walls")
    ed.draw(surface)                                                 # other layers do not show it
    assert surface.get_at((auto.left + 3, auto.top + 3))[:3] != tuple(c * 2 // 3 for c in heat_auto)


def test_hover_text_describes_the_ceiling_over_a_wall(ed):
    short_wall(ed.level, 5, 4)
    short_wall(ed.level, 7, 4)
    ed.level.set("wall_ceil", 7, 4, 1.5)
    ed.level.set("walls", 9, 4, 1)
    for x, expect in ((5, "ceiling over it 3 (automatic)"), (7, "ceiling over it 1.5 (set)")):
        ed.mouse = ed.cell_rect(x, 4).center
        assert expect in ed.hover_info()
    ed.mouse = ed.cell_rect(9, 4).center
    assert "ceiling over it" not in ed.hover_info()


def test_the_key_explains_the_bracketed_numbers_only_on_the_ceiling_layer(ed):
    kinds = lambda: [k for k, _t in ed.legend_entries()]
    short_wall(ed.level, 5, 4)
    ed.revision += 1
    assert "wall_ceiling" not in kinds()                            # not on the Walls layer
    ed.do("layer:ceil_h")
    assert "wall_ceiling" in kinds()
    ed.do("floor:0")
    ed.level.set("walls", 5, 4, 0)
    ed.revision += 1
    assert "wall_ceiling" not in kinds()                            # no wall shows a number any more


def test_every_layer_draws_with_wall_ceilings_set_on_every_floor(tmp_path):
    editor = make_editor(tmp_path)
    editor.level = Level.blank(12, 9, floors=3)
    short_wall(editor.level, 5, 4)
    editor.level.set("wall_ceil", 5, 4, 1.25)
    surface = pygame.display.get_surface()
    for floor in range(3):
        editor.do(f"floor:{floor}")
        for name in map_editor.EDIT_LAYERS:
            editor.do(f"layer:{name}")
            editor.draw(surface)
