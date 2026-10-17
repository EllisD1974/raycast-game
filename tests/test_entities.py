"""Items in the world: the map data, picking them up, respawning, the sprite renderer and the editor tool."""
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
from constants import HEIGHT, WIDTH
from entities import Entities, PlayerStats
from mapfile import Animation, Entity, Level, load_level, save_level
from renderer import Renderer
from world import World


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1280, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


def level_with(*entities, floors=1):
    level = Level.blank(12, 12, floors=floors)
    level.entities.extend(entities)
    return level


def at(x, y, z=0.0):
    return physics.Player(x, y, z)


# ------------------------------------------------------------------ the map file

def test_entities_survive_save_and_load(tmp_path):
    level = level_with(Entity(3.5, 4.5, mode="respawn", effect="health", amount=25, respawn=7, tile=8,
                              size=0.6, lift=0.2))
    save_level(str(tmp_path / "m.json"), level)
    again = load_level(str(tmp_path / "m.json"))
    assert again.entities == level.entities


def test_a_map_without_entities_loads_with_none_and_saves_no_entities_key(tmp_path):
    level = Level.blank(8, 8)
    save_level(str(tmp_path / "m.json"), level)
    assert '"entities"' not in (tmp_path / "m.json").read_text()
    assert load_level(str(tmp_path / "m.json")).entities == []


def test_bad_entity_values_in_a_file_fall_back_to_defaults():
    entity = Entity.from_dict({"x": 2.5, "y": 2.5, "mode": "explode", "effect": "fly", "size": -3})
    assert entity.mode == "once" and entity.effect == "score" and entity.size > 0


def test_entities_follow_the_map_when_it_is_resized_or_a_floor_is_removed():
    level = level_with(Entity(2.5, 2.5), Entity(5.5, 5.5, span=1), Entity(6.5, 6.5, span=2), floors=3)
    level.resize_edges(left=2, top=1)
    assert [(e.x, e.y) for e in level.entities] == [(4.5, 3.5), (7.5, 6.5), (8.5, 7.5)]
    level.remove_floor(1)
    assert [e.span for e in level.entities] == [0, 1]           # the one on the removed floor is gone
    level.resize(5, 5)
    assert [(e.x, e.y) for e in level.entities] == [(4.5, 3.5)]


# ------------------------------------------------------------------ picking up

def run(items, player, stats, seconds):
    messages = []
    for _ in range(int(seconds * 60)):
        messages += items.update(player, stats, 1 / 60)
    return messages


def test_a_once_item_gives_its_effect_and_is_gone_for_good():
    level = level_with(Entity(5.5, 5.5, mode="once", effect="score", amount=10))
    items, stats = Entities(level, World(level, 16)), PlayerStats()
    assert items.update(at(2.5, 2.5), stats, 0.1) == [] and stats.score == 0
    assert items.update(at(5.5, 5.4), stats, 0.1) == ["+10 score"] and stats.score == 10
    assert items.sprites() == []
    run(items, at(2.5, 2.5), stats, 60)
    run(items, at(5.5, 5.5), stats, 1)
    assert stats.score == 10 and items.sprites() == []


def test_a_respawning_item_comes_back_after_its_time_and_can_be_picked_up_again():
    level = level_with(Entity(5.5, 5.5, mode="respawn", effect="score", amount=5, respawn=3))
    items, stats = Entities(level, World(level, 16)), PlayerStats()
    run(items, at(5.5, 5.5), stats, 1)
    assert stats.score == 5 and items.sprites() == []
    run(items, at(2.5, 2.5), stats, 1.5)
    assert items.sprites() == []                                # 2.5 s of the 3 have passed
    run(items, at(2.5, 2.5), stats, 1)
    assert len(items.sprites()) == 1
    run(items, at(5.5, 5.5), stats, 0.1)
    assert stats.score == 10


