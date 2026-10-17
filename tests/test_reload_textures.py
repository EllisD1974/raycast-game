"""Reloading textures.png in the editor, by hand (F6) and by itself when the file changes."""
import collections
import os
import shutil
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import atlas
import map_editor
from mapfile import Level

REAL_ATLAS = atlas.ATLAS_PATH                                # the user's file: only ever read


@pytest.fixture
def ed(tmp_path, monkeypatch):
    """An editor reading a private copy of the atlas, so tests may change it freely."""
    copy = tmp_path / "textures.png"
    shutil.copy(REAL_ATLAS, copy)
    monkeypatch.setattr(map_editor, "ATLAS_PATH", str(copy))
    monkeypatch.setattr(atlas, "ATLAS_PATH", str(copy))
    monkeypatch.setattr(map_editor, "unpack_atlas", lambda path=str(copy): atlas.unpack_atlas(path))
    pygame.init()
    pygame.display.set_mode((1600, 900), pygame.RESIZABLE)
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(12, 10)
    editor.revision += 1
    editor.copy_path = copy
    yield editor
    pygame.quit()


def repaint(path, colour, tile=0):
    """Fill one tile of the atlas file with a colour."""
    image = pygame.image.load(str(path)).convert_alpha()      # the atlas file may be palettised
    image.fill(colour, (tile % 16 * 32, tile // 16 * 32, 32, 32))
    pygame.image.save(image, str(path))


def bump(path):
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


def test_the_button_and_key_exist(ed):
    assert "Reload tex(F6)" in [label for _r, label, _a in ed.layout()]
    repaint(ed.copy_path, (1, 2, 3))
    ed.on_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6, mod=0, unicode=""))
    assert tuple(ed.tiles[0].get_at((5, 5)))[:3] == (1, 2, 3)


def test_reload_updates_tiles_atlas_picture_and_scaled_caches(ed):
    ed.tile_surface(0)                                       # warm the scaled-tile cache
    repaint(ed.copy_path, (10, 200, 30))
    assert ed.reload_textures()
    assert tuple(ed.tile_surface(0).get_at((3, 3)))[:3] == (10, 200, 30)
    assert tuple(ed.atlas_img.get_at((3, 3)))[:3] == (10, 200, 30)
    assert tuple(ed.legend_tile(0, False).get_at((3, 3)))[:3] == (10, 200, 30)


def test_reload_updates_which_tiles_are_see_through(ed):
    assert not ed.transparent[40]
    image = pygame.image.load(str(ed.copy_path)).convert_alpha()
    image.fill((0, 0, 0, 0), (40 % 16 * 32, 40 // 16 * 32, 16, 32))
    pygame.image.save(image, str(ed.copy_path))
    ed.reload_textures()
    assert ed.transparent[40]
    assert ed.is_transparent_tile(41)


def test_reload_updates_the_3d_view(ed):
    ed.level.start_x, ed.level.start_y = 2.5, 5.5
    ed.set_preview(True)
    ed.update(0.0, collections.defaultdict(int))
    before = pygame.surfarray.array3d(ed.preview.render()).copy()
    for tile in range(8):                                    # every common floor/wall/ceiling tile
        repaint(ed.copy_path, (250, 0, 250), tile)
    ed.reload_textures()
    ed.update(0.0, collections.defaultdict(int))
    after = pygame.surfarray.array3d(ed.preview.render()).copy()
    assert not np.array_equal(before, after)
    assert ed.preview.built_revision == ed.revision


def test_a_changed_file_is_picked_up_by_itself(ed):
    repaint(ed.copy_path, (9, 9, 99))
    bump(ed.copy_path)
    ed.watch_textures(now=ed._atlas_check + 1)
    assert tuple(ed.tiles[0].get_at((5, 5)))[:3] == (9, 9, 99)
    assert "reloaded" in ed.message.lower()


def test_an_unchanged_file_is_not_reloaded_and_checks_are_throttled(ed, monkeypatch):
    calls = []
    monkeypatch.setattr(ed, "load_textures", lambda: calls.append(1))
    ed.watch_textures(now=ed._atlas_check + 1)
    assert calls == []
    bump(ed.copy_path)
    ed.watch_textures(now=ed._atlas_check + 0.1)             # too soon: not even looked at
    assert calls == []
    ed.watch_textures(now=ed._atlas_check + 1)
    assert calls == [1]


def test_a_broken_file_keeps_the_old_textures_and_is_not_retried_until_it_changes_again(ed):
    old = tuple(ed.tiles[0].get_at((5, 5)))
    ed.copy_path.write_bytes(b"not a png")
    bump(ed.copy_path)
    ed.watch_textures(now=ed._atlas_check + 1)               # silent for automatic reloads
    assert tuple(ed.tiles[0].get_at((5, 5))) == old
    stamp = ed._atlas_stamp
    assert not ed.reload_textures()
    assert "could not" in ed.message.lower()
    assert tuple(ed.tiles[0].get_at((5, 5))) == old
    ed.watch_textures(now=ed._atlas_check + 1)
    assert ed._atlas_stamp == stamp                          # no retry loop on the same bad file
    shutil.copy(REAL_ATLAS, ed.copy_path)
    repaint(ed.copy_path, (7, 7, 7))
    bump(ed.copy_path)
    bump(ed.copy_path)
    ed.watch_textures(now=ed._atlas_check + 1)
    assert tuple(ed.tiles[0].get_at((5, 5)))[:3] == (7, 7, 7)


def test_a_missing_file_is_handled(ed):
    ed.copy_path.unlink()
    assert not ed.reload_textures()
    ed.watch_textures(now=ed._atlas_check + 1)               # nothing to compare: quietly ignored
    ed.draw(pygame.display.get_surface())


def test_the_selection_survives_a_reload_and_is_clamped(ed):
    ed.selection = {1, 2}
    ed.reload_textures()
    assert ed.selection == {1, 2}
    ed.selection = {99999}
    ed.reload_textures()
    assert ed.selection == {0}

