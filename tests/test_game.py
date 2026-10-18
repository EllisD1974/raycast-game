"""The windowless game: players, one step of time, and several players sharing a world."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import physics
from game import Game, Inputs
from mapfile import Entity, Gun, Level
from world import World

DT = 1 / 60


def game_with(*entities, guns=()):
    level = Level.blank(12, 12)
    level.entities = list(entities)
    level.guns = list(guns)
    return Game(level, World(level, 16), random.Random(1))


def run(game, inputs, seconds):
    events = []
    for _ in range(round(seconds / DT)):
        events.append(game.tick(inputs, DT))
    return events


def test_a_new_player_starts_at_the_level_start():
    game = game_with()
    state = game.add_player(0)
    assert (state.body.x, state.body.y) == (game.level.start_x, game.level.start_y)
    assert state.stats.health == state.stats.max_health


def test_inputs_move_that_player_only():
    game = game_with()
    a, b = game.add_player(1), game.add_player(2)
    start = (b.body.x, b.body.y)
    run(game, {1: Inputs(forward=1)}, 0.3)
    assert a.body.x > game.level.start_x + 0.5
    assert (b.body.x, b.body.y) == start                    # no inputs for 2: it stands still


def test_tick_matches_calling_physics_directly():
    game = game_with()
    state = game.add_player(0)
    twin = physics.spawn(game.level, game.world)
    for i in range(120):
        game.tick({0: Inputs(forward=1, strafe=i % 2, turn=0.01, jump=i == 30, sprint=True, tilt=0.002)}, DT)
        physics.step(game.world, twin, 1, i % 2, 0.01, i == 30, DT, True)
        physics.look(twin, 0.002)
    assert state.body == twin


def test_firing_makes_bullets_and_reports_the_shots():
    pistol = Gun("Pistol", mag_size=10, start_ammo=30)
    game = game_with(Entity(1.5, 1.5, effect="gun", gun="Pistol"), guns=[pistol])
    game.add_player(0)
    game.tick({}, DT)                                       # standing on the pickup: gets the gun
    events = run(game, {0: Inputs(fire=True)}, 0.1)
    assert sum(e[0].fired for e in events) == 1             # a semi-auto gun: one shot per press
    assert game.projectiles.bullets or game.sprites()


def test_equip_and_cycle_change_the_gun_in_hand():
    a, b = Gun("A"), Gun("B")
    game = game_with(guns=[a, b])
    inv = game.add_player(0).inventory
    inv.give_gun(a)
    inv.give_gun(b)
    game.tick({0: Inputs(equip=(1,))}, DT)
    assert inv.current().gun.name == "B"
    game.tick({0: Inputs(cycle=1)}, DT)
    assert inv.equipped is None                             # the step after the last gun is empty hands


def test_each_player_gets_their_own_pickup_messages_and_inventory():
    game = game_with(Entity(5.5, 5.5, effect="item", item="Key", amount=1, mode="persistent"))
    a, b = game.add_player(1), game.add_player(2)
    a.body.x = a.body.y = 5.5
    events = game.tick({}, DT)
    assert events[1].picked == ["+1 Key"] and events[2].picked == []
    assert a.inventory.count("Key") == 1 and b.inventory.count("Key") == 0
    b.body.x = b.body.y = 5.5                               # a persistent item stays for the next player
    assert game.tick({}, DT)[2].picked == ["+1 Key"]
    assert game.tick({}, DT)[1].picked == []                # (1 is still standing on it: not again)


def test_a_pickup_taken_by_one_player_is_gone_for_the_other():
    game = game_with(Entity(5.5, 5.5, effect="score", amount=10, mode="once"))
    a, b = game.add_player(1), game.add_player(2)
    a.body.x = a.body.y = 5.5
    b.body.x = b.body.y = 5.5
    events = game.tick({}, DT)
    assert events[1].picked == ["+10 score"] and events[2].picked == []
    assert a.stats.score == 10 and b.stats.score == 0


def test_the_item_clock_runs_once_however_many_players():
    game = game_with()
    for pid in range(4):
        game.add_player(pid)
    run(game, {}, 1.0)
    assert abs(game.items.clock - 1.0) < 1e-6


def test_removed_players_stop_being_simulated():
    game = game_with()
    game.add_player(1)
    game.remove_player(1)
    assert game.tick({1: Inputs(forward=1)}, DT) == {}


def test_the_same_inputs_give_the_same_game():
    def play():
        pistol = Gun("Pistol", mag_size=10, start_ammo=30, spread=3.0, mode="auto")
        game = game_with(Entity(1.5, 1.5, effect="gun", gun="Pistol"), guns=[pistol])
        game.add_player(0)
        run(game, {0: Inputs(forward=1, turn=0.02, fire=True)}, 1.5)
        return game.players[0].body, [vars(b) for b in game.projectiles.bullets]
    assert play() == play()
