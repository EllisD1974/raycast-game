"""Prefabs: reusable items made in the editor's Prefabs section, placed with the Entity tool."""
import json
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import details
import map_editor
import physics
from entities import Entities, PlayerStats
from inventory import Inventory
from mapfile import Animation, AmmoType, Entity, Gun, Level, load_level, save_level
from world import World


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1500, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(12, 12)
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


def type_text(ed, text):
    for ch in text:
        key(ed, ord(ch.lower()) if ch.isalnum() else 0, ch)


def rename_selected(ed, text):
    click(ed, row(ed, "name").value.center)
    for _ in range(30):
        key(ed, pygame.K_BACKSPACE)
    type_text(ed, text)
    key(ed, pygame.K_RETURN)


def add_prefab(ed):
    if not ed.prefabs_mode:
        ed.do("prefabs")
    click(ed, ed.prefab_rows()[1].center)
    return ed.level.prefabs[-1]


def place(ed, cell):
    ed.do("tool:entity")
    ed.map_click(cell, 1)
    return ed.level.entities[-1]


# ------------------------------------------------------------------ the map file

def test_prefabs_and_their_instances_survive_save_and_load(tmp_path):
    level = Level.blank(10, 10)
    level.prefabs = [Entity(0.0, 0.0, name="9mm box", tile=21, effect="ammo", ammo="9mm", amount=24,
                            animations=[Animation("rotate", 0.3)])]
    level.entities = [Entity(3.5, 3.5, prefab="9mm box"), Entity(5.5, 5.5)]
    level.apply_prefabs()
    save_level(str(tmp_path / "m.json"), level)
    again = load_level(str(tmp_path / "m.json"))
    assert again.prefabs == level.prefabs and again.entities == level.entities
    assert again.entities[0].effect == "ammo" and again.entities[0].amount == 24 and again.entities[0].tile == 21
    assert again.entities[0].animations == [Animation("rotate", 0.3)]
    assert again.entities[1].prefab == "" and again.entities[1].effect == "score"       # the plain item is untouched


def test_instances_take_their_settings_from_the_prefab_when_a_map_loads(tmp_path):
    level = Level.blank(10, 10)
    level.prefabs = [Entity(0.0, 0.0, name="Heart", effect="health", amount=25, tile=11)]
    level.entities = [Entity(3.5, 3.5, prefab="Heart")]
    save_level(str(tmp_path / "m.json"), level)
    data = json.loads((tmp_path / "m.json").read_text())
    data["prefabs"][0]["amount"] = 50                                     # the prefab is edited in the file
    (tmp_path / "m.json").write_text(json.dumps(data))
    assert load_level(str(tmp_path / "m.json")).entities[0].amount == 50


def test_an_item_whose_prefab_is_gone_is_detached_and_keeps_its_settings():
    level = Level.blank(10, 10)
    level.entities = [Entity(3.5, 3.5, prefab="Missing", effect="health", amount=7)]
    level.apply_prefabs()
    assert level.entities[0].prefab == "" and level.entities[0].amount == 7


def test_apply_prefabs_keeps_the_place_and_copies_animations_not_shares_them():
    level = Level.blank(10, 10)
    level.prefabs = [Entity(0.0, 0.0, name="P", animations=[Animation("float", 1.0, 0.2)])]
    level.entities = [Entity(3.5, 4.5, span=0, prefab="P")]
    level.apply_prefabs()
    e = level.entities[0]
    assert (e.x, e.y) == (3.5, 4.5) and e.animations == level.prefabs[0].animations
    e.animations[0].speed = 9
    assert level.prefabs[0].animations[0].speed == 1.0
    copy = level.copy()
    copy.prefabs[0].name = "Changed"
    assert level.prefabs[0].name == "P"


def test_a_prefab_item_is_picked_up_like_any_other():
    level = Level.blank(12, 12)
    level.guns = [Gun("Pistol", ammo="9mm", start_ammo=0)]
    level.prefabs = [Entity(0.0, 0.0, name="9mm box", effect="ammo", ammo="9mm", amount=24)]
    level.entities = [Entity(5.5, 5.5, prefab="9mm box")]
    level.apply_prefabs()
    inv = Inventory()
    messages = Entities(level, World(level, 16)).update(physics.Player(5.5, 5.5, 0.0), PlayerStats(), 0.1, inv)
    assert messages == ["+24 9mm ammo"] and inv.ammo["9mm"] == 24


