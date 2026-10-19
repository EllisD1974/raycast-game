"""Exploding ammo: falloff with distance, a bigger hit up close, cover, the shooter's rocket jump, knockback."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from game import Game
from mapfile import AmmoType, Gun, Level
from world import World

DT = 1 / 60
ROCKET = AmmoType(name="Rocket", speed=10.0, explodes=True, blast_radius=3.0, blast_damage=50.0, knockback=5.0,
                  air_knockback_mult=1.5, self_damage_mult=0.25, self_knockback_mult=1.0)


def game_with(level=None, ammo=ROCKET):
    level = level or Level.blank(14, 14)
    game = Game(level, World(level, 16), random.Random(1))
    for pid in (0, 1):
        game.add_player(pid)
    game.players[0].body.x, game.players[0].body.y, game.players[0].body.angle = 3.0, 7.0, 0.0
    game.players[1].body.x, game.players[1].body.y = 12.0, 1.0      # far away by default
    return game


def fire(game, pitch=0.0, ammo=ROCKET, damage=10.0):
    body = game.players[0].body
    body.pitch = pitch
    game.projectiles.fire(body, Gun(damage=damage), ammo, 0)
    for _ in range(240):
        game.advance_world(DT)
        if not game.projectiles.bullets:
            return


def test_a_direct_hit_does_the_most_damage():
    game = game_with()
    game.players[1].body.x, game.players[1].body.y = 7.0, 7.0
    fire(game)
    assert game.players[1].stats.health == pytest.approx(100.0 - 10.0 - 50.0, abs=1.0)


def test_closer_to_the_center_means_more_damage_and_knockback():
    near, far = game_with(), game_with()
    near.players[1].body.x, near.players[1].body.y = 12.0, 7.5      # the rocket explodes on the far wall, x = 14
    far.players[1].body.x, far.players[1].body.y = 12.0, 9.0
    fire(near)
    fire(far)
    assert near.players[1].stats.health < far.players[1].stats.health < 100.0
    assert near.players[1].body.vz > far.players[1].body.vz > 0.0


def test_a_player_in_the_air_is_thrown_harder():
    ground, air = game_with(), game_with()
    for game in (ground, air):
        game.players[1].body.x, game.players[1].body.y = 12.0, 7.5
    air.players[1].body.on_ground = False                   # same place, only not standing
    fire(ground)
    fire(air)
    speed = lambda g: sum(v * v for v in (g.players[1].body.vx, g.players[1].body.vy, g.players[1].body.vz)) ** 0.5
    assert speed(air) == pytest.approx(speed(ground) * 1.5, rel=0.01) and speed(ground) > 0.0


def test_a_wall_shields_from_the_blast():
    level = Level.blank(14, 14)
    game = game_with(level)
    game.players[1].body.x, game.players[1].body.y = 12.0, 3.0
    for x in range(8, 14):                                  # a wall between the blast and the target
        level.walls[5][x] = 1
    game.world = World(level, 16)
    game.players[0].body.angle = 0.0
    game.players[0].body.y = 7.0
    fire(game)
    assert game.players[1].stats.health == 100.0 and game.players[1].body.vz == 0.0


def test_firing_at_your_feet_launches_you_for_less_damage():
    game = game_with()
    body = game.players[0].body
    fire(game, pitch=-1.4)
    assert body.vz > 2.0 and not body.on_ground
    assert 0.0 < 100.0 - game.players[0].stats.health < 50.0 * 0.25 + 0.01


def test_no_knockback_setting_still_hurts_but_does_not_move():
    game = game_with(ammo=None)
    ammo = AmmoType(explodes=True, knockback=0.0, speed=10.0)
    game.players[1].body.x, game.players[1].body.y = 12.0, 7.5
    fire(game, ammo=ammo)
    assert game.players[1].stats.health < 100.0 and game.players[1].body.vz == 0.0


def test_ammo_that_does_not_explode_is_unchanged():
    game = game_with()
    game.players[1].body.x, game.players[1].body.y = 12.0, 7.5
    fire(game, ammo=AmmoType(speed=10.0))
    assert game.players[1].stats.health == 100.0 and game.players[1].body.vz == 0.0


def test_explosion_settings_survive_saving():
    a = AmmoType.from_dict({"name": "R", "explodes": True, "blast_radius": 2.5, "knockback": 7.0,
                            "explosion_effects": ["boom"]})
    assert (a.explodes, a.blast_radius, a.knockback, a.explosion_effects) == (True, 2.5, 7.0, ("boom",))
    assert AmmoType.from_dict({"name": "old"}).explodes is False
