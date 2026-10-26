"""Walls with a texture of their own on one side, and items hung flat on a wall."""
import json
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import map_editor
import physics
from entities import Entities
from mapfile import Entity, Level, level_text, mounted_position, parse_level, wall_facing
from renderer import Renderer
from world import World

RED, GREEN, BLUE, YELLOW, MAGENTA = (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)
HEIGHT_MIDDLE, WIDTH_MIDDLE = 180, 320              # the middle of the 640 x 360 picture
SIDE_TILE, ITEM_TILE = 8, 9                     # map id 8 (atlas index 7) is yellow; atlas index 9 is the item


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1920, 1009), pygame.RESIZABLE)        # (room for the map beside the item list)
    yield
    pygame.quit()


def flat_textures():
    textures = np.zeros((16, 32, 32, 4), np.uint8)
    textures[..., :3] = 120
    textures[..., 3] = 255
    textures[0, ..., :3] = RED                  # walls (map id 1)
    textures[4, ..., :3] = GREEN                # floor
    textures[5, ..., :3] = BLUE                 # ceiling
    textures[SIDE_TILE - 1, ..., :3] = YELLOW
    textures[ITEM_TILE, ..., :3] = MAGENTA
    return textures


def room():
    """A 10 x 10 room with one wall in the middle, at (5, 5)."""
    level = Level.blank(10, 10)
    level.walls[5][5] = 1
    return level


def look(level, x, y, angle, pitch=0.0, sprites=None):
    renderer = Renderer(flat_textures())
    world = World(level, 16)
    player = physics.Player(x, y, 0.0, angle, pitch=pitch)
    renderer.draw(world, player, Entities(level, world).sprites() if sprites is None else sprites)
    return np.array(renderer.framebuffer).astype(int)