# ------------------------------------------------------------------ the Prefabs section

def test_the_prefabs_button_and_p_key_open_the_section_and_it_excludes_the_guns_section(ed):
    assert any(a == "prefabs" for _r, _l, a in ed.layout())
    key(ed, pygame.K_p)
    assert ed.prefabs_mode
    ed.do("guns")
    assert ed.guns_mode and not ed.prefabs_mode
    ed.do("prefabs")
    assert ed.prefabs_mode and not ed.guns_mode
    ed.do("tool:paint")
    assert not ed.prefabs_mode
    ed.do("prefabs")
    ed.draw(pygame.display.get_surface())                       # draws with none yet


def test_add_select_and_delete_prefabs_with_unique_names(ed):
    first = add_prefab(ed)
    assert ed.level.prefabs == [first] and ed.selected_prefab() is first and first.name == "Prefab"
    second = add_prefab(ed)
    assert second.name == "Prefab 2" and ed.selected_prefab() is second
    click(ed, ed.prefab_rows()[0][0][0].center)
    assert ed.selected_prefab() is first
    assert keys(ed)[:5] == ["name", "tile", "mode", "effect", "amount"]
    assert row(ed, "tile").field.label == "Icon"
    click(ed, details.button_rect(ed.details_rect(), ed.details_rows()).center)       # Delete prefab
    assert ed.level.prefabs == [second] and ed.details_rect() is None
    ed.do("undo")
    assert len(ed.level.prefabs) == 2
    ed.draw(pygame.display.get_surface())


def test_a_prefab_is_edited_like_an_item_icon_effect_amount_animation(ed):
    p = add_prefab(ed)
    ed.atlas_drag = ((7, 0), (7, 0))
    ed.finish_atlas_drag()
    assert p.tile == 7                                           # the atlas sets the icon
    choose(ed, "effect", "ammo")
    ed.level.ammo_types = [AmmoType("9mm")]
    choose(ed, "ammo", "9mm")
    click(ed, row(ed, "amount").plus.center)
    assert (p.effect, p.ammo, p.amount) == ("ammo", "9mm", 30.0)
    choose(ed, "add_animation", "rotate")
    click(ed, row(ed, "a0_speed").plus.center)
    assert [(a.kind, round(a.speed, 2)) for a in p.animations] == [("rotate", 0.6)]
    assert "make_prefab" not in keys(ed)                         # a prefab cannot be saved as a prefab
    ed.draw(pygame.display.get_surface())
    ed.do("undo")
    assert ed.level.prefabs[0].animations[0].speed == pytest.approx(0.5)


def test_renaming_a_prefab_keeps_its_items_linked_and_names_stay_unique(ed):
    a, b = add_prefab(ed), add_prefab(ed)
    ed.level.entities = [Entity(3.5, 3.5, prefab="Prefab 2"), Entity(4.5, 4.5, prefab="Prefab")]
    rename_selected(ed, "Heart")
    assert b.name == "Heart" and ed.level.entities[0].prefab == "Heart" and ed.level.entities[1].prefab == "Prefab"
    rename_selected(ed, "Prefab")                                # taken by the other one: made unique
    assert b.name == "Prefab 2"
    rename_selected(ed, "")                                      # empty: keeps the name
    assert b.name == "Prefab 2"


def test_deleting_a_prefab_detaches_its_items_without_changing_them(ed):
    p = add_prefab(ed)
    ed.level.entities = [Entity(3.5, 3.5, prefab=p.name)]
    p.effect, p.amount = "health", 33.0
    ed.level.apply_prefabs()
    ed.delete_prefab()
    assert ed.level.prefabs == []
    e = ed.level.entities[0]
    assert e.prefab == "" and e.effect == "health" and e.amount == 33.0


def test_renaming_guns_and_ammo_reaches_the_prefabs_that_use_them(ed):
    ed.do("guns")
    ed.add_gun()
    ed.add_ammo_type()
    ed.level.prefabs = [Entity(0.0, 0.0, name="G", effect="gun", gun="Gun"),
                        Entity(0.0, 0.0, name="A", effect="ammo", ammo="Ammo")]
    ed.level.entities = [Entity(3.5, 3.5, prefab="G"), Entity(4.5, 4.5, prefab="A")]
    ed.level.apply_prefabs()
    ed.ammo_selected, ed.gun_selected = 0, None
    rename_selected(ed, "9mm")
    assert ed.level.prefabs[1].ammo == "9mm" and ed.level.entities[1].ammo == "9mm"
    ed.gun_selected, ed.ammo_selected = 0, None
    rename_selected(ed, "Pistol")
    assert ed.level.prefabs[0].gun == "Pistol" and ed.level.entities[0].gun == "Pistol"
    ed.ammo_selected, ed.gun_selected = 0, None
    ed.delete_ammo_type()
    assert ed.level.prefabs[1].ammo == "" and ed.level.entities[1].ammo == ""