def test_a_persistent_item_stays_and_counts_once_per_visit():
    level = level_with(Entity(5.5, 5.5, mode="persistent", effect="health", amount=10))
    items, stats = Entities(level, World(level, 16)), PlayerStats(health=50)
    run(items, at(5.5, 5.5), stats, 2)                          # standing on it for two seconds
    assert stats.health == 60 and len(items.sprites()) == 1
    run(items, at(2.5, 2.5), stats, 0.5)                        # step away ...
    run(items, at(5.5, 5.5), stats, 0.5)                        # ... and back: counts again
    assert stats.health == 70


def test_health_is_capped_and_an_effect_of_none_only_picks_up():
    level = level_with(Entity(5.5, 5.5, effect="health", amount=500), Entity(7.5, 7.5, effect="none"))
    items, stats = Entities(level, World(level, 16)), PlayerStats(health=90)
    items.update(at(5.5, 5.5), stats, 0.1)
    assert stats.health == stats.max_health
    assert items.update(at(7.5, 7.5), stats, 0.1) == ["Picked up"] and stats.score == 0


def test_an_item_on_a_higher_floor_is_not_touched_from_the_floor_below():
    level = level_with(Entity(5.5, 5.5, span=1), floors=2)
    for x in range(3, 9):
        for y in range(3, 9):
            level.set("floor_h2", x, y, 2.0)
            level.set("ceil_h2", x, y, 3.5)
    items, stats = Entities(level, World(level, 16)), PlayerStats()
    assert items.update(at(5.5, 5.5, 0.0), stats, 0.1) == [] and stats.score == 0
    assert items.update(at(5.5, 5.5, 2.0), stats, 0.1) != []


def test_an_item_with_no_floor_under_it_is_left_out():
    level = level_with(Entity(5.5, 5.5, span=1), floors=2)      # floor 2 has no room there
    assert Entities(level, World(level, 16)).items == []


# ------------------------------------------------------------------ drawing

def frame(world, sprites, x=3.5, angle=0.0):
    textures = np.zeros((16, 32, 32, 4), np.uint8)
    textures[..., :3] = 90
    textures[..., 3] = 255
    textures[7, ..., :3] = (255, 0, 0)                          # tile 7: solid red sprite
    textures[8, ..., 3] = 0                                     # tile 8: fully transparent sprite
    renderer = Renderer(textures)
    player = physics.Player(x, 5.5, 0.0, angle)
    renderer.draw(world, player, sprites)
    return np.array(renderer.framebuffer)


def red(fb):
    return (fb[..., 0] > 60) & (fb[..., 1] < 20) & (fb[..., 2] < 20)     # (fog darkens it with distance)


