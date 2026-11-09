"""Bullets and blasts hitting what is not a player (game.Game.other_targets): a round's enemies, which the round is
told about through hurt_target."""
import os
import random
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import Game
from mapfile import AmmoType, Gun, Level
from physics import Player
from projectiles import struck_player
from world import World

DT = 1 / 60


@dataclass
class Body:
    x: float
    y: float
    z: float = 0.0
    height: float = 1.0
    radius: float = 0.4
    on_ground: bool = True


class Targets:
    """A round with enemies to shoot (only what Game asks of a round for this)."""

    def __init__(self, bodies):
        self.bodies = bodies
        self.hurt = []

    def targets(self):
        return list(self.bodies.items())

    def hurt_target(self, target, damage, attacker, push):
        self.hurt.append((target, round(damage, 3), attacker, push))

    def update(self, dt):
        pass


def game_with(bodies):
    level = Level.blank(20, 12)
    game = Game(level, World(level, 32), random.Random(1))
    game.add_player(0)
    game.round = Targets(bodies)
    return game


def shoot(game, ammo=None, seconds=1.0):
    shooter = Player(3.5, 5.5, 0.0)
    game.projectiles.fire(shooter, Gun(spread=0.0, damage=10), ammo or AmmoType(speed=20.0, range=30.0), owner=0)
    for _ in range(round(seconds / DT)):
        game.advance_world(DT)


def test_a_bullet_hurts_an_enemy_and_says_who_shot():
    game = game_with({("z", 1): Body(8.5, 5.5)})
    game.players[0].body.x, game.players[0].body.y = 3.5, 2.5      # (out of the way)
    shoot(game)
    assert game.round.hurt == [(("z", 1), 10.0, 0, None)]
    assert game.players[0].stats.health == game.players[0].stats.max_health


def test_the_first_enemy_in_the_way_takes_the_bullet():
    game = game_with({("z", 1): Body(12.5, 5.5), ("z", 2): Body(8.5, 5.5)})
    game.players[0].body.x, game.players[0].body.y = 3.5, 2.5
    shoot(game)
    assert [hurt[0] for hurt in game.round.hurt] == [("z", 2)]


def test_an_enemy_is_as_wide_as_it_says():
    assert struck_player([(("z", 1), 5.0, 5.0, 0.0, 1.0, 0.4)], 0, 5.35, 5.0, 0.5) == ("z", 1)
    assert struck_player([(("z", 1), 5.0, 5.0, 0.0, 1.0, 0.1)], 0, 5.35, 5.0, 0.5) is None
    assert struck_player([(("z", 1), 5.0, 5.0, 0.0, 1.0, 0.4)], 0, 5.0, 5.0, 1.2) is None     # over its head


def test_a_blast_hurts_and_throws_enemies():
    game = game_with({("z", 1): Body(8.5, 5.5), ("z", 2): Body(9.5, 6.5)})
    game.players[0].body.x, game.players[0].body.y = 3.5, 2.5
    shoot(game, AmmoType(speed=20.0, range=30.0, explodes=True, blast_radius=3.0, blast_damage=50, knockback=4.0))
    hurt = {target: (damage, push) for target, damage, _owner, push in game.round.hurt}
    assert set(hurt) == {("z", 1), ("z", 2)}
    assert hurt[("z", 2)][0] < 50 and hurt[("z", 2)][1] is not None    # farther from the blast: less, and thrown
