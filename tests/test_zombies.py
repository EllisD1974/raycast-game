"""Zombies: enemy kinds in the map file, the rounds, enemies coming in, chasing, attacking and dying, money for hits
and kills, the game ending and starting over, and playing it through a host (zombies.py, with game.py, session.py)."""
import math
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import net
from game import Game, Inputs
from mapfile import (ENEMY_SPAWN, Attack, Enemy, Level, MapSettings, Spawner, curve_at, level_text, parse_level,
                     read_curve)
from session import ClientSession, HostSession
from test_session import FIRST_CHARACTER, make_world, run
from world import World
from zombies import SHIRT, ZombieRound, ZombieView, enemy_sprites
import json

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


def quick(**rules):
    base = dict(mode="zombies", intermission=0.5, spawn_interval=0.1, zombie_count=[[1, 2], [2, 4]],
                zombie_health=[[1, 1.0], [2, 2.0]], max_alive=24, game_over_time=1.0)
    base.update(rules)
    return MapSettings(**base)


def zombie_level(enemies=None, spawners=((17.5, 5.5),), **rules):
    """A 20 x 12 room: players come in on the left, enemies at `spawners` (on the right)."""
    level = Level.blank(20, 12)
    level.spawners = [Spawner(2.5, 5.5)] + [Spawner(x, y, team=ENEMY_SPAWN) for x, y in spawners]
    level.enemies = list(enemies) if enemies is not None else [Enemy(name="Walker", speed=3.0, health=50,
                                                                     attacks=[Attack(damage=20, windup=0.2)])]
    level.settings = quick(**rules)
    return level


def zombie_game(players=(0,), **kwargs):
    level = zombie_level(**kwargs)
    game = Game(level, World(level, 32), random.Random(1), character_tile=FIRST_CHARACTER)
    for pid in players:
        game.add_player(pid)
    return game


def play(game, seconds, inputs=None, until=None):
    for _ in range(round(seconds / DT)):
        game.tick(inputs or {}, DT)
        if until is not None and until():
            return True
    return False


def go_live(game):
    assert play(game, 5.0, until=lambda: game.round.phase == "live")


def place(body, x, y):
    body.x, body.y, body.z, body.vz, body.on_ground = x, y, 0.0, 0.0, True


# ------------------------------------------------------------------ the map file

def test_enemies_and_the_zombie_settings_are_saved_and_loaded():
    level = zombie_level(zombie_count=[[1, 3], [4, 9]], max_alive=7)
    level.enemies[0].color = [10, 20, 30]
    level.enemies[0].attacks.append(Attack(damage=5, range=2.0))
    again = parse_level(json.loads(level_text(level)))
    assert again.enemies == level.enemies
    assert again.settings == level.settings
    assert [s.team for s in again.spawners] == [0, ENEMY_SPAWN]


def test_no_enemies_no_key():
    level = Level.blank(8, 8)
    assert '"enemies"' not in level_text(level)
    assert parse_level(json.loads(level_text(level))).enemies == []


def test_unusable_enemy_values_fall_back():
    enemy = Enemy.from_dict({"name": "", "speed": "fast", "health": -5, "pathing": "teleport", "color": [1, 2],
                             "attacks": [{"kind": "laser", "damage": 1e9}, "nonsense"]})
    assert enemy.name == "Zombie" and enemy.speed == Enemy().speed and enemy.health == 1.0
    assert enemy.pathing == "sticky" and enemy.color == Enemy().color
    assert len(enemy.attacks) == 1 and enemy.attacks[0].kind == "melee" and enemy.attacks[0].damage == 100000.0


def test_curves():
    points = [[1, 6], [5, 18], [10, 40]]
    assert curve_at(points, 1) == 6 and curve_at(points, 3) == 12 and curve_at(points, 10) == 40
    assert curve_at(points, 0) == 6                         # before the first point: level
    assert curve_at(points, 15) == 62                       # after the last: on along the last line
    assert curve_at([[1, 5]], 50) == 5
    assert curve_at([[1, 10], [2, 0]], 10) == 0             # never below 0
    assert read_curve([[3, 1], [2, 5], [4, "x"], [5, 1e9]], [[1, 1]], 0, 100) == [[3, 1.0], [5, 100.0]]
    assert read_curve("junk", [[1, 1]], 0, 100) == [[1, 1]]


def test_a_copy_of_the_level_does_not_share_enemies_or_curves():
    level = zombie_level()
    copy = level.copy()
    copy.enemies[0].attacks[0].damage = 1
    copy.settings.zombie_count[0][1] = 99
    assert level.enemies[0].attacks[0].damage == 20 and level.settings.zombie_count[0][1] == 2


# ------------------------------------------------------------------ rounds

def test_players_never_come_in_at_the_enemies_spawn_points():
    game = zombie_game(players=(0, 1, 2, 3))
    assert all(state.body.x < 5 for state in game.players.values())
    assert all(state.team == 1 for state in game.players.values())


def test_a_round_starts_after_the_intermission_and_sends_its_enemies():
    game = zombie_game()
    assert isinstance(game.round, ZombieRound) and game.round.phase == "intermission" and game.round.number == 0
    go_live(game)
    assert game.round.number == 1
    play(game, 0.3)
    assert len(game.round.enemies) == 2 and game.round.to_spawn == 0


