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
    assert ed.level.grids["ceil_h"][4][5] == 3.0                        # neighbors unchanged
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


# ------------------------------------------------------------------ starting the game from the editor

def test_play_starts_main_py_with_this_python_and_the_built_game_when_frozen(monkeypatch):
    import sys
    command, folder = map_editor.Editor.game_command()
    assert command[0] == sys.executable and command[1].endswith("main.py") and os.path.dirname(command[1]) == folder
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", os.path.join("C:\\", "games", "RaycastGame", "RaycastEditor.exe"))
    command, folder = map_editor.Editor.game_command()
    assert command == [os.path.join(os.path.dirname(sys.executable), "RaycastGame.exe")]
    assert folder == os.path.dirname(sys.executable)


# ---------------------------------------------------------------- New: naming the new map

def type_text(ed, text):
    for char in text:
        ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=0, mod=0, unicode=char))


def press(ed, k):
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))


def clear_name(ed):
    for _ in range(len(ed.new_name)):
        press(ed, pygame.K_BACKSPACE)


def test_new_asks_for_a_name_and_saves_the_blank_map_under_it(ed, tmp_path):
    first = tmp_path / "m.json"
    ed.save()
    ed.do("new")
    assert ed.new_name == "new_map" and ed.level.width == 10        # nothing changes until it is named
    ed.draw(pygame.display.get_surface())                            # the dialog draws
    clear_name(ed)
    type_text(ed, "Castle 2")
    press(ed, pygame.K_RETURN)
    made = tmp_path / "Castle 2.json"
    assert ed.new_name is None and made.exists()
    assert ed.path == str(made) and ed.level.width == 16 and not ed.dirty
    assert load_level(str(first)).width == 10                        # the map it was editing is left alone
    ed.do("tool:paint")
    ed.level.walls[3][3] = 1
    ed.save()                                                        # Save now writes the new map
    assert load_level(str(made)).walls[3][3] == 1 and load_level(str(first)).walls[3][3] == 0


def test_a_map_name_takes_only_file_name_characters(ed):
    ed.do("new")
    clear_name(ed)
    type_text(ed, "a/b\\c.d:e*")
    assert ed.new_name == "abcde"
    type_text(ed, "x" * 100)
    assert len(ed.new_name) == map_editor.MAX_MAP_NAME


def test_the_offered_name_is_one_no_map_has_yet(ed, tmp_path):
    (tmp_path / "new_map.json").write_text("{}")
    (tmp_path / "new_map_2.json").write_text("{}")
    ed.do("new")
    assert ed.new_name == "new_map_3"


def test_an_existing_or_empty_name_keeps_the_dialog_open_and_overwrites_nothing(ed, tmp_path):
    taken = tmp_path / "taken.json"
    taken.write_text("keep me")
    ed.do("new")
    clear_name(ed)
    type_text(ed, "taken")
    press(ed, pygame.K_RETURN)
    assert ed.new_name == "taken" and "already exists" in ed.new_error
    assert taken.read_text() == "keep me" and ed.level.width == 10
    ed.draw(pygame.display.get_surface())                            # the reason draws
    type_text(ed, "2")
    assert ed.new_error == ""                                        # typing clears it
    clear_name(ed)
    press(ed, pygame.K_RETURN)
    assert ed.new_name == "" and ed.new_error


def test_escape_or_cancel_closes_the_dialog_and_keeps_the_map(ed, tmp_path):
    path = ed.path
    ed.do("new")
    press(ed, pygame.K_ESCAPE)
    assert ed.new_name is None and ed.path == path and ed.level.width == 10
    ed.do("new")
    _box, _field, _create, cancel = ed.new_map_rects()
    mouse(ed, pygame.MOUSEBUTTONDOWN, cancel.center)
    assert ed.new_name is None and ed.path == path and not list(tmp_path.glob("new_map*.json"))


