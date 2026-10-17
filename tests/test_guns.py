"""Guns and the inventory: the map data, picking things up, firing, reloading and bullets in flight."""
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import physics
from entities import Entities, PlayerStats
from hud import draw_hud, weapon_picture
from inventory import Inventory
from mapfile import AmmoType, Entity, Gun, Level, load_level, save_level
from projectiles import Projectiles
from world import World

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((100, 100))
    yield
    pygame.quit()


def run(inventory, seconds, trigger=False, reload_pressed=False):
    """Advance the inventory, returning every gun fired."""
    fired = []
    for i in range(round(seconds / DT)):
        fired += inventory.update(DT, trigger, reload_pressed and i == 0)
    return fired


# ------------------------------------------------------------------ the map file

def test_guns_survive_save_and_load_and_bad_values_are_repaired(tmp_path):
    level = Level.blank(8, 8)
    level.guns = [Gun("Rifle", tile=20, size=6.5, mode="auto", damage=7.5, fire_rate=9, mag_size=30,
                      start_ammo=90, reload_time=2.25, ammo="5.56", spread=1.5)]
    level.ammo_types = [AmmoType("5.56", tile=15, size=0.2, speed=40, range=33, damage_mult=1.5)]
    save_level(str(tmp_path / "m.json"), level)
    again = load_level(str(tmp_path / "m.json"))
    assert again.guns == level.guns and again.ammo_types == level.ammo_types
    assert again.ammo_for(again.guns[0]).speed == 40
    assert again.ammo_for(Gun("Other", ammo="missing")).name == "missing"        # no such type: a plain bullet
    mended = Gun.from_dict({"name": "  ", "mode": "laser", "damage": "lots", "fire_rate": -5, "mag_size": 0})
    assert mended.name == "Pistol" and mended.mode == "semi" and mended.damage == 10 and mended.fire_rate > 0
    assert mended.mag_size >= 1
    assert Level.blank(5, 5).guns == []


def test_undo_copies_do_not_share_guns():
    level = Level.blank(8, 8)
    level.guns = [Gun("A")]
    copy = level.copy()
    copy.guns[0].damage = 99
    assert level.guns[0].damage == 10


# ------------------------------------------------------------------ the inventory and pickups

def test_items_stack_in_the_inventory():
    inv = Inventory()
    inv.add_item("Red key")
    inv.add_item("Red key", 2)
    inv.add_item("Coin", 10)
    assert inv.count("Red key") == 3 and inv.count("Coin") == 10 and inv.count("Nothing") == 0
    inv.add_item("")                                            # an unnamed item still goes somewhere
    assert inv.count("Item") == 1


def test_a_pickup_with_the_item_effect_goes_into_the_inventory_and_can_respawn():
    level = Level.blank(12, 12)
    level.entities = [Entity(5.5, 5.5, effect="item", item="Red key", amount=1, mode="respawn", respawn=2),
                      Entity(7.5, 7.5, effect="item", item="Gem", amount=3)]
    items, stats, inv = Entities(level, World(level, 16)), PlayerStats(), Inventory()
    messages = items.update(physics.Player(5.5, 5.5, 0.0), stats, DT, inv)
    assert messages == ["+1 Red key"] and inv.count("Red key") == 1
    items.update(physics.Player(7.5, 7.5, 0.0), stats, DT, inv)
    assert inv.count("Gem") == 3
    for _ in range(130):
        items.update(physics.Player(2.5, 2.5, 0.0), stats, DT, inv)   # away: the key comes back after 2 s
    items.update(physics.Player(5.5, 5.5, 0.0), stats, DT, inv)
    assert inv.count("Red key") == 2


def test_a_gun_pickup_gives_the_gun_loaded_and_equips_it_and_a_second_one_gives_ammo():
    pistol = Gun("Pistol", mag_size=10, start_ammo=30, ammo="9mm")
    level = Level.blank(12, 12)
    level.guns = [pistol]
    level.entities = [Entity(5.5, 5.5, effect="gun", gun="Pistol"), Entity(7.5, 7.5, effect="gun", gun="Pistol"),
                      Entity(3.5, 3.5, effect="ammo", ammo="9mm", amount=15)]
    items, stats, inv = Entities(level, World(level, 16)), PlayerStats(), Inventory()
    assert items.update(physics.Player(5.5, 5.5, 0.0), stats, DT, inv) == ["Picked up Pistol"]
    state = inv.current()
    assert state is not None and (state.mag, state.reserve) == (10, 30) and inv.equipped == 0
    items.update(physics.Player(7.5, 7.5, 0.0), stats, DT, inv)
    assert len(inv.guns) == 1 and inv.guns[0].reserve == 60     # the same gun again: more ammunition
    assert items.update(physics.Player(3.5, 3.5, 0.0), stats, DT, inv) == ["+15 9mm ammo"]
    assert inv.guns[0].reserve == 75


