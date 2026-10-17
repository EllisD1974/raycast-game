import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
from mapfile import DEFAULTS, Level, load_level


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1280, 800), pygame.RESIZABLE)
    yield
    pygame.quit()


@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))     # file doesn't exist: default map
    editor.level = Level.blank(10, 10, floors=2)
    editor.level.start_x = editor.level.start_y = 1.5
    editor.show_legend = False                       # the key has its own tests; keep it off the cells
    editor.draw(pygame.display.get_surface())
    return editor


def mouse(ed, kind, pos, button=1, rel=(0, 0)):
    if kind == pygame.MOUSEMOTION:
        ed.handle_event(pygame.event.Event(kind, pos=pos, rel=rel, buttons=(1, 0, 0)))
    else:
        ed.handle_event(pygame.event.Event(kind, pos=pos, button=button))


def atlas_pos(col, row):
    return (map_editor.ATLAS_X + col * 32 + 5, map_editor.ATLAS_Y + row * 32 + 5)


def select(ed, a, b=None):
    mouse(ed, pygame.MOUSEBUTTONDOWN, atlas_pos(*a))
    if b:
        mouse(ed, pygame.MOUSEMOTION, atlas_pos(*b))
    mouse(ed, pygame.MOUSEBUTTONUP, atlas_pos(*(b or a)))


def cell_pos(ed, x, y):
    return ed.cell_rect(x, y).center


def click(ed, x, y, button=1):
    mouse(ed, pygame.MOUSEBUTTONDOWN, cell_pos(ed, x, y), button=button)
    mouse(ed, pygame.MOUSEBUTTONUP, cell_pos(ed, x, y), button=button)


def key(ed, k, mod=0):
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod))


def test_click_selects_single_tile_and_drag_selects_rectangle(ed):
    select(ed, (5, 0))
    assert ed.selection == {5}
    select(ed, (1, 0), (2, 1))
    assert ed.selection == {1, 2, 17, 18}
    assert ed.stamp() == [(0, 0, 2), (1, 0, 3), (0, 1, 18), (1, 1, 19)]


def test_ctrl_adds_and_removes_tiles(ed):
    select(ed, (3, 0))
    ed.mods = lambda: pygame.KMOD_CTRL
    select(ed, (7, 0))
    assert ed.selection == {3, 7}
    select(ed, (3, 0))                          # Ctrl+click a selected tile removes it
    assert ed.selection == {7}


def test_paint_stamp_erase_and_undo(ed):
    select(ed, (1, 0), (2, 1))
    click(ed, 3, 3)
    walls = ed.level.walls
    assert [walls[3][3:5], walls[4][3:5]] == [[2, 3], [18, 19]]
    click(ed, 3, 3, button=3)                   # right click erases
    assert walls[3][3] == 0 and walls[3][4] == 3
    ed.do("undo")
    assert ed.level.walls[3][3] == 2
    ed.do("undo")
    assert ed.level.walls[3][3] == 0 and ed.level.walls[3][4] == 0
    ed.do("redo")
    assert ed.level.walls[3][3] == 2


def test_drag_paints_a_continuous_line(ed):
    select(ed, (4, 0))
    mouse(ed, pygame.MOUSEBUTTONDOWN, cell_pos(ed, 2, 5))
    mouse(ed, pygame.MOUSEMOTION, cell_pos(ed, 7, 5))                   # fast jump across cells
    mouse(ed, pygame.MOUSEBUTTONUP, cell_pos(ed, 7, 5))
    assert ed.level.walls[5][2:8] == [5] * 6


def test_texture_layers_paint_floor_and_ceiling_tiles(ed):
    select(ed, (2, 0))
    ed.do("layer:floor_tex")
    click(ed, 4, 4)
    assert ed.level.grids["floor_tex"][4][4] == 3 and ed.level.walls[4][4] == 0
    ed.do("layer:ceil_tex")
    click(ed, 4, 4)
    assert ed.level.grids["ceil_tex"][4][4] == 3
    click(ed, 4, 4, button=3)                   # erase restores the layer default
    assert ed.level.grids["ceil_tex"][4][4] == DEFAULTS["ceil_tex"]


def test_height_layers_paint_adjust_pick_and_fill(ed):
    ed.do("layer:floor_h")
    key(ed, pygame.K_RIGHTBRACKET)              # brush 0.5 -> 0.75
    key(ed, pygame.K_RIGHTBRACKET)              # -> 1.0
    assert ed.value["floor_h"] == 1.0
    click(ed, 3, 3)
    assert ed.level.grids["floor_h"][3][3] == 1.0
    click(ed, 3, 3, button=3)
    assert ed.level.grids["floor_h"][3][3] == DEFAULTS["floor_h"]
    ed.do("layer:ceil_h")
    ed.do("tool:fill")
    click(ed, 5, 5)                             # fill the whole open interior with the ceiling brush
    assert ed.level.grids["ceil_h"][5][5] == 2.0 and ed.level.grids["ceil_h"][8][8] == 2.0
    ed.value["ceil_h"] = 0.0
    ed.do("tool:pick")
    click(ed, 5, 5)
    assert ed.value["ceil_h"] == 2.0 and ed.tool == "paint"