def test_the_create_button_makes_the_map_and_other_clicks_do_nothing(ed, tmp_path):
    ed.do("new")
    mouse(ed, pygame.MOUSEBUTTONDOWN, (5, 5))                        # outside the dialog: ignored
    assert ed.new_name == "new_map" and ed.level.width == 10 and not ed.dirty
    _box, _field, create, _cancel = ed.new_map_rects()
    mouse(ed, pygame.MOUSEBUTTONDOWN, create.center)
    assert ed.new_name is None and (tmp_path / "new_map.json").exists() and ed.level.width == 16


def test_unsaved_changes_are_confirmed_before_the_dialog_opens(ed):
    ed.dirty = True
    ed.do("new")
    assert ed.new_name is None and ed.confirm == "new"
    ed.do("new")
    assert ed.new_name == "new_map"


# ---------------------------------------------------------------- Open: switching to another map

def saved_map(path, width):
    level = Level.blank(width, 8)
    level.start_x = level.start_y = 1.5
    map_editor.save_level(str(path), level)


def test_open_lists_the_maps_in_the_folder_with_the_open_one_picked(ed, tmp_path):
    ed.save()                                                       # m.json
    saved_map(tmp_path / "beta.json", 12)
    saved_map(tmp_path / "Alpha.json", 11)
    (tmp_path / "notes.txt").write_text("not a map")
    ed.do("open")
    assert ed.open_maps == ["Alpha.json", "beta.json", "m.json"]
    assert ed.open_maps[ed.open_pick] == "m.json"
    ed.draw(pygame.display.get_surface())                           # the dialog draws


def test_picking_with_the_keys_and_enter_opens_that_map(ed, tmp_path):
    ed.save()
    saved_map(tmp_path / "beta.json", 12)
    ed.do("open")
    press(ed, pygame.K_UP)
    assert ed.open_maps[ed.open_pick] == "beta.json"
    press(ed, pygame.K_RETURN)
    assert ed.open_maps is None and ed.path == str(tmp_path / "beta.json")
    assert ed.level.width == 12 and not ed.dirty and not ed.undo
    ed.level.walls[2][2] = 1
    ed.save()                                                       # Save writes the opened map
    assert load_level(str(tmp_path / "beta.json")).walls[2][2] == 1


def test_a_double_click_opens_a_map_and_one_click_only_picks_it(ed, tmp_path):
    ed.save()
    saved_map(tmp_path / "beta.json", 12)
    ed.do("open")
    _box, _listing, _opener, _cancel, shown = ed.open_rects()
    row = next(rect for rect, index in shown if ed.open_maps[index] == "beta.json")
    mouse(ed, pygame.MOUSEBUTTONDOWN, row.center)
    assert ed.open_maps is not None and ed.open_maps[ed.open_pick] == "beta.json"
    mouse(ed, pygame.MOUSEBUTTONDOWN, row.center)
    assert ed.open_maps is None and ed.level.width == 12


def test_the_open_button_opens_and_cancel_or_escape_keep_the_map(ed, tmp_path):
    ed.save()
    saved_map(tmp_path / "beta.json", 12)
    for close in ("escape", "cancel"):
        ed.do("open")
        press(ed, pygame.K_UP)
        if close == "escape":
            press(ed, pygame.K_ESCAPE)
        else:
            mouse(ed, pygame.MOUSEBUTTONDOWN, ed.open_rects()[3].center)
        assert ed.open_maps is None and ed.path == str(tmp_path / "m.json") and ed.level.width == 10
    ed.do("open")
    press(ed, pygame.K_UP)
    mouse(ed, pygame.MOUSEBUTTONDOWN, ed.open_rects()[2].center)
    assert ed.open_maps is None and ed.level.width == 12