def test_ammo_found_before_its_gun_is_kept_for_when_the_gun_is_picked_up():
    inv = Inventory()
    assert not inv.add_ammo("9mm", 20)                                       # no gun uses it yet: still kept
    inv.give_gun(Gun("Pistol", mag_size=10, start_ammo=5, ammo="9mm"))
    assert inv.current().reserve == 25


def test_guns_that_share_an_ammo_type_share_one_pool_and_others_do_not():
    inv = Inventory()
    inv.give_gun(Gun("Pistol", ammo="9mm", mag_size=4, start_ammo=10, mode="auto", fire_rate=50, reload_time=0.1))
    inv.give_gun(Gun("SMG", ammo="9mm", mag_size=20, start_ammo=10))
    inv.give_gun(Gun("Rifle", ammo="5.56", mag_size=30, start_ammo=7))
    assert inv.ammo == {"9mm": 20, "5.56": 7}                                # the 9mm guns' starting rounds add up
    assert inv.guns[0].reserve == inv.guns[1].reserve == 20 and inv.guns[2].reserve == 7
    run(inv, 0.3, trigger=True)                                              # empty the pistol: it reloads from the pool
    run(inv, 0.5)
    assert inv.guns[0].reserve == inv.guns[1].reserve and inv.guns[0].reserve < 20
    assert inv.ammo["5.56"] == 7                                             # the rifle's rounds are untouched
    before = inv.ammo["9mm"]
    inv.add_ammo("9mm", 6)
    assert inv.guns[0].reserve == inv.guns[1].reserve == before + 6


def test_an_ammo_pickup_feeds_every_gun_using_that_type():
    level = Level.blank(12, 12)
    level.guns = [Gun("Pistol", ammo="9mm", start_ammo=0), Gun("SMG", ammo="9mm", start_ammo=0)]
    level.entities = [Entity(5.5, 5.5, effect="ammo", ammo="9mm", amount=30)]
    items, inv = Entities(level, World(level, 16)), Inventory()
    inv.give_gun(level.guns[0])
    inv.give_gun(level.guns[1])
    items.update(physics.Player(5.5, 5.5, 0.0), PlayerStats(), DT, inv)
    assert inv.guns[0].reserve == inv.guns[1].reserve == 30


def test_picking_up_inventory_things_without_an_inventory_does_not_crash():
    level = Level.blank(12, 12)
    level.entities = [Entity(5.5, 5.5, effect="item", item="Key")]
    items = Entities(level, World(level, 16))
    assert items.update(physics.Player(5.5, 5.5, 0.0), PlayerStats(), DT) == ["+10 Key"]


def test_equipping_switches_puts_away_and_wheels_through_the_guns():
    inv = Inventory()
    inv.give_gun(Gun("A"))
    inv.give_gun(Gun("B"))
    assert inv.equipped == 0
    assert inv.equip(1) and inv.equipped == 1
    assert inv.equip(1) and inv.equipped is None                # the same slot again: put it away
    assert not inv.equip(5)
    inv.cycle(1)
    assert inv.equipped == 0
    inv.cycle(1)
    inv.cycle(1)
    assert inv.equipped is None                                 # empty hands are one of the stops
    inv.cycle(-1)
    assert inv.equipped == 1


# ------------------------------------------------------------------ firing

def test_nothing_fires_without_an_equipped_gun_or_a_trigger():
    inv = Inventory()
    assert run(inv, 1.0, trigger=True) == []
    inv.give_gun(Gun("A"))
    assert run(inv, 1.0, trigger=False) == []
    inv.equip(0)
    assert run(inv, 1.0, trigger=True) == []                    # holstered


def test_full_auto_fires_at_the_fire_rate_while_the_trigger_is_held():
    inv = Inventory()
    inv.give_gun(Gun("A", mode="auto", fire_rate=10, mag_size=100, start_ammo=0))
    shots = run(inv, 1.0, trigger=True)
    assert 9 <= len(shots) <= 11
    assert inv.current().mag == 100 - len(shots)