def test_no_more_than_max_alive_at_once():
    game = zombie_game(zombie_count=[[1, 10]], max_alive=3)
    go_live(game)
    play(game, 1.0)
    assert len(game.round.enemies) == 3 and game.round.to_spawn == 7


def test_later_rounds_have_tougher_enemies():
    game = zombie_game()
    go_live(game)
    play(game, 0.3)
    assert {e.health for e in game.round.enemies.values()} == {50}
    for enemy in list(game.round.enemies.values()):
        game.round.hurt_target(("z", enemy.ident), 1000, 0, None)
    play(game, 2.0, until=lambda: game.round.number == 2 and game.round.phase == "live" and game.round.enemies)
    assert {e.health for e in game.round.enemies.values()} == {100}


def test_killing_every_enemy_ends_the_round_and_brings_the_out_players_back():
    game = zombie_game(players=(0, 1, 2), bleed_out=0.1)
    go_live(game)
    play(game, 0.3)
    game.hurt(1, 1000)
    game.hurt(2, 1000)
    play(game, 0.2)                                         # 1 and 2 bleed out
    assert not game.players[1].alive and game.round.phase == "live"
    for enemy in list(game.round.enemies.values()):
        game.round.hurt_target(("z", enemy.ident), 1000, 0, None)
    play(game, DT * 2)
    assert game.round.phase == "intermission" and game.players[1].alive and game.players[2].alive
    assert game.players[1].stats.health == game.players[1].stats.max_health
    assert "Round 1 survived" in game.round.message


def test_hits_and_kills_pay():
    game = zombie_game(enemies=[Enemy(health=30, hit_reward=10, kill_reward=60)])
    go_live(game)
    play(game, 0.3)
    enemy = next(iter(game.round.enemies.values()))
    game.round.hurt_target(("z", enemy.ident), 10, 0, None)
    assert game.players[0].stats.money == 10
    game.round.hurt_target(("z", enemy.ident), 25, 0, None)
    assert game.players[0].stats.money == 70 and enemy.ident not in game.round.enemies


def test_a_shot_enemy_dies():
    game = zombie_game(enemies=[Enemy(health=10, speed=0.1)], zombie_count=[[1, 1]])
    go_live(game)
    play(game, 0.2)
    enemy = next(iter(game.round.enemies.values()))
    me = game.players[0].body
    place(me, 10.5, 5.5)
    me.angle = math.atan2(enemy.body.y - me.y, enemy.body.x - me.x)
    me.pitch = math.atan2(enemy.body.z + 0.4 - me.eye_z, math.hypot(enemy.body.x - me.x, enemy.body.y - me.y))
    from mapfile import Gun
    game.projectiles.fire(me, Gun(spread=0.0, damage=50), owner=0)
    play(game, 1.0)
    assert enemy.ident not in game.round.enemies


# ------------------------------------------------------------------ chasing and attacking

def test_an_enemy_walks_round_a_wall_to_the_player_and_hurts_them():
    level_walls = [(10, y) for y in range(1, 9)]            # a wall with a gap at the bottom
    game = zombie_game(zombie_count=[[1, 1]])
    for x, y in level_walls:
        game.level.set("walls", x, y, 1)
    game.world = World(game.level, 32)
    game.round = ZombieRound(game)
    go_live(game)
    me = game.players[0]
    place(me.body, 3.5, 3.5)
    health = me.stats.health
    assert play(game, 15.0, until=lambda: me.stats.health < health)
    assert me.stats.health == health - 20


def test_an_attack_misses_a_player_who_gets_away_during_the_windup():
    game = zombie_game(enemies=[Enemy(speed=0.1, attacks=[Attack(damage=20, windup=0.5, range=0.5)])],
                       zombie_count=[[1, 1]])
    go_live(game)
    play(game, 0.2)
    enemy = next(iter(game.round.enemies.values()))
    me = game.players[0]
    place(me.body, enemy.body.x - 0.6, enemy.body.y)
    play(game, 0.1)
    assert enemy.attack is not None
    place(me.body, 2.5, 2.5)                                # out of reach before it lands
    play(game, 0.6)
    assert me.stats.health == me.stats.max_health


def test_sticky_pathing_keeps_its_target_until_another_is_clearly_nearer():
    game = zombie_game(players=(0, 1), enemies=[Enemy(speed=0.1, switch_margin=3.0, switch_delay=1.0)],
                       zombie_count=[[1, 1]])
    go_live(game)
    play(game, 0.3)
    enemy = next(iter(game.round.enemies.values()))
    a, b = game.players[0].body, game.players[1].body
    place(a, enemy.body.x - 6, enemy.body.y)
    place(b, enemy.body.x - 8, enemy.body.y)
    play(game, 0.5)
    assert enemy.target == 0
    place(b, enemy.body.x - 5, enemy.body.y)                # nearer, but not by more than the margin
    play(game, 2.0)
    assert enemy.target == 0
    place(b, enemy.body.x - 1.5, enemy.body.y)              # clearly nearer: switches after the delay
    play(game, 0.5)
    assert enemy.target == 0
    play(game, 1.0)
    assert enemy.target == 1