def test_a_map_that_cannot_be_read_keeps_the_dialog_open_with_the_reason(ed, tmp_path):
    ed.save()
    (tmp_path / "broken.json").write_text("{ not json")
    ed.do("open")
    press(ed, pygame.K_HOME)
    press(ed, pygame.K_RETURN)
    assert ed.open_maps is not None and "broken.json" in ed.open_error
    assert ed.path == str(tmp_path / "m.json") and ed.level.width == 10
    ed.draw(pygame.display.get_surface())                           # the reason draws
    press(ed, pygame.K_DOWN)
    assert ed.open_error == ""


def test_a_long_list_scrolls_to_keep_the_pick_in_view(ed, tmp_path):
    for i in range(30):
        saved_map(tmp_path / f"map{i:02}.json", 8)
    ed.do("open")
    press(ed, pygame.K_END)
    _box, _listing, _opener, _cancel, shown = ed.open_rects()
    assert len(shown) == map_editor.OPEN_ROWS and ed.open_pick in [index for _rect, index in shown]
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=100))
    assert ed.open_scroll == 0
    ed.draw(pygame.display.get_surface())


def test_unsaved_changes_are_confirmed_before_open_and_ctrl_o_opens_it(ed):
    ed.save()
    ed.dirty = True
    ed.do("open")
    assert ed.open_maps is None and ed.confirm == "open"
    key(ed, pygame.K_o, pygame.KMOD_CTRL)
    assert ed.open_maps == ["m.json"]


# ---------------------------------------------------------------- remembering the map edited last

def test_the_map_made_or_opened_last_is_remembered(tmp_path):
    settings = str(tmp_path / "settings" / "editor.json")
    first = tmp_path / "first.json"
    saved_map(first, 9)
    ed = map_editor.Editor(str(first), settings)
    assert map_editor.last_map(settings) == str(first)              # the one it starts on
    ed.do("new")
    press(ed, pygame.K_RETURN)
    assert map_editor.last_map(settings) == str(tmp_path / "new_map.json")
    ed.do("open")
    press(ed, pygame.K_HOME)
    press(ed, pygame.K_RETURN)
    assert map_editor.last_map(settings) == str(first)


def test_without_a_remembered_map_there_is_none(tmp_path):
    settings = tmp_path / "editor.json"
    assert map_editor.last_map(str(settings)) is None                # never written
    settings.write_text("{ not json")
    assert map_editor.last_map(str(settings)) is None
    map_editor.remember_map(str(tmp_path / "gone.json"), str(settings))
    assert map_editor.last_map(str(settings)) is None                # the map has since been deleted


def test_an_editor_without_settings_remembers_nothing(ed, tmp_path, monkeypatch):
    written = []
    monkeypatch.setattr(map_editor, "remember_map", lambda *args: written.append(args))
    ed.do("new")
    press(ed, pygame.K_RETURN)
    assert not written and ed.settings is None


def test_started_without_a_map_the_editor_opens_the_one_edited_last(tmp_path):
    settings = str(tmp_path / "editor.json")
    assert map_editor.starting_map([], settings) == map_editor.MAP_PATH          # nothing remembered yet
    remembered = tmp_path / "castle.json"
    saved_map(remembered, 13)
    map_editor.remember_map(str(remembered), settings)
    assert map_editor.starting_map([], settings) == str(remembered)
    assert map_editor.starting_map([str(tmp_path / "other.json")], settings) == str(tmp_path / "other.json")
    remembered.unlink()
    assert map_editor.starting_map([], settings) == map_editor.MAP_PATH          # gone: back to the default


# ---------------------------------------------------------------- the Shape tool

def no_corner_gaps(cells):
    """True if no two cells of `cells` touch only at a corner (with both cells beside them missing)."""
    cells = set(cells)
    return all((x + 1, y) in cells or (x, y + d) in cells
               for x, y in cells for d in (-1, 1) if (x + 1, y + d) in cells)


