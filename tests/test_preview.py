"""The editor's live 3D view: it follows edits, can be looked through and walked, and the map still works."""
import collections
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import map_editor
import preview as preview_module
from atlas import ATLAS_PATH, atlas_array, unpack_atlas
from constants import MOUSE_SENSITIVITY
from mapfile import Level
from preview import Preview

SIZE = (1600, 900)


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode(SIZE, pygame.RESIZABLE)
    yield
    pygame.quit()


def make_editor(tmp_path, show=True):
    pygame.display.set_mode(SIZE, pygame.RESIZABLE)
    map_editor.DEFAULT_SHOW_PREVIEW = show
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(12, 10)
    editor.level.start_x, editor.level.start_y = 2.5, 5.5
    editor.mouse = (0, 0)
    editor.fit_view()
    editor.update(0.0, collections.defaultdict(int))
    editor.draw(pygame.display.get_surface())
    return editor


def keys(*held):
    pressed = collections.defaultdict(int)
    for key in held:
        pressed[key] = 1
    return pressed


def click(editor, pos, button=1):
    editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))


def release(editor, pos, button=1):
    editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))


def move(editor, pos, rel=(0, 0)):
    editor.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=rel, buttons=(1, 0, 0)))


def frame(editor):
    return pygame.surfarray.array3d(editor.preview.render()).copy()


@pytest.fixture
def ed(tmp_path):
    return make_editor(tmp_path)


def test_the_view_is_on_by_default_and_takes_room_from_the_map(ed, tmp_path):
    assert ed.preview is not None and ed.preview.ready
    off = make_editor(tmp_path, show=False)
    assert off.preview is None and off.preview_column() is None
    assert ed.map_area().right == ed.preview_column().left
    assert ed.map_area().width == off.map_area().width - ed.preview_width()
    rect = ed.preview_rect()
    assert rect.height == rect.width * 360 // 640


def test_toggle_hides_and_shows_it_and_refits_the_map(ed):
    ed.do("preview")
    assert not ed.show_preview and ed.preview_column() is None
    wide = ed.map_area().width
    ed.do("preview")
    assert ed.show_preview and ed.map_area().width < wide
    cell = ed.cell_rect(0, 0)
    assert ed.map_area().contains(cell)             # the refit keeps the map inside the narrower area


def test_v_toggles_and_the_toolbar_has_the_buttons(ed):
    labels = [label for _rect, label, _action in ed.layout()]
    assert "3D(V)" in labels and "Cam->Start" in labels and "Camera(C)" in labels
    ed.on_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_v, mod=0, unicode="v"))
    assert not ed.show_preview
    assert "Cam->Start" not in [label for _r, label, _a in ed.layout()]


def test_the_camera_starts_at_the_level_start(ed):
    p = ed.preview.player
    assert (p.x, p.y, p.span) == (2.5, 5.5, 0)


def test_edits_show_up_in_the_view(ed):
    before = frame(ed)
    p = ed.preview.player
    ed.begin_edit()                                          # put a wall straight ahead of the camera
    ed.level.walls[5][4] = 3
    ed.update(0.0, keys())
    after = frame(ed)
    assert ed.preview.built_revision == ed.revision
    assert not np.array_equal(before, after)
    assert (p.x, p.y) == (2.5, 5.5)


def test_undo_updates_the_view_back(ed):
    before = frame(ed)
    ed.begin_edit()
    ed.level.walls[5][4] = 3
    ed.update(0.0, keys())
    assert not np.array_equal(before, frame(ed))
    ed.do("undo")
    ed.update(0.0, keys())
    assert np.array_equal(before, frame(ed))


def test_rebuilds_are_throttled_while_edits_keep_coming_then_catch_up(ed, monkeypatch):
    monkeypatch.setattr(preview_module, "REBUILD_INTERVAL", 0.5)
    view = ed.preview
    view.last_build = 100.0
    view.built_revision = -1
    assert not view.sync(ed.level, 5, now=100.1)              # too soon: keeps the old world
    assert view.built_revision == -1
    assert view.sync(ed.level, 5, now=100.6)                  # later: catches up
    assert view.built_revision == 5
    assert not view.sync(ed.level, 5, now=200.0)              # nothing changed: nothing rebuilt


def test_raising_the_floor_under_the_camera_lifts_it_instead_of_burying_it(ed):
    ed.begin_edit()
    ed.level.grids["floor_h"][5][2] = 0.2                     # a step up: the camera rides onto it
    ed.level.grids["ceil_h"][5][2] = 2.0
    ed.update(0.0, keys())
    ed.update(0.1, keys())
    p = ed.preview.player
    assert p.z == pytest.approx(0.2, abs=1e-6)


