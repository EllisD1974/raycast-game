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
                      {2: (12.5, 3.5, 4.5, 0.0, "Sam")}, {2: (0, 1.25)}, 0.8)
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
