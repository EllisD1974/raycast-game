"""The key (legend) that explains the small marks drawn on the map."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
from mapfile import Level

BIG = (1920, 1009)          # a maximized window: the key has room in the left panel
SMALL = (1280, 800)         # too short for that: the key floats over the map


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode(BIG, pygame.RESIZABLE)
    yield
    pygame.quit()


def make_editor(tmp_path, floors=2, size=BIG):
    pygame.display.set_mode(size, pygame.RESIZABLE)
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(12, 10, floors=floors)
    editor.level.start_x = editor.level.start_y = 1.5
    editor.mouse = (0, 0)
    editor.fit_view()
    editor.draw(pygame.display.get_surface())
    return editor


@pytest.fixture
def ed(tmp_path):
    return make_editor(tmp_path)


def kinds(editor):
    return [kind for kind, _text in editor.legend_entries()]


def click_at(editor, pos, button=1):
    editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
    editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))


def key(editor, k):
    editor.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))


# ------------------------------------------------------------------ what the key lists

def test_a_single_floor_map_only_explains_what_it_can_show(tmp_path):
    editor = make_editor(tmp_path, floors=1)
    assert kinds(editor) == ["start"]                          # no floors above or below, no problems


def test_floor_marks_depend_on_the_floor_being_viewed(ed):
    assert kinds(ed) == ["upper", "start"]                      # ground floor: a floor exists above
    ed.do("floor:1")
    assert kinds(ed) == ["start_other", "below"]                # top floor: nothing above; start is below


def test_the_dot_is_only_listed_where_a_floor_exists_above(tmp_path):
    editor = make_editor(tmp_path, floors=3)
    assert "upper" in kinds(editor)
    editor.do("floor:1")
    assert "upper" in kinds(editor)
    editor.do("floor:2")
    assert "upper" not in kinds(editor)


def test_the_start_entry_shows_solid_or_hollow_as_drawn(ed):
    assert "start" in kinds(ed) and "start_other" not in kinds(ed)
    ed.level.start_span = 1
    assert "start_other" in kinds(ed) and "start" not in kinds(ed)
    ed.do("floor:1")
    assert "start" in kinds(ed)


def test_layer_marks_are_only_listed_on_the_layers_that_draw_them(ed):
    ed.do("layer:walls")
    assert not {"wall_dim", "ramp", "heat"} & set(kinds(ed))
    ed.do("layer:floor_tex")
    assert "wall_dim" in kinds(ed) and "ramp" not in kinds(ed) and "heat" not in kinds(ed)
    ed.do("layer:floor_h")
    assert {"wall_dim", "heat"} <= set(kinds(ed)) and "ramp" not in kinds(ed)
    ed.do("layer:ramp")
    assert {"wall_dim", "ramp", "heat"} <= set(kinds(ed))


def test_the_problem_entry_appears_only_while_there_are_problem_cells(ed):
    assert "problem" not in kinds(ed)
    ed.level.set("ceil_h", 4, 4, 0.0)                           # ceiling at the floor: a problem
    ed.revision += 1
    assert ed.problem_cells() and "problem" in kinds(ed)
    ed.level.set("ceil_h", 4, 4, 1.0)
    ed.revision += 1
    assert "problem" not in kinds(ed)


def test_every_entry_has_text(ed):
    ed.do("floor:1")
    ed.do("layer:ramp")
    ed.level.set("ceil_h", 4, 4, 0.0)
    ed.revision += 1
    for kind, text in ed.legend_entries():
        assert text.strip() and len(text) <= 32, (kind, text)


# ------------------------------------------------------------------ where the key goes

def test_in_a_maximized_window_the_key_is_docked_in_the_left_panel(ed):
    rect, columns, docked = ed.legend_layout()
    assert docked and columns == 2
    assert rect.right <= map_editor.PANEL_W and rect.left >= 0
    assert not rect.colliderect(ed.atlas_rect())
    _y, _cell, after, hints_y = ed.panel_metrics()
    assert rect.top >= after and rect.bottom <= hints_y          # between the tile preview and the hints
    assert not rect.colliderect(ed.map_area())                   # so it never covers the map


def test_in_a_short_window_the_key_floats_over_the_map_corner(tmp_path):
    editor = make_editor(tmp_path, size=SMALL)
    rect, columns, docked = editor.legend_layout()
    assert not docked and columns == 1
    area = editor.map_area()
    assert area.contains(rect) and rect.right <= area.right - 5 and rect.bottom <= area.bottom - 5


def test_the_docked_key_follows_the_stamp_preview(ed):
    ed.selection = {0, 1, 2, 3, 16, 17, 18, 19}                  # a taller preview takes more room
    rect, _cols, docked = ed.legend_layout()
    _y, _cell, after, hints_y = ed.panel_metrics()
    assert (not docked) or (rect.top >= after and rect.bottom <= hints_y)


def test_the_key_never_overlaps_the_hints_or_the_preview_at_any_window_height(tmp_path):
    for height in range(700, 1100, 40):
        editor = make_editor(tmp_path, size=(1600, height))
        rect, _cols, docked = editor.legend_layout()
        if docked:
            _y, _cell, after, hints_y = editor.panel_metrics()
            assert rect.top >= after and rect.bottom <= hints_y, height


# ------------------------------------------------------------------ showing and hiding it

def test_the_key_is_shown_at_first_and_k_or_the_button_toggles_it(ed):
    ed.show_legend = True
    key(ed, pygame.K_k)
    assert not ed.show_legend
    key(ed, pygame.K_k)
    assert ed.show_legend
    button = next(r for r, _l, a in ed.layout() if a == "legend")
    click_at(ed, button.center)
    assert not ed.show_legend
    click_at(ed, button.center)
    assert ed.show_legend


def test_a_fresh_editor_shows_the_key(tmp_path):
    pygame.display.set_mode(BIG, pygame.RESIZABLE)
    assert map_editor.Editor(str(tmp_path / "x.json")).show_legend is True


def big_map_editor(tmp_path, show_key):
    """A short window (so the key floats) with a map large enough to reach under the key."""
    editor = make_editor(tmp_path, size=SMALL)
    editor.level = Level.blank(60, 40, floors=2)
    editor.level.start_x = editor.level.start_y = 1.5
    editor.zoom, editor.pan = 32, [0, 0]
    editor.show_legend = show_key
    editor.draw(pygame.display.get_surface())
    return editor


def test_a_hidden_key_does_not_take_clicks(tmp_path):
    editor = big_map_editor(tmp_path, show_key=False)
    spot = (editor.map_area().right - 100, editor.map_area().bottom - 100)   # where the key would be
    cell = editor.cell_at(spot)
    assert editor.level.walls[cell[1]][cell[0]] == 0
    click_at(editor, spot)
    assert editor.level.walls[cell[1]][cell[0]] != 0             # painted: nothing intercepted the click


# ------------------------------------------------------------------ clicks

def test_a_floating_key_does_not_paint_through_to_the_cells_under_it(tmp_path):
    editor = big_map_editor(tmp_path, show_key=True)
    rect, _cols, docked = editor.legend_layout()
    assert not docked
    cell = editor.cell_at(rect.center)
    assert editor.level.in_bounds(*cell), "test setup: the key should sit over the map"
    before = [row[:] for row in editor.level.walls]
    click_at(editor, rect.center)
    assert editor.level.walls == before and not editor.dirty
    outside = (rect.left - 60, rect.centery)                     # just beside the key: painting works
    click_at(editor, outside)
    assert editor.level.walls != before


def test_a_docked_key_leaves_every_map_cell_clickable(ed):
    assert ed.legend_layout()[2]
    area = ed.map_area()
    for x in (0, 5, 11):
        for y in (0, 5, 9):
            pos = ed.cell_rect(x, y).center
            assert area.collidepoint(pos) and not ed.legend_rect().collidepoint(pos)
    click_at(ed, ed.cell_rect(5, 5).center)
    assert ed.level.walls[5][5] != 0                             # painted: the key did not intercept it


# ------------------------------------------------------------------ the icons match the map

def icon_box_for(editor, kind):
    """The on-screen box of the key icon for `kind`, found by redoing the key's layout maths."""
    rect, columns, _docked = editor.legend_layout()
    entries = editor.legend_entries()
    per_column = (len(entries) + columns - 1) // columns
    column_w = rect.w // columns
    for i, (k, _text) in enumerate(entries):
        if k == kind:
            column, row = divmod(i, per_column)
            y = rect.y + map_editor.LEGEND_TITLE + row * map_editor.LEGEND_ROW
            return pygame.Rect(rect.x + 10 + column * column_w, y + (map_editor.LEGEND_ROW - map_editor.LEGEND_ICON) // 2,
                               map_editor.LEGEND_ICON, map_editor.LEGEND_ICON)
    raise AssertionError(f"{kind} is not in the key")