def color_at_middle(fb):
    r, g, b = fb[fb.shape[0] // 2, fb.shape[1] // 2]
    if r > 100 and g > 100 and b < 60:
        return YELLOW
    if r > 100 and g < 60 and b < 60:
        return RED
    if r > 100 and b > 100 and g < 60:
        return MAGENTA
    return (r, g, b)


def magenta(fb):
    return (fb[..., 0] > 100) & (fb[..., 2] > 100) & (fb[..., 1] < 60)


# ------------------------------------------------------------------ a texture on one side of a wall

@pytest.mark.parametrize("pitch", [0.0, math.radians(3), -0.15])         # level, sheared, and rotated
def test_a_side_with_its_own_tile_shows_it_and_the_other_sides_keep_the_wall_tile(pitch):
    level = room()
    level.grids["side_s"][5][5] = SIDE_TILE
    assert color_at_middle(look(level, 5.5, 8.5, -math.pi / 2, pitch)) == YELLOW      # looking north at its south side
    assert color_at_middle(look(level, 5.5, 2.5, math.pi / 2, pitch)) == RED          # its north side
    assert color_at_middle(look(level, 2.5, 5.5, 0.0, pitch)) == RED                  # its west side
    level.grids["side_w"][5][5] = SIDE_TILE
    assert color_at_middle(look(level, 2.5, 5.5, 0.0, pitch)) == YELLOW


def test_a_short_wall_shows_a_sides_tile_on_that_side_too():
    level = room()
    level.grids["wall_h"][5][5] = 0.4                   # short: you can see over it
    level.grids["side_s"][5][5] = SIDE_TILE
    fb = look(level, 5.5, 8.5, -math.pi / 2)
    column = fb[fb.shape[0] // 2]
    yellow = (column[:, 0] > 100) & (column[:, 1] > 100) & (column[:, 2] < 60)
    assert yellow.any() and yellow[fb.shape[1] // 2 + 5:].any()      # the low wall's face, below the middle


def test_side_tiles_are_saved_only_when_some_wall_has_one():
    level = room()
    assert "side_n" not in level_text(level)
    level.grids["side_e"][5][5] = SIDE_TILE
    text = level_text(level)
    assert '"side_e"' in text and '"side_n"' not in text
    again = parse_level(json.loads(text))
    assert again.grids["side_e"][5][5] == SIDE_TILE and again.grids["side_n"][5][5] == 0


def test_a_side_tile_on_an_open_cell_means_nothing():
    level = room()
    level.grids["side_s"][3][3] = SIDE_TILE                       # (3, 3) is open
    assert (World(level, 16).wall_sides[3, 3, :, 0] == -1).all()


# ------------------------------------------------------------------ items hung on a wall

def hung_item(level, cell=(5, 6), wall="n", lift=0.25, size=0.5):
    x, y = mounted_position(*cell, wall)
    item = Entity(x, y, tile=ITEM_TILE, size=size, lift=lift, wall=wall, mode="scenery", effect="none")
    level.entities.append(item)
    return item


def test_a_hung_item_sits_just_off_its_wall_and_faces_into_its_cell():
    x, y = mounted_position(5, 6, "n")
    assert x == 5.5 and 6.0 < y < 6.1
    assert wall_facing("n") == pytest.approx(math.pi / 2)            # facing south, away from a north wall
    assert wall_facing("w") == pytest.approx(0.0)
    level = room()
    hung_item(level)
    sprite = Entities(level, World(level, 16)).sprites()[0]
    assert len(sprite) == 10 and sprite[9] == pytest.approx(math.pi / 2)


def test_a_hung_item_is_kept_with_the_map_and_free_standing_items_are_unchanged():
    level = room()
    hung_item(level)
    level.entities.append(Entity(2.5, 2.5))
    again = parse_level(json.loads(level_text(level)))
    assert [e.wall for e in again.entities] == ["n", ""]
    assert len(Entities(again, World(again, 16)).sprites()[1]) == 8      # a free-standing item faces the camera
    assert Entity.from_dict({"x": 1.5, "y": 1.5, "wall": "up"}).wall == ""


def test_a_hung_item_is_drawn_on_its_wall_from_in_front():
    level = room()
    hung_item(level)
    item = level.entities[0]
    fb = look(level, 5.5, 9.0, -math.pi / 2)
    assert color_at_middle(fb) == MAGENTA
    rows = np.nonzero(magenta(fb)[fb.shape[0] // 2])[0]
    focal, distance = Renderer(flat_textures()).focal, 9.0 - item.y
    top = fb.shape[1] / 2 - (item.lift + item.size - 0.5) / distance * focal       # (the eye is 0.5 up)
    bottom = fb.shape[1] / 2 + (0.5 - item.lift) / distance * focal                 # lifted off the floor
    assert abs(rows.min() - top) <= 2 and abs(rows.max() + 1 - bottom) <= 2


def test_a_hung_item_is_not_drawn_from_behind():
    level = Level.blank(10, 10)                                      # no wall: nothing hides it from behind
    hung_item(level)
    assert magenta(look(level, 5.5, 9.0, -math.pi / 2)).sum() > 100
    assert magenta(look(level, 5.5, 3.0, math.pi / 2)).sum() == 0


def test_a_hung_item_seen_from_the_side_narrows_like_a_flat_picture():
    level = room()
    item = hung_item(level, size=0.6)
    distance = 3.0
    front = magenta(look(level, item.x, item.y + distance, -math.pi / 2))
    side_x, side_y = item.x + distance * math.sin(math.radians(50)), item.y + distance * math.cos(math.radians(50))
    angled = magenta(look(level, side_x, side_y, math.atan2(item.y - side_y, item.x - side_x)))
    width = lambda mask: np.ptp(np.nonzero(mask.any(axis=1))[0]) + 1
    assert width(front) * 0.45 < width(angled) < width(front) * 0.8      # about cos(50 degrees) as wide
    assert angled.sum() > 0


def test_an_item_from_a_prefab_keeps_its_own_wall():
    level = room()
    prefab = Entity(0.0, 0.0, name="torch", tile=ITEM_TILE)
    level.prefabs.append(prefab)
    item = hung_item(level)
    item.prefab = "torch"
    level.apply_prefabs()
    assert item.wall == "n" and item.tile == ITEM_TILE


# ------------------------------------------------------------------ the editor

@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = room()
    editor.show_legend = False
    editor.draw(pygame.display.get_surface())
    return editor


def near(ed, cell, side):
    """A screen point inside `cell`, close to its `side`."""
    rect = ed.cell_rect(*cell)
    return {"n": (rect.centerx, rect.y + 2), "s": (rect.centerx, rect.bottom - 3),
            "w": (rect.x + 2, rect.centery), "e": (rect.right - 3, rect.centery)}[side]


def press(ed, pos, button=1):
    ed.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
    ed.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
    ed.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))


def test_the_wallside_layer_paints_the_side_nearest_the_mouse_and_erases_it(ed):
    ed.selection = {SIDE_TILE - 1}
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_8, mod=0, unicode="8"))
    assert ed.layer == "sides"
    press(ed, near(ed, (5, 5), "s"))
    assert ed.level.grids["side_s"][5][5] == SIDE_TILE and ed.level.grids["side_n"][5][5] == 0
    ed.draw(pygame.display.get_surface())                            # the side's strip draws
    press(ed, near(ed, (5, 5), "s"), button=3)
    assert ed.level.grids["side_s"][5][5] == 0
    press(ed, near(ed, (3, 3), "s"))                                 # an open cell has no sides to paint
    assert ed.level.grids["side_s"][3][3] == 0


def test_fill_gives_one_side_of_the_whole_wall_the_tile_and_pick_takes_it(ed):
    for x in range(3, 7):
        ed.level.walls[5][x] = 1                                     # a wall from (3, 5) to (6, 5)
    ed.selection = {SIDE_TILE - 1}
    ed.do("layer:sides")
    ed.do("tool:fill")
    press(ed, near(ed, (4, 5), "s"))
    assert [ed.level.grids["side_s"][5][x] for x in range(3, 7)] == [SIDE_TILE] * 4
    assert ed.level.grids["side_n"][5][4] == 0
    ed.selection = {0}
    ed.do("tool:pick")
    press(ed, near(ed, (6, 5), "s"))
    assert ed.selection == {SIDE_TILE - 1} and ed.tool == "paint"


def test_a_shape_on_the_wallside_layer_paints_the_side_picked_where_it_starts(ed):
    for x in range(3, 7):
        ed.level.walls[5][x] = 1
    ed.selection = {SIDE_TILE - 1}
    ed.do("layer:sides")
    ed.do("tool:shape")
    ed.do("shape:line")
    start, end = near(ed, (3, 5), "n"), near(ed, (6, 5), "s")       # ends near another side: the start counts
    ed.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=start, rel=(0, 0), buttons=(0, 0, 0)))
    ed.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=start, button=1))
    ed.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=end, rel=(0, 0), buttons=(1, 0, 0)))
    ed.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=end, button=1))
    assert [ed.level.grids["side_n"][5][x] for x in range(3, 7)] == [SIDE_TILE] * 4
    assert not any(ed.level.grids["side_s"][5][x] for x in range(3, 7))