def test_boxes_are_their_outline_or_all_of_them_whichever_corner_the_drag_starts_from():
    for a, b in (((1, 1), (5, 4)), ((5, 4), (1, 1)), ((5, 1), (1, 4))):
        box = set(map_editor.shape_cells("box", a, b))
        assert len(box) == 2 * 5 + 2 * 2 and (1, 1) in box and (5, 4) in box and (3, 2) not in box
        assert len(set(map_editor.shape_cells("filled_box", a, b))) == 5 * 4


def test_ellipses_fit_their_box_and_their_outline_is_sealed():
    for size in ((9, 7), (13, 13), (4, 9), (1, 1), (2, 2)):
        b = (size[0] - 1, size[1] - 1)
        filled = set(map_editor.shape_cells("filled_ellipse", (0, 0), b))
        ring = set(map_editor.shape_cells("ellipse", (0, 0), b))
        assert ring <= filled and filled
        xs, ys = [c[0] for c in filled], [c[1] for c in filled]
        assert (min(xs), max(xs), min(ys), max(ys)) == (0, b[0], 0, b[1])        # touches all four sides
        assert no_corner_gaps(ring)
        inside = filled - ring
        assert all(n in filled for x, y in inside for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))


def test_a_line_runs_from_end_to_end_with_no_corner_gaps():
    for b in ((8, 6), (0, 5), (7, 0), (-6, 3), (3, -3)):
        cells = map_editor.shape_cells("line", (0, 0), b)
        assert cells[0] == (0, 0) and cells[-1] == b and no_corner_gaps(cells)


def drag(ed, a, b, button=1):
    mouse(ed, pygame.MOUSEBUTTONDOWN, cell_pos(ed, *a), button=button)
    mouse(ed, pygame.MOUSEMOTION, cell_pos(ed, *b))
    ed.draw(pygame.display.get_surface())                           # the shape is previewed while dragging
    mouse(ed, pygame.MOUSEBUTTONUP, cell_pos(ed, *b), button=button)


def walls(ed):
    """The wall cells inside the map's border wall."""
    return {(x, y) for y in range(1, ed.level.height - 1) for x in range(1, ed.level.width - 1) if ed.level.walls[y][x]}


def test_dragging_a_box_draws_its_walls_in_one_undo_step(ed):
    select(ed, (0, 0))
    key(ed, pygame.K_h)
    assert ed.tool == "shape" and ed.shape == "box"
    drag(ed, (2, 2), (6, 5))
    assert walls(ed) == set(map_editor.shape_cells("box", (2, 2), (6, 5)))
    assert all(ed.level.walls[y][x] == 1 for x, y in walls(ed))
    assert all(ed.level.get("wall_h", x, y) == map_editor.DEFAULTS["wall_h"] for x, y in walls(ed))
    key(ed, pygame.K_z, pygame.KMOD_CTRL)
    assert not walls(ed)


def test_right_dragging_a_shape_erases_it(ed):
    select(ed, (0, 0))
    ed.do("tool:shape")
    ed.do("shape:filled_box")
    drag(ed, (1, 1), (8, 8))
    ed.do("shape:box")
    drag(ed, (3, 3), (6, 6), button=3)
    assert walls(ed) == set(map_editor.shape_cells("filled_box", (1, 1), (8, 8))) \
        - set(map_editor.shape_cells("box", (3, 3), (6, 6)))


def test_shift_makes_a_square_or_a_circle_and_escape_cancels(ed):
    select(ed, (0, 0))
    ed.do("tool:shape")
    ed.mods = lambda: pygame.KMOD_SHIFT
    drag(ed, (1, 1), (7, 4))
    assert walls(ed) == set(map_editor.shape_cells("box", (1, 1), (7, 7)))
    ed.mods = lambda: 0
    mouse(ed, pygame.MOUSEBUTTONDOWN, cell_pos(ed, 2, 2))
    mouse(ed, pygame.MOUSEMOTION, cell_pos(ed, 5, 5))
    key(ed, pygame.K_ESCAPE)
    mouse(ed, pygame.MOUSEBUTTONUP, cell_pos(ed, 5, 5))
    assert ed.shape_drag is None and walls(ed) == set(map_editor.shape_cells("box", (1, 1), (7, 7)))


