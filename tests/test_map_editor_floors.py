"""Editor tests for any number of floors: the dropdown, adding, renaming and deleting floors."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
from mapfile import Level


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1280, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(10, 10, floors=2)
    editor.level.start_x = editor.level.start_y = 1.5
    editor.show_legend = False                       # the key has its own tests; keep it off the cells
    editor.draw(pygame.display.get_surface())
    return editor


def mouse(ed, kind, pos, button=1):
    ed.handle_event(pygame.event.Event(kind, pos=pos, button=button))


def click_at(ed, pos, button=1):
    mouse(ed, pygame.MOUSEBUTTONDOWN, pos, button)
    mouse(ed, pygame.MOUSEBUTTONUP, pos, button)


def click(ed, x, y, button=1):
    click_at(ed, ed.cell_rect(x, y).center, button)


def cell_pos(ed, x, y):
    return ed.cell_rect(x, y).center


def press(ed, k, mod=0):
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode=""))


def type_text(ed, text):
    for ch in text:
        ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=ord(ch.lower()), mod=0, unicode=ch))


def button_pos(ed, action):
    for rect, _label, act in ed.layout():
        if act == action:
            return rect.center
    raise AssertionError(f"no button {action}")


def has_button(ed, action):
    return any(act == action for _r, _l, act in ed.layout())


def clear_name(ed):
    for _ in range(map_editor.MAX_NAME_LENGTH + 2):
        press(ed, pygame.K_BACKSPACE)


# ------------------------------------------------------------------ dropdown

def test_dropdown_lists_every_floor_and_selects_one(ed):
    ed.level.rename_floor(0, "Ground")
    ed.level.rename_floor(1, "Upstairs")
    click_at(ed, button_pos(ed, "dropdown"))
    assert ed.dropdown_open
    labels = [label for _r, label, _a in ed.dropdown_items()]
    assert labels == ["1. Ground", "2. Upstairs", "+ New floor"]
    ed.draw(pygame.display.get_surface())                        # the open list draws
    upstairs = next(r for r, _l, a in ed.dropdown_items() if a == "floor:1")
    click_at(ed, upstairs.center)
    assert ed.floor == 1 and not ed.dropdown_open


def test_clicking_away_closes_the_dropdown_without_painting(ed):
    click_at(ed, button_pos(ed, "dropdown"))
    click(ed, 4, 4)                                              # lands on the map, only closes the list
    assert not ed.dropdown_open and ed.level.walls[4][4] == 0 and not ed.dirty
    click_at(ed, button_pos(ed, "dropdown"))
    press(ed, pygame.K_ESCAPE)
    assert not ed.dropdown_open and ed.running                   # Esc closes the list, doesn't quit


def test_the_dropdown_button_shows_the_current_floor_name(ed):
    ed.level.rename_floor(1, "Upstairs")
    ed.do("floor:1")
    label = next(l for _r, l, a in ed.layout() if a == "dropdown")
    assert label == "Upstairs"


# ------------------------------------------------------------------ adding floors

def test_adding_floors_without_limit(ed):
    for expected in (3, 4, 5, 6):
        click_at(ed, button_pos(ed, "addfloor"))
        assert ed.level.floor_count == expected and ed.floor == expected - 1
    assert ed.level.names[-1] == "Floor 6"
    assert ed.level.problems() == []
    ed.do("dropdown")
    items = ed.dropdown_items()
    assert len(items) == 7                                       # six floors plus "+ New floor"
    click_at(ed, items[-1][0].center)                            # the list's own "+ New floor"
    assert ed.level.floor_count == 7 and ed.floor == 6


def test_undo_of_an_added_floor_keeps_the_edited_floor_valid(ed):
    ed.do("addfloor")
    assert ed.floor == 2
    ed.do("undo")
    assert ed.level.floor_count == 2 and ed.floor == 1


# ------------------------------------------------------------------ renaming

def test_rename_with_the_keyboard_and_undo(ed):
    ed.do("floor:1")
    press(ed, pygame.K_F2)
    assert ed.rename == "Floor 2"
    clear_name(ed)
    type_text(ed, "Upstairs")
    press(ed, pygame.K_RETURN)
    assert ed.rename is None and ed.level.names == ["Floor 1", "Upstairs"] and ed.dirty
    ed.draw(pygame.display.get_surface())
    ed.do("undo")
    assert ed.level.names == ["Floor 1", "Floor 2"]


def test_rename_button_escape_cancels_and_clicking_away_keeps(ed):
    click_at(ed, button_pos(ed, "rename"))
    assert ed.rename == "Floor 1"
    ed.draw(pygame.display.get_surface())                        # the text box draws
    type_text(ed, "X")
    press(ed, pygame.K_ESCAPE)
    assert ed.level.names[0] == "Floor 1" and ed.running         # Esc cancels, doesn't quit
    ed.do("rename")
    type_text(ed, "!")
    click(ed, 4, 4)                                              # clicking elsewhere keeps the typed name
    assert ed.level.names[0] == "Floor 1!" and ed.level.walls[4][4] == 0


def test_rename_limits_length_and_keeps_names_unique(ed):
    ed.do("rename")
    clear_name(ed)
    type_text(ed, "A" * 40)
    assert len(ed.rename) == 24
    press(ed, pygame.K_RETURN)
    ed.do("floor:1")
    ed.do("rename")
    clear_name(ed)
    type_text(ed, "A" * 24)
    press(ed, pygame.K_RETURN)
    assert ed.level.names[1] != ed.level.names[0] and len(set(ed.level.names)) == 2


def test_an_empty_name_is_not_accepted(ed):
    ed.do("rename")
    clear_name(ed)
    press(ed, pygame.K_RETURN)
    assert ed.level.names == ["Floor 1", "Floor 2"] and not ed.dirty


# ------------------------------------------------------------------ deleting

def test_delete_floor_needs_confirmation_and_never_deletes_the_ground(ed):
    assert not has_button(ed, "delfloor")                        # no Del button on the ground floor
    ed.do("delfloor")
    assert ed.level.floor_count == 2
    ed.do("addfloor")
    ed.level.rename_floor(1, "Middle")
    ed.level.rename_floor(2, "Roof")
    ed.do("floor:1")
    click_at(ed, button_pos(ed, "delfloor"))                     # the first click only asks
    assert ed.level.floor_count == 3
    click_at(ed, button_pos(ed, "delfloor"))
    assert ed.level.names == ["Floor 1", "Roof"] and ed.floor == 0
    ed.do("undo")
    assert ed.level.names == ["Floor 1", "Middle", "Roof"]


def test_deleting_a_floor_drops_its_brush_values(ed):
    ed.do("addfloor")
    ed.do("layer:floor_h")
    ed.value["floor_h3"] = 9.0
    ed.value["floor_h2"] = 2.0
    ed.do("floor:2")
    ed.do("delfloor")
    ed.do("delfloor")
    assert "floor_h3" not in ed.value and ed.value["floor_h2"] == 2.0


# ------------------------------------------------------------------ painting on higher floors

def test_a_third_floor_gets_its_own_brushes_and_a_slab_over_the_floor_below(ed):
    ed.do("addfloor")                                            # floor index 2
    ed.level.set("floor_h2", 4, 4, 1.5)
    ed.level.set("ceil_h2", 4, 4, 2.75)                          # a room on floor 2 at (4, 4)
    ed.do("layer:floor_h")
    assert ed.brush("floor_h3") == 3.0 and ed.brush("ceil_h3") == 4.5
    click(ed, 4, 4)
    g = ed.level.grids
    assert (g["floor_h3"][4][4], g["ceil_h3"][4][4]) == (3.0, 4.5)
    assert g["ceil_h2"][4][4] == 2.75                            # already under the new floor: untouched
    assert ed.level.problems() == []

    ed.level.set("floor_h2", 5, 4, 1.5)
    ed.level.set("ceil_h2", 5, 4, 4.0)                           # a tall room below, at (5, 4)
    click(ed, 5, 4)
    assert g["ceil_h2"][4][5] == pytest.approx(2.75)             # lowered, leaving a 0.25 slab
    click(ed, 5, 4, button=3)                                    # erase removes the room again
    assert not ed.level.span_present(2, 5, 4)


def test_the_slab_goes_under_the_nearest_room_below_when_floors_are_skipped(ed):
    ed.do("addfloor")                                            # floor 3 over a cell with no floor 2 room
    ed.level.set("ceil_h", 4, 4, 4.0)
    ed.do("layer:floor_h")
    click(ed, 4, 4)
    assert ed.level.grids["ceil_h"][4][4] == pytest.approx(2.75)  # floor 1's ceiling, under floor 3 at 3.0
    assert ed.level.problems() == []


def test_start_on_a_third_floor_and_hover_names_every_floor(ed):
    ed.do("addfloor")
    ed.level.rename_floor(2, "Roof")
    ed.do("layer:floor_h")
    click(ed, 3, 3)
    ed.do("tool:start")
    click(ed, 3, 3)
    assert ed.level.start_span == 2 and ed.level.problems() == []
    ed.mouse = cell_pos(ed, 3, 3)
    assert "Roof:" in ed.hover_info() and "Floor 1:" in ed.hover_info()


def test_every_floor_draws_every_layer_with_the_dropdown_open(ed):
    ed.do("addfloor")
    ed.do("layer:floor_h")
    click(ed, 4, 4)
    ed.level.set("ramp3", 5, 4, 1)
    surface = pygame.display.get_surface()
    for floor in range(3):
        ed.do(f"floor:{floor}")
        for name in map_editor.EDIT_LAYERS:
            ed.do(f"layer:{name}")
            ed.dropdown_open = floor == 1
            ed.draw(surface)


# ------------------------------------------------------------------ problems are shown on the map

def test_problem_cells_are_outlined_and_counted(ed):
    ed.do("floor:1")
    ed.do("layer:floor_h")
    click(ed, 4, 4)                                              # a room on floor 2, slab lowered: valid
    assert ed.problem_cells() == set() and ed.problems() == []
    ed.level.set("ceil_h", 4, 4, 4.0)                            # now the lower room pokes through it
    ed.revision += 1
    assert ed.problem_cells() == {(4, 4)}
    assert "is below the ceiling of" in ed.problems()[0]
    surface = pygame.display.get_surface()
    ed.mouse = (0, 0)                                            # keep the tool cursor off the cell
    ed.draw(surface)
    rect = ed.cell_rect(4, 4)
    assert surface.get_at((rect.left + 1, rect.centery))[:3] == map_editor.WARN   # red outline


# ------------------------------------------------------------------ walls on a higher floor

def test_a_wall_painted_on_a_higher_floor_does_not_reach_the_floors_below(ed):
    ed.level.set("floor_h2", 4, 4, 2.0)
    ed.level.set("ceil_h2", 4, 4, 3.5)
    ed.do("floor:1")
    ed.do("layer:walls")
    ed.paint_at(5, 5)
    level = ed.level
    assert level.walls[5][5] and level.wall_floor(5, 5) == 1
    assert level.is_solid(5, 5, 1) and not level.is_solid(5, 5, 0)
    assert level.span_present(0, 5, 5) and not level.span_present(1, 5, 5)


def test_a_wall_painted_on_the_ground_floor_still_fills_every_floor(ed):
    ed.do("layer:walls")
    ed.paint_at(5, 5)
    assert ed.level.wall_floor(5, 5) == 0
    assert ed.level.is_solid(5, 5, 0) and ed.level.is_solid(5, 5, 1)


def test_the_ground_floor_view_shows_a_higher_floors_wall_as_open(ed):
    ed.do("floor:1")
    ed.do("layer:walls")
    ed.paint_at(5, 5)
    ed.do("floor:0")
    ed.draw(pygame.display.get_surface())
    assert not ed.level.is_solid(5, 5, ed.floor)


def test_erasing_a_wall_forgets_its_floor(ed):
    ed.do("floor:1")
    ed.do("layer:walls")
    ed.paint_at(5, 5)
    ed.erase_at(5, 5)
    assert not ed.level.walls[5][5] and ed.level.wall_floor(5, 5) == 0


def test_wall_floor_survives_save_and_load(ed, tmp_path):
    from mapfile import load_level, save_level
    ed.do("floor:1")
    ed.do("layer:walls")
    ed.paint_at(5, 5)
    save_level(str(tmp_path / "w.json"), ed.level)
    assert load_level(str(tmp_path / "w.json")).wall_floor(5, 5) == 1


def test_the_player_walks_under_a_higher_floors_wall_but_not_through_it_upstairs(ed):
    from world import World
    level = ed.level
    for x in range(2, 8):
        for y in range(2, 8):
            level.set("floor_h2", x, y, 2.0)
            level.set("ceil_h2", x, y, 3.5)
            level.set("ceil_h", x, y, 1.75)
    level.set("walls", 5, 5, 1)
    level.set("wall_floor", 5, 5, 1)
    world = World(level, 4)
    assert not world.is_blocked(5, 5)
    assert world.span_at(5.5, 5.5, 0.0, 0) == 0                 # downstairs: open
    assert world.span_at(5.5, 5.5, 2.0, 1) == -1                # upstairs: a wall
    assert world.span_on[0, 5, 5] == 1 and world.span_on[1, 5, 5] == 0


def test_a_floating_wall_on_a_higher_floor_hangs_into_the_room_below(ed):
    import numpy as np
    from world import World
    ed.do("floor:1")
    ed.do("layer:walls")
    ed.paint_at(5, 5)
    base = ed.level.get("floor_h2", 5, 5)
    assert base > 0                                             # it has a base, not the ground
    ed.level.set("ceil_h", 5, 5, base + 1.0)                    # the room below is taller than the base
    world = World(ed.level, 4)
    assert world.ceil_of(0, 5.5, 5.5) == pytest.approx(base)    # the wall shows below the old ceiling
    assert world.span_on[0, 5, 5] == 1 and world.solid_from[5, 5] == 1


def test_ceil_h_on_a_higher_floors_wall_sets_its_top_and_makes_it_a_short_block(ed):
    from world import World
    level = ed.level
    for x in range(2, 9):
        for y in range(2, 9):
            level.set("floor_h2", x, y, 1.5)
            level.set("ceil_h2", x, y, 3.5)
    ed.do("floor:1")
    ed.do("layer:walls")
    ed.paint_at(5, 5)
    ed.do("layer:ceil_h")
    ed.value[ed.gname("ceil_h")] = 2.0
    ed.paint_at(5, 5)
    assert level.get("ceil_h2", 5, 5) == 2.0 and level.get("floor_h2", 5, 5) == 1.5   # base untouched
    ed.draw(pygame.display.get_surface())
    world = World(level, 4)
    assert world.span_on[1, 5, 5] == 1 and world.floor_of(1, 5.5, 5.5) == pytest.approx(2.0)
    ed.erase_at(5, 5)
    assert level.get("ceil_h2", 5, 5) == 0.0 and World(level, 4).span_on[1, 5, 5] == 0


def wheel(ed, cell, y, ctrl=True):
    ed.mouse = ed.cell_rect(*cell).center
    ed.mods = lambda: pygame.KMOD_CTRL if ctrl else 0
    zoom = ed.zoom
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=y))
    return zoom


def upstairs_wall(ed):
    for x in range(2, 9):
        for y in range(2, 9):
            ed.level.set("floor_h2", x, y, 1.5)
            ed.level.set("ceil_h2", x, y, 3.5)
    ed.do("floor:1")
    ed.do("layer:walls")
    ed.paint_at(5, 5)


def test_wall_height_of_a_higher_floors_wall_can_be_painted(ed):
    from world import World
    upstairs_wall(ed)
    ed.do("layer:wall_h")
    ed.paint_at(5, 5)
    assert ed.level.grids["wall_h"][5][5] == ed.brush("wall_h")
    assert ed.level.short_wall_top(5, 5) == pytest.approx(1.5 + ed.brush("wall_h"))
    assert World(ed.level, 4).span_on[1, 5, 5] == 1


def test_ctrl_wheel_changes_the_layers_value_and_does_not_zoom(ed):
    upstairs_wall(ed)
    ed.do("layer:ceil_h")
    ed.level.set("ceil_h2", 6, 6, 3.5)
    zoom = wheel(ed, (6, 6), 2)
    assert ed.zoom == zoom and ed.level.get("ceil_h2", 6, 6) == pytest.approx(4.0)
    wheel(ed, (6, 6), -1)
    assert ed.level.get("ceil_h2", 6, 6) == pytest.approx(3.75)
    ed.level.set("ceil_h2", 5, 5, 0.0)
    wheel(ed, (5, 5), 1)                                    # the wall: sets its top, above its base
    assert ed.level.get("ceil_h2", 5, 5) == pytest.approx(1.75) and ed.level.get("floor_h2", 5, 5) == 1.5
    ed.do("layer:wall_h")
    wheel(ed, (5, 5), -1)                                   # full height steps down
    assert 0 < ed.level.grids["wall_h"][5][5] < 2.0
    ed.do("layer:floor_tex")
    before = [row[:] for row in ed.level.grids["floor_tex2"]]
    wheel(ed, (6, 6), 1)
    assert ed.level.grids["floor_tex2"] == before


def test_plain_wheel_still_zooms(ed):
    zoom = wheel(ed, (5, 5), 1, ctrl=False)
    assert ed.zoom == zoom + 4


def test_a_floating_wall_with_no_room_beside_it_shows_its_height_from_both_floors(ed):
    from world import World
    level = ed.level
    for x in range(10):
        for y in range(10):
            level.set("ceil_h", x, y, 5.0)
    ed.do("floor:1")
    ed.do("layer:walls")
    ed.paint_at(5, 5)                                           # base 1.5, nothing else on floor 2
    ed.do("layer:ceil_h")
    ed.level.set("ceil_h2", 5, 5, 3.0)
    w = World(level, 4)
    assert w.ceil_of(0, 5.5, 5.5) == pytest.approx(1.5)         # seen from below: it hangs to its base
    assert w.span_on[1, 5, 5] == 1 and w.floor_of(1, 5.5, 5.5) == pytest.approx(3.0)
    assert w.ceil_of(1, 5.5, 5.5) == pytest.approx(5.0)         # open above its top
    wheel(ed, (5, 5), 4)                                        # Ctrl + wheel raises the top
    assert World(level, 4).floor_of(1, 5.5, 5.5) == pytest.approx(4.0)
    ed.do("layer:wall_h")
    ed.level.set("ceil_h2", 5, 5, 0.0)                          # full height: the wheel steps it down from 3.5
    wheel(ed, (5, 5), -2)
    assert level.grids["wall_h"][5][5] == pytest.approx(3.0)
    assert World(level, 4).floor_of(1, 5.5, 5.5) == pytest.approx(4.5)
