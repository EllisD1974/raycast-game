"""Transparency in the map editor, and the guard that stops make_atlas from erasing textures.png."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import make_atlas
import map_editor
from atlas import atlas_array, transparent_tiles
from mapfile import Level

GLASS_INDEX = 6                                  # the atlas tile these tests turn into a see-through one


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1920, 1009), pygame.RESIZABLE)
    yield
    pygame.quit()


@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(12, 9)
    for y in range(1, 8):
        for x in range(1, 11):
            editor.level.set("ceil_h", x, y, 3.0)
    editor.mouse = (0, 0)
    # make atlas tile GLASS_INDEX a half transparent one, whatever textures.png holds
    tile = pygame.Surface((32, 32), pygame.SRCALPHA)
    tile.fill((0, 0, 0, 0))
    tile.fill((220, 40, 40, 255), (0, 0, 16, 32))               # an opaque red left half, a hole on the right
    editor.tiles[GLASS_INDEX] = tile
    editor.transparent = transparent_tiles(atlas_array(editor.tiles))
    editor._scaled.clear()
    editor.fit_view()
    editor.draw(pygame.display.get_surface())
    return editor


def test_the_editor_loads_the_atlas_with_its_alpha_channel(ed):
    assert ed.atlas_img.get_flags() & pygame.SRCALPHA
    assert len(ed.transparent) == len(ed.tiles) and ed.transparent.dtype == bool
    assert ed.is_transparent_tile(GLASS_INDEX + 1) and not ed.is_transparent_tile(1)
    assert ed.is_transparent_tile(10 ** 6) in (True, False)         # out-of-range ids don't raise


def test_transparent_atlas_pixels_show_a_checkerboard_behind_them(ed):
    # put the half transparent tile into the atlas picture itself, as an image editor would have
    ed.atlas_img.blit(ed.tiles[GLASS_INDEX], ed.tile_rect(GLASS_INDEX).move(-map_editor.ATLAS_X,
                                                                              -map_editor.ATLAS_Y).topleft,
                      special_flags=pygame.BLEND_RGBA_MAX)
    ed.atlas_img.fill((0, 0, 0, 0), ed.tile_rect(GLASS_INDEX).move(-map_editor.ATLAS_X + 16, -map_editor.ATLAS_Y))
    surface = pygame.display.get_surface()
    ed.draw(surface)
    rect = ed.tile_rect(GLASS_INDEX)
    hole = {tuple(surface.get_at((rect.x + 18 + dx, rect.y + 4 + dy)))[:3] for dx in range(0, 8) for dy in range(0, 8)}
    assert hole <= {(46, 48, 56), (70, 72, 82)} and len(hole) == 2   # exactly the two checker colors


def test_a_see_through_wall_shows_the_cell_behind_it_in_the_map(ed):
    ed.level.set("walls", 5, 4, GLASS_INDEX + 1)
    ed.revision += 1
    surface = pygame.display.get_surface()
    ed.draw(surface)
    rect = ed.cell_rect(5, 4)
    left = surface.get_at((rect.x + 3, rect.centery))[:3]
    right = surface.get_at((rect.right - 4, rect.centery))[:3]
    assert left == (220, 40, 40)                                    # the opaque part of the tile
    assert right == map_editor.EMPTY_CELL                           # the hole shows the empty cell, not black


def test_an_opaque_wall_is_drawn_as_before(ed):
    ed.level.set("walls", 5, 4, 1)
    ed.draw(pygame.display.get_surface())
    assert not ed.is_transparent_tile(1)


def test_hover_text_says_a_wall_is_see_through(ed):
    ed.level.set("walls", 5, 4, GLASS_INDEX + 1)
    ed.level.set("walls", 6, 4, 1)
    ed.mouse = ed.cell_rect(5, 4).center
    assert "see-through (blocks movement)" in ed.hover_info()
    ed.mouse = ed.cell_rect(6, 4).center
    assert "see-through" not in ed.hover_info()


def test_the_key_lists_see_through_walls_only_when_the_map_has_one(ed):
    kinds = lambda: [k for k, _t in ed.legend_entries()]
    assert "see_through" not in kinds() and ed.see_through_wall_tile() is None
    ed.level.set("walls", 5, 4, GLASS_INDEX + 1)
    ed.revision += 1
    assert "see_through" in kinds() and ed.see_through_wall_tile() == GLASS_INDEX + 1
    ed.do("layer:wall_h")
    assert "see_through" not in kinds()                              # the WallH layer shows heights instead
    ed.do("layer:floor_tex")
    assert "see_through" in kinds()
    ed.level.set("walls", 5, 4, 0)
    ed.revision += 1
    assert "see_through" not in kinds()


def test_the_key_icon_for_a_see_through_wall_shows_the_real_tile(ed):
    ed.level.set("walls", 5, 4, GLASS_INDEX + 1)
    ed.revision += 1
    surface = pygame.display.get_surface()
    ed.draw(surface)
    rect, columns, _docked = ed.legend_layout()
    entries = ed.legend_entries()
    per_column = (len(entries) + columns - 1) // columns
    i = [k for k, _t in entries].index("see_through")
    column, row = divmod(i, per_column)
    box = pygame.Rect(rect.x + 10 + column * (rect.w // columns),
                      rect.y + map_editor.LEGEND_TITLE + row * map_editor.LEGEND_ROW
                      + (map_editor.LEGEND_ROW - map_editor.LEGEND_ICON) // 2,
                      map_editor.LEGEND_ICON, map_editor.LEGEND_ICON)
    colors = {tuple(surface.get_at((x, y)))[:3] for x in range(box.left, box.right) for y in range(box.top, box.bottom)}
    assert (220, 40, 40) in colors and map_editor.EMPTY_CELL in colors


def test_a_see_through_short_wall_gets_the_short_wall_mark_too(ed):
    ed.level.set("walls", 5, 4, GLASS_INDEX + 1)
    ed.level.set("wall_h", 5, 4, 0.5)
    ed.revision += 1
    surface = pygame.display.get_surface()
    ed.do("layer:walls")
    ed.draw(surface)
    rect = ed.cell_rect(5, 4)
    assert surface.get_at((rect.centerx, rect.bottom - 6))[:3] == map_editor.SHORT_WALL
    ed.mouse = rect.center
    assert "short: 0.5 high" in ed.hover_info() and "see-through" in ed.hover_info()


def test_painting_a_see_through_wall_works_like_any_other(ed):
    ed.selection = {GLASS_INDEX}
    ed.do("layer:walls")
    ed.mouse = ed.cell_rect(5, 4).center
    pos = ed.cell_rect(5, 4).center
    ed.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    ed.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
    assert ed.level.walls[4][5] == GLASS_INDEX + 1
    ed.draw(pygame.display.get_surface())


def test_every_layer_and_floor_draws_with_see_through_walls(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "x.json"))
    editor.level = Level.blank(12, 9, floors=3)
    tile = pygame.Surface((32, 32), pygame.SRCALPHA)
    tile.fill((90, 90, 255, 100))
    editor.tiles[GLASS_INDEX] = tile
    editor.transparent = transparent_tiles(atlas_array(editor.tiles))
    editor._scaled.clear()
    editor.level.set("walls", 5, 4, GLASS_INDEX + 1)
    editor.mouse = (0, 0)
    surface = pygame.display.get_surface()
    for floor in range(3):
        editor.do(f"floor:{floor}")
        for name in map_editor.EDIT_LAYERS:
            editor.do(f"layer:{name}")
            editor.draw(surface)


# ------------------------------------------------------------------ make_atlas keeps hand-made atlases

def test_make_atlas_refuses_to_overwrite_an_existing_atlas(tmp_path):
    path = tmp_path / "textures.png"
    hand_made = pygame.Surface((64, 64), pygame.SRCALPHA)
    hand_made.fill((10, 200, 10, 77))
    pygame.image.save(hand_made, str(path))
    before = path.read_bytes()
    with pytest.raises(SystemExit) as stopped:
        make_atlas.main(str(path))
    assert "--force" in str(stopped.value) and "already exists" in str(stopped.value)
    assert path.read_bytes() == before                              # untouched


def test_make_atlas_creates_a_missing_atlas_and_regenerates_when_forced(tmp_path):
    path = tmp_path / "new.png"
    make_atlas.main(str(path))
    assert path.exists()
    image = pygame.image.load(str(path))
    assert image.get_size() == (make_atlas.TILE * make_atlas.COLUMNS, make_atlas.TILE * make_atlas.ROWS)
    path.write_bytes(b"not an atlas any more")
    make_atlas.main(str(path), force=True)                          # --force replaces it
    assert pygame.image.load(str(path)).get_size() == image.get_size()