def test_a_new_or_erased_wall_has_no_side_tiles(ed):
    ed.level.grids["side_e"][5][5] = SIDE_TILE
    ed.do("layer:walls")
    ed.do("tool:erase")
    press(ed, ed.cell_rect(5, 5).center)
    assert ed.level.walls[5][5] == 0 and ed.level.grids["side_e"][5][5] == 0
    ed.level.grids["side_e"][5][5] = SIDE_TILE                       # (left behind by something else)
    ed.selection = {0}
    ed.do("tool:paint")
    press(ed, ed.cell_rect(5, 5).center)
    assert ed.level.walls[5][5] == 1 and ed.level.grids["side_e"][5][5] == 0


def test_an_item_added_near_a_walled_side_hangs_on_that_wall(ed):
    ed.do("tool:entity")
    ed.draw(pygame.display.get_surface())
    ed.fit_view()
    press(ed, near(ed, (5, 6), "n"))                                 # (5, 5) above it is a wall
    item = ed.level.entities[-1]
    assert item.wall == "n" and (item.x, item.y) == mounted_position(5, 6, "n")
    ed.deselect()
    press(ed, ed.cell_rect(3, 3).center)                             # the middle of a cell: standing
    assert ed.level.entities[-1].wall == "" and (ed.level.entities[-1].x, ed.level.entities[-1].y) == (3.5, 3.5)
    ed.deselect()
    press(ed, near(ed, (3, 4), "s"))                                 # near a side with no wall: standing
    assert ed.level.entities[-1].wall == ""


def test_the_on_wall_setting_moves_an_item_between_its_walls(ed):
    ed.level.walls[6][4] = 1                                         # (5, 6) has walls north and west
    ed.do("tool:entity")
    ed.fit_view()
    press(ed, ed.cell_rect(5, 6).center)
    item = ed.level.entities[-1]
    field = next(r.field for r in ed.details_rows() if r.field.key == "wall")
    assert field.choices == ("", "n", "w")
    field.set("w")
    assert item.wall == "w" and (item.x, item.y) == mounted_position(5, 6, "w")
    field.set("")
    assert item.wall == "" and (item.x, item.y) == (5.5, 6.5)
    ed.draw(pygame.display.get_surface())


# ------------------------------------------------------------------ a side's tile over only part of its height