def test_a_wall_built_on_the_camera_moves_it_out(ed):
    ed.begin_edit()
    ed.level.walls[5][2] = 1                                  # exactly where the camera stands
    ed.update(0.0, keys())
    p = ed.preview.player
    assert not ed.preview.world.is_blocked(int(p.x), int(p.y))
    assert (int(p.x), int(p.y)) != (2, 5)                     # it was relocated


def test_removing_the_floor_the_camera_is_on_does_not_crash(tmp_path):
    ed = make_editor(tmp_path)
    ed.level = Level.blank(12, 10, floors=2)
    ed.level.start_x = ed.level.start_y = 2.5
    ed.revision += 1
    ed.update(0.0, keys())
    ed.preview.player.span = 1
    ed.begin_edit()
    ed.level.floor_count                                      # still two floors, but span 1 has no room
    ed.update(0.0, keys())
    assert ed.preview.player.span in (0, 1)
    ed.level = Level.blank(12, 10)                            # now only one floor exists
    ed.revision += 1
    ed.update(0.0, keys())
    assert ed.preview.player.span == 0


def test_dragging_in_the_view_looks_around_and_clamps_the_pitch(ed):
    rect = ed.preview_rect()
    start = rect.center
    angle, pitch = ed.preview.player.angle, ed.preview.player.pitch
    click(ed, start)
    assert ed.look_drag
    move(ed, (start[0] + 40, start[1] - 20), rel=(40, -20))
    p = ed.preview.player
    assert p.angle == pytest.approx(angle + 40 * MOUSE_SENSITIVITY)
    assert p.pitch == pytest.approx(pitch + 20 * MOUSE_SENSITIVITY)       # up on screen looks up
    for _ in range(200):
        move(ed, start, rel=(0, -50))
    assert p.pitch == pytest.approx(np.radians(45), abs=0.02)
    release(ed, start)
    assert not ed.look_drag


def test_a_look_drag_does_not_paint_the_map(ed):
    before = [row[:] for row in ed.level.walls]
    revision = ed.revision
    click(ed, ed.preview_rect().center)
    move(ed, ed.map_area().center, rel=(100, 100))            # the cursor leaves the view mid-drag
    release(ed, ed.map_area().center)
    assert ed.level.walls == before and ed.revision == revision


def test_clicking_in_the_view_never_paints(ed):
    revision = ed.revision
    click(ed, ed.preview_column().center)
    release(ed, ed.preview_column().center)
    click(ed, ed.preview_column().center, button=3)
    release(ed, ed.preview_column().center, button=3)
    assert ed.revision == revision


def test_wasd_walks_the_camera_only_while_the_mouse_is_over_the_view(ed):
    p = ed.preview.player
    ed.mouse = ed.map_area().center
    ed.update(0.1, keys(pygame.K_w))
    assert (p.x, p.y) == (2.5, 5.5)
    ed.mouse = ed.preview_rect().center
    for _ in range(10):
        ed.update(1 / 60, keys(pygame.K_w))
    assert p.x > 2.5                                           # angle 0 faces +x
    x = p.x
    for _ in range(10):
        ed.update(1 / 60, keys(pygame.K_s))
    assert p.x < x


def test_strafe_turn_and_sprint(ed):
    p = ed.preview.player
    ed.mouse = ed.preview_rect().center
    for _ in range(10):
        ed.update(1 / 60, keys(pygame.K_d))
    assert p.y > 5.5                                           # strafing right from +x heads +y
    angle = p.angle
    ed.update(0.1, keys(pygame.K_RIGHT))
    assert p.angle > angle
    walk, run = Preview(atlas_array(unpack_atlas(ATLAS_PATH))), Preview(atlas_array(unpack_atlas(ATLAS_PATH)))
    for view, sprint in ((walk, False), (run, True)):
        view.sync(Level.blank(12, 10), 1)
        view.place(2.5, 5.5)
        for _ in range(20):
            view.update(1 / 60, 1, 0, 0.0, sprint)
    assert run.player.x - 2.5 > (walk.player.x - 2.5) * 1.3


def test_wasd_do_not_trigger_tool_hotkeys_over_the_view_but_do_elsewhere(ed):
    ed.mouse = ed.preview_rect().center
    tool = ed.tool
    ed.on_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s, mod=0, unicode="s"))
    assert ed.tool == tool                                     # S would have chosen the Start tool
    ed.mouse = ed.map_area().center
    ed.on_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s, mod=0, unicode="s"))
    assert ed.tool == "start"


def test_space_over_the_view_jumps(ed):
    p = ed.preview.player
    ed.mouse = ed.preview_rect().center
    ed.on_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=" "))
    ed.update(1 / 60, keys())
    ed.update(1 / 60, keys())
    assert p.z > 0 and not p.on_ground
    for _ in range(120):
        ed.update(1 / 60, keys())
    assert p.on_ground and p.z == pytest.approx(0.0, abs=1e-6)