def test_a_sprite_is_drawn_in_front_of_the_player_and_not_behind_or_when_transparent():
    world = World(Level.blank(12, 12), 16)
    ahead = frame(world, [(7.5, 5.5, 0.0, 0.5, 7)])
    assert red(ahead).sum() > 200 and red(ahead)[WIDTH // 2, HEIGHT // 2 + 20]
    assert red(frame(world, [(7.5, 5.5, 0.0, 0.5, 7)], angle=math.pi)).sum() == 0     # behind the player
    assert red(frame(world, [(7.5, 5.5, 0.0, 0.5, 8)])).sum() == 0                    # see-through tile


def test_a_nearer_sprite_is_bigger_and_a_wall_hides_a_sprite_behind_it():
    level = Level.blank(12, 12)
    near = red(frame(World(level, 16), [(5.5, 5.5, 0.0, 0.5, 7)])).sum()
    far = red(frame(World(level, 16), [(9.5, 5.5, 0.0, 0.5, 7)])).sum()
    assert near > far > 0
    level.set("walls", 6, 5, 1)
    assert red(frame(World(level, 16), [(9.5, 5.5, 0.0, 0.5, 7)])).sum() == 0


# ------------------------------------------------------------------ the editor tool

@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(10, 10, floors=2)
    editor.level.start_x = editor.level.start_y = 1.5
    editor.show_legend = False
    editor.draw(pygame.display.get_surface())
    return editor


def test_the_entity_tool_places_selects_and_removes_items(ed):
    ed.do("tool:entity")
    assert ed.selected_entity() is None and ed.palette_active()      # nothing selected: the prefab list shows
    ed.map_click((4, 4), 1)
    assert len(ed.level.entities) == 1 and ed.selected_entity() is ed.level.entities[0]
    assert ed.details_rect() is not None                        # a selected item opens the pane
    e = ed.level.entities[0]
    assert (e.x, e.y, e.span) == (4.5, 4.5, 0)
    ed.map_click((6, 6), 1)                                     # a second item
    assert len(ed.level.entities) == 2 and ed.selected == 1
    ed.map_click((4, 4), 1)                                     # clicking an existing item selects it, no new one
    assert len(ed.level.entities) == 2 and ed.selected == 0
    ed.map_click((4, 4), 3)                                     # right click removes it
    assert len(ed.level.entities) == 1 and ed.selected_entity() is None
    ed.do("undo")
    assert len(ed.level.entities) == 2


def test_the_entity_tool_needs_a_room_on_the_floor_being_edited(ed):
    ed.do("tool:entity")
    ed.do("floor:1")
    ed.map_click((4, 4), 1)
    assert ed.level.entities == []                              # floor 2 has no room there
    ed.do("floor:0")
    ed.map_click((4, 4), 1)
    assert len(ed.level.entities) == 1
    ed.draw(pygame.display.get_surface())                       # draws without error, also from the other floor
    ed.do("floor:1")
    ed.draw(pygame.display.get_surface())


def pane_row(ed, key):
    return next(r for r in ed.details_rows() if r.field.key == key)


def choose(ed, key, choice):
    """Open a field's drop-down list and click one of its choices."""
    import details
    row = pane_row(ed, key)
    pane_click(ed, details.menu_anchor(row))
    assert ed.menu_open == key
    for rect, option in details.menu_rects(row):
        if option == choice:
            pane_click(ed, rect)
            return
    raise AssertionError(f"{choice} is not in the list for {key}")


def pane_click(ed, rect):
    ed.on_mouse_down(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=rect.center, button=1))
    ed.on_mouse_up(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=rect.center, button=1))


def type_keys(ed, text):
    for ch in text:
        ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=ord(ch) if ch.isalnum() else 0, mod=0, unicode=ch))


def test_the_pane_edits_the_selected_item_in_place(ed):
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    ed.map_click((6, 6), 1)
    ed.map_click((4, 4), 1)                                     # select the first one again
    first, second = ed.level.entities
    pane_click(ed, pane_row(ed, "mode").plus)                   # + steps to the next choice
    assert first.mode == "respawn" and second.mode == "once"
    choose(ed, "effect", "health")                              # the effect is picked from a drop-down list
    assert first.effect == "health"
    pane_click(ed, pane_row(ed, "amount").plus)
    pane_click(ed, pane_row(ed, "respawn").plus)                # only shown for respawning items
    assert first.amount == 15 and first.respawn == 11
    pane_click(ed, pane_row(ed, "size").minus)
    assert first.size == pytest.approx(0.3)
    assert (first.x, first.y) == (4.5, 4.5) and len(ed.level.entities) == 2       # edited, not replaced
    ed.do("undo")
    assert ed.level.entities[0].size == pytest.approx(0.4)


def test_the_pane_only_shows_the_fields_that_apply(ed):
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    keys = [r.field.key for r in ed.details_rows()]
    assert keys == ["tile", "mode", "effect", "amount", "size", "lift", "animations", "add_animation", "make_prefab"]
    ed.level.entities[0].effect = "none"
    ed.level.entities[0].mode = "respawn"
    keys = [r.field.key for r in ed.details_rows()]
    assert "amount" not in keys and "respawn" in keys