def column_colors(fb):
    """The middle column of the picture as a list of YELLOW / RED / None per row."""
    out = []
    for r, g, b in fb[fb.shape[0] // 2]:
        out.append(YELLOW if r > 100 and g > 100 and b < 60 else RED if r > 100 and g < 60 and b < 60 else None)
    return out


@pytest.mark.parametrize("pitch", [0.0, math.radians(3), -0.15])
def test_a_side_tile_with_a_band_covers_only_those_heights(pitch):
    level = room()
    level.grids["side_s"][5][5] = SIDE_TILE
    level.grids["side_s_to"][5][5] = 0.4                            # the bottom 0.4 of a 1.0 tall wall
    rows = column_colors(look(level, 5.5, 8.0, -math.pi / 2, pitch))
    wall = [c for c in rows if c is not None]
    assert wall[0] == RED and wall[-1] == YELLOW                     # wall's tile at the top, the band at the foot
    first_yellow = wall.index(YELLOW)
    assert all(c == RED for c in wall[:first_yellow]) and all(c == YELLOW for c in wall[first_yellow:])
    assert 0.5 < first_yellow / len(wall) < 0.7                      # the band is the bottom 40 percent
    level.grids["side_s_from"][5][5] = 0.2                           # from 0.2 to 0.4: wall tile below it too
    wall = [c for c in column_colors(look(level, 5.5, 8.0, -math.pi / 2, pitch)) if c is not None]
    assert wall[0] == RED and wall[-1] == RED and YELLOW in wall


def test_the_band_is_measured_from_the_foot_of_the_wall():
    level = room()
    for x in range(1, 9):
        for y in range(6, 9):
            level.grids["floor_h"][y][x] = 0.5                       # the room in front of the wall is raised
    level.grids["side_s"][5][5] = SIDE_TILE
    level.grids["side_s_to"][5][5] = 0.4
    world = World(level, 16)
    assert world.wall_sides[5, 5, 2, 0] == SIDE_TILE - 1
    low, high = world.wall_sides[5, 5, 2, 1:]
    assert low < -1e8 and high == pytest.approx(level.wall_base(5, 5) + 0.4)


def test_the_band_is_saved_with_the_map():
    level = room()
    level.grids["side_s"][5][5] = SIDE_TILE
    level.grids["side_s_from"][5][5], level.grids["side_s_to"][5][5] = 0.2, 0.6
    again = parse_level(json.loads(level_text(level)))
    assert (again.grids["side_s_from"][5][5], again.grids["side_s_to"][5][5]) == (0.2, 0.6)
    assert '"side_n_from"' not in level_text(level)


def test_from_and_to_set_the_band_that_painting_a_side_gives_it(ed):
    ed.selection = {SIDE_TILE - 1}
    ed.do("layer:sides")
    actions = [action for _rect, _label, action in ed.layout()]
    assert {"side_from-", "side_from+", "side_to-", "side_to+", "side_full"} <= set(actions)
    ed.do("side_to-")
    assert ed.side_to == 0.9                                         # from the top: just under a standard wall
    for _ in range(5):
        ed.do("side_to-")
    ed.do("side_from+")
    ed.do("side_from+")
    assert (ed.side_from, ed.side_to) == (0.2, 0.4)
    press(ed, near(ed, (5, 5), "s"))
    assert (ed.level.grids["side_s_from"][5][5], ed.level.grids["side_s_to"][5][5]) == (0.2, 0.4)
    for _ in range(3):
        ed.do("side_from+")                                          # the band never ends where it starts
    assert ed.side_from == 0.5 and ed.side_to == 0.6
    ed.do("side_full")
    assert (ed.side_from, ed.side_to) == (0.0, 0.0)
    ed.do("tool:pick")
    press(ed, near(ed, (5, 5), "s"))                                 # Pick takes the band too
    assert (ed.side_from, ed.side_to) == (0.2, 0.4)
    press(ed, near(ed, (5, 5), "s"), button=3)                       # (right-click erases)
    assert ed.level.grids["side_s"][5][5] == 0 and ed.level.grids["side_s_to"][5][5] == 0.0
    ed.draw(pygame.display.get_surface())


# ------------------------------------------------------------------ a side tile with transparent pixels

def look_with(textures, level, x, y, angle, pitch):
    renderer = Renderer(textures)
    renderer.draw(World(level, 16), physics.Player(x, y, 0.0, angle, pitch=pitch))
    return np.array(renderer.framebuffer).astype(int)


@pytest.mark.parametrize("pitch", [0.0, math.radians(3), -0.15])
def test_the_wall_shows_through_the_transparent_part_of_a_side_tile(pitch):
    textures = flat_textures()
    textures[SIDE_TILE - 1, :, :16, :3] = MAGENTA                    # (what a transparent pixel holds: never shown)
    textures[SIDE_TILE - 1, :, :16, 3] = 0                           # half of the tile is see-through
    level = room()
    level.grids["side_s"][5][5] = SIDE_TILE
    row = look_with(textures, level, 5.5, 7.0, -math.pi / 2, pitch)[:, HEIGHT_MIDDLE]
    yellow = (row[:, 0] > 100) & (row[:, 1] > 100) & (row[:, 2] < 60)
    red = (row[:, 0] > 100) & (row[:, 1] < 60) & (row[:, 2] < 60)
    leaked = (row[:, 0] > 100) & (row[:, 2] > 100) & (row[:, 1] < 60)
    assert yellow.sum() > 20 and red.sum() > 20 and not leaked.any()


def test_a_partly_transparent_side_tile_mixes_with_the_wall():
    textures = flat_textures()
    textures[SIDE_TILE - 1, ..., 3] = 128                            # yellow at half strength over red
    level = room()
    level.grids["side_s"][5][5] = SIDE_TILE
    for pitch in (0.0, -0.15):
        r, g, b = look_with(textures, level, 5.5, 7.0, -math.pi / 2, pitch)[WIDTH_MIDDLE, HEIGHT_MIDDLE]
        assert g > 20 and abs(r - 2 * g) <= 3 and b < 20             # half yellow, half red: green at half the red


# ------------------------------------------------------------------ each placed copy's own elevation

def test_elevation_raises_one_placed_item_and_is_kept_with_the_map():
    level = room()
    item = hung_item(level, lift=0.25)
    level.entities.append(Entity(2.5, 2.5, lift=0.25))
    item.elevation = 0.3
    zs = [i.z for i in Entities(level, World(level, 16)).items]
    assert zs == [pytest.approx(0.55), pytest.approx(0.25)]
    again = parse_level(json.loads(level_text(level)))
    assert [e.elevation for e in again.entities] == [0.3, 0.0]


def test_a_prefab_never_sets_the_elevation_of_its_copies():
    level = room()
    level.prefabs.append(Entity(0.0, 0.0, name="torch", tile=ITEM_TILE, lift=0.2, elevation=0.0))
    a, b = hung_item(level), hung_item(level, cell=(3, 1))
    a.prefab = b.prefab = "torch"
    a.elevation = 0.5
    level.prefabs[0].lift = 0.4
    level.apply_prefabs()
    assert (a.lift, b.lift) == (0.4, 0.4) and (a.elevation, b.elevation) == (0.5, 0.0)


def test_raising_a_hung_item_moves_it_up_the_wall_in_the_3d_view():
    level = room()
    item = hung_item(level)
    top = lambda: np.nonzero(magenta(look(level, 5.5, 9.0, -math.pi / 2))[WIDTH_MIDDLE])[0].min()
    low = top()
    item.elevation = 0.2
    assert top() < low - 10                                          # higher on the wall: nearer the top of the picture


def test_the_elevation_row_and_brackets_move_only_the_selected_copy(ed):
    ed.level.prefabs.append(Entity(0.0, 0.0, name="torch", tile=ITEM_TILE, lift=0.2))
    ed.place_prefab = "torch"
    ed.do("tool:entity")
    ed.fit_view()
    press(ed, near(ed, (5, 6), "n"))
    first = ed.level.entities[-1]
    ed.deselect()
    press(ed, near(ed, (3, 6), "s"))                                 # a second copy, standing
    second = ed.level.entities[-1]
    keys = [r.field.key for r in ed.details_rows()]
    assert keys[:5] == ["prefab", "edit_prefab", "detach", "this_copy", "elevation"]
    field = next(r.field for r in ed.details_rows() if r.field.key == "elevation")
    field.set(0.35)
    assert second.elevation == 0.35 and first.elevation == 0.0 and ed.level.prefabs[0].elevation == 0.0
    assert second.lift == first.lift == 0.2                          # the prefab's settings are untouched
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHTBRACKET, mod=0, unicode="]"))
    assert second.elevation == pytest.approx(0.4)
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFTBRACKET, mod=pygame.KMOD_SHIFT, unicode="["))
    assert second.elevation == pytest.approx(0.15) and first.elevation == 0.0
    ed.draw(pygame.display.get_surface())                            # (the map shows +0.15 beside it)
    ed.do("undo")                                                    # (undo puts back a copy of the level)
    assert [e.elevation for e in ed.level.entities] == [0.0, pytest.approx(0.4)]