def test_the_wheel_over_the_view_walks_and_does_not_zoom_the_map(ed):
    ed.mouse = ed.preview_rect().center
    zoom, x = ed.zoom, ed.preview.player.x
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
    assert ed.zoom == zoom and ed.preview.player.x > x
    x = ed.preview.player.x
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
    assert ed.preview.player.x < x
    ed.mouse = ed.map_area().center
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
    assert ed.zoom > zoom


def test_the_camera_tool_places_and_aims_from_the_map(ed):
    ed.do("tool:camera")
    cell = (8, 3)
    pos = ed.cell_rect(*cell).center
    ed.mouse = pos
    revision = ed.revision
    click(ed, pos)
    p = ed.preview.player
    assert (p.x, p.y) == (8.5, 3.5) and ed.camera_drag
    target = ed.cell_rect(8, 8).center
    ed.mouse = target
    move(ed, target)
    assert p.angle == pytest.approx(np.pi / 2, abs=0.05)       # facing +y (down the map)
    release(ed, target)
    assert not ed.camera_drag and ed.revision == revision      # nothing in the level changed


def test_the_camera_tool_refuses_a_wall(ed):
    ed.begin_edit()
    ed.level.walls[3][8] = 1
    ed.update(0.0, keys())
    ed.do("tool:camera")
    pos = ed.cell_rect(8, 3).center
    ed.mouse = pos
    p = ed.preview.player
    before = (p.x, p.y)
    click(ed, pos)
    assert (p.x, p.y) == before and not ed.camera_drag


def test_choosing_the_camera_tool_shows_a_hidden_view(tmp_path):
    ed = make_editor(tmp_path, show=False)
    ed.on_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c, mod=0, unicode="c"))
    assert ed.tool == "camera" and ed.show_preview and ed.preview.ready


def test_camera_to_start_button_resets_the_camera(ed):
    ed.preview.place(8.5, 3.5)
    ed.do("camstart")
    p = ed.preview.player
    assert (p.x, p.y) == (2.5, 5.5)


def test_the_map_still_paints_in_the_narrowed_map_area(ed):
    ed.layer, ed.tool = "walls", "paint"
    pos = ed.cell_rect(4, 4).center
    assert ed.map_area().collidepoint(pos)
    ed.mouse = pos
    click(ed, pos)
    release(ed, pos)
    assert ed.level.walls[4][4] != 0
    ed.update(0.0, keys())
    assert ed.preview.built_revision == ed.revision


def test_a_paint_stroke_updates_the_view_live(ed):
    ed.layer, ed.tool = "walls", "paint"
    start = ed.cell_rect(3, 2).center
    ed.mouse = start
    before = frame(ed)
    click(ed, start)
    end = ed.cell_rect(9, 2).center
    move(ed, end, rel=(1, 0))
    ed.update(0.0, keys())                                    # mid-stroke: the wall is already visible
    assert ed.preview.built_revision == ed.revision
    release(ed, end)
    assert not np.array_equal(before, frame(ed))


def test_the_key_lists_the_camera_only_while_the_view_is_shown(ed):
    assert any(kind == "camera" for kind, _text in ed.legend_entries())
    ed.draw(pygame.display.get_surface())                      # the icon draws without error
    ed.do("preview")
    assert not any(kind == "camera" for kind, _text in ed.legend_entries())


def test_the_camera_marker_is_drawn_on_the_map(ed):
    screen = pygame.display.get_surface()
    ed.draw(screen)
    p = ed.preview.player
    origin = ed.cell_rect(0, 0)
    spot = (int(origin.x + p.x * ed.zoom), int(origin.y + p.y * ed.zoom))
    assert tuple(screen.get_at(spot))[:3] == (255, 255, 255)   # the camera's centre dot
    ed.do("preview")
    ed.draw(screen)
    assert tuple(screen.get_at(spot))[:3] != (255, 255, 255)


def test_a_small_window_still_lays_out_and_draws(tmp_path):
    pygame.display.set_mode((1000, 600), pygame.RESIZABLE)
    map_editor.DEFAULT_SHOW_PREVIEW = True
    ed = map_editor.Editor(str(tmp_path / "m.json"))
    ed.update(0.0, keys())
    ed.draw(pygame.display.get_surface())
    assert ed.map_area().width >= 1


def test_new_and_reload_keep_the_view_working(ed, tmp_path):
    ed.do("new")
    ed.update(0.0, keys())
    assert ed.preview.built_revision == ed.revision and ed.preview.world.width == 16
    ed.draw(pygame.display.get_surface())