def test_the_wheel_over_a_row_steps_it_and_a_number_can_be_typed(ed):
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    e = ed.level.entities[0]
    ed.mouse = pane_row(ed, "amount").rect.center
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=2))
    assert e.amount == 20
    zoom = ed.zoom
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
    assert e.amount == 15 and ed.zoom == zoom                   # the map did not zoom
    pane_click(ed, pane_row(ed, "size").value)                  # click the number: type a new one
    assert ed.field_edit is not None
    for _ in range(6):
        ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, mod=0, unicode=""))
    type_keys(ed, "1.25")
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    assert e.size == 1.25 and ed.field_edit is None
    pane_click(ed, pane_row(ed, "lift").value)
    type_keys(ed, "99")                                         # out of range: clamped
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    assert e.lift == 5.0
    pane_click(ed, pane_row(ed, "size").value)
    type_keys(ed, "x")
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert e.size == 1.25 and ed.field_edit is None and ed.selected_entity() is e    # Esc cancels typing only


def test_new_items_start_with_the_settings_you_last_edited(ed):
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    pane_click(ed, pane_row(ed, "mode").plus)
    pane_click(ed, pane_row(ed, "size").plus)
    ed.map_click((7, 7), 1)
    assert (ed.level.entities[1].mode, ed.level.entities[1].size) == ("respawn", pytest.approx(0.5))


def test_delete_button_delete_key_escape_and_changing_tools_close_the_pane(ed):
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    pane_click(ed, details_button(ed))
    assert ed.level.entities == [] and ed.selected_entity() is None
    ed.map_click((4, 4), 1)
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DELETE, mod=0, unicode=""))
    assert ed.level.entities == []
    ed.map_click((4, 4), 1)
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert ed.selected_entity() is None and len(ed.level.entities) == 1    # closed, item kept
    ed.map_click((4, 4), 1)
    ed.do("tool:paint")
    assert ed.details_rect() is None


def details_button(ed):
    import details
    return details.button_rect(ed.details_rect(), ed.details_rows())


def test_clicking_the_pane_does_not_paint_the_map_and_the_atlas_sets_the_sprite(ed):
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    before = [row[:] for row in ed.level.walls]
    pane_click(ed, pane_row(ed, "tile").plus)
    assert ed.level.walls == before and ed.level.entities[0].tile == map_editor.ENTITY_FIRST_TILE + 1
    ed.atlas_drag = ((1, 0), (1, 0))
    ed.finish_atlas_drag()
    assert ed.level.entities[0].tile == 1


def test_the_pane_is_drawn_and_shrinks_the_map_area(ed):
    ed.do("tool:entity")
    wide = ed.map_area().width                                  # the prefab list is already docked here
    ed.do("tool:paint")
    assert ed.map_area().width == wide + map_editor.PANE_WIDTH   # with another tool there is no pane
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    assert ed.map_area().width == wide
    ed.draw(pygame.display.get_surface())
    ed.field_edit = ["size", "1."]
    ed.draw(pygame.display.get_surface())


def test_the_3d_preview_shows_items(ed):
    ed.do("tool:entity")
    ed.map_click((5, 1), 1)
    preview = ed.ensure_preview()
    preview.sync(ed.level, ed.revision, force=True)
    assert len(preview.items.sprites()) == 1
    preview.render()


# ------------------------------------------------------------------ drop-downs and animations

def test_a_drop_down_opens_lists_the_choices_and_closes_without_choosing(ed):
    import details
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    row = pane_row(ed, "effect")
    pane_click(ed, row.value)
    assert ed.menu_open == "effect" and [c for _r, c in details.menu_rects(row)] == ["none", "score", "health", "item", "gun", "ammo"]
    ed.draw(pygame.display.get_surface())                       # the open list draws
    pane_click(ed, pygame.Rect(700, 700, 4, 4))                 # click away: closed, nothing changed
    assert ed.menu_open is None and ed.level.entities[0].effect == "score"
    pane_click(ed, row.value)
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert ed.menu_open is None and ed.selected_entity() is not None      # Esc closes the list first
    choose(ed, "effect", "none")
    assert ed.level.entities[0].effect == "none"
    assert "amount" not in [r.field.key for r in ed.details_rows()]