def test_semi_auto_fires_once_per_pull_however_long_it_is_held_and_not_faster_than_the_rate():
    inv = Inventory()
    inv.give_gun(Gun("A", mode="semi", fire_rate=4, mag_size=50))
    assert len(run(inv, 2.0, trigger=True)) == 1                # held for 2 s: still one round
    run(inv, 0.5, trigger=False)
    assert len(run(inv, 0.1, trigger=True)) == 1                # a new pull fires again
    run(inv, 0.02, trigger=False)
    assert len(run(inv, 0.02, trigger=True)) == 0               # but not before the 1/4 s between rounds is up


def test_a_magazine_empties_then_reloads_from_the_reserve_taking_the_reload_time():
    inv = Inventory()
    inv.give_gun(Gun("A", mode="auto", fire_rate=20, mag_size=5, start_ammo=7, reload_time=1.0))
    shots = run(inv, 0.5, trigger=True)
    assert len(shots) == 5
    state = inv.current()
    assert state.mag == 0 and state.reloading                   # it started reloading by itself
    assert run(inv, 0.5, trigger=True) == []                    # no shooting while reloading
    run(inv, 0.6, trigger=False)
    assert not state.reloading and (state.mag, state.reserve) == (5, 2)
    run(inv, 1.0, trigger=True)
    run(inv, 1.2)
    assert (state.mag, state.reserve) == (2, 0)                 # the last of the reserve


def test_reload_key_tops_up_a_part_empty_magazine_and_does_nothing_when_full_or_dry():
    inv = Inventory()
    inv.give_gun(Gun("A", mode="semi", fire_rate=50, mag_size=6, start_ammo=10, reload_time=0.5))
    state = inv.current()
    run(inv, 0.1, reload_pressed=True)
    assert not state.reloading                                  # already full
    run(inv, 0.05, trigger=True)
    run(inv, 0.05, trigger=False)
    run(inv, 0.05, trigger=True)
    assert state.mag == 4
    run(inv, 0.1, reload_pressed=True)
    assert state.reloading
    run(inv, 0.6)
    assert (state.mag, state.reserve) == (6, 8)
    state.reserve = 0
    state.mag = 2
    run(inv, 0.1, reload_pressed=True)
    assert not state.reloading                                  # nothing to reload with


def test_a_single_shot_gun_holds_one_round_and_reloads_after_every_shot():
    inv = Inventory()
    inv.give_gun(Gun("Musket", mode="single", mag_size=99, start_ammo=3, reload_time=1.0, fire_rate=10))
    state = inv.current()
    assert state.mag == 1 and state.gun.capacity == 1
    assert len(run(inv, 0.2, trigger=True)) == 1
    assert state.reloading
    assert run(inv, 0.5, trigger=False) == []
    run(inv, 0.6)
    assert (state.mag, state.reserve) == (1, 2)


def test_pulling_the_trigger_on_an_empty_gun_reloads_it_and_switching_cancels_a_reload():
    inv = Inventory()
    inv.give_gun(Gun("A", mode="semi", mag_size=1, start_ammo=5, reload_time=1.0, fire_rate=10))
    inv.give_gun(Gun("B"))
    state = inv.current()
    state.mag = 0
    run(inv, 0.1, trigger=True)
    assert state.reloading
    inv.equip(1)
    assert not state.reloading and state.mag == 0


# ------------------------------------------------------------------ bullets

def test_a_bullet_flies_where_the_player_looks_at_its_speed_and_vanishes_at_its_range():
    world = World(Level.blank(40, 12), 16)
    player = physics.Player(2.5, 5.5, 0.0, angle=0.0)
    bullets = Projectiles()
    gun = Gun("A")
    bullets.fire(player, gun, AmmoType("B", tile=14, size=0.2, speed=10.0, range=6.0))
    b = bullets.bullets[0]
    assert b.vx == pytest.approx(10.0) and b.vy == pytest.approx(0.0, abs=1e-9) and b.vz == pytest.approx(0.0, abs=1e-9)
    assert b.z == pytest.approx(player.eye_z - 0.03)
    x0 = b.x
    bullets.update(world, 0.25)
    assert bullets.bullets[0].x == pytest.approx(x0 + 2.5)
    assert bullets.sprites()[0][3:5] == (0.2, 14)
    for _ in range(60):
        assert bullets.update(world, 0.05) == []                # ran out of range without hitting anything
    assert bullets.bullets == []