def test_nearest_pathing_switches_at_once():
    game = zombie_game(players=(0, 1), enemies=[Enemy(speed=0.1, pathing="nearest")], zombie_count=[[1, 1]])
    go_live(game)
    play(game, 0.3)
    enemy = next(iter(game.round.enemies.values()))
    place(game.players[0].body, enemy.body.x - 6, enemy.body.y)
    place(game.players[1].body, enemy.body.x - 8, enemy.body.y)
    play(game, 0.5)
    assert enemy.target == 0
    place(game.players[1].body, enemy.body.x - 5, enemy.body.y)
    play(game, 0.5)
    assert enemy.target == 1


def test_enemies_spread_out_instead_of_piling_up():
    game = zombie_game(enemies=[Enemy(speed=0.1)], zombie_count=[[1, 4]], spawn_interval=0.0)
    go_live(game)
    play(game, 1.0)
    bodies = [e.body for e in game.round.enemies.values()]
    assert len(bodies) == 4
    assert min(math.hypot(a.x - b.x, a.y - b.y) for i, a in enumerate(bodies) for b in bodies[i + 1:]) > 0.3


# ------------------------------------------------------------------ the game ending

def test_everyone_out_is_game_over_then_a_new_game():
    game = zombie_game(players=(0, 1), start_money=500)
    go_live(game)
    game.players[0].stats.money = 2000
    game.hurt(0, 1000)
    game.hurt(1, 1000)
    assert game.round.phase == "over" and "Game over" in game.round.message
    play(game, 1.1)
    assert game.round.phase == "intermission" and game.round.number == 0 and not game.round.enemies
    assert all(s.alive for s in game.players.values()) and game.players[0].stats.money == 500


def test_a_map_without_enemy_spawn_points_says_so():
    game = zombie_game(spawners=())
    play(game, 1.0)
    assert game.round.phase == "intermission" and "no enemy spawn points" in game.round.message


def test_a_map_without_enemy_kinds_sends_plain_zombies():
    game = zombie_game(enemies=[])
    go_live(game)
    play(game, 0.3)
    assert game.round.enemies


# ------------------------------------------------------------------ going down and reviving

def down(game, pid):
    game.hurt(pid, 10000)
    assert pid in game.round.downed and game.players[pid].alive


def test_a_player_with_a_teammate_standing_goes_down_instead_of_out():
    game = zombie_game(players=(0, 1))
    go_live(game)
    down(game, 1)
    assert game.round.phase == "live"
    assert game.round.view().downed[1][0] == game.level.settings.bleed_out


def test_alone_going_down_is_game_over():
    game = zombie_game()
    go_live(game)
    game.hurt(0, 10000)
    assert game.round.phase == "over" and not game.round.downed


def test_nobody_left_standing_is_game_over():
    game = zombie_game(players=(0, 1))
    go_live(game)
    down(game, 1)
    game.hurt(0, 10000)
    assert game.round.phase == "over"


def test_a_downed_player_crawls_crouched_and_may_shoot():
    game = zombie_game(players=(0, 1), downed_speed=0.6)
    go_live(game)
    down(game, 1)
    body = game.players[1].body
    place(body, 5.5, 5.5)
    body.angle = 0.0
    play(game, 1.0, {1: Inputs(forward=1, sprint=True, jump=True, fire=True)})
    assert body.crouched and body.on_ground
    assert body.x - 5.5 == pytest.approx(0.6, abs=0.05)
    assert game.round.act(1, Inputs(fire=True, use=True), DT).fire
    assert not game.round.act(1, Inputs(use=True), DT).use


def test_a_downed_player_may_not_shoot_on_maps_that_say_so():
    game = zombie_game(players=(0, 1), downed_can_shoot=False)
    go_live(game)
    down(game, 1)
    assert not game.round.act(1, Inputs(fire=True), DT).fire


def test_bleeding_out():
    game = zombie_game(players=(0, 1), bleed_out=1.0)
    go_live(game)
    down(game, 1)
    play(game, 1.1)
    assert not game.players[1].alive and 1 not in game.round.downed and game.round.phase == "live"


def test_a_revive_takes_holding_e_beside_them_and_pays():
    game = zombie_game(players=(0, 1), revive_time=1.0, revive_reward=100, revive_health=40)
    go_live(game)
    down(game, 1)
    place(game.players[1].body, 5.5, 5.5)
    place(game.players[0].body, 6.2, 5.5)
    play(game, 0.5, {0: Inputs(use=True, fire=True)})
    assert game.round.view().revives[1][0] == 0 and 1 in game.round.downed
    assert not game.round.act(0, Inputs(use=True, fire=True), DT).fire        # (no shooting while reviving)
    play(game, 0.6, {0: Inputs(use=True)})
    assert 1 not in game.round.downed
    assert game.players[1].stats.health == 40 and game.players[0].stats.money == 100


def test_letting_go_or_walking_away_starts_the_revive_over():
    game = zombie_game(players=(0, 1), revive_time=1.0)
    go_live(game)
    down(game, 1)
    place(game.players[1].body, 5.5, 5.5)
    place(game.players[0].body, 6.2, 5.5)
    play(game, 0.6, {0: Inputs(use=True)})
    play(game, DT, {0: Inputs()})
    assert 1 not in game.round.revives
    play(game, 0.6, {0: Inputs(use=True)})
    place(game.players[0].body, 9.5, 5.5)                   # too far now
    play(game, 0.6, {0: Inputs(use=True)})
    assert 1 in game.round.downed and 1 not in game.round.revives