def pixels(surface, box):
    return {tuple(surface.get_at((x, y)))[:3] for x in range(box.left, box.right) for y in range(box.top, box.bottom)}


def test_each_icon_in_the_key_is_drawn_with_the_same_colors_as_on_the_map(ed):
    ed.do("floor:1")
    ed.do("layer:ramp")
    ed.level.start_span = 0
    ed.level.set("ceil_h", 4, 4, 0.0)                            # a problem cell
    ed.revision += 1
    ed.draw(pygame.display.get_surface())
    surface = pygame.display.get_surface()
    seen = {kind: pixels(surface, icon_box_for(ed, kind)) for kind in kinds(ed)}
    assert map_editor.START_FILL in seen["start_other"]          # the hollow ring
    assert map_editor.WARN in seen["problem"]                    # the red outline
    assert map_editor.ACCENT in seen["ramp"]                     # the arrow
    assert len(seen["heat"]) > 10                                # the blue-to-yellow strip
    assert len(seen["wall_dim"]) > 4 and len(seen["below"]) > 4  # faded tiles

    ed.do("floor:0")
    ed.level.start_span = 0
    ed.draw(surface)
    seen = {kind: pixels(surface, icon_box_for(ed, kind)) for kind in kinds(ed)}
    assert map_editor.UPPER_MARK in seen["upper"]                # the orange dot
    assert map_editor.START_FILL in seen["start"] and map_editor.START_EDGE in seen["start"]


