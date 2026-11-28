"""Melee weapons: a gun whose shot is a swing that strikes what is within reach, with no ammunition."""
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

from game import Game, Inputs
from hud import ammo_text, draw_hud
from entities import PlayerStats
from inventory import Inventory
from mapfile import AmmoType, Gun, Level, load_level, save_level
from world import World

DT = 1 / 60


def knife(**options):
    return Gun("Knife", **{"shot": "melee", "damage": 40.0, "fire_rate": 2.0, "reach": 1.5, "arc": 60.0, **options})


def duel(gap=1.0, gun=None):
    """Player 0, holding the knife, faces east toward player 1 `gap` cells away (center to center)."""
    level = Level.blank(12, 12)
    level.guns = [gun or knife()]
    game = Game(level, World(level, 16), random.Random(1))
    for pid in (0, 1):
        game.add_player(pid)
    me, them = game.players[0].body, game.players[1].body
    me.x, me.y, me.angle, me.pitch = 3.0, 6.0, 0.0, 0.0
    them.x, them.y, them.z = 3.0 + gap, 6.0, me.z
    game.players[0].inventory.give_gun(level.guns[0])
    return game


def swing(game, pid=0):
    game.move_player(pid, Inputs(fire=True), DT)
    game.move_player(pid, Inputs(), DT)


def test_a_melee_weapon_survives_save_and_load_and_its_numbers_are_kept_in_range(tmp_path):
    level = Level.blank(8, 8)
    level.guns = [knife(reach=2.5, arc=90.0)]
    save_level(str(tmp_path / "m.json"), level)
    assert load_level(str(tmp_path / "m.json")).guns == level.guns
    mended = Gun.from_dict({"shot": "melee", "reach": 99, "arc": -5})
    assert mended.melee and mended.reach == 10.0 and mended.arc == 0.0
    assert Gun.from_dict({}).reach == 1.5 and not Gun.from_dict({}).melee      # (older maps: guns stay guns)


def test_a_melee_weapon_swings_at_its_rate_forever_and_never_reloads():
    inventory = Inventory()
    inventory.give_gun(Gun("Pistol"))
    pistol_rounds = inventory.ammo[""]
    inventory.give_gun(knife(fire_rate=2.0, mode="auto"))       # (held down, it keeps swinging)
    assert inventory.ammo[""] == pistol_rounds                 # (it brings no rounds into the shared pool)
    inventory.equip(1)
    swings = sum(len(inventory.update(DT, True)) for _ in range(round(10 / DT)))
    assert 19 <= swings <= 21
    assert not inventory.start_reload() and not inventory.current().reloading
    inventory.refill()
    assert inventory.ammo[""] == Gun("Pistol").start_ammo


def test_a_swing_hurts_the_player_in_front_within_reach():
    game = duel(gap=1.0)
    swing(game)
    assert game.players[1].stats.health == pytest.approx(60.0)
    assert game.projectiles.bullets == []                      # (no bullet flies)


def test_a_swing_misses_out_of_reach_behind_or_beside():
    game = duel(gap=2.5)                                      # 2.5 - radius is beyond a 1.5 reach
    swing(game)
    assert game.players[1].stats.health == 100.0
    game = duel(gap=1.0)
    game.players[0].body.angle = 3.14159                       # facing away
    swing(game)
    assert game.players[1].stats.health == 100.0
    game = duel(gap=1.0, gun=knife(arc=0.0))
    game.players[1].body.y += 0.6                              # off to the side, beyond a narrow swing
    swing(game)
    assert game.players[1].stats.health == 100.0


def test_a_wide_swing_reaches_to_the_side():
    game = duel(gap=1.0, gun=knife(arc=120.0))
    game.players[1].body.y += 0.8
    swing(game)
    assert game.players[1].stats.health == pytest.approx(60.0)


def test_a_wall_in_between_shields_from_a_swing():
    game = duel(gap=1.2)
    game.world.point_open = lambda x, y, z: x < 3.4
    swing(game)
    assert game.players[1].stats.health == 100.0


def test_a_swing_strikes_only_the_nearest_and_uses_its_ammo_types_hit_effects():
    game = duel(gap=1.2, gun=knife(ammo="Blade"))
    game.level.ammo_types = [AmmoType("Blade", damage_mult=2.0, player_hit_effects=("Blood",))]
    game.add_player(2)
    third = game.players[2].body
    third.x, third.y, third.z = 3.7, 6.0, game.players[0].body.z
    swing(game)
    assert game.players[2].stats.health == 20.0 and game.players[1].stats.health == 100.0
    assert [fx[0] for fx in game.take_fx()] == ["Blood"]


def test_the_hud_shows_no_ammunition_for_a_melee_weapon():
    pygame.init()
    pygame.display.set_mode((100, 100))
    inventory = Inventory()
    inventory.give_gun(knife())
    assert ammo_text(inventory.current()) == ""
    picture = pygame.Surface((320, 200))
    tiles = [pygame.Surface((32, 32), pygame.SRCALPHA) for _ in range(32)]
    tiles[16].fill((200, 200, 200))
    for kick in (0.0, 0.5, 1.0):
        draw_hud(picture, pygame.font.Font(None, 16), PlayerStats(), "", inventory, tiles, kick)