def test_animations_are_none_by_default_and_added_from_a_list(ed):
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    e = ed.level.entities[0]
    assert e.animations == []
    choose(ed, "add_animation", "float")
    assert [a.kind for a in e.animations] == ["float"]
    assert {"a0_speed", "a0_amount"} <= {r.field.key for r in ed.details_rows()}
    choose(ed, "add_animation", "rotate")
    assert [a.kind for a in e.animations] == ["float", "rotate"]
    keys = [r.field.key for r in ed.details_rows()]
    assert "a1_speed" in keys and "a1_amount" not in keys       # rotating has no height
    assert "add_animation" not in keys                          # both are in use: nothing left to add


def test_each_animation_has_its_own_settings_and_can_be_removed(ed):
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    e = ed.level.entities[0]
    choose(ed, "add_animation", "float")
    choose(ed, "add_animation", "rotate")
    pane_click(ed, pane_row(ed, "a0_speed").plus)               # float speed 0.5 -> 0.6
    pane_click(ed, pane_row(ed, "a1_speed").plus)
    pane_click(ed, pane_row(ed, "a1_speed").plus)               # rotate speed 0.5 -> 0.7
    pane_click(ed, pane_row(ed, "a0_amount").plus)
    assert (e.animations[0].speed, e.animations[1].speed) == (pytest.approx(0.6), pytest.approx(0.7))
    assert e.animations[0].amount == pytest.approx(0.15)
    ed.mouse = pane_row(ed, "a1_speed").rect.center
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-3))
    assert e.animations[1].speed == pytest.approx(0.4) and e.animations[0].speed == pytest.approx(0.6)
    header = next(r for r in ed.details_rows() if r.field.key == "a0")
    pane_click(ed, header.plus)                                 # the x on the Float heading
    assert [a.kind for a in e.animations] == ["rotate"]
    assert "add_animation" in [r.field.key for r in ed.details_rows()]    # float can be added again
    ed.do("undo")
    assert [a.kind for a in ed.level.entities[0].animations] == ["float", "rotate"]


def test_animations_are_not_shared_between_items_or_with_undo_copies(ed):
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    choose(ed, "add_animation", "float")
    ed.map_click((7, 7), 1)                                     # a new item does not inherit the animations
    assert ed.level.entities[1].animations == []
    ed.map_click((4, 4), 1)
    pane_click(ed, pane_row(ed, "a0_speed").plus)
    ed.do("undo")
    assert ed.level.entities[0].animations[0].speed == pytest.approx(0.5)
    copy = ed.level.copy()
    copy.entities[0].animations[0].speed = 9
    assert ed.level.entities[0].animations[0].speed == pytest.approx(0.5)


def test_animations_survive_save_and_load_and_bad_ones_are_dropped(tmp_path):
    level = level_with(Entity(3.5, 4.5, animations=[Animation("float", 0.8, 0.2), Animation("rotate", 1.5)]))
    save_level(str(tmp_path / "m.json"), level)
    again = load_level(str(tmp_path / "m.json"))
    assert again.entities[0].animations == level.entities[0].animations
    entity = Entity.from_dict({"x": 1.5, "y": 1.5, "animations": [{"kind": "wobble", "speed": -4}, "junk"]})
    assert [(a.kind, a.speed) for a in entity.animations] == [("float", 0.0)]


def test_a_floating_item_bobs_up_and_down_and_a_rotating_one_spins():
    level = level_with(Entity(5.5, 5.5, animations=[Animation("float", 1.0, 0.2)]),
                       Entity(7.5, 7.5, animations=[Animation("rotate", 0.5)]),
                       Entity(9.5, 9.5))
    items = Entities(level, World(level, 16))
    base = items.sprites()
    assert [s[5] for s in base][2] == 0.0
    heights, spins = [], []
    for _ in range(120):
        items.clock += 1 / 60
        a, b, c = items.sprites()
        heights.append(a[2])
        spins.append(b[5])
        assert c[2] == base[2][2] and c[5] == 0.0               # a plain item does not move
    assert min(heights) >= 0.0 - 1e-9 and max(heights) - min(heights) > 0.3      # bobs about 0.4 (2 x 0.2)
    assert max(heights) <= 0.4 + 1e-9
    assert spins[-1] - spins[0] > 2.5                           # it keeps turning (0.5 turns a second)


