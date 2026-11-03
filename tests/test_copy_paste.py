"""Copying an area of one floor and pasting it elsewhere (any floor, any map)."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
from mapfile import Entity, Level, Spawner, clear_area, copy_area, grid_name, paste_area, save_level


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1920, 1009), pygame.RESIZABLE)
    yield
    pygame.quit()


def two_floors():
    """16 x 12, two floors. Floor 0: a wall at (3, 3) with a side tile, floor tile 7 at (2, 2), a raised cell, an
    item and a spawn point. Floor 1: a room over (2..4, 2..4) with a wall of its own at (4, 4)."""
    level = Level.blank(16, 12, floors=2)
    level.walls[3][3] = 2
    level.grids["side_s"][3][3] = 9
    level.grids["floor_tex"][2][2] = 7
    level.grids["floor_h"][2][4] = 0.5
    level.entities = [Entity(2.5, 4.5, tile=3), Entity(9.5, 9.5, tile=4)]
    level.spawners = [Spawner(4.5, 2.5, order=1)]
    for y in range(2, 5):
        for x in range(2, 5):
            level.grids["floor_h2"][y][x], level.grids["ceil_h2"][y][x] = 1.4, 2.4
    level.walls[4][4], level.grids["wall_floor"][4][4] = 5, 1          # a wall standing on floor 1
    level.entities.append(Entity(3.5, 3.5, span=1, tile=6))
    return level


# ------------------------------------------------------------------ the area itself

def test_an_area_holds_its_floors_grids_walls_items_and_spawn_points():
    level = two_floors()
    area = copy_area(level, (4, 4), (2, 2), 0)                         # (corners either way round)
    assert (area.width, area.height, area.floor) == (3, 3, 0)
    assert area.span["floor_tex"][0][0] == 7 and area.span["floor_h"][0][2] == 0.5
    assert set(area.walls) == {(1, 1)}                                 # only floor 0's wall, not floor 1's at (4, 4)
    assert area.walls[(1, 1)]["walls"] == 2 and area.walls[(1, 1)]["side_s"] == 9
    assert [(e.x, e.y) for e in area.entities] == [(0.5, 2.5)] and [(s.x, s.y) for s in area.spawners] == [(2.5, 0.5)]
    upper = copy_area(level, (2, 2), (4, 4), 1)
    assert set(upper.walls) == {(2, 2)} and len(upper.entities) == 1 and upper.span["ceil_h"][1][1] == 2.4


def test_pasting_puts_the_area_down_in_place_of_what_was_there():
    level = two_floors()
    level.walls[10][8] = 1                                             # something in the way, to be replaced
    area = copy_area(level, (2, 2), (4, 4), 0)
    paste_area(level, area, 8, 8, 0)
    assert level.walls[9][9] == 2 and level.grids["side_s"][9][9] == 9 and level.grids["floor_tex"][8][8] == 7
    assert level.grids["floor_h"][8][10] == 0.5
    assert level.walls[10][8] == 0                                     # the area had no wall there
    assert sorted((e.x, e.y) for e in level.entities if e.span == 0) == [(2.5, 4.5), (8.5, 10.5)]   # (9.5, 9.5) made way
    assert sorted((s.x, s.y) for s in level.spawners) == [(4.5, 2.5), (10.5, 8.5)]
    assert level.walls[3][3] == 2                                      # the original stays (a copy, not a move)


def test_an_upper_floor_pastes_its_rooms_and_walls_and_leaves_the_ground_floors_walls():
    level = two_floors()
    level.walls[9][10] = 1                                             # a ground-floor wall: it fills floor 1 too
    area = copy_area(level, (2, 2), (4, 4), 1)
    paste_area(level, area, 8, 8, 1)
    assert level.span_present(1, 9, 9) and level.grids["ceil_h2"][9][9] == 2.4
    assert level.walls[10][10] == 5 and level.wall_floor(10, 10) == 1
    assert level.walls[9][10] == 1 and level.wall_floor(10, 9) == 0   # untouched
    assert [(e.x, e.y) for e in level.entities if e.span == 1] == [(3.5, 3.5), (9.5, 9.5)]


def test_an_area_can_be_pasted_onto_another_floor():
    level = two_floors()
    paste_area(level, copy_area(level, (2, 2), (4, 4), 0), 9, 6, 1)    # the ground floor's area, onto floor 1
    assert level.walls[7][10] == 2 and level.wall_floor(10, 7) == 1    # its wall now starts on floor 1
    assert level.grids["floor_tex2"][6][9] == 7
    assert [e.span for e in level.entities if (e.x, e.y) == (9.5, 8.5)] == [1]


def test_clearing_an_area_empties_only_that_floor():
    level = two_floors()
    clear_area(level, (2, 2), (4, 4), 1)
    assert not any(level.span_present(1, x, y) for x in range(2, 5) for y in range(2, 5))   # no rooms left
    assert level.walls[4][4] == 0 and not [e for e in level.entities if e.span == 1]
    assert level.walls[3][3] == 2 and level.grids["floor_tex"][2][2] == 7                    # floor 0 as it was
    clear_area(level, (2, 2), (4, 4), 0)
    assert level.walls[3][3] == 0 and level.grids["side_s"][3][3] == 0 and level.grids["floor_tex"][2][2] == 5
    assert not level.spawners and [(e.x, e.y) for e in level.entities] == [(9.5, 9.5)]


def test_pasting_at_the_edge_keeps_what_fits():
    level = two_floors()
    area = copy_area(level, (2, 2), (4, 4), 0)
    paste_area(level, area, 14, -1, 0)                                 # only the cells x 14..15, y 0..1 are on the map
    assert level.grids["floor_h"][0][14] == 0.0 and level.grids["floor_tex"][1][14] == 5
    assert level.walls[0][15] == 2                                     # area (1, 1) -> (15, 0)
    paste_area(level, area, 40, 40, 0)                                 # nothing on the map: nothing happens


# ------------------------------------------------------------------ the editor's Select tool

@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = two_floors()
    editor.show_legend = False
    editor.fit_view()
    editor.draw(pygame.display.get_surface())
    return editor


def mouse(ed, kind, cell, button=1):
    pos = ed.cell_rect(*cell).center
    if kind == pygame.MOUSEMOTION:
        ed.handle_event(pygame.event.Event(kind, pos=pos, rel=(0, 0), buttons=(1, 0, 0)))
    else:
        ed.handle_event(pygame.event.Event(kind, pos=pos, button=button))


def key(ed, k, mod=0):
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode=""))


def select(ed, a, b):
    mouse(ed, pygame.MOUSEBUTTONDOWN, a)
    mouse(ed, pygame.MOUSEMOTION, b)
    mouse(ed, pygame.MOUSEBUTTONUP, b)


def test_select_copy_and_paste_with_the_mouse_and_keys_in_one_undo_step_each(ed):
    key(ed, pygame.K_m)
    assert ed.tool == "select"
    select(ed, (2, 2), (4, 4))
    assert ed.area == (2, 2, 4, 4)
    ed.draw(pygame.display.get_surface())
    key(ed, pygame.K_c, pygame.KMOD_CTRL)
    assert ed.clip is not None and (ed.clip.width, ed.clip.height) == (3, 3)
    key(ed, pygame.K_v, pygame.KMOD_CTRL)
    assert ed.pasting
    ed.mouse = ed.cell_rect(10, 7).center
    ed.draw(pygame.display.get_surface())                              # the copy shows under the mouse
    mouse(ed, pygame.MOUSEBUTTONDOWN, (10, 7))                         # centered on the mouse: corner (9, 6)
    mouse(ed, pygame.MOUSEBUTTONUP, (10, 7))
    assert ed.level.walls[7][10] == 2 and ed.area == (9, 6, 11, 8) and ed.pasting
    mouse(ed, pygame.MOUSEBUTTONDOWN, (13, 3))                         # another, still pasting
    assert ed.level.walls[3][13] == 2
    key(ed, pygame.K_ESCAPE)
    assert not ed.pasting
    ed.do("undo")
    assert ed.level.walls[3][13] == 0 and ed.level.walls[7][10] == 2  # one paste per undo step


def test_cut_clear_select_all_and_right_click(ed):
    ed.do("tool:select")
    select(ed, (2, 2), (4, 4))
    key(ed, pygame.K_x, pygame.KMOD_CTRL)
    assert ed.level.walls[3][3] == 0 and ed.clip.walls                 # cut: gone from the map, kept in the copy
    ed.do("undo")
    assert ed.level.walls[3][3] == 2
    key(ed, pygame.K_DELETE)
    assert ed.level.walls[3][3] == 0                                   # Delete clears the selection
    key(ed, pygame.K_a, pygame.KMOD_CTRL)
    assert ed.area == (0, 0, 15, 11)
    mouse(ed, pygame.MOUSEBUTTONDOWN, (5, 5), button=3)
    assert ed.area is None                                             # right-click lets go of the selection
    ed.do("paste")
    mouse(ed, pygame.MOUSEBUTTONDOWN, (5, 5), button=3)
    assert not ed.pasting                                              # ... or stops pasting


def test_buttons_and_messages_when_there_is_nothing_to_copy_or_paste(ed):
    ed.do("tool:select")
    actions = [action for _rect, _label, action in ed.layout()]
    assert {"copy", "cut", "paste", "clear", "select_all"} <= set(actions)
    ed.do("copy")
    assert "Select an area first" in ed.message and ed.clip is None
    ed.do("paste")
    assert "Nothing copied" in ed.message and not ed.pasting


def test_the_copy_is_kept_when_another_map_is_opened(ed, tmp_path):
    ed.do("tool:select")
    select(ed, (2, 2), (4, 4))
    ed.do("copy")
    save_level(str(tmp_path / "other.json"), Level.blank(10, 10))
    ed.save()
    ed.do("open")
    ed.importing = None
    ed.open_pick = ed.open_maps.index("other.json")
    ed.finish_open(True)
    assert ed.level.width == 10 and ed.clip is not None
    ed.do("paste")
    mouse(ed, pygame.MOUSEBUTTONDOWN, (5, 5))
    assert ed.level.walls[5][5] == 2 and ed.level.grids[grid_name("floor_tex", 0)][4][4] == 7