def test_the_dot_on_the_map_and_in_the_key_are_the_same_mark(ed):
    ed.do("layer:floor_tex")
    ed.level.set("floor_h2", 3, 3, 1.5)
    ed.level.set("ceil_h2", 3, 3, 3.0)                           # a room above (3, 3)
    ed.revision += 1
    ed.draw(pygame.display.get_surface())
    surface = pygame.display.get_surface()
    cell = ed.cell_rect(3, 3)
    on_map = surface.get_at((cell.right - 6, cell.top + 6))[:3]
    box = icon_box_for(ed, "upper")
    in_key = surface.get_at((box.right - 6, box.top + 6))[:3]
    assert on_map == in_key == map_editor.UPPER_MARK


def test_the_problem_outline_on_the_map_and_in_the_key_are_the_same_mark(ed):
    ed.level.set("ceil_h", 4, 4, 0.0)
    ed.revision += 1
    ed.draw(pygame.display.get_surface())
    surface = pygame.display.get_surface()
    cell = ed.cell_rect(4, 4)
    box = icon_box_for(ed, "problem")
    assert surface.get_at((cell.left + 1, cell.centery))[:3] == surface.get_at((box.left + 1, box.centery))[:3] \
        == map_editor.WARN


def test_the_key_draws_in_every_state_and_in_both_layouts(tmp_path):
    for size in (BIG, SMALL):
        editor = make_editor(tmp_path, floors=3, size=size)
        editor.level.set("ceil_h", 4, 4, 0.0)
        editor.revision += 1
        surface = pygame.display.get_surface()
        for floor in range(3):
            editor.do(f"floor:{floor}")
            for name in map_editor.EDIT_LAYERS:
                editor.do(f"layer:{name}")
                editor.draw(surface)