def test_enemies_leave_the_downed_alone_and_spare_the_just_revived():
    game = zombie_game(players=(0, 1), enemies=[Enemy(speed=0.1, attacks=[Attack(damage=10, windup=0.0,
                                                                                    cooldown=0.1)])],
                       zombie_count=[[1, 1]], revive_grace=1.0)
    go_live(game)
    play(game, 0.3)
    enemy = next(iter(game.round.enemies.values()))
    place(game.players[0].body, 2.5, 9.5)
    victim = game.players[1]
    place(victim.body, enemy.body.x - 0.6, enemy.body.y)
    down(game, 1)
    play(game, 1.0)
    assert victim.stats.health == 0 and enemy.target == 0  # (left alone, chasing the one standing)
    game.round.revive(1)
    place(victim.body, enemy.body.x - 0.6, enemy.body.y)
    health = victim.stats.health
    play(game, 0.5)
    assert victim.stats.health == health                    # in its grace
    play(game, 1.5)
    assert victim.stats.health < health


def test_the_downed_get_up_when_the_round_is_won():
    game = zombie_game(players=(0, 1))
    go_live(game)
    play(game, 0.3)
    down(game, 1)
    for enemy in list(game.round.enemies.values()):
        game.round.hurt_target(("z", enemy.ident), 1000, 0, None)
    play(game, DT * 2)
    assert not game.round.downed and game.players[1].stats.health == game.level.settings.revive_health


def test_players_out_keep_their_guns_if_the_map_says_so():
    from mapfile import Gun
    for keep in (False, True):
        game = zombie_game(players=(0, 1, 2), bleed_out=0.1, keep_guns=keep)
        game.level.guns = [Gun(name="Rifle")]
        go_live(game)
        game.players[1].inventory.give_gun(game.level.guns[0])
        down(game, 1)
        play(game, 0.2)
        game.round.end_round()
        assert bool(game.players[1].inventory.guns) == keep


# ------------------------------------------------------------------ barricades

WINDOW = (12, 5)


def barricade_game(players=(0,), boards=3, **kwargs):
    """The zombie room cut in two by a wall at x = 12 with one boarded window at WINDOW: players on the left,
    enemies coming in on the right."""
    from mapfile import Barricade
    level = zombie_level(**kwargs)
    for y in range(1, 11):
        if (12, y) != WINDOW:
            level.set("walls", 12, y, 1)
    level.barricades = [Barricade(*WINDOW, boards=boards, repair_time=0.5, reward=10, reward_cap=25)]
    game = Game(level, World(level, 32), random.Random(1), character_tile=FIRST_CHARACTER)
    for pid in players:
        game.add_player(pid)
    return game


def test_barricades_are_saved_and_loaded():
    from mapfile import Barricade
    level = zombie_level()
    level.barricades = [Barricade(3, 4, boards=4, reward_kind="score", tile=7)]
    again = parse_level(json.loads(level_text(level)))
    assert again.barricades == level.barricades and again.barricade_at(3, 4) == 0
    data = json.loads(level_text(level))
    data["barricades"] += [{"x": 3, "y": 4}, {"x": 99, "y": 1}, {"y": 2}, {"x": 5, "y": 5, "boards": 500,
                                                                       "reward_kind": "gold", "repair_time": "x"}]
    again = parse_level(data)
    assert [(b.x, b.y) for b in again.barricades] == [(3, 4), (5, 5)]
    assert again.barricades[1].boards == 20 and again.barricades[1].reward_kind == "money"
    assert again.barricades[1].repair_time == Barricade().repair_time
    assert '"barricades"' not in level_text(Level.blank(5, 5))


def test_a_barricade_stops_players_always_and_enemies_while_it_has_boards():
    game = barricade_game()
    world = game.world
    x, y = WINDOW
    assert world.span_at(x + 0.5, y + 0.5, 0.0) == -1                       # players
    assert world.for_enemies().span_at(x + 0.5, y + 0.5, 0.0) == -1         # enemies, boarded
    assert world.pane_tex[y, x] == 2 and world.pane_top[y, x] == pytest.approx(1.0)
    game.round.boards[0] = 1
    from zombies import apply_boards
    apply_boards(world, game.level, game.round.boards)
    assert world.pane_top[y, x] == pytest.approx(1 / 3)                     # a third of the boards left
    game.round.boards[0] = 0
    apply_boards(world, game.level, game.round.boards)
    assert world.for_enemies().span_at(x + 0.5, y + 0.5, 0.0) == 0          # open to enemies
    assert world.span_at(x + 0.5, y + 0.5, 0.0) == -1                       # never to players
    assert world.pane_tex[y, x] == -1


def test_enemies_tear_the_boards_off_and_come_through():
    game = barricade_game(enemies=[Enemy(speed=3.0, break_rate=0.5, attacks=[Attack(damage=10)])],
                          zombie_count=[[1, 1]])
    me = game.players[0]
    place(me.body, 3.5, 5.5)
    go_live(game)
    assert play(game, 10.0, until=lambda: game.round.boards[0] < 3)
    enemy = next(iter(game.round.enemies.values()))
    assert enemy.body.x > 12.5                                              # still outside, at the window
    assert play(game, 3.0, until=lambda: game.round.boards[0] == 0)
    health = me.stats.health
    assert play(game, 10.0, until=lambda: me.stats.health < health)         # through, and at the player
    assert enemy.body.x < 12.0