def test_stairs_tool_raises_heights_along_a_dragged_line(ed):
    ed.layer = "walls"
    ed.do("tool:stairs")
    mouse(ed, pygame.MOUSEBUTTONDOWN, cell_pos(ed, 2, 2))
    assert ed.layer == "floor_h"                # stairs switch to the height layer
    mouse(ed, pygame.MOUSEMOTION, cell_pos(ed, 5, 2))
    mouse(ed, pygame.MOUSEBUTTONUP, cell_pos(ed, 5, 2))
    assert ed.level.grids["floor_h"][2][2:6] == [0.5, 0.75, 1.0, 1.25]
    ed.do("undo")
    assert ed.level.grids["floor_h"][2][2:6] == [0.0] * 4


def test_ramp_layer_paints_direction_and_rotates(ed):
    ed.do("layer:ramp")
    click(ed, 3, 3)
    assert ed.level.grids["ramp"][3][3] == 1
    key(ed, pygame.K_r)
    click(ed, 4, 3)
    assert ed.level.grids["ramp"][3][4] == 2
    ed.do("tool:fill")
    click(ed, 6, 6)
    assert ed.level.grids["ramp"][7][7] == 2


def test_fill_border_start_and_resize_buttons(ed):
    select(ed, (9, 0))
    ed.do("border")
    assert set(ed.level.walls[0]) == {10}
    ed.do("tool:start")
    click(ed, 3, 2)
    assert (ed.level.start_x, ed.level.start_y) == (3.5, 2.5)
    click(ed, 3, 2)                             # same cell: rotate 90 deg
    assert ed.level.start_angle == pytest.approx(3.14159 / 2, abs=1e-3)
    ed.do("edge:R+")
    ed.do("edge:B-")
    assert (ed.level.width, ed.level.height) == (11, 9)
    assert all(len(g) == 9 and len(g[0]) == 11 for g in ed.level.grids.values())


def test_save_reload_and_discard_confirmation(ed):
    select(ed, (2, 0))
    click(ed, 5, 5)
    assert ed.dirty
    ed.do("reload")                             # unsaved: first click only asks for confirmation
    assert ed.dirty and ed.level.walls[5][5] == 3
    ed.do("save")
    assert not ed.dirty and load_level(ed.path).walls[5][5] == 3
    ed.level.walls[5][5] = 0
    ed.dirty = True
    ed.do("reload")
    ed.do("reload")                             # second click discards and reloads from disk
    assert ed.level.walls[5][5] == 3 and not ed.dirty


def test_quit_requires_confirmation_when_dirty(ed):
    ed.touch()
    ed.request_quit()
    assert ed.running
    ed.request_quit()
    assert not ed.running


def test_zoom_keeps_cell_under_cursor(ed):
    area = ed.map_area()
    ed.mouse = (area.x + 200, area.y + 150)
    before = ed.cell_at(ed.mouse)
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=2))
    assert ed.zoom != 32
    assert ed.cell_at(ed.mouse) == before


def test_every_layer_draws_without_error(ed):
    ed.level.set("ramp", 3, 3, 1)
    surface = pygame.display.get_surface()
    for name in map_editor.EDIT_LAYERS:
        ed.do(f"layer:{name}")
        ed.draw(surface)


# ------------------------------------------------------------------ the second floor

def test_tab_steps_through_the_floors_and_wraps(ed):
    assert ed.floor == 0
    key(ed, pygame.K_TAB)
    assert ed.floor == 1 and ed.gname("floor_h") == "floor_h2" and ed.gname("walls") == "walls"
    key(ed, pygame.K_TAB)                        # wraps back to the ground floor
    assert ed.floor == 0
    key(ed, pygame.K_TAB, mod=pygame.KMOD_SHIFT)  # Shift+Tab goes backwards, wrapping
    assert ed.floor == 1


def test_painting_floor_height_on_floor_2_creates_a_room(ed):
    ed.do("floor:1")
    ed.do("layer:floor_h")
    assert not ed.level.span_present(1, 4, 4)
    click(ed, 4, 4)                              # brush: floor 1.5, ceiling brush 3.0
    g = ed.level.grids
    assert (g["floor_h2"][4][4], g["ceil_h2"][4][4]) == (1.5, 3.0)
    assert ed.level.span_present(1, 4, 4)
    assert g["floor_h"][4][4] == 0.0              # Floor 1 untouched
    assert ed.level.problems() == []


def test_painting_ceiling_on_floor_2_first_uses_the_floor_brush(ed):
    ed.do("floor:1")
    ed.do("layer:ceil_h")
    click(ed, 5, 5)
    g = ed.level.grids
    assert (g["floor_h2"][5][5], g["ceil_h2"][5][5]) == (1.5, 3.0)
    ed.value["ceil_h2"] = 1.0                     # too low for a room above a 1.5 floor
    click(ed, 6, 5)
    assert g["ceil_h2"][5][6] == 1.0 and g["floor_h2"][5][6] == pytest.approx(-0.5)