def test_bullets_follow_the_pitch_and_the_spread_is_random_within_its_limit():
    player = physics.Player(2.5, 5.5, 0.0, angle=0.0, pitch=math.radians(30))
    bullets = Projectiles()
    bullets.fire(player, Gun("A"), AmmoType(speed=10.0))
    b = bullets.bullets[0]
    assert b.vz == pytest.approx(5.0) and b.vx == pytest.approx(10 * math.cos(math.radians(30)))
    level_player = physics.Player(2.5, 5.5, 0.0, angle=0.0)
    yaws = set()
    for _ in range(40):
        bullets.bullets.clear()
        bullets.fire(level_player, Gun("A", spread=5.0), AmmoType(speed=10.0))
        angle = math.atan2(bullets.bullets[0].vy, bullets.bullets[0].vx)
        assert abs(angle) <= math.radians(5.0) + 1e-9
        yaws.add(round(angle, 4))
    assert len(yaws) > 10


def test_bullets_stop_at_walls_floors_and_ceilings_and_report_the_hit():
    level = Level.blank(40, 12)
    level.set("walls", 10, 5, 1)
    world = World(level, 16)
    bullets = Projectiles()
    bullets.fire(physics.Player(2.5, 5.5, 0.0, angle=0.0), Gun("A", damage=12),
                 AmmoType(speed=30.0, range=50.0, damage_mult=2.0))
    hits = []
    for _ in range(40):
        hits += bullets.update(world, 1 / 60)
    assert len(hits) == 1 and hits[0].damage == 24 and 9.5 < hits[0].x < 10.2 and bullets.bullets == []
    down = Projectiles()
    down.fire(physics.Player(5.5, 5.5, 0.0, angle=0.0, pitch=-math.radians(60)), Gun("A"), AmmoType(speed=30.0))
    assert len(sum((down.update(world, 1 / 60) for _ in range(30)), [])) == 1       # into the floor
    up = Projectiles()
    up.fire(physics.Player(5.5, 5.5, 0.0, angle=0.0, pitch=math.radians(60)), Gun("A"), AmmoType(speed=30.0))
    assert len(sum((up.update(world, 1 / 60) for _ in range(30)), [])) == 1         # into the ceiling


def test_a_fast_bullet_cannot_skip_through_a_thin_wall_and_glass_stops_bullets():
    level = Level.blank(40, 12)
    level.set("walls", 10, 5, 1)
    world = World(level, 16)
    bullets = Projectiles()
    bullets.fire(physics.Player(2.5, 5.5, 0.0, angle=0.0), Gun("A"), AmmoType(speed=200.0, range=60.0))
    hits = bullets.update(world, 0.2)                           # 40 cells in one frame
    assert len(hits) == 1 and hits[0].x < 11.0
    textures = np.zeros((16, 32, 32, 4), np.uint8)
    textures[..., 3] = 255
    textures[3, ..., 3] = 80                                    # tile 3 is glass
    glass_level = Level.blank(40, 12)
    glass_level.set("walls", 10, 5, 4)                          # map id 4 = tile 3
    glass_world = World(glass_level, 16, transparent_tiles=(textures[..., 3] < 255).any(axis=(1, 2)))
    shot = Projectiles()
    shot.fire(physics.Player(2.5, 5.5, 0.0, angle=0.0), Gun("A"), AmmoType(speed=200.0, range=60.0))
    assert len(shot.update(glass_world, 0.2)) == 1


def test_a_bullet_fired_point_blank_into_a_wall_hits_at_once():
    level = Level.blank(12, 12)
    world = World(level, 16)
    bullets = Projectiles()
    bullets.fire(physics.Player(1.4, 5.5, 0.0, angle=math.pi), Gun("A"))      # facing the border wall, 0.4 away
    assert len(bullets.update(world, 1 / 60)) == 1


# ------------------------------------------------------------------ what is drawn

def test_the_weapon_picture_is_cropped_to_its_pixels_and_scaled_by_the_size_setting():
    tile = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.rect(tile, (0, 0, 0, 255), (4, 10, 16, 6))
    small, big = weapon_picture(tile, 2.0), weapon_picture(tile, 4.0)
    assert big.get_width() == pytest.approx(2 * small.get_width(), abs=2) and big.get_height() > small.get_height()
    assert weapon_picture(pygame.Surface((32, 32), pygame.SRCALPHA), 1.0) is None