# ------------------------------------------------------------------ placing prefabs

def test_the_entity_tool_shows_the_prefabs_to_place_and_placing_makes_a_linked_item(ed):
    heart = add_prefab(ed)
    heart.name, heart.effect, heart.amount, heart.tile = "Heart", "health", 40.0, 11
    ed.level.prefabs.append(Entity(0.0, 0.0, name="Coin", effect="score", amount=5, tile=12))
    ed.do("tool:entity")
    assert ed.palette_active() and ed.details_rect() is not None
    assert [r.field.label for r in ed.details_rows()] == ["Place", "Plain item", "Heart", "Coin"]
    ed.draw(pygame.display.get_surface())
    click(ed, details.button_box(row(ed, "pick_0")).center)
    assert ed.place_prefab == "Heart"
    e = place(ed, (4, 4))
    assert (e.prefab, e.effect, e.amount, e.tile) == ("Heart", "health", 40.0, 11)
    assert (e.x, e.y) == (4.5, 4.5)
    assert keys(ed)[:4] == ["prefab", "edit_prefab", "detach", "from_prefab"]    # a linked item shows which prefab it is, then its details
    ed.draw(pygame.display.get_surface())
    ed.deselect()
    click(ed, details.button_box(row(ed, "pick_1")).center)
    c = place(ed, (6, 6))
    assert (c.prefab, c.effect) == ("Coin", "score")
    ed.deselect()
    click(ed, details.button_box(row(ed, "pick_plain")).center)
    plain = place(ed, (8, 8))
    assert plain.prefab == "" and "tile" in keys(ed)             # back to a plain, editable item


def test_editing_the_prefab_updates_every_placed_item(ed):
    p = add_prefab(ed)
    p.name = "Gem"
    ed.place_prefab = "Gem"
    a, b = place(ed, (3, 3)), place(ed, (5, 5))
    ed.do("prefabs")
    ed.do("prefabs")
    ed.prefabs_mode, ed.prefab_selected = True, 0
    choose(ed, "effect", "health")
    click(ed, row(ed, "amount").plus.center)
    click(ed, row(ed, "size").plus.center)
    for item in (a, b):
        assert item.effect == "health" and item.amount == 15.0 and item.size == pytest.approx(0.5)
    ed.do("undo")
    assert all(i.size == pytest.approx(0.4) for i in ed.level.entities)


def test_detaching_an_item_keeps_its_settings_and_makes_it_editable(ed):
    p = add_prefab(ed)
    p.name, p.effect, p.amount = "Heart", "health", 40.0
    ed.place_prefab = "Heart"
    e = place(ed, (4, 4))
    choose(ed, "prefab", "")
    assert e.prefab == "" and (e.effect, e.amount) == ("health", 40.0)
    assert "tile" in keys(ed) and "make_prefab" in keys(ed)
    click(ed, row(ed, "amount").plus.center)
    assert e.amount == 45.0 and p.amount == 40.0                 # now independent of the prefab


def test_an_item_can_be_pointed_at_another_prefab(ed):
    ed.level.prefabs = [Entity(0.0, 0.0, name="A", effect="health", amount=1), Entity(0.0, 0.0, name="B", effect="score", amount=2)]
    ed.place_prefab = "A"
    e = place(ed, (4, 4))
    choose(ed, "prefab", "B")
    assert (e.prefab, e.effect, e.amount) == ("B", "score", 2)