def test_a_shape_with_several_tiles_selected_repeats_them_as_a_pattern(ed):
    select(ed, (0, 0), (1, 0))                                       # tiles 1 and 2 side by side
    ed.do("tool:shape")
    ed.do("shape:line")
    drag(ed, (1, 4), (6, 4))
    assert [ed.level.walls[4][x] for x in range(1, 7)] == [1, 2, 1, 2, 1, 2]
    assert ed.level.walls[5][1] == 0                                 # one tile per cell, not the whole stamp


def test_shapes_paint_other_layers_too(ed):
    ed.do("layer:floor_h")
    ed.value[ed.gname()] = 0.5
    ed.do("tool:shape")
    ed.do("shape:filled_ellipse")
    drag(ed, (2, 2), (6, 6))
    for x, y in map_editor.shape_cells("filled_ellipse", (2, 2), (6, 6)):
        assert ed.level.get("floor_h", x, y) == 0.5
    assert ed.level.get("floor_h", 2, 2) != 0.5                      # outside the ellipse, in its box


def test_the_shape_buttons_choose_the_shape_and_show_it(ed):
    ed.do("tool:shape")
    actions = [action for _rect, _label, action in ed.layout()]
    assert [a for a in actions if a.startswith("shape:")] == [f"shape:{k}" for k in map_editor.SHAPES]
    ed.do("shape:ellipse")
    assert ed.shape == "ellipse"
    ed.draw(pygame.display.get_surface())


# ---------------------------------------------------------------- the rulers

def test_fit_view_keeps_the_map_clear_of_the_rulers(ed):
    ed.fit_view()
    area, origin = ed.map_area(), ed.cell_rect(0, 0)
    assert origin.x >= area.x + map_editor.RULER and origin.y >= area.y + map_editor.RULER
    far = ed.cell_rect(ed.level.width - 1, ed.level.height - 1)
    assert far.right <= area.right and far.bottom <= area.bottom


def test_ruler_numbers_are_spaced_to_fit_the_zoom(ed):
    ed.zoom = 64
    assert ed.ruler_label_step() == 1
    ed.zoom = 8
    assert ed.ruler_label_step() in (5, 10)
    assert all(step * 8 >= ed.small.size("10")[0] + 10 for step in [ed.ruler_label_step()])


def test_the_rulers_mark_the_middle_of_each_axis(ed):
    ed.fit_view()
    surface = pygame.display.get_surface()
    ed.draw(surface)
    area = ed.map_area()
    mx, my = (round(v) for v in ed.map_center())
    assert mx == ed.cell_rect(5, 0).x and my == ed.cell_rect(0, 5).y            # a 10 x 10 map: between cells 4 and 5
    assert tuple(surface.get_at((mx, area.y + map_editor.RULER - 4)))[:3] == map_editor.ACCENT
    assert tuple(surface.get_at((area.x + map_editor.RULER - 4, my)))[:3] == map_editor.ACCENT
    origin = ed.cell_rect(0, 0)
    assert tuple(surface.get_at((mx, origin.y - 3)))[:3] == map_editor.ACCENT    # and on the map's border


def test_clicking_a_ruler_does_not_paint_the_map_under_it(ed):
    ed.fit_view()
    ed.pan[1] -= ed.zoom * 2                                         # scroll so row 1 is under the top ruler
    area = ed.map_area()
    pos = (ed.cell_rect(3, 1).centerx, area.y + map_editor.RULER // 2)
    assert ed.over_ruler(pos) and ed.cell_at(pos)[1] >= 0
    select(ed, (0, 0))
    before = [row[:] for row in ed.level.walls]
    mouse(ed, pygame.MOUSEBUTTONDOWN, pos)
    mouse(ed, pygame.MOUSEBUTTONUP, pos)
    assert ed.level.walls == before