def test_the_hud_draws_the_inventory_the_guns_and_the_equipped_weapon():
    font = pygame.font.Font(None, 22)
    tiles = [pygame.Surface((32, 32), pygame.SRCALPHA) for _ in range(20)]
    pygame.draw.rect(tiles[16], (200, 0, 0, 255), (4, 10, 16, 6))
    inv = Inventory()
    inv.add_item("Red key", 2)
    inv.give_gun(Gun("Pistol", tile=16))
    inv.give_gun(Gun("Rifle", tile=16))
    inv.current().reload_left = 0.5
    picture = pygame.Surface((640, 360))
    picture.fill((0, 0, 0))
    draw_hud(picture, font, PlayerStats(), "+1 Red key", inv, tiles, kick=1.0)
    red = pygame.surfarray.array3d(picture)
    assert ((red[..., 0] > 150) & (red[..., 1] < 60)).any()        # the weapon is on the picture
    plain = pygame.Surface((640, 360))
    draw_hud(plain, font, PlayerStats(), "", None, None)            # and the HUD still works without an inventory


# ------------------------------------------------------------------ shot types

def test_a_single_bullet_shot_sends_one_bullet_and_a_multi_bullet_shot_sends_every_pellet():
    player = physics.Player(2.5, 5.5, 0.0, angle=0.0)
    one = Projectiles()
    one.fire(player, Gun("A", shot="single", pellets=8))
    assert len(one.bullets) == 1
    many = Projectiles()
    many.fire(player, Gun("Shotgun", shot="multi", pellets=7, spread=6.0))
    assert len(many.bullets) == 7
    angles = [math.atan2(b.vy, b.vx) for b in many.bullets]
    assert len(set(round(a, 5) for a in angles)) > 1                       # each pellet is aimed on its own
    assert all(abs(a) <= math.radians(6.0) + 1e-9 for a in angles)
    assert all(b.damage == 10 for b in many.bullets)                       # the damage is per bullet


def test_a_projectile_shot_fires_like_a_single_bullet_until_it_is_built():
    bullets = Projectiles()
    bullets.fire(physics.Player(2.5, 5.5, 0.0), Gun("Launcher", shot="projectile", pellets=8))
    assert len(bullets.bullets) == 1


def test_a_multi_shot_uses_one_round_of_ammunition():
    inv = Inventory()
    inv.give_gun(Gun("Shotgun", shot="multi", pellets=8, mode="semi", mag_size=6, start_ammo=0, fire_rate=5))
    fired = run(inv, 0.1, trigger=True)
    assert len(fired) == 1 and inv.current().mag == 5


def test_shot_type_and_pellets_are_saved_and_bad_values_repaired(tmp_path):
    level = Level.blank(8, 8)
    level.guns = [Gun("Shotgun", shot="multi", pellets=12)]
    save_level(str(tmp_path / "s.json"), level)
    again = load_level(str(tmp_path / "s.json"))
    assert again.guns[0].shot == "multi" and again.guns[0].pellets == 12
    assert Gun.from_dict({"shot": "laser", "pellets": 0}).shot == "single"
    assert Gun.from_dict({"pellets": 0}).pellets == 1
    assert Gun.from_dict({}).shot == "single"                               # older maps have no shot type


def test_an_older_map_with_the_bullet_on_the_gun_gets_an_ammo_type_per_gun(tmp_path):
    import json
    level = Level.blank(8, 8)
    level.guns = [Gun("Pistol", ammo="x")]
    level.entities = [Entity(3.5, 3.5, effect="ammo", ammo="x", amount=5)]
    path = str(tmp_path / "old.json")
    save_level(path, level)
    data = json.loads(open(path).read())
    data.pop("ammo_types", None)
    data["guns"] = [{"name": "Pistol", "proj_tile": 15, "proj_size": 0.3, "proj_speed": 25, "proj_range": 9}]
    data["entities"] = [{"x": 3.5, "y": 3.5, "effect": "ammo", "gun": "Pistol", "amount": 5}]
    open(path, "w").write(json.dumps(data))
    old = load_level(path)
    assert [a.name for a in old.ammo_types] == ["Pistol ammo"] and old.guns[0].ammo == "Pistol ammo"
    kind = old.ammo_for(old.guns[0])
    assert (kind.tile, kind.size, kind.speed, kind.range) == (15, 0.3, 25, 9)
    assert old.entities[0].ammo == "Pistol ammo"                          # the pickup now names the ammo type
