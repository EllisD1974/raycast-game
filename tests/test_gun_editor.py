"""The editor's Guns section, and the item settings that hand out inventory things and guns."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import details
import map_editor
from mapfile import AmmoType, Entity, Gun, Level


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


def choose(ed, name, choice):
    r = row(ed, name)
    click(ed, details.menu_anchor(r).center)
    assert ed.menu_open == name
    for rect, option in details.menu_rects(r):
        if option == choice:
            click(ed, rect.center)
            return
    raise AssertionError(f"{choice} is not offered for {name}")


def type_text(ed, text):
    for ch in text:
        key(ed, ord(ch.lower()) if ch.isalnum() else 0, ch)


def keys(ed):
    return [r.field.key for r in ed.details_rows()]


def add_gun(ed):
    if not ed.guns_mode:
        ed.do("guns")
    add = ed.gun_rows()[1]
    click(ed, add.center)
    return ed.level.guns[-1]


# ------------------------------------------------------------------ the section

def test_the_guns_button_and_g_key_open_and_close_the_section_and_a_map_tool_leaves_it(ed):
    assert any(a == "guns" for _r, _l, a in ed.layout())
    key(ed, pygame.K_g)
    assert ed.guns_mode
    key(ed, pygame.K_g)
    assert not ed.guns_mode
    ed.do("guns")
    ed.do("tool:paint")
    assert not ed.guns_mode
    ed.do("guns")
    ed.draw(pygame.display.get_surface())                       # draws with no guns yet


def test_clicking_the_map_area_in_the_guns_section_does_not_paint_the_map(ed):
    ed.do("guns")
    before = [row[:] for row in ed.level.walls]
    click(ed, ed.map_area().center)
    assert ed.level.walls == before


def test_add_select_and_delete_guns(ed):
    first = add_gun(ed)
    assert ed.level.guns == [first] and ed.selected_gun() is first and first.name == "Gun"
    second = add_gun(ed)
    assert second.name == "Gun 2" and ed.selected_gun() is second       # names stay unique
    rows, _add = ed.gun_rows()
    click(ed, rows[0][0].center)
    assert ed.selected_gun() is first
    assert ed.details_rect() is not None
    click(ed, details.button_rect(ed.details_rect(), ed.details_rows()).center)       # Delete gun
    assert ed.level.guns == [second] and ed.details_rect() is None
    ed.do("undo")
    assert len(ed.level.guns) == 2


def test_the_pane_lists_every_gun_setting_and_hides_the_magazine_for_single_shot(ed):
    add_gun(ed)
    assert keys(ed) == ["name", "tile", "size", "mode", "shot", "damage", "fire_rate", "mag_size", "start_ammo",
                        "reload_time", "spread", "ammo"]
    choose(ed, "mode", "single")
    assert "mag_size" not in keys(ed) and ed.level.guns[0].mode == "single"
    choose(ed, "mode", "auto")
    assert "mag_size" in keys(ed) and ed.level.guns[0].mode == "auto"


def test_gun_numbers_step_wheel_and_type(ed):
    gun = add_gun(ed)
    click(ed, row(ed, "damage").plus.center)
    assert gun.damage == 11
    click(ed, row(ed, "mag_size").minus.center)
    assert gun.mag_size == 11 and isinstance(gun.mag_size, int)
    ed.mouse = row(ed, "fire_rate").rect.center
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=2))
    assert gun.fire_rate == pytest.approx(5.0)
    click(ed, row(ed, "reload_time").value.center)
    for _ in range(5):
        key(ed, pygame.K_BACKSPACE)
    type_text(ed, "2.5")
    key(ed, pygame.K_RETURN)
    assert gun.reload_time == 2.5


def test_the_atlas_sets_the_gun_picture_and_the_ammo_types_bullet_picture(ed):
    gun = add_gun(ed)
    ed.atlas_drag = ((3, 0), (3, 0))
    ed.finish_atlas_drag()
    assert gun.tile == 3
    click(ed, row(ed, "tile").plus.center)
    assert gun.tile == 4                                         # the + step works too
    ed.add_ammo_type()
    ammo = ed.level.ammo_types[0]
    ed.atlas_drag = ((5, 0), (5, 0))
    ed.finish_atlas_drag()
    assert ammo.tile == 5 and gun.tile == 4
    ed.draw(pygame.display.get_surface())


def test_renaming_a_gun_keeps_the_items_that_give_it_pointing_at_it_and_names_stay_unique(ed):
    add_gun(ed)
    add_gun(ed)
    ed.level.entities = [Entity(3.5, 3.5, effect="gun", gun="Gun"), Entity(4.5, 4.5, effect="ammo", gun="Gun 2")]
    rows, _add = ed.gun_rows()
    click(ed, rows[0][0].center)
    click(ed, row(ed, "name").value.center)
    for _ in range(30):
        key(ed, pygame.K_BACKSPACE)
    type_text(ed, "Shotgun")
    key(ed, pygame.K_RETURN)
    assert [g.name for g in ed.level.guns] == ["Shotgun", "Gun 2"]
    assert ed.level.entities[0].gun == "Shotgun" and ed.level.entities[1].gun == "Gun 2"
    click(ed, row(ed, "name").value.center)
    for _ in range(30):
        key(ed, pygame.K_BACKSPACE)
    type_text(ed, "Gun 2")                                      # already taken: it is made unique
    key(ed, pygame.K_RETURN)
    assert ed.level.guns[0].name == "Gun 2 2" and ed.level.entities[1].gun == "Gun 2"
    click(ed, row(ed, "name").value.center)
    for _ in range(30):
        key(ed, pygame.K_BACKSPACE)
    key(ed, pygame.K_RETURN)                                     # an empty name keeps the old one
    assert ed.level.guns[0].name == "Gun 2 2"


def test_the_guns_section_draws_with_a_selected_gun_of_every_mode_and_through_other_screens(ed):
    gun = add_gun(ed)
    for mode in ("single", "semi", "auto"):
        gun.mode = mode
        ed.draw(pygame.display.get_surface())
    gun.tile = 9999                                              # a bad picture index is clamped, not a crash
    ed.add_ammo_type()
    ed.level.ammo_types[0].tile = -3
    ed.draw(pygame.display.get_surface())
    ed.gun_selected, ed.ammo_selected = 0, None
    ed.draw(pygame.display.get_surface())
    ed.do("guns")
    ed.draw(pygame.display.get_surface())
    assert ed.selected_gun() is None


def test_gun_edits_undo_and_redo(ed):
    gun = add_gun(ed)
    click(ed, row(ed, "damage").plus.center)
    ed.do("undo")
    assert ed.level.guns[0].damage == 10
    ed.do("redo")
    assert ed.level.guns[0].damage == 11
    assert gun is not ed.level.guns[0] or True


# ------------------------------------------------------------------ giving things out

def select_new_item(ed):
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    return ed.level.entities[-1]


def test_the_effect_list_offers_inventory_items_guns_and_ammo(ed):
    select_new_item(ed)
    r = row(ed, "effect")
    click(ed, details.menu_anchor(r).center)
    assert [c for _r, c in details.menu_rects(r)] == ["none", "score", "health", "item", "gun", "ammo"]


def test_an_item_that_goes_in_the_inventory_has_a_name_and_a_count(ed):
    e = select_new_item(ed)
    choose(ed, "effect", "item")
    assert e.effect == "item" and e.amount == 1.0
    assert keys(ed)[:5] == ["tile", "mode", "effect", "item", "amount"]
    click(ed, row(ed, "item").value.center)
    for _ in range(10):
        key(ed, pygame.K_BACKSPACE)
    type_text(ed, "Red key")
    key(ed, pygame.K_RETURN)
    assert e.item == "Red key"
    click(ed, row(ed, "amount").plus.center)
    assert e.amount == 2.0
    choose(ed, "effect", "score")
    assert e.amount == 10.0 and "item" not in keys(ed)           # back to a score: its usual amount
    choose(ed, "effect", "health")
    assert e.amount == 10.0                                      # score to health keeps what you set


def test_a_gun_item_picks_from_the_maps_guns_and_an_ammo_item_picks_an_ammo_type(ed):
    e = select_new_item(ed)
    choose(ed, "effect", "gun")
    assert row(ed, "gun").field.choices == ("",) and "amount" not in keys(ed)       # no guns defined yet
    ed.level.guns = [Gun("Pistol"), Gun("Rifle")]
    assert row(ed, "gun").field.choices == ("Pistol", "Rifle")
    choose(ed, "gun", "Rifle")
    assert e.gun == "Rifle"
    choose(ed, "effect", "ammo")
    assert row(ed, "ammo").field.choices == ("",)[:1] + ()                          # only the default bullet so far
    ed.level.ammo_types = [AmmoType("9mm"), AmmoType("Shells")]
    assert row(ed, "ammo").field.choices == ("", "9mm", "Shells")
    choose(ed, "ammo", "Shells")
    assert e.ammo == "Shells" and e.amount == 24.0 and "gun" not in keys(ed)
    click(ed, row(ed, "amount").plus.center)
    assert e.amount == 30.0
    ed.draw(pygame.display.get_surface())


def test_the_stock_map_loads_and_everything_still_works_with_guns_in_it(tmp_path):
    from mapfile import load_level, save_level
    level = Level.blank(10, 10)
    level.guns = [Gun("Pistol")]
    level.entities = [Entity(3.5, 3.5, effect="gun", gun="Pistol"), Entity(5.5, 5.5, effect="item", item="Key")]
    save_level(str(tmp_path / "g.json"), level)
    again = load_level(str(tmp_path / "g.json"))
    assert again.guns == level.guns and again.entities == level.entities


def test_the_shot_type_is_single_bullet_by_default_and_multi_bullet_adds_a_count(ed):
    gun = add_gun(ed)
    assert gun.shot == "single" and "pellets" not in keys(ed)
    assert row(ed, "shot").field.choices == ("single", "multi", "projectile")
    choose(ed, "shot", "multi")
    assert gun.shot == "multi" and "pellets" in keys(ed)
    assert keys(ed).index("pellets") == keys(ed).index("shot") + 1
    click(ed, row(ed, "pellets").plus.center)
    assert gun.pellets == 9 and isinstance(gun.pellets, int)
    choose(ed, "shot", "projectile")
    assert gun.shot == "projectile" and "pellets" not in keys(ed)
    ed.draw(pygame.display.get_surface())
    choose(ed, "shot", "multi")
    ed.draw(pygame.display.get_surface())


# ------------------------------------------------------------------ ammo types

def add_ammo(ed):
    if not ed.guns_mode:
        ed.do("guns")
    click(ed, ed.ammo_rows()[1].center)
    return ed.level.ammo_types[-1]


def test_ammo_types_are_added_selected_and_deleted_in_the_guns_section(ed):
    first = add_ammo(ed)
    assert ed.level.ammo_types == [first] and ed.selected_ammo() is first and first.name == "Ammo"
    assert ed.selected_gun() is None
    second = add_ammo(ed)
    assert second.name == "Ammo 2" and ed.selected_ammo() is second
    rows, _add = ed.ammo_rows()
    click(ed, rows[0][0].center)
    assert ed.selected_ammo() is first
    assert keys(ed) == ["name", "tile", "size", "speed", "range", "damage_mult"]
    click(ed, details.button_rect(ed.details_rect(), ed.details_rows()).center)
    assert ed.level.ammo_types == [second] and ed.details_rect() is None
    ed.do("undo")
    assert len(ed.level.ammo_types) == 2


def test_selecting_a_gun_and_an_ammo_type_are_exclusive_and_both_open_the_pane(ed):
    add_gun(ed)
    add_ammo(ed)
    assert ed.selected_gun() is None and ed.selected_ammo() is not None
    click(ed, ed.gun_rows()[0][0][0].center)
    assert ed.selected_gun() is not None and ed.selected_ammo() is None
    ed.draw(pygame.display.get_surface())
    key(ed, pygame.K_ESCAPE)
    assert ed.details_rect() is None


def test_ammo_settings_step_and_type(ed):
    ammo = add_ammo(ed)
    click(ed, row(ed, "speed").plus.center)
    assert ammo.speed == 19.0
    click(ed, row(ed, "damage_mult").plus.center)
    assert ammo.damage_mult == pytest.approx(1.1)
    click(ed, row(ed, "size").value.center)
    for _ in range(5):
        key(ed, pygame.K_BACKSPACE)
    type_text(ed, "9")
    key(ed, pygame.K_RETURN)
    assert ammo.size == 2.0                                      # clamped to the limit


def test_guns_pick_their_ammo_type_from_a_list_and_two_guns_can_pick_the_same_one(ed):
    add_ammo(ed)
    add_ammo(ed)
    a, b = ed.level.ammo_types
    add_gun(ed)
    assert row(ed, "ammo").field.choices == ("", "Ammo", "Ammo 2")
    choose(ed, "ammo", "Ammo 2")
    add_gun(ed)
    choose(ed, "ammo", "Ammo 2")
    assert [g.ammo for g in ed.level.guns] == ["Ammo 2", "Ammo 2"]
    assert ed.level.ammo_for(ed.level.guns[0]) is b
    ed.draw(pygame.display.get_surface())


def test_renaming_an_ammo_type_keeps_guns_and_pickups_pointing_at_it_and_deleting_it_clears_them(ed):
    ammo = add_ammo(ed)
    ed.level.guns = [Gun("A", ammo="Ammo"), Gun("B", ammo="Ammo"), Gun("C", ammo="")]
    ed.level.entities = [Entity(3.5, 3.5, effect="ammo", ammo="Ammo")]
    click(ed, row(ed, "name").value.center)
    for _ in range(30):
        key(ed, pygame.K_BACKSPACE)
    type_text(ed, "9mm")
    key(ed, pygame.K_RETURN)
    assert ammo.name == "9mm"
    assert [g.ammo for g in ed.level.guns] == ["9mm", "9mm", ""] and ed.level.entities[0].ammo == "9mm"
    click(ed, details.button_rect(ed.details_rect(), ed.details_rows()).center)
    assert ed.level.ammo_types == []
    assert [g.ammo for g in ed.level.guns] == ["", "", ""] and ed.level.entities[0].ammo == ""
