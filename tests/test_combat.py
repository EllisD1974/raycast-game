"""Bullets striking players: hurting them, passing through the shooter, stopping at walls, respawning."""
import os
import random
from dataclasses import asdict
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from constants import PLAYER_HEIGHT
from game import Game
from mapfile import AmmoType, Gun, Level
from world import World

DT = 1 / 60


def two_player_game():
    level = Level.blank(12, 12)
    game = Game(level, World(level, 16), random.Random(1))
    for pid in (0, 1):
        game.add_player(pid)
    shooter, target = game.players[0].body, game.players[1].body
    shooter.x, shooter.y, shooter.angle, shooter.pitch = 3.0, 6.0, 0.0, 0.0
    target.x, target.y = 6.0, 6.0
    shooter.z = target.z = game.players[0].body.z
    return game


def shoot(game, damage=30.0):
    """Player 0 fires level along their aim at the height of their eye, aimed at the other's middle."""
    body = game.players[0].body
    body.pitch = 0.0
    game.projectiles.fire(body, Gun(damage=damage), None, 0)


def fly(game, seconds=1.0):
    for _ in range(int(seconds / DT)):
        game.advance_world(DT)


def test_a_bullet_hurts_the_player_it_hits_and_is_used_up():
    game = two_player_game()
    shoot(game)
    fly(game)
    assert game.players[1].stats.health == pytest.approx(70.0)
    assert game.players[0].stats.health == 100.0
    assert game.projectiles.bullets == []


def test_a_bullet_passes_through_the_player_who_fired_it():
    game = two_player_game()
    game.players[1].body.x = 20.0                  # nobody in the way
    shoot(game)
    game.advance_world(DT)
    assert game.players[0].stats.health == 100.0 and len(game.projectiles.bullets) == 1


def test_a_bullet_passing_beside_or_over_a_player_misses():
    game = two_player_game()
    game.players[1].body.y = 6.0 + 0.5             # more than a radius off the line
    shoot(game)
    fly(game)
    assert game.players[1].stats.health == 100.0
    game = two_player_game()
    game.players[1].body.z -= PLAYER_HEIGHT + 0.5   # standing below the bullet's height
    shoot(game)
    fly(game)
    assert game.players[1].stats.health == 100.0


def test_a_wall_in_between_shields_the_player():
    game = two_player_game()
    game.world.point_open = lambda x, y, z: x < 4.5     # a wall across the line of fire
    shoot(game)
    fly(game)
    assert game.players[1].stats.health == 100.0


def test_dying_puts_a_player_back_at_the_start_with_full_health_and_their_score():
    game = two_player_game()
    state = game.players[1]
    state.stats.score = 7
    shoot(game, damage=100.0)
    fly(game)
    assert game.players[1] is state                       # same object: sessions hold on to it
    assert state.stats.health == 100.0 and state.stats.score == 7
    assert (state.body.x, state.body.y) == (game.level.start_x, game.level.start_y)


def test_a_hit_plays_the_ammos_effect_and_light_where_the_bullet_struck():
    game = two_player_game()
    ammo = AmmoType(speed=30.0, hit_effect="Spark", hit_light="Pop")
    game.projectiles.fire(game.players[0].body, Gun(damage=1.0), ammo, 0)
    fly(game)
    (name, x, y, z, dx, dy, dz), = game.take_fx()
    assert name == "Spark" and 5.5 < x < 6.0 and y == pytest.approx(6.0)       # in the player's near edge
    assert dx == pytest.approx(-1.0) and dy == pytest.approx(0.0)              # spraying back at the shooter
    assert [(f[0], f[1:3]) for f in game.take_flashes()] == [("Pop", pytest.approx((x, y)))]


def test_a_bullet_that_hits_a_wall_plays_its_hit_effect_too_and_one_without_plays_nothing():
    game = two_player_game()
    game.players[1].body.x = 20.0
    game.world.point_open = lambda x, y, z: x < 4.5
    game.projectiles.fire(game.players[0].body, Gun(), AmmoType(hit_effect="Spark"), 0)
    game.projectiles.fire(game.players[0].body, Gun(), AmmoType(), 0)
    fly(game)
    assert [e[0] for e in game.take_fx()] == ["Spark"] and game.take_flashes() == []


def test_hit_effect_and_light_are_kept_by_ammo_types_and_bad_values_are_repaired():
    ammo = AmmoType.from_dict(asdict(AmmoType(hit_effect="Spark", hit_light="Pop")))
    assert (ammo.hit_effect, ammo.hit_light) == ("Spark", "Pop")
    assert AmmoType.from_dict({}).hit_effect == "" and AmmoType.from_dict({"hit_light": 5}).hit_light == "5"
