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
from mapfile import Entity, Level, load_level, save_level
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


def test_the_entity_tool_places_replaces_and_removes_items(ed):
    ed.do("tool:entity")
    ed.do("ent:mode")
    ed.do("ent:effect")
    ed.map_click((4, 4), 1)
    assert len(ed.level.entities) == 1
    e = ed.level.entities[0]
    assert (e.x, e.y, e.span, e.mode, e.effect) == (4.5, 4.5, 0, "respawn", "health")
    ed.do("ent:amount+")
    ed.map_click((4, 4), 1)                                     # again: replaces, not duplicates
    assert len(ed.level.entities) == 1 and ed.level.entities[0].amount == 15
    ed.map_click((4, 4), 3)                                     # right click removes it
    assert ed.level.entities == []
    ed.do("undo")
    assert len(ed.level.entities) == 1


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


def test_the_buttons_step_the_item_settings(ed):
    ed.do("tool:entity")
    for action in ("ent:size+", "ent:lift+", "ent:respawn+", "ent:amount-", "ent:amount-"):
        ed.do(action)
    b = ed.entity_brush
    assert b.size == pytest.approx(0.5) and b.lift == pytest.approx(0.1) and b.respawn == 11 and b.amount == 0
    assert any(a == "ent:effect" for _r, _l, a in ed.layout())
    assert not any(a == "ent:respawn+" for _r, _l, a in ed.layout())      # only shown for respawning items
    ed.do("ent:mode")
    assert any(a == "ent:respawn+" for _r, _l, a in ed.layout())


def test_the_3d_preview_shows_items(ed):
    ed.do("tool:entity")
    ed.map_click((5, 1), 1)
    preview = ed.ensure_preview()
    preview.sync(ed.level, ed.revision, force=True)
    assert len(preview.items.sprites()) == 1
    preview.render()