def test_enemies_go_round_by_a_door_when_that_is_shorter_than_breaking_in():
    game = barricade_game(enemies=[Enemy(speed=3.0)], zombie_count=[[1, 1]])
    game.level.set("walls", 12, 6, 0)                                       # an open doorway beside the window
    game.world = World(game.level, 32)
    game.round = ZombieRound(game)
    place(game.players[0].body, 3.5, 6.5)
    go_live(game)
    assert play(game, 10.0, until=lambda: any(e.body.x < 12 for e in game.round.enemies.values()))
    assert game.round.boards[0] == 3


def test_holding_e_beside_a_barricade_rebuilds_it_for_a_capped_reward():
    game = barricade_game(spawners=())
    game.round.start_round()                                # (a round with nobody coming: the cap is per round)
    game.round.boards[0] = 0
    me = game.players[0]
    place(me.body, 11.5, 5.5)
    play(game, 0.1, {0: Inputs(use=True)})
    assert game.round.view().repairs[0][0] == 0
    assert not game.round.act(0, Inputs(use=True, fire=True), DT).fire      # (hands busy)
    play(game, 0.5, {0: Inputs(use=True)})
    assert game.round.boards[0] == 1 and me.stats.money == 10
    play(game, 2.0, {0: Inputs(use=True)})
    assert game.round.boards[0] == 3                                        # whole: no more
    assert me.stats.money == 25                                             # 10 + 10 + 5: the cap
    assert 0 not in game.round.repairs


def test_rebuilding_pays_again_next_round_and_letting_go_starts_the_board_over():
    game = barricade_game(spawners=())
    game.round.start_round()
    game.round.boards[0] = 0
    me = game.players[0]
    place(me.body, 11.5, 5.5)
    game.round.repaid[0] = 25
    play(game, 0.6, {0: Inputs(use=True)})
    assert game.round.boards[0] == 1 and me.stats.money == 0                # capped this round
    game.round.start_round()
    play(game, 0.3, {0: Inputs(use=True)})
    play(game, DT, {0: Inputs()})
    play(game, 0.3, {0: Inputs(use=True)})
    assert game.round.boards[0] == 1                                        # (let go halfway: started over)
    play(game, 0.3, {0: Inputs(use=True)})
    assert game.round.boards[0] == 2 and me.stats.money == 10


def test_a_new_game_puts_every_board_back():
    game = barricade_game()
    game.round.boards[0] = 0
    from zombies import apply_boards
    apply_boards(game.world, game.level, game.round.boards)
    game.round.new_game()
    assert game.round.boards == [3] and game.world.pane_tex[WINDOW[1], WINDOW[0]] == 2