def test_the_preview_advances_the_animation_clock(ed):
    ed.do("tool:entity")
    ed.map_click((5, 1), 1)
    choose(ed, "add_animation", "rotate")
    preview = ed.ensure_preview()
    preview.sync(ed.level, ed.revision, force=True)
    before = preview.items.sprites()[0][5]
    preview.update(0.2)
    assert preview.items.sprites()[0][5] != before


def test_a_spinning_sprite_narrows_edge_on_and_is_mirrored_from_behind():
    world = World(Level.blank(12, 12), 16)
    textures = np.zeros((16, 32, 32, 4), np.uint8)
    textures[..., :3] = 90
    textures[..., 3] = 255
    textures[7, :, :16, :3] = (255, 0, 0)                       # tile 7: red left half, blue right half
    textures[7, :, 16:, :3] = (0, 0, 255)

    def look(spin):
        renderer = Renderer(textures)
        renderer.draw(world, physics.Player(3.5, 5.5, 0.0, 0.0), [(7.5, 5.5, 0.0, 0.6, 7, spin)])
        fb = np.array(renderer.framebuffer).astype(int)
        red = (fb[..., 0] > fb[..., 2] + 30) & (fb[..., 0] > 60)
        blue = (fb[..., 2] > fb[..., 0] + 30) & (fb[..., 2] > 60)
        cols_r, cols_b = np.nonzero(red.any(axis=1))[0], np.nonzero(blue.any(axis=1))[0]
        return cols_r, cols_b

    r0, b0 = look(0.0)
    assert r0.max() < b0.min()                                  # facing us: red on the left, blue on the right
    width_front = b0.max() - r0.min()
    r1, b1 = look(math.pi)
    assert b1.max() < r1.min()                                  # turned round: mirrored
    r2, b2 = look(math.pi / 2)
    assert (max(r2.max() if len(r2) else 0, b2.max() if len(b2) else 0)
            - min(r2.min() if len(r2) else 999, b2.min() if len(b2) else 999)) < width_front * 0.2   # edge-on: a sliver


# ------------------------------------------------------------------ standing on top of walls

def test_items_can_be_placed_on_top_of_walls(ed):
    ed.level.set("walls", 4, 4, 1)
    ed.level.set("wall_h", 4, 4, 0.5)                           # a low wall
    ed.level.set("walls", 6, 6, 1)                              # a full-height wall
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    ed.map_click((6, 6), 1)
    assert len(ed.level.entities) == 2
    world = World(ed.level, 16)
    items = Entities(ed.level, world)
    assert [round(i.z, 2) for i in items.items] == [0.5, ed.level.wall_ceiling(6, 6)]    # at the top of each wall
    ed.map_click((4, 4), 1)                                     # clicking it selects it like any other item
    assert ed.selected_entity() is ed.level.entities[0]


def test_an_item_on_a_low_wall_is_drawn_above_it_and_can_be_picked_up_from_its_top():
    level = Level.blank(12, 12)
    level.set("walls", 5, 5, 1)
    level.set("wall_h", 5, 5, 0.25)
    level.entities.append(Entity(5.5, 5.5, effect="score", amount=3, lift=0.0))
    world = World(level, 16)
    items = Entities(level, world)
    assert items.items[0].z == pytest.approx(0.25)
    stats = PlayerStats()
    assert items.update(at(5.5, 3.0, 0.0), stats, 0.1) == []                    # nowhere near
    assert items.update(at(5.5, 5.3, 0.25), stats, 0.1) == ["+3 score"]       # standing on the wall's top