def test_new_upper_floor_lowers_the_lower_ceiling_into_a_slab(ed):
    ed.level.grids["ceil_h"] = [[3.0] * 10 for _ in range(10)]          # tall ground floor
    ed.do("floor:1")
    ed.do("layer:floor_h")
    click(ed, 4, 4)
    assert ed.level.grids["ceil_h"][4][4] == pytest.approx(1.25)        # 1.5 minus a 0.25 slab
    assert ed.level.grids["ceil_h"][4][5] == 3.0                        # neighbours unchanged
    assert ed.level.problems() == []


def test_erasing_a_floor_2_height_removes_the_room(ed):
    ed.do("floor:1")
    ed.do("layer:floor_h")
    click(ed, 4, 4)
    click(ed, 4, 4, button=3)
    assert not ed.level.span_present(1, 4, 4)
    assert ed.level.grids["floor_h2"][4][4] == 0.0 and ed.level.grids["ceil_h2"][4][4] == 0.0


def test_fill_on_floor_2_makes_rooms_but_not_inside_walls(ed):
    ed.do("floor:1")
    ed.do("layer:floor_h")
    ed.do("tool:fill")
    click(ed, 5, 5)
    assert ed.level.span_present(1, 5, 5) and ed.level.span_present(1, 1, 8)
    assert not ed.level.span_present(1, 0, 0)                           # the border wall
    assert ed.level.grids["floor_h2"][0][0] == 0.0                      # no data written under walls
    ed.do("undo")
    assert not ed.level.span_present(1, 5, 5)


def test_stairs_on_floor_2_create_rooms_with_rising_floors(ed):
    ed.do("floor:1")
    ed.do("tool:stairs")
    mouse(ed, pygame.MOUSEBUTTONDOWN, cell_pos(ed, 2, 3))
    assert ed.layer == "floor_h"
    mouse(ed, pygame.MOUSEMOTION, cell_pos(ed, 5, 3))
    mouse(ed, pygame.MOUSEBUTTONUP, cell_pos(ed, 5, 3))
    assert ed.level.grids["floor_h2"][3][2:6] == [1.5, 1.75, 2.0, 2.25]
    assert all(ed.level.span_present(1, x, 3) for x in range(2, 6))
    assert ed.level.grids["floor_h"][3][2:6] == [0.0] * 4               # Floor 1 untouched


def test_ramp_and_texture_layers_write_the_floor_2_grids(ed):
    ed.do("floor:1")
    ed.do("layer:ramp")
    click(ed, 3, 3)
    assert ed.level.grids["ramp2"][3][3] == 1 and ed.level.grids["ramp"][3][3] == 0
    select(ed, (2, 0))
    ed.do("layer:floor_tex")
    click(ed, 4, 4)
    assert ed.level.grids["floor_tex2"][4][4] == 3 and ed.level.grids["floor_tex"][4][4] == 5
    click(ed, 4, 4, button=3)
    assert ed.level.grids["floor_tex2"][4][4] == 3                      # default wood
    ed.do("layer:ceil_tex")
    select(ed, (1, 0))
    ed.do("layer:ceil_tex")
    click(ed, 4, 4)
    assert ed.level.grids["ceil_tex2"][4][4] == 2


def test_start_can_be_placed_on_floor_2_only_where_there_is_a_room(ed):
    ed.do("floor:1")
    ed.do("tool:start")
    click(ed, 3, 3)
    assert ed.level.start_span == 0                                      # refused: no room there
    ed.do("layer:floor_h")
    ed.do("tool:paint")
    click(ed, 3, 3)
    ed.do("tool:start")
    click(ed, 3, 3)
    assert ed.level.start_span == 1 and (ed.level.start_x, ed.level.start_y) == (3.5, 3.5)
    assert ed.level.problems() == []
    ed.do("floor:0")
    ed.do("tool:start")
    click(ed, 6, 6)
    assert ed.level.start_span == 0


def test_floor_2_data_survives_save_and_reload(ed):
    ed.do("floor:1")
    ed.do("layer:floor_h")
    click(ed, 4, 4)
    ed.do("save")
    again = load_level(ed.path)
    assert again.span_present(1, 4, 4) and again.grids["floor_h2"][4][4] == 1.5


def test_both_floors_draw_every_layer_without_error(ed):
    ed.do("layer:floor_h")
    ed.do("floor:1")
    click(ed, 4, 4)
    ed.level.set("ramp2", 5, 4, 1)
    surface = pygame.display.get_surface()
    for floor in (0, 1):
        ed.do(f"floor:{floor}")
        for name in map_editor.EDIT_LAYERS:
            ed.do(f"layer:{name}")
            ed.draw(surface)


def test_escape_does_not_quit_the_editor(ed):
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert ed.running
    ed.handle_event(pygame.event.Event(pygame.QUIT))            # closing the window still quits
    assert not ed.running
