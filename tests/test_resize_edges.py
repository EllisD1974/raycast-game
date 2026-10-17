"""Growing and shrinking the map from any side."""
import collections
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
from mapfile import Level, grid_name


def marked(width=6, height=5, floors=2):
    level = Level.blank(width, height, floors=floors)
    level.walls[2][3] = 7
    level.grids["floor_h"][2][3] = 0.5
    level.grids[grid_name("floor_h", 1)][2][3] = 1.5
    level.start_x, level.start_y = 3.5, 2.5
    return level


def test_adding_left_and_top_shifts_every_grid_and_the_start():
    level = marked()
    level.resize_edges(left=2, top=1)
    assert (level.width, level.height) == (8, 6)
    assert level.walls[3][5] == 7 and level.grids["floor_h"][3][5] == 0.5
    assert level.grids[grid_name("floor_h", 1)][3][5] == 1.5
    assert (level.start_x, level.start_y) == (5.5, 3.5)
    assert level.walls[0][0] == 0 and level.walls[3][0] == 0          # new cells are open defaults
    assert all(len(g) == 6 and len(g[0]) == 8 for g in level.grids.values())


def test_adding_right_and_bottom_keeps_cells_in_place():
    level = marked()
    level.resize_edges(right=3, bottom=2)
    assert (level.width, level.height) == (9, 7)
    assert level.walls[2][3] == 7 and (level.start_x, level.start_y) == (3.5, 2.5)


def test_removing_from_the_left_and_top_shifts_back():
    level = marked()
    level.resize_edges(left=-2, top=-1)
    assert (level.width, level.height) == (4, 4)
    assert level.walls[1][1] == 7 and (level.start_x, level.start_y) == (1.5, 1.5)


def test_the_start_is_kept_on_the_map_when_its_cell_is_removed():
    level = marked()
    level.resize_edges(left=-3)
    assert 0 < level.start_x < level.width


def test_never_smaller_than_three_each_way():
    level = marked(4, 4)
    level.resize_edges(left=-5, right=-5, top=-9)
    assert level.width >= 3 and level.height >= 3
    assert all(len(g) == level.height and len(g[0]) == level.width for g in level.grids.values())


@pytest.fixture
def ed(tmp_path):
    pygame.init()
    pygame.display.set_mode((1600, 900), pygame.RESIZABLE)
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = marked()
    editor.revision += 1
    editor.fit_view()
    yield editor
    pygame.quit()


def test_edge_buttons_exist_for_every_side(ed):
    actions = {action for _r, _l, action in ed.layout()}
    assert {f"edge:{s}{d}" for s in "LRTB" for d in "+-"} <= actions


def test_adding_on_the_left_keeps_the_map_still_on_screen(ed):
    before = ed.cell_rect(3, 2).topleft
    ed.do("edge:L+")
    assert ed.level.width == 7 and ed.level.walls[2][4] == 7
    assert ed.cell_rect(4, 2).topleft == before


def test_each_edge_button_changes_only_its_side_and_undo_restores(ed):
    for action, size in (("edge:L+", (7, 5)), ("edge:R+", (7, 5)), ("edge:T+", (6, 6)), ("edge:B+", (6, 6)),
                         ("edge:L-", (5, 5)), ("edge:R-", (5, 5)), ("edge:T-", (6, 4)), ("edge:B-", (6, 4))):
        ed.do(action)
        assert (ed.level.width, ed.level.height) == size, action
        ed.do("undo")
        assert (ed.level.width, ed.level.height) == (6, 5)


def test_limits_are_respected_with_a_message(ed):
    ed.level = Level.blank(3, 3)
    ed.do("edge:R-")
    assert ed.level.width == 3
    ed.level = Level.blank(map_editor.MAX_SIZE, 5)
    ed.do("edge:L+")
    assert ed.level.width == map_editor.MAX_SIZE


def test_the_3d_camera_keeps_its_place_on_the_map(ed):
    ed.set_preview(True)
    assert ed.preview.place(1.5, 1.5)
    ed.do("edge:L+")
    ed.do("edge:T+")
    ed.update(0.0, collections.defaultdict(int))
    p = ed.preview.player
    assert (p.x, p.y) == pytest.approx((2.5, 2.5), abs=0.01)