def test_save_as_prefab_turns_an_item_into_a_reusable_one(ed):
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    e = ed.level.entities[0]
    choose(ed, "effect", "item")
    click(ed, row(ed, "item").value.center)
    for _ in range(10):
        key(ed, pygame.K_BACKSPACE)
    type_text(ed, "Red key")
    key(ed, pygame.K_RETURN)
    click(ed, details.button_box(row(ed, "make_prefab")).center)
    assert [p.name for p in ed.level.prefabs] == ["Red key pickup"]
    assert e.prefab == "Red key pickup" and ed.level.prefabs[0].item == "Red key"
    assert ed.place_prefab == "Red key pickup" and keys(ed)[0] == "prefab"
    ed.deselect()
    place(ed, (7, 7))
    assert ed.level.entities[1].prefab == "Red key pickup" and ed.level.entities[1].item == "Red key"
    ed.do("undo")                                                # the placed item
    ed.do("undo")                                                # the prefab made from the first one
    assert ed.level.prefabs == [] and ed.level.entities[0].prefab == ""


def test_a_selection_in_the_prefabs_section_does_not_leak_into_the_map(ed):
    add_prefab(ed)
    ed.do("tool:entity")
    assert ed.selected_prefab() is None and not ed.prefabs_mode
    ed.do("prefabs")
    assert ed.selected_entity() is None


# ------------------------------------------------------------------ selecting a placed copy

def placed_copy(ed, **prefab_settings):
    """A prefab with some settings and a copy of it placed at cell (4, 4), selected."""
    ed.level.effects = [] if not prefab_settings.get("emits") else [__import__("mapfile").Effect(prefab_settings["emits"])]
    ed.level.prefabs = [Entity(0.0, 0.0, name="Torch", **prefab_settings)]
    ed.do("tool:entity")
    ed.place_prefab = "Torch"
    ed.map_click((4, 4), 1)
    ed.draw(pygame.display.get_surface())
    return ed.level.entities[-1]


def info(ed):
    return {r.field.key: r.field.text() for r in ed.details_rows() if r.field.kind == "info"}


def test_a_placed_copy_shows_its_own_details_and_not_only_a_list_of_prefabs(ed):
    copy = placed_copy(ed, mode="persistent", effect="health", amount=25.0, size=0.5, lift=0.2, tile=11,
                       animations=[Animation("rotate")], light="Glow", emits="Fire", emits_override=True,
                       emits_offset_x=0.5, shown=False)
    assert ed.selected_entity() is copy
    assert keys(ed)[:4] == ["prefab", "edit_prefab", "detach", "from_prefab"]
    shown = info(ed)
    assert shown["where"] == "cell 4, 4 on Floor 1"
    assert shown["sprite"] == "#12  (hidden)" and shown["mode"] == "Stays" and shown["effect"] == "Health: +25"
    assert shown["size"] == "0.5" and shown["lift"] == "0.2" and shown["light"] == "Glow"
    assert shown["emits"].startswith("Fire  from 0.5") and shown["animations"] == "Rotate"
    assert "respawn" not in shown
    ed.draw(pygame.display.get_surface())


def test_a_respawning_copy_also_shows_its_respawn_time(ed):
    placed_copy(ed, mode="respawn", respawn=12.0)
    assert info(ed)["respawn"] == "12 s"


def test_the_detail_rows_are_read_only_clicks_and_the_wheel_change_nothing(ed):
    copy = placed_copy(ed, mode="persistent", effect="health", amount=25.0)
    before = (copy.prefab, copy.mode, copy.effect, copy.amount, copy.size, ed.level.prefabs[0].size)
    count = len(ed.level.undo) if hasattr(ed.level, "undo") else len(ed.undo)
    for name in ("where", "sprite", "mode", "effect", "size", "lift", "emits", "light", "animations"):
        r = row(ed, name)
        for spot in (r.minus.center, r.value.center, r.plus.center, r.rect.center):
            click(ed, spot)
        ed.mouse = r.rect.center
        ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=3))
        ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-3))
    assert (copy.prefab, copy.mode, copy.effect, copy.amount, copy.size, ed.level.prefabs[0].size) == before
    assert len(ed.undo) == count and ed.field_edit is None and ed.selected_entity() is copy


def test_the_wheel_over_the_prefab_row_does_not_quietly_point_the_copy_at_another_prefab(ed):
    copy = placed_copy(ed)
    ed.level.prefabs.append(Entity(0.0, 0.0, name="Coin", effect="score"))
    ed.draw(pygame.display.get_surface())
    ed.mouse = row(ed, "prefab").rect.center
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
    assert copy.prefab == "Torch"
    click(ed, row(ed, "prefab").plus.center)                                      # an explicit click on + still does
    assert copy.prefab == "Coin"


