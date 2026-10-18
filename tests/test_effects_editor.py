"""The editor's Effects section, and the pickers that hand an effect to a gun, an ammo type or an item."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import details
import map_editor
from mapfile import AmmoType, Effect, Entity, Gun, Level, load_level


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


def add_effect(ed):
    if not ed.effects_mode:
        ed.do("effects")
    click(ed, ed.effect_rows()[1].center)
    return ed.level.effects[-1]


# ------------------------------------------------------------------ the section

def test_the_effects_button_and_x_key_open_and_close_the_section_and_a_map_tool_leaves_it(ed):
    assert any(a == "effects" for _r, _l, a in ed.layout())
    key(ed, pygame.K_x)
    assert ed.effects_mode and ed.section_open()
    key(ed, pygame.K_x)
    assert not ed.effects_mode
    ed.do("effects")
    ed.do("guns")                                               # sections replace each other
    assert ed.guns_mode and not ed.effects_mode
    ed.do("effects")
    ed.do("tool:paint")
    assert not ed.effects_mode
    ed.do("effects")
    ed.draw(pygame.display.get_surface())                       # draws with no effects yet


def test_clicking_the_map_area_in_the_effects_section_does_not_paint_the_map(ed):
    ed.do("effects")
    before = [row_[:] for row_ in ed.level.walls]
    click(ed, ed.map_area().center)
    assert ed.level.walls == before


def test_add_select_and_delete_effects(ed):
    first = add_effect(ed)
    assert ed.level.effects == [first] and ed.selected_effect() is first and first.name == "Effect"
    second = add_effect(ed)
    assert second.name == "Effect 2" and ed.selected_effect() is second
    click(ed, ed.effect_rows()[0][0][0].center)
    assert ed.selected_effect() is first
    click(ed, details.button_rect(ed.details_rect(), ed.details_rows()).center)       # Delete effect
    assert ed.level.effects == [second] and ed.details_rect() is None
    ed.do("undo")
    assert len(ed.level.effects) == 2


def test_the_pane_shows_the_settings_that_fit_the_kind(ed):
    effect = add_effect(ed)
    burst = keys(ed)
    assert burst[:3] == ["name", "tile", "kind"] and "count" in burst and "interval" in burst
    assert "rate" not in burst and "duration" not in burst
    choose(ed, "kind", "stream")
    assert effect.kind == "stream"
    stream = keys(ed)
    assert "rate" in stream and "duration" in stream and "count" not in stream and "interval" not in stream
    for common in ("life", "speed", "spread", "gravity", "drag", "size_start", "size_end", "alpha_start",
                   "alpha_end", "collide"):
        assert common in stream and common in burst


def test_values_step_type_and_undo(ed):
    effect = add_effect(ed)
    start = effect.count
    click(ed, row(ed, "count").plus.center)
    assert effect.count == start + 1
    click(ed, row(ed, "gravity").minus.center)
    assert effect.gravity == -0.5
    ed.do("undo")                                               # (undo brings back a copy of the map's effects)
    again = ed.level.effects[0]
    assert again.gravity == 0.0 and again.count == start + 1
    choose(ed, "collide", False)
    assert ed.level.effects[0].collide is False


def test_an_atlas_click_sets_the_particle_picture(ed):
    effect = add_effect(ed)
    index = 3
    click(ed, ed.tile_rect(index).center)
    assert effect.tile == index


def test_renaming_an_effect_keeps_what_uses_it_pointing_at_it(ed):
    effect = add_effect(ed)
    ed.level.guns = [Gun("Pistol", muzzle=effect.name)]
    ed.level.ammo_types = [AmmoType("Tracer", trail=effect.name)]
    ed.level.entities = [Entity(2.5, 2.5, emits=effect.name)]
    ed.level.prefabs = [Entity(0, 0, name="Torch", emits=effect.name)]
    ed.set_effect("name", "Sparks")
    assert effect.name == "Sparks"
    assert ed.level.guns[0].muzzle == ed.level.ammo_types[0].trail == ed.level.entities[0].emits == "Sparks"
    assert ed.level.prefabs[0].emits == "Sparks"
    ed.do("undo")
    assert ed.level.effects[0].name == "Effect" and ed.level.guns[0].muzzle == "Effect"


def test_deleting_an_effect_clears_what_used_it(ed):
    effect = add_effect(ed)
    ed.level.guns = [Gun("Pistol", muzzle=effect.name)]
    ed.level.ammo_types = [AmmoType("Tracer", trail=effect.name)]
    ed.level.entities = [Entity(2.5, 2.5, emits=effect.name)]
    ed.delete_effect()
    assert ed.level.effects == []
    assert ed.level.guns[0].muzzle == "" and ed.level.ammo_types[0].trail == "" and ed.level.entities[0].emits == ""


def test_the_effect_names_must_be_unique(ed):
    first = add_effect(ed)
    second = add_effect(ed)
    ed.set_effect("name", first.name)
    assert second.name != first.name


# ------------------------------------------------------------------ handing effects out

def test_a_gun_picks_its_muzzle_effect_and_an_ammo_type_its_trail(ed):
    effect = add_effect(ed)
    ed.do("guns")
    click(ed, ed.gun_rows()[1].center)                           # + Add gun
    choose(ed, "muzzle", effect.name)
    assert ed.level.guns[-1].muzzle == effect.name
    choose(ed, "muzzle", "")
    assert ed.level.guns[-1].muzzle == ""
    click(ed, ed.ammo_rows()[1].center)                          # + Add ammo type
    choose(ed, "trail", effect.name)
    assert ed.level.ammo_types[-1].trail == effect.name


def test_an_item_can_emit_an_effect_be_scenery_and_hide_its_sprite(ed):
    effect = add_effect(ed)
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    item = ed.level.entities[0]
    choose(ed, "emits", effect.name)
    choose(ed, "mode", "scenery")
    choose(ed, "shown", False)
    assert (item.emits, item.mode, item.shown) == (effect.name, "scenery", False)
    ed.draw(pygame.display.get_surface())                        # a scenery item is drawn on the map


def test_a_prefab_can_carry_an_effect_to_its_copies(ed):
    effect = add_effect(ed)
    ed.level.prefabs = [Entity(0, 0, name="Torch")]
    ed.level.entities = [Entity(3.5, 3.5, prefab="Torch")]
    ed.do("prefabs")
    ed.prefab_selected = 0
    choose(ed, "emits", effect.name)
    assert ed.level.entities[0].emits == effect.name


# ------------------------------------------------------------------ the preview and saving

def test_the_preview_plays_the_selected_effect_and_restarts_when_it_changes(ed):
    effect = add_effect(ed)
    effect.count = 10
    for _ in range(3):
        ed.update(1 / 60, pygame.key.get_pressed())
    sim = ed.fx_sim[0]
    assert sim.count() == 10
    first = sim
    ed.set_effect("count", 20)
    ed.update(1 / 60, pygame.key.get_pressed())
    assert ed.fx_sim[0] is not first and ed.fx_sim[0].count() == 20       # a new run with the new settings
    ed.draw(pygame.display.get_surface())


def test_a_stream_preview_keeps_going_and_a_burst_repeats(ed):
    effect = add_effect(ed)
    ed.set_effect("kind", "stream")
    for _ in range(90):
        ed.update(1 / 60, pygame.key.get_pressed())
    assert ed.fx_sim[0].count() > 10
    ed.set_effect("kind", "burst")
    ed.set_effect("life", 0.1)
    ed.set_effect("life_var", 0.0)
    seen = []
    for _ in range(120):
        ed.update(1 / 60, pygame.key.get_pressed())
        seen.append(ed.fx_sim[0].count())
    assert 0 in seen and max(seen) == effect.count
    assert sum(1 for a, b in zip(seen, seen[1:]) if b > a) >= 2                # it went off more than once


def test_leaving_the_section_stops_the_preview(ed):
    add_effect(ed)
    ed.update(1 / 60, pygame.key.get_pressed())
    assert ed.fx_sim is not None
    ed.do("effects")
    ed.update(1 / 60, pygame.key.get_pressed())
    assert ed.fx_sim is None


def test_effects_are_saved_with_the_map_and_loaded_again(ed, tmp_path):
    effect = add_effect(ed)
    ed.set_effect("name", "Sparks")
    ed.set_effect("gravity", 4.5)
    ed.level.guns = [Gun("Pistol", muzzle="Sparks")]
    ed.do("save")
    again = load_level(ed.path)
    assert [(f.name, f.gravity) for f in again.effects] == [("Sparks", 4.5)]
    assert again.guns[0].muzzle == "Sparks"
    assert effect.name == "Sparks"


# ------------------------------------------------------------------ the start offset and the direction

def test_the_pane_has_the_offset_rows_and_the_direction_rows_only_for_a_custom_direction(ed):
    effect = add_effect(ed)
    plain = keys(ed)
    for name in ("offset_x", "offset_y", "offset_z", "aim", "relative"):
        assert name in plain
    assert not any(name in plain for name in ("dir_x", "dir_y", "dir_z"))
    assert plain.index("aim") < plain.index("relative")
    choose(ed, "aim", "custom")
    custom = keys(ed)
    assert effect.aim == "custom"
    assert custom[custom.index("aim") + 1:custom.index("aim") + 4] == ["dir_x", "dir_y", "dir_z"]
    choose(ed, "aim", "auto")
    assert "dir_x" not in keys(ed)


def test_offsets_and_a_custom_direction_can_be_set_and_undone(ed):
    effect = add_effect(ed)
    click(ed, row(ed, "offset_x").plus.center)
    click(ed, row(ed, "offset_z").plus.center)
    assert (effect.offset_x, effect.offset_z) == (0.05, 0.05)
    choose(ed, "aim", "custom")
    click(ed, row(ed, "dir_x").plus.center)
    assert ed.level.effects[0].dir_x == 0.25
    choose(ed, "relative", True)
    assert ed.level.effects[0].relative is True
    ed.do("undo")
    ed.do("undo")
    ed.do("undo")
    assert ed.level.effects[0].aim == "auto" and ed.level.effects[0].dir_x == 0.0


def test_the_preview_starts_particles_at_the_offset_and_draws_without_trouble(ed):
    effect = add_effect(ed)
    effect.count, effect.spread, effect.speed, effect.life = 5, 0.0, 0.0, 5.0
    ed.set_effect("offset_x", 1.5)
    ed.set_effect("aim", "custom")
    for _ in range(3):
        ed.update(1 / 60, pygame.key.get_pressed())
    sim = ed.fx_sim[0]
    assert sim.count() == 5 and all(abs(p.x - 1.5) < 1e-6 for p in sim.particles)
    ed.draw(pygame.display.get_surface())


def test_the_colour_choice_shows_only_the_rows_it_needs_and_they_all_fit_the_pane(ed):
    effect = add_effect(ed)
    assert "hue" not in keys(ed) and "tint_r" not in keys(ed)
    choose(ed, "colour", "hue")
    assert effect.colour == "hue" and "hue" in keys(ed) and "tint_r" not in keys(ed)
    click(ed, row(ed, "hue").plus.center)
    assert effect.hue == 15.0
    choose(ed, "colour", "rgb")
    assert [k for k in keys(ed) if k.startswith("tint")] == ["tint_r", "tint_g", "tint_b"] and "hue" not in keys(ed)
    click(ed, row(ed, "tint_g").minus.center)
    assert effect.tint_g == 240
    ed.draw(pygame.display.get_surface())
    assert details.button_rect(ed.details_rect(), ed.details_rows()).bottom <= ed.details_rect().bottom


def test_the_preview_draws_a_tinted_effect_in_its_tint(ed):
    effect = add_effect(ed)
    effect.count = 10
    ed.set_effect("colour", "rgb")
    ed.set_effect("tint_r", 0)
    for _ in range(3):
        ed.update(1 / 60, pygame.key.get_pressed())
    ed.draw(pygame.display.get_surface())                                   # a tinted sprite is longer than 8 numbers
    from particles import colour_matrix
    white = pygame.Surface((4, 4))
    white.fill((200, 200, 200))
    assert map_editor.recoloured(white, colour_matrix(0.0, 0, 255, 255)).get_at((0, 0))[:3] == (0, 200, 200)
    assert white.get_at((0, 0))[:3] == (200, 200, 200)                      # the original is left alone
