"""The editor's Lights section, the ambient light, and the pickers that hand a light to guns, ammo, effects and items."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import details
import map_editor
from mapfile import AmmoType, Effect, Entity, Gun, Level, Light, load_level
from preview import Preview


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(10, 10)
    editor.level.start_x = editor.level.start_y = 1.5
    editor.show_legend = False
    editor.draw(pygame.display.get_surface())
    return editor


def key(ed, k, char=""):
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=char))


def click(ed, pos, button=1):
    ed.on_mouse_down(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
    ed.on_mouse_up(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))


def row(ed, name):
    return next(r for r in ed.details_rows() if r.field.key == name)


def keys(ed):
    return [r.field.key for r in ed.details_rows()]


def choose(ed, name, choice):
    r = row(ed, name)
    click(ed, details.menu_anchor(r).center)
    assert ed.menu_open == name
    for rect, option in details.menu_rects(r):
        if option == choice:
            click(ed, rect.center)
            return
    raise AssertionError(f"{choice} is not offered for {name}")


def add_light(ed):
    if not ed.lights_mode:
        ed.do("lights")
    click(ed, ed.light_rows()[2].center)
    return ed.level.lights[-1]


# ------------------------------------------------------------------ the section

def test_the_lights_button_and_l_key_open_and_close_the_section_and_sections_replace_each_other(ed):
    assert any(a == "lights" for _r, _l, a in ed.layout())
    key(ed, pygame.K_l)
    assert ed.lights_mode and ed.section_open()
    key(ed, pygame.K_l)
    assert not ed.lights_mode
    ed.do("lights")
    ed.do("effects")
    assert ed.effects_mode and not ed.lights_mode
    ed.do("lights")
    assert ed.lights_mode and not ed.effects_mode
    ed.do("guns")
    assert ed.guns_mode and not ed.lights_mode
    ed.do("lights")
    ed.do("tool:paint")
    assert not ed.lights_mode
    ed.do("lights")
    ed.draw(pygame.display.get_surface())                       # draws with no lights yet


def test_clicking_the_map_area_in_the_lights_section_does_not_paint_the_map(ed):
    ed.do("lights")
    before = [row_[:] for row_ in ed.level.walls]
    click(ed, ed.map_area().center)
    assert ed.level.walls == before and ed.details_rect() is None


def test_add_select_and_delete_lights(ed):
    first = add_light(ed)
    assert ed.level.lights == [first] and ed.selected_light() is first and first.name == "Light"
    second = add_light(ed)
    assert second.name == "Light 2" and ed.selected_light() is second
    click(ed, ed.light_rows()[1][0][0].center)
    assert ed.selected_light() is first
    click(ed, details.button_rect(ed.details_rect(), ed.details_rows()).center)       # Delete light
    assert ed.level.lights == [second] and ed.details_rect() is None
    ed.do("undo")
    assert len(ed.level.lights) == 2


def test_the_pane_lists_every_light_setting(ed):
    add_light(ed)
    assert keys(ed) == ["name", "r", "g", "b", "intensity", "radius", "flicker", "flicker_speed", "duration", "wall_tile"]


def test_the_delete_button_stays_inside_the_pane_even_for_the_longest_panes(ed):
    ed.do("effects")
    click(ed, ed.effect_rows()[1].center)
    rect, rows = ed.details_rect(), ed.details_rows()
    assert details.button_rect(rect, rows).bottom <= rect.bottom
    assert all(r.rect.h >= details.MIN_ROW_H for r in rows)


def test_values_step_type_and_undo(ed):
    light = add_light(ed)
    start = light.intensity
    click(ed, row(ed, "intensity").plus.center)
    assert light.intensity == start + 0.25
    click(ed, row(ed, "r").minus.center)
    assert light.r == 240
    ed.do("undo")
    again = ed.level.lights[0]
    assert again.r == 255 and again.intensity == start + 0.25


def test_the_light_names_are_unique_and_renaming_keeps_what_carries_the_light(ed):
    light = add_light(ed)
    ed.level.guns = [Gun("Pistol", flash=light.name)]
    ed.level.ammo_types = [AmmoType("Tracer", light=light.name)]
    ed.level.effects = [Effect("Fire", light=light.name)]
    ed.level.entities = [Entity(2.5, 2.5, light=light.name)]
    ed.level.prefabs = [Entity(0, 0, name="Torch", light=light.name)]
    ed.set_light("name", "Torchlight")
    assert light.name == "Torchlight"
    assert ed.level.guns[0].flash == ed.level.ammo_types[0].light == ed.level.effects[0].light == "Torchlight"
    assert ed.level.entities[0].light == ed.level.prefabs[0].light == "Torchlight"
    other = add_light(ed)
    ed.set_light("name", "Torchlight")
    assert other.name != "Torchlight"
    ed.do("undo")
    ed.do("undo")
    assert ed.level.guns[0].flash == "Light"


def test_deleting_a_light_clears_what_carried_it(ed):
    light = add_light(ed)
    ed.level.guns = [Gun("Pistol", flash=light.name)]
    ed.level.ammo_types = [AmmoType("Tracer", light=light.name)]
    ed.level.effects = [Effect("Fire", light=light.name)]
    ed.level.entities = [Entity(2.5, 2.5, light=light.name)]
    ed.delete_light()
    assert ed.level.lights == []
    assert (ed.level.guns[0].flash, ed.level.ammo_types[0].light, ed.level.effects[0].light,
            ed.level.entities[0].light) == ("", "", "", "")


# ------------------------------------------------------------------ the ambient light and glowing walls

def test_the_ambient_row_opens_a_pane_that_sets_the_maps_ambient_light(ed):
    ed.do("lights")
    ambient = ed.light_rows()[0]
    click(ed, ambient.center)
    assert ed.ambient_chosen() and ed.selected_light() is None and ed.details_rect() is not None
    assert keys(ed) == ["ambient"]
    assert ed.details_delete_label() == ""
    click(ed, row(ed, "ambient").minus.center)
    assert ed.level.ambient == pytest.approx(0.95)
    for _ in range(40):
        click(ed, row(ed, "ambient").minus.center)
    assert ed.level.ambient == pytest.approx(0.02)                   # never fully dark
    ed.do("undo")
    assert ed.level.ambient > 0.02
    ed.draw(pygame.display.get_surface())


def test_an_atlas_click_makes_a_wall_tile_glow_and_it_can_be_turned_off(ed):
    light = add_light(ed)
    assert light.wall_tile == -1 and row(ed, "wall_tile").field.text() == "none"
    click(ed, ed.tile_rect(3).center)
    assert light.wall_tile == 3
    click(ed, row(ed, "wall_tile").plus.center)
    assert light.wall_tile == 4
    for _ in range(5):
        click(ed, row(ed, "wall_tile").minus.center)
    assert light.wall_tile == -1
    ed.draw(pygame.display.get_surface())


def test_a_tile_click_with_no_light_selected_changes_nothing(ed):
    ed.do("lights")
    click(ed, ed.tile_rect(3).center)
    assert ed.level.lights == []


# ------------------------------------------------------------------ handing lights out

def test_guns_ammo_effects_and_items_pick_a_light(ed):
    light = add_light(ed)
    ed.do("guns")
    click(ed, ed.gun_rows()[1].center)
    choose(ed, "flash", light.name)
    assert ed.level.guns[-1].flash == light.name
    click(ed, ed.ammo_rows()[1].center)
    choose(ed, "light", light.name)
    assert ed.level.ammo_types[-1].light == light.name
    ed.do("effects")
    click(ed, ed.effect_rows()[1].center)
    choose(ed, "light", light.name)
    assert ed.level.effects[-1].light == light.name
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    choose(ed, "light", light.name)
    assert ed.level.entities[0].light == light.name
    choose(ed, "light", "")
    assert ed.level.entities[0].light == ""


# ------------------------------------------------------------------ the preview and saving

def test_the_preview_draws_and_flickers(ed):
    light = add_light(ed)
    ed.set_light("flicker", 0.8)
    pictures = []
    for _ in range(6):
        ed.update(0.07, pygame.key.get_pressed())
        ed.draw(pygame.display.get_surface())
        area = ed.map_area()
        pictures.append(pygame.image.tobytes(pygame.display.get_surface().subsurface(
            pygame.Rect(area.right - 300, area.y + 150, 200, 200)), "RGB"))
    assert len(set(pictures)) > 1                                   # it changes from frame to frame
    light.flicker = 0.0


def test_lights_and_ambient_are_saved_with_the_map_and_loaded_again(ed):
    light = add_light(ed)
    ed.set_light("name", "Torch")
    ed.set_light("radius", 7.5)
    ed.set_light("wall_tile", 6)
    ed.set_ambient(0.35)
    ed.level.guns = [Gun("Pistol", flash="Torch")]
    ed.do("save")
    again = load_level(ed.path)
    assert [(item.name, item.radius, item.wall_tile) for item in again.lights] == [("Torch", 7.5, 6)]
    assert again.ambient == pytest.approx(0.35) and again.guns[0].flash == "Torch"
    assert light.name == "Torch"


def test_the_3d_view_in_the_editor_is_lit_by_the_maps_lights(ed):
    from atlas import atlas_array, unpack_atlas
    textures = atlas_array(unpack_atlas())
    level = Level.blank(12, 12)
    level.lights = [Light("Lamp", intensity=3.0, radius=6.0)]
    level.entities = [Entity(6.5, 6.5, mode="scenery", light="Lamp", shown=False)]

    def middle(preview):
        preview.sync(level, 1, now=1e9, force=True)
        preview.player.x, preview.player.y, preview.player.angle = 3.5, 6.5, 0.0
        for _ in range(3):
            preview.update(1 / 60)
        picture = preview.render()
        w, h = picture.get_size()
        return np.array(pygame.image.tobytes(picture, "RGB"), np.uint8).reshape(h, w, 3)

    lit = middle(Preview(textures))
    level.ambient = 0.2
    dim = middle(Preview(textures))
    level.lights = []
    dark = middle(Preview(textures))
    assert dim.mean() < lit.mean()                                  # the dark map is darker overall...
    assert dim.max() > dark.max()                                   # ...but the lamp still lights its surroundings
