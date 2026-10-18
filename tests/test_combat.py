"""Bullets striking players: hurting them, passing through the shooter, stopping at walls, respawning."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from constants import PLAYER_HEIGHT
from game import Game
from mapfile import Gun, Level
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