def test_a_joiners_world_shows_the_boards_the_host_says_are_left():
    game = barricade_game()
    host = HostSession(game, net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
    x, y = WINDOW
    try:
        run([host, client], lambda: client.ready and isinstance(client.round, ZombieView))
        assert client.world.for_enemies().span_at(x + 0.5, y + 0.5, 0.0) == -1
        game.round.boards[0] = 0
        run([host, client], lambda: client.round.boards == [0])
        assert client.world.for_enemies().span_at(x + 0.5, y + 0.5, 0.0) == 0
        assert client.world.span_at(x + 0.5, y + 0.5, 0.0) == -1 and client.world.pane_tex[y, x] == -1
    finally:
        client.close()
        host.close()


# ------------------------------------------------------------------ what players see

def test_enemies_are_drawn_tinted_and_as_tall_as_their_kind():
    game = zombie_game(enemies=[Enemy(height=1.2, color=[255, 255, 255]), Enemy(name="B", color=[100, 200, 50])])
    go_live(game)
    play(game, 0.3)
    sprites = [s for s in game.sprites(0) if s[4] >= FIRST_CHARACTER]
    assert len(sprites) == 2
    for sprite in sprites:
        assert sprite[3] in (1.2, 0.8)
        assert (sprite[4] - FIRST_CHARACTER) // 16 == SHIRT
        assert (len(sprite) == 5) == (sprite[3] == 1.2)     # white: drawn as it is; else tinted


def test_the_view_goes_over_the_network_and_back():
    view = ZombieView({0, 2}, {}, 3, "live", 0.0, 12, "Round 3", 1.5, [(0, 1.5, 2.5, 0.0, 0.5, 0.25)],
                      downed={2: (12.5, 3.5, 4.5, 0.0, "Sam")}, revives={2: (0, 1.25)}, boards=[3, 0],
                      repairs={0: (1, 0.5)}, crawl=0.8)
    again = ZombieView.from_dict(json.loads(json.dumps(view.to_dict())))
    assert again == view
    assert ZombieView.from_dict({"mode": "zombies", "enemies": [[1, 2]]}) is None


def test_a_joiner_sees_the_round_and_the_enemies():
    level = zombie_level()
    host = HostSession(Game(level, World(level, 32), random.Random(1), character_tile=FIRST_CHARACTER),
                       net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
    try:
        run([host, client], lambda: client.ready and isinstance(client.round, ZombieView)
            and client.round.phase == "live" and len(client.round.enemies) == 2, timeout=6.0)
        assert client.round.number == 1
        drawn = enemy_sprites(client.level, client.round.enemies, FIRST_CHARACTER, 0.0)
        assert len(drawn) == 2 and all(s in client.sprites() for s in drawn)
    finally:
        client.close()
        host.close()


# ------------------------------------------------------------------ the editor

@pytest.fixture
def ed(tmp_path):
    import map_editor
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(10, 10)
    editor.show_legend = False
    editor.draw(pygame.display.get_surface())
    return editor


def click(ed, pos):
    ed.on_mouse_down(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    ed.on_mouse_up(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))


def test_choosing_zombies_adds_a_zombie_and_lists_the_enemies(ed):
    import map_editor
    ed.do("mapsettings")
    assert ed.enemy_rows() == ([], None)                    # (not in the other modes)
    ed.set_rule("mode", "zombies")
    assert [e.name for e in ed.level.enemies] == ["Zombie"]
    keys = [r.field.key for r in ed.details_rows()]
    assert "max_alive" in keys and "zombie_count_note" in keys
    rows, add = ed.enemy_rows()
    assert len(rows) == 1
    click(ed, add.center)
    assert [e.name for e in ed.level.enemies] == ["Zombie", "Zombie 2"]
    assert ed.selected_enemy() is ed.level.enemies[1]
    ed.draw(pygame.display.get_surface())
    rules, buy, _rows, _add = ed.settings_rows()
    assert buy.top > ed.enemy_rows()[1].bottom              # the buy menu comes after the enemies
    click(ed, ed.enemy_rows()[0][0][0].center)
    assert ed.settings_selected == map_editor.ENEMY_ROW


def test_editing_an_enemy_and_its_attacks(ed):
    ed.do("mapsettings")
    ed.set_rule("mode", "zombies")
    ed.add_enemy()
    enemy = ed.selected_enemy()
    ed.set_enemy("name", "Zombie")                          # (taken: it stays unique)
    assert enemy.name == "Zombie 2"
    ed.set_enemy("name", "Brute")
    assert enemy.name == "Brute"
    ed.set_enemy("speed", 4.0)
    ed.set_enemy_color(0, 300)
    ed.add_attack()
    ed.set_attack(1, "damage", 70)
    keys = [r.field.key for r in ed.details_rows()]
    assert {"switch_margin", "a1_damage", "color2", "add_attack"} <= set(keys)
    assert enemy.speed == 4.0 and enemy.color[0] == 255 and enemy.attacks[1].damage == 70
    ed.set_enemy("pathing", "nearest")
    assert "switch_margin" not in [r.field.key for r in ed.details_rows()]
    ed.remove_attack(0)
    assert [a.damage for a in enemy.attacks] == [70]
    ed.draw(pygame.display.get_surface())
    ed.do("undo")
    assert len(ed.level.enemies[1].attacks) == 2
    import map_editor
    ed.settings_selected = map_editor.ENEMY_ROW - 1
    assert ed.details_delete_label() == "Delete enemy"
    ed.delete_selected()
    assert [e.name for e in ed.level.enemies] == ["Zombie"]


def test_spawn_points_can_be_for_enemies(ed):
    for _ in range(3):
        ed.do("spawn_team")
    assert ed.spawn_team == ENEMY_SPAWN and ed.spawn_team_label(ed.spawn_team) == "Enemies"
    ed.do("spawn_team")
    assert ed.spawn_team == 0


def test_a_downed_joiner_crawls_on_its_own_screen_as_on_the_host():
    level = zombie_level(downed_speed=0.6)
    host = HostSession(Game(level, World(level, 32), random.Random(1), character_tile=FIRST_CHARACTER),
                       net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
    try:
        run([host, client], lambda: client.ready and isinstance(client.round, ZombieView))
        host.game.hurt(client.id, 10000)
        run([host, client], lambda: client.id in client.round.downed)
        place(host.game.players[client.id].body, 5.5, 5.5)
        run([host, client], lambda: abs(client.me.body.x - 5.5) < 0.01)
        client.me.body.angle = host.game.players[client.id].body.angle = 0.0
        start = client.me.body.x
        for _ in range(30):
            client.step(Inputs(forward=1, sprint=True), DT)
        assert client.me.body.x - start == pytest.approx(0.3, abs=0.05)     # crawling, ahead of the host
        run([host, client], lambda: abs(host.game.players[client.id].body.x - client.me.body.x) < 0.02)
    finally:
        client.close()
        host.close()


class Lens:
    """A renderer that only projects (what draw_downed asks of it): everything ahead lands mid-picture."""

    def project(self, camera, x, y, z):
        ahead = (x - camera.x) * math.cos(camera.angle) + (y - camera.y) * math.sin(camera.angle)
        return (320.0, 180.0, ahead) if ahead > 0.1 else None


def test_the_downed_hud_draws_for_everyone():
    from hud import draw_downed
    game = zombie_game(players=(0, 1, 2))
    go_live(game)
    down(game, 1)
    place(game.players[1].body, 5.5, 5.5)
    place(game.players[0].body, 6.0, 5.5)
    place(game.players[2].body, 9.5, 5.5)
    game.players[2].body.angle = 0.0                        # (facing away: the marker goes to the edge)
    picture = pygame.Surface((640, 360))
    font, big = pygame.font.Font(None, 22), pygame.font.Font(None, 30)
    for pid in (0, 1, 2):
        draw_downed(picture, font, big, Lens(), game.players[pid].body, game.round.view(), pid, game.players[pid],
                    game.level)
    play(game, 0.2, {0: Inputs(use=True)})
    for pid in (0, 1):
        draw_downed(picture, font, big, Lens(), game.players[pid].body, game.round.view(), pid, game.players[pid],
                    game.level)


def test_the_barricade_tool_boards_up_gaps_and_edits_them(ed):
    from mapfile import Barricade
    ed.level.set("walls", 4, 4, 1)
    ed.do("tool:barricade")
    ed.map_click((4, 4), 1)
    assert ed.level.barricades == [] and "open cell" in ed.message
    ed.map_click((5, 4), 1)
    assert ed.level.barricades == [Barricade(5, 4)] and ed.selected_barricade() is ed.level.barricades[0]
    keys = [r.field.key for r in ed.details_rows()]
    assert {"boards", "repair_time", "reward", "reward_cap", "reward_kind", "tile"} <= set(keys)
    ed.set_barricade("boards", 9.4)
    assert ed.level.barricades[0].boards == 9
    ed.draw(pygame.display.get_surface())
    ed.do("undo")
    assert ed.level.barricades[0].boards == 6
    ed.map_click((5, 4), 3)
    assert ed.level.barricades == []
    ed.do("undo")
    ed.map_click((5, 4), 1)
    assert ed.details_delete_label() == "Delete barricade"
    ed.delete_selected()
    assert ed.level.barricades == []


def test_barricades_move_with_the_map_and_are_copied_with_an_area():
    from mapfile import Barricade, copy_area, paste_area
    level = Level.blank(10, 10)
    level.barricades = [Barricade(3, 3)]
    level.resize_edges(left=2, top=1)
    assert (level.barricades[0].x, level.barricades[0].y) == (5, 4)
    area = copy_area(level, (4, 3), (6, 5), 0)
    paste_area(level, area, 7, 6, 0)
    assert sorted((b.x, b.y) for b in level.barricades) == [(5, 4), (8, 7)]
    level.resize(6, 6)
    assert [(b.x, b.y) for b in level.barricades] == [(5, 4)]


def test_a_barricade_with_stages_shows_the_one_for_how_torn_down_it_is():
    from mapfile import Barricade
    from zombies import apply_boards
    b = Barricade(0, 0, boards=6, stages=[40, 41, 42])
    assert [b.stage_tile(left) for left in (6, 5, 4, 3, 2, 1)] == [40, 40, 41, 41, 42, 42]
    assert Barricade(0, 0, boards=4, stages=[7]).stage_tile(1) == 7
    assert Barricade(0, 0, boards=2, stages=[1, 2, 3, 4]).stage_tile(1) == 3     # (more stages than boards)
    assert Barricade(0, 0, tile=9).stage_tile(3) == 9                           # no stages: its tile
    game = barricade_game(boards=3)
    game.level.barricades[0].stages = [3, 4, 5]
    world, (x, y) = game.world, WINDOW
    world.extras.clear()
    for left, tile in ((3, 3), (2, 4), (1, 5)):
        game.round.boards[0] = left
        apply_boards(world, game.level, game.round.boards)
        assert world.pane_tex[y, x] == tile and world.pane_top[y, x] == pytest.approx(1.0)   # (filling it)
        assert world.for_enemies().span_at(x + 0.5, y + 0.5, 0.0) == -1                       # still closed
    game.round.boards[0] = 0
    apply_boards(world, game.level, game.round.boards)
    assert world.pane_tex[y, x] == -1 and world.for_enemies().span_at(x + 0.5, y + 0.5, 0.0) == 0


def test_stages_are_saved_and_kept_apart_in_copies():
    from mapfile import Barricade
    level = zombie_level()
    level.barricades = [Barricade(3, 4, stages=[8, 9])]
    again = parse_level(json.loads(level_text(level)))
    assert again.barricades[0].stages == [8, 9]
    copy = level.copy()
    copy.barricades[0].stages.append(10)
    assert level.barricades[0].stages == [8, 9]
    data = json.loads(level_text(level))
    data["barricades"][0]["stages"] = [1, "x", 999, True] + [2] * 20
    assert parse_level(data).barricades[0].stages == [1, 255] + [2] * 10


def test_the_editor_adds_stages_and_atlas_clicks_set_them(ed):
    ed.do("tool:barricade")
    ed.map_click((5, 4), 1)
    barricade = ed.selected_barricade()
    ed.add_barricade_stage()
    ed.add_barricade_stage()
    assert barricade.stages == [barricade.tile, barricade.tile] and ed.tile_target == "stage1"
    keys = [r.field.key for r in ed.details_rows()]
    assert {"stage0", "stage1", "add_stage", "remove_stage"} <= set(keys) and "tile" not in keys
    ed.set_barricade_stage(1, 33)
    ed.tile_target = "stage0"
    ed.set_barricade_stage(0, 31)
    assert barricade.stages == [31, 33]
    ed.draw(pygame.display.get_surface())
    ed.remove_barricade_stage()
    assert barricade.stages == [31]
    ed.do("undo")
    assert ed.level.barricades[0].stages == [31, 33]


# ------------------------------------------------------------------ saved barricade types

def test_barricade_types_are_saved_and_barricades_take_their_settings():
    from mapfile import Barricade, BarricadeKind
    level = Level.blank(10, 10)
    level.barricade_kinds = [BarricadeKind("Steel", boards=10, reward=25, stages=[5, 6])]
    level.barricades = [Barricade(3, 3, kind="Steel"), Barricade(4, 4, boards=2), Barricade(5, 5, kind="Gone")]
    level.apply_barricade_kinds()
    assert (level.barricades[0].boards, level.barricades[0].reward, level.barricades[0].stages) == (10, 25, [5, 6])
    assert level.barricades[1].boards == 2 and level.barricades[2].kind == ""      # (no such type: detached)
    level.barricades[0].stages.append(9)
    assert level.barricade_kinds[0].stages == [5, 6]                                # (copies, not shared)
    again = parse_level(json.loads(level_text(level)))
    assert again.barricade_kinds == level.barricade_kinds
    assert again.barricades[0].kind == "Steel" and again.barricades[0].stages == [5, 6]
    assert '"barricade_kinds"' not in level_text(Level.blank(5, 5))


def test_saving_a_barricade_as_a_type_and_placing_more_of_it(ed):
    ed.do("tool:barricade")
    assert ed.barricade_palette_active()
    assert [r.field.key for r in ed.details_rows()][:2] == ["palette", "pick_plain"]
    ed.map_click((5, 4), 1)
    ed.set_barricade("boards", 9)
    ed.add_barricade_stage()
    ed.set_barricade_stage(0, 40)
    ed.save_barricade_kind()
    kind = ed.level.barricade_kinds[0]
    assert kind.name == "Barricade" and kind.boards == 9 and kind.stages == [40]
    assert ed.level.barricades[0].kind == "Barricade" and ed.place_barricade_kind == "Barricade"
    ed.deselect()
    ed.map_click((5, 6), 1)                                 # placed from the type
    second = ed.level.barricades[1]
    assert second.kind == "Barricade" and second.boards == 9 and second.stages == [40]
    ed.set_barricade("reward", 50)                          # changes the type: both follow
    ed.set_barricade_stage(0, 41)
    assert kind.reward == 50 and [b.reward for b in ed.level.barricades] == [50, 50]
    assert [b.stages for b in ed.level.barricades] == [[41], [41]]
    ed.draw(pygame.display.get_surface())
    ed.do("undo")
    assert [b.stages for b in ed.level.barricades] == [[40], [40]]


def test_renaming_detaching_and_deleting_a_type(ed):
    from mapfile import Barricade, BarricadeKind
    ed.level.barricade_kinds = [BarricadeKind("Wood", boards=4), BarricadeKind("Steel", boards=8)]
    ed.level.barricades = [Barricade(2, 2, kind="Wood"), Barricade(3, 3, kind="Wood"), Barricade(4, 4)]
    ed.level.apply_barricade_kinds()
    ed.do("tool:barricade")
    ed.place_barricade_kind = "Wood"
    ed.map_click((2, 2), 1)
    ed.rename_barricade_kind("Steel")                       # (taken: kept unique)
    assert ed.level.barricade_kinds[0].name == "Steel 2"
    ed.rename_barricade_kind("Planks")
    assert [b.kind for b in ed.level.barricades] == ["Planks", "Planks", ""] and ed.place_barricade_kind == "Planks"
    ed.set_barricade_kind("")                               # detach this one: it keeps the settings
    assert ed.level.barricades[0].kind == "" and ed.level.barricades[0].boards == 4
    ed.set_barricade_kind("Steel")
    assert ed.level.barricades[0].boards == 8
    ed.map_click((3, 3), 1)
    ed.delete_barricade_kind()
    assert [k.name for k in ed.level.barricade_kinds] == ["Steel"]
    assert ed.level.barricades[1].kind == "" and ed.level.barricades[1].boards == 4
    assert ed.place_barricade_kind == ""


def test_barricade_types_can_be_imported_from_another_map():
    from mapfile import Barricade, BarricadeKind, import_things
    source = Level.blank(8, 8)
    source.barricade_kinds = [BarricadeKind("Steel", boards=8, stages=[3, 4])]
    level = Level.blank(8, 8)
    level.barricade_kinds = [BarricadeKind("Steel", boards=2)]
    level.barricades = [Barricade(2, 2, kind="Steel")]
    level.apply_barricade_kinds()
    import_things(level, source, {("barricade_kinds", "Steel")}, taken="replace")
    assert level.barricade_kinds[0].stages == [3, 4] and level.barricades[0].boards == 8   # (they follow the type)
    source.barricade_kinds[0].stages.append(5)
    assert level.barricade_kinds[0].stages == [3, 4]


def test_the_import_dialog_lists_and_pictures_barricade_types(ed):
    import map_editor
    from mapfile import BarricadeKind
    dialog = map_editor.ImportDialog("", [], ed.level, ed.font, ed.small, ed.tiles)
    dialog.source = Level.blank(6, 6)
    dialog.source.barricade_kinds = [BarricadeKind("Steel", stages=[3, 4])]
    dialog.source_name = "other"
    assert dialog.rows() == [("kind", "barricade_kinds"), ("thing", ("barricade_kinds", "Steel"))]
    assert dialog.icon("barricade_kinds", "Steel") is not None                 # (its whole stage's picture)
    dialog.draw(pygame.display.get_surface(), pygame.display.get_surface().get_size(), (0, 0))