def test_edit_prefab_opens_the_prefabs_section_on_that_prefab(ed):
    ed.level.prefabs = [Entity(0.0, 0.0, name="Coin"), Entity(0.0, 0.0, name="Torch", effect="health")]
    ed.do("tool:entity")
    ed.place_prefab = "Torch"
    ed.map_click((4, 4), 1)
    ed.draw(pygame.display.get_surface())
    click(ed, details.button_box(row(ed, "edit_prefab")).center)
    assert ed.prefabs_mode and ed.selected_prefab() is ed.level.prefabs[1] and ed.selected_entity() is None
    assert "name" in keys(ed)                                                     # the pane is now the prefab's own
    ed.draw(pygame.display.get_surface())


def test_detach_turns_the_copy_into_a_plain_item_that_keeps_its_settings(ed):
    copy = placed_copy(ed, mode="persistent", effect="health", amount=25.0, size=0.5)
    click(ed, details.button_box(row(ed, "detach")).center)
    assert copy.prefab == "" and (copy.effect, copy.amount, copy.size) == ("health", 25.0, 0.5)
    assert ed.selected_entity() is copy and "amount" in keys(ed) and "edit_prefab" not in keys(ed)
    click(ed, row(ed, "amount").plus.center)                                      # now editable, on its own
    assert copy.amount == 30.0 and ed.level.prefabs[0].amount == 25.0                   # the prefab is untouched


def test_an_atlas_click_with_a_copy_selected_changes_nothing_and_says_why(ed):
    copy = placed_copy(ed, tile=11)
    click(ed, ed.tile_rect(3).center)
    assert copy.tile == 11 and ed.level.prefabs[0].tile == 11 and ed.entity_brush.tile != 3
    assert "Torch" in ed.message and "Prefabs section" in ed.message


def test_the_delete_button_removes_only_the_selected_copy_and_sits_below_every_row(ed):
    copy = placed_copy(ed, effect="health")
    other = Entity(6.5, 6.5, prefab="Torch")
    ed.level.entities.append(other)
    ed.draw(pygame.display.get_surface())
    rows, rect = ed.details_rows(), ed.details_rect()
    button = details.button_rect(rect, rows)
    assert button.top > max(r.rect.bottom for r in rows) and button.bottom <= rect.bottom
    click(ed, button.center)
    assert copy not in ed.level.entities and other in ed.level.entities and len(ed.level.prefabs) == 1


def test_clicking_the_map_next_to_a_selected_copy_selects_or_places_and_never_removes(ed):
    copy = placed_copy(ed)
    ed.map_click((5, 4), 1)                                                       # the next cell: a new copy is placed
    assert len(ed.level.entities) == 2 and copy in ed.level.entities
    ed.map_click((4, 4), 1)                                                       # back on the first: it is selected
    assert ed.selected_entity() is copy and len(ed.level.entities) == 2


# ------------------------------------------------------------------ the 3D view beside the Prefabs section

def test_the_3d_view_stays_open_beside_the_prefabs_section_and_not_the_others(ed):
    ed.set_preview(True)
    add_prefab(ed)
    ed.prefab_selected = 0
    ed.update(0.0, [0] * 512)
    ed.draw(pygame.display.get_surface())
    column, pane, area = ed.preview_column(), ed.details_rect(), ed.map_area()
    assert column is not None and pane is not None
    assert area.right <= pane.x and pane.right <= column.x                    # list, settings, 3D view side by side
    assert all(rect.right <= area.right for rect, _i in ed.prefab_rows()[0])
    ed.do("guns")
    assert ed.preview_column() is None                                        # (the Guns section has its own preview)


def test_editing_a_prefab_shows_in_the_3d_view(ed):
    p = add_prefab(ed)
    p.name = "Gem"
    ed.place_prefab = "Gem"
    place(ed, (3, 3))
    ed.set_preview(True)
    ed.do("prefabs")
    ed.prefab_selected = 0
    ed.update(0.0, [0] * 512)
    assert [s[4] for s in ed.preview.items.sprites()] == [p.tile]
    before = p.tile
    click(ed, row(ed, "tile").plus.center)                                   # the next icon
    assert p.tile == before + 1
    ed.preview.last_build = -1e9                                              # (no wait for the rebuild throttle)
    ed.update(0.0, [0] * 512)
    assert ed.preview.built_revision == ed.revision
    assert [s[4] for s in ed.preview.items.sprites()] == [p.tile]
    ed.draw(pygame.display.get_surface())
