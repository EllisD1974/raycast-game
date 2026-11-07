"""Bomb defusal: rounds, the bomb, planting and defusing, the timers, the score and money, and playing it through a
host (bomb.py, with game.py, session.py and the map's site layer)."""
import math
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
import net
from bomb import BOMB_TILE, RoundView, bomb_damage, clock_text
from game import Game, Inputs
from mapfile import (CT_TEAM, DEFUSE_KIT, T_TEAM, BuyItem, Gun, Level, MapSettings, Spawner, level_text, load_level,
                     parse_level, save_level)
from session import ClientSession, HostSession
from test_session import FIRST_CHARACTER, make_world, run
from world import World

DT = 1 / 60
SITE = (15, 4)                          # a cell of bomb site A


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


def quick(**rules):
    """Short timers, so a round plays out in a few seconds of game time."""
    base = dict(mode="bomb", freeze_time=1.0, round_time=10.0, buy_time=2.0, bomb_time=5.0, plant_time=1.0,
                defuse_time=2.0, kit_defuse_time=1.0, round_end_time=1.0, max_rounds=24, start_money=800,
                bomb_radius=6.0, buy_menu=True, buy_cost="money",
                buy_items=[BuyItem(kind="item", item=DEFUSE_KIT, amount=1, price=400)])
    base.update(rules)
    return MapSettings(**base)


def bomb_level(**rules):
    """A 20 x 12 room: T spawn points on the left, CT on the right, bomb site A around SITE."""
    level = Level.blank(20, 12)
    for y in range(3, 6):
        for x in range(14, 17):
            level.set("site", x, y, 1)
    level.spawners = [Spawner(2.5, 6.5, team=T_TEAM), Spawner(2.5, 8.5, team=T_TEAM),
                      Spawner(17.5, 8.5, team=CT_TEAM), Spawner(17.5, 9.5, team=CT_TEAM)]
    level.guns = [Gun(name="Pistol")]
    level.settings = quick(**rules)
    return level


def bomb_game(players=(0, 1), **rules):
    level = bomb_level(**rules)
    game = Game(level, World(level, 32), random.Random(1))
    for pid in players:
        game.add_player(pid)
    return game


def play(game, seconds, inputs=None):
    """Run the game `seconds` with `inputs` {player id: Inputs} held the whole time; returns the messages each got."""
    said = {}
    for _ in range(round(seconds / DT)):
        for pid, events in game.tick(inputs or {}, DT).items():
            said.setdefault(pid, []).extend(events.picked)
    return said


def go_live(game):
    play(game, game.level.settings.freeze_time + DT)
    assert game.round.phase == "live"


def stand(game, pid, cell):
    body = game.players[pid].body
    body.x, body.y = cell[0] + 0.5, cell[1] + 0.5
    body.z, body.vz, body.on_ground = 0.0, 0.0, True


def carrier(game):
    return game.round.bomb.carrier


def plant(game):
    """The bomb carrier walks to site A and plants it."""
    go_live(game)
    pid = carrier(game)
    stand(game, pid, SITE)
    play(game, game.level.settings.plant_time + 0.1, {pid: Inputs(use=True)})
    assert game.round.phase == "planted"
    return pid


# ------------------------------------------------------------------ the settings and the map file

def test_the_defaults_are_counter_strikes():
    s = MapSettings()
    assert (s.freeze_time, s.round_time, s.buy_time, s.bomb_time) == (15.0, 115.0, 20.0, 40.0)
    assert (s.plant_time, s.defuse_time, s.kit_defuse_time, s.round_end_time) == (3.2, 10.0, 5.0, 7.0)
    assert (s.max_rounds, s.bomb_damage) == (24.0, 500.0)
    assert (s.win_money, s.bomb_win_money, s.loss_money, s.loss_bonus, s.max_loss_money) == (3250, 3500, 1400, 500, 3400)
    assert (s.plant_money, s.objective_money, s.money_cap) == (800, 300, 16000)


def test_bomb_sites_spawn_teams_and_the_settings_are_saved_with_the_map(tmp_path):
    level = bomb_level(round_time=90, bomb_effect="boom")
    path = tmp_path / "bomb.json"
    save_level(str(path), level)
    back = load_level(str(path))
    assert back.settings.mode == "bomb" and back.settings.round_time == 90 and back.settings.bomb_effect == "boom"
    assert back.get("site", 15, 4) == 1 and back.get("site", 1, 1) == 0
    assert [s.team for s in back.spawners] == [T_TEAM, T_TEAM, CT_TEAM, CT_TEAM]


def test_a_map_without_bomb_sites_writes_no_site_grid():
    assert '"site"' not in level_text(Level.blank(6, 6))
    assert '"site"' in level_text(bomb_level())


def test_settings_from_a_file_are_kept_in_range():
    s = MapSettings.from_dict({"mode": "bomb", "round_time": -5, "plant_time": "x", "max_rounds": 500})
    assert s.round_time == 10.0 and s.plant_time == 3.2 and s.max_rounds == 99.0


# ------------------------------------------------------------------ rounds

def test_teams_are_split_and_come_in_at_their_own_spawn_points():
    game = bomb_game(players=(0, 1, 2, 3))
    teams = {pid: s.team for pid, s in game.players.items()}
    assert sorted(teams.values()) == [T_TEAM, T_TEAM, CT_TEAM, CT_TEAM]
    for pid, state in game.players.items():
        assert (state.body.x < 10) == (state.team == T_TEAM)


def test_nobody_moves_during_the_freeze_time_but_everyone_can_look_around():
    game = bomb_game()
    body = game.players[0].body
    x, angle = body.x, body.angle
    play(game, 0.5, {0: Inputs(forward=1, turn=0.01)})
    assert game.round.phase == "freeze"
    assert body.x == pytest.approx(x) and body.angle != angle
    play(game, 1.0, {0: Inputs(forward=1)})
    assert game.round.phase == "live" and body.x != pytest.approx(x)


def test_one_t_gets_the_bomb_and_is_told():
    game = bomb_game()
    assert game.round.bomb.state == "carried"
    assert game.players[carrier(game)].team == T_TEAM
    said = play(game, DT)
    assert any("You have the bomb" in m for m in said[carrier(game)])


def test_the_bomb_is_only_planted_in_a_bomb_site():
    game = bomb_game()
    go_live(game)
    pid = carrier(game)
    stand(game, pid, (5, 6))
    said = play(game, 2.0, {pid: Inputs(use=True)})
    assert game.round.phase == "live" and game.round.bomb.state == "carried"
    assert any("bomb site" in m for m in said[pid])
    assert sum("bomb site" in m for m in said[pid]) == 1          # told once per press, not every step


def test_planting_takes_the_plant_time_and_the_planter_cannot_move_meanwhile():
    game = bomb_game()
    go_live(game)
    pid = carrier(game)
    stand(game, pid, SITE)
    x = game.players[pid].body.x
    money = game.players[pid].stats.money
    play(game, 0.5, {pid: Inputs(use=True, forward=1)})
    assert game.round.phase == "live" and game.round.planting[0] == pid
    assert game.players[pid].body.x == pytest.approx(x)
    play(game, 0.6, {pid: Inputs(use=True)})
    assert game.round.phase == "planted" and game.round.bomb.site == 1
    assert game.players[pid].stats.money == money + 300            # the plant bonus
    assert 4.8 < game.round.bomb.left <= 5.0                        # (planted partway into the last 0.6 s)


def test_letting_go_of_the_use_key_starts_planting_over():
    game = bomb_game()
    go_live(game)
    pid = carrier(game)
    stand(game, pid, SITE)
    play(game, 0.6, {pid: Inputs(use=True)})
    play(game, DT)
    assert game.round.planting == (None, 0.0)
    play(game, 0.6, {pid: Inputs(use=True)})
    assert game.round.phase == "live"


def test_the_bomb_explodes_the_ts_win_and_those_near_it_are_out_until_the_next_round():
    game = bomb_game()
    pid = plant(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    stand(game, ct, (SITE[0] + 1, SITE[1]))
    play(game, 5.1)
    assert game.round.bomb.state == "exploded" and game.round.score[T_TEAM] == 1
    assert game.round.phase == "over" and "Terrorists win" in game.round.message
    assert not game.players[ct].alive                               # 500 damage a cell away
    assert game.players[pid].alive is False                         # the planter stood at the bomb too
    play(game, 1.1)                                                 # the pause, then the next round
    assert game.round.phase == "freeze" and game.round.number == 2
    assert all(s.alive for s in game.players.values())


def test_the_explosion_falls_off_with_distance_and_does_not_reach_past_its_radius():
    s = MapSettings(bomb_damage=500, bomb_radius=27)
    assert bomb_damage(s, 0) == 500
    assert bomb_damage(s, 9) == pytest.approx(500 * 0.6065, rel=1e-3)        # a third of the radius
    assert bomb_damage(s, 20) < 50 and bomb_damage(s, 27) == 0.0


def test_a_ct_at_the_bomb_defuses_it_and_the_cts_win():
    game = bomb_game()
    plant(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    stand(game, ct, SITE)
    money = game.players[ct].stats.money
    play(game, 1.0, {ct: Inputs(use=True)})
    assert game.round.phase == "planted" and game.round.defusing[0] == ct
    play(game, 1.1, {ct: Inputs(use=True)})
    assert game.round.bomb.state == "defused" and game.round.score[CT_TEAM] == 1
    assert "defused" in game.round.message
    assert game.players[ct].stats.money == money + 300 + 3500       # defuse bonus and a bomb win


def test_a_defuse_kit_halves_the_defuse_time():
    game = bomb_game()
    plant(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    game.players[ct].inventory.add_item(DEFUSE_KIT)
    stand(game, ct, SITE)
    play(game, 1.1, {ct: Inputs(use=True)})
    assert game.round.bomb.state == "defused"


def test_a_ct_too_far_from_the_bomb_cannot_defuse_it():
    game = bomb_game()
    plant(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    stand(game, ct, (SITE[0] - 3, SITE[1]))
    play(game, 2.5, {ct: Inputs(use=True)})
    assert game.round.defusing == (None, 0.0) and game.round.bomb.state == "planted"


def test_eliminating_the_ts_before_the_plant_wins_it_for_the_cts():
    game = bomb_game()
    go_live(game)
    t = carrier(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    game.hurt(t, 1000, ct)
    assert game.round.phase == "over" and game.round.score[CT_TEAM] == 1
    assert "All enemies eliminated" in game.round.message
    assert game.round.bomb.state == "dropped"


def test_after_the_plant_the_cts_still_have_to_defuse_when_the_ts_are_out():
    game = bomb_game()
    t = plant(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    game.hurt(t, 1000, ct)
    assert game.round.phase == "planted"


def test_eliminating_the_cts_wins_it_for_the_ts_even_after_the_plant():
    game = bomb_game()
    t = plant(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    game.hurt(ct, 1000, t)
    assert game.round.phase == "over" and game.round.score[T_TEAM] == 1


def test_running_out_of_time_without_a_plant_wins_it_for_the_cts_and_ts_who_hid_get_nothing():
    game = bomb_game()
    t = carrier(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    t_money, ct_money = game.players[t].stats.money, game.players[ct].stats.money
    play(game, 1.0 + 10.0 + DT)
    assert game.round.phase == "over" and "Target saved" in game.round.message
    assert game.players[ct].stats.money == ct_money + 3250
    assert game.players[t].stats.money == t_money                  # alive at the time-out: no loss money


def test_the_loss_bonus_grows_with_each_round_lost_in_a_row():
    game = bomb_game()
    t = carrier(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    paid = []
    for _ in range(3):
        go_live(game)
        before = game.players[t].stats.money
        game.hurt(game.round.bomb.carrier or t, 1000, ct)
        paid.append(game.players[t].stats.money - before)
        play(game, 1.1)
    assert paid == [1400, 1900, 2400]


def test_the_carrier_drops_the_bomb_when_knocked_out_and_another_t_picks_it_up():
    game = bomb_game(players=(0, 1, 2, 3))
    go_live(game)
    first = carrier(game)
    other_t = next(p for p, s in game.players.items() if s.team == T_TEAM and p != first)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    stand(game, first, (8, 6))
    game.hurt(first, 1000, ct)
    assert game.round.bomb.state == "dropped" and game.round.bomb.x == pytest.approx(8.5)
    stand(game, ct, (8, 6))
    play(game, DT)
    assert game.round.bomb.state == "dropped"                      # a CT cannot take it
    stand(game, ct, (17, 9))
    stand(game, other_t, (8, 6))
    said = play(game, DT)
    assert game.round.bomb.state == "carried" and carrier(game) == other_t
    assert "You picked up the bomb" in said[other_t]


def test_g_drops_the_bomb_and_the_dropper_does_not_take_it_straight_back():
    game = bomb_game()
    go_live(game)
    pid = carrier(game)
    game.players[pid].body.pitch = -math.pi / 2                    # looking straight down: it lands at their feet
    play(game, DT, {pid: Inputs(drop=True)})
    assert game.round.bomb.state == "dropped"
    play(game, 0.5)
    assert game.round.bomb.state == "dropped"
    play(game, 0.6)
    assert game.round.bomb.state == "carried" and carrier(game) == pid


def thrown(pitch, angle=0.0, cell=(4, 6)):
    """Where the bomb lands when the carrier, standing in `cell`, throws it with G looking that way."""
    game = bomb_game()
    go_live(game)
    pid = carrier(game)
    stand(game, pid, cell)
    body = game.players[pid].body
    body.angle, body.pitch = angle, pitch
    play(game, DT, {pid: Inputs(drop=True)})
    bomb, start = game.round.bomb, body.x
    assert bomb.state == "dropped" and bomb.z > 0.0                # in the air, out of the hand
    stand(game, pid, (1, 1))                                       # (away, so they don't pick it back up)
    play(game, 2.0)
    assert bomb.state == "dropped" and bomb.z == 0.0 and (bomb.vx, bomb.vy, bomb.vz) == (0.0, 0.0, 0.0)
    return bomb, start


def test_g_throws_the_bomb_the_way_the_player_looks():
    level, _ = thrown(0.0)
    assert level.x > 5.0 and level.y == pytest.approx(6.5)        # ahead (+x), straight
    up, _ = thrown(math.radians(30))
    assert up.x > level.x                                          # aimed up it flies further
    down, start = thrown(math.radians(-60))
    assert start < down.x < level.x                               # aimed down it lands close
    side, _ = thrown(0.0, angle=math.pi / 2)
    assert side.x == pytest.approx(4.5) and side.y > 7.0           # the way they face


def test_a_thrown_bomb_bounces_off_a_wall_and_stays_in_the_room():
    bomb, _ = thrown(math.radians(20), cell=(18, 6))              # right at the east wall of the 20 wide room
    assert 0.0 < bomb.x < 19.0 and bomb.x < 18.9


def test_a_bomb_dropped_in_the_air_falls_to_the_floor():
    game = bomb_game()
    go_live(game)
    pid = carrier(game)
    body = game.players[pid].body
    body.z, body.vz, body.on_ground = 1.0, 0.0, False             # mid jump (or falling)
    game.round.drop(pid)
    stand(game, pid, (3, 3))                                       # (away, so they don't pick it back up)
    assert game.round.bomb.z == pytest.approx(1.0)
    game.round.update(0.1)
    assert 0.0 < game.round.bomb.z < 1.0                           # on its way down
    game.round.update(1.0)
    assert game.round.bomb.z == 0.0 and game.round.bomb.vz == 0.0  # on the floor, and it stays there
    game.round.update(0.5)
    assert game.round.bomb.z == 0.0


def test_survivors_start_the_next_round_with_their_guns_full_of_ammo():
    level = bomb_level()
    level.guns = [Gun(name="Pistol", mag_size=12, start_ammo=24, ammo="9mm"),
                  Gun(name="Smg", mag_size=30, start_ammo=60, ammo="9mm"),
                  Gun(name="Shotgun", mag_size=8, start_ammo=16, ammo="Shells")]
    level.settings.start_gun = "Pistol"
    game = Game(level, World(level, 32), random.Random(1))
    for pid in (0, 1):
        game.add_player(pid)
    inventory = game.players[0].inventory
    for name in ("Smg", "Shotgun"):
        inventory.give_gun(next(g for g in level.guns if g.name == name))
    for state in inventory.guns:
        state.mag = 1
    inventory.ammo = {"9mm": 3, "Shells": 0}
    inventory.guns[1].reload_left = 0.5
    go_live(game)
    game.round.end_round(T_TEAM, "eliminated")
    play(game, level.settings.round_end_time + DT)
    assert game.round.phase == "freeze" and game.round.number == 2
    inventory = game.players[0].inventory
    assert [(s.gun.name, s.mag) for s in inventory.guns] == [("Pistol", 12), ("Smg", 30), ("Shotgun", 8)]
    assert inventory.ammo == {"9mm": 60, "Shells": 16}         # a shared ammo type: the most any of its guns brings
    assert not inventory.guns[1].reloading


def test_buying_is_only_allowed_during_the_freeze_and_the_buy_time():
    game = bomb_game()
    assert play(game, DT, {0: Inputs(buy=(0,))})[0][-1].startswith("Bought")
    play(game, 1.0 + 2.1)
    assert play(game, DT, {0: Inputs(buy=(0,))})[0][-1] == "The buy time is over"


def test_survivors_keep_what_they_carry_and_the_out_come_back_with_only_the_start_gun():
    game = bomb_game(start_gun="Pistol")
    t = carrier(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    game.players[ct].inventory.add_item("Medal")
    go_live(game)
    game.players[t].inventory.add_item("Medal")
    game.hurt(t, 1000, ct)
    play(game, 1.1)
    assert game.round.number == 2
    assert game.players[ct].inventory.count("Medal") == 1
    assert game.players[t].inventory.count("Medal") == 0
    assert [g.gun.name for g in game.players[t].inventory.guns] == ["Pistol"]


def test_the_sides_swap_at_half_time_and_the_match_ends_on_a_majority():
    game = bomb_game(max_rounds=4)
    t = carrier(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    for _ in range(2):                                               # the CTs win the first half
        go_live(game)
        game.hurt(game.round.bomb.carrier or t, 1000, ct)
        play(game, 1.1)
    assert game.players[t].team == CT_TEAM and game.players[ct].team == T_TEAM    # swapped
    assert game.round.score == {T_TEAM: 2, CT_TEAM: 0}                             # the score went with them
    assert game.players[t].stats.money == 800                                      # money starts over
    for _ in range(1):                                               # the old CTs (now T) win once more: 3 of 4
        go_live(game)
        game.hurt(t, 1000, ct)
    assert "win the match 3-0" in game.round.message
    play(game, 1.1)
    assert game.round.score == {T_TEAM: 0, CT_TEAM: 0} and game.round.number == 1


def test_a_player_joining_mid_round_waits_for_the_next_one():
    game = bomb_game()
    go_live(game)
    game.add_player(2)
    assert not game.players[2].alive
    assert all(sprite[4] != 2 for sprite in game.player_sprites(0))
    play(game, 10.0 + 1.1)
    assert game.players[2].alive


def test_a_player_out_of_the_round_is_not_hit_moved_or_drawn():
    game = bomb_game()
    go_live(game)
    ct = next(p for p, s in game.players.items() if s.team == CT_TEAM)
    t = carrier(game)
    game.hurt(ct, 1000, t)
    body = game.players[ct].body
    x = body.x
    play(game, 0.3, {ct: Inputs(forward=1)})
    assert body.x == pytest.approx(x)
    game.hurt(ct, 50)
    assert game.players[ct].stats.health == 0.0
    assert game.labels(t) == []


def test_alone_on_one_team_a_round_is_won_by_the_bomb_or_lost_on_time():
    game = bomb_game(players=(0,))
    assert game.players[0].team == T_TEAM
    plant(game)
    stand(game, 0, (2, 8))                                       # (far enough away to live through it)
    play(game, 5.1)
    assert game.round.score[T_TEAM] == 1 and game.players[0].alive


def test_the_bomb_is_drawn_when_it_lies_on_the_ground_and_blinks_when_planted():
    game = bomb_game()
    assert not [s for s in game.sprites(0) if s[4] == BOMB_TILE]        # carried: not drawn
    plant(game)
    bombs = [s for s in game.sprites(0) if s[4] == BOMB_TILE]
    assert len(bombs) == 1 and bombs[0][:2] == pytest.approx((SITE[0] + 0.5, SITE[1] + 0.5))
    glows = {s[7] for _ in range(60) for s in (play(game, DT) and game.sprites(0)) if s[4] == BOMB_TILE}
    assert glows == {0.0, 1.0}


def test_the_round_view_goes_through_a_message_and_rejects_junk():
    game = bomb_game()
    plant(game)
    view = game.round.view()
    back = RoundView.from_dict(view.to_dict(), view.teams)
    assert back.phase == "planted" and back.bomb.state == "planted" and back.bomb.site == 1
    assert back.alive == view.alive and back.score == view.score
    assert RoundView.from_dict({"phase": "live"}) is None
    assert RoundView.from_dict({**view.to_dict(), "bomb": "nope"}) is None


def test_clock_text():
    assert clock_text(115) == "1:55" and clock_text(6.2) == "0:07" and clock_text(-1) == "0:00"


# ------------------------------------------------------------------ through a host

def test_a_joiner_sees_the_round_and_is_held_still_during_the_freeze():
    level = bomb_level(freeze_time=2.0)
    host = HostSession(Game(level, World(level, 32), random.Random(1)), net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
    try:
        run([host, client], lambda: client.ready and client.round is not None)
        assert client.round.phase == "freeze" and client.id in client.round.alive
        assert client.me.team in (T_TEAM, CT_TEAM) and client.me.alive
        x = client.me.body.x
        for _ in range(20):                                          # held still by its own prediction too
            host.step(Inputs(), DT)
            client.step(Inputs(forward=1), DT)
        assert client.me.body.x == pytest.approx(x)
        run([host, client], lambda: client.round.phase == "live", timeout=4.0)
    finally:
        client.close()
        host.close()


def test_a_joiner_out_of_the_round_can_watch_the_others():
    level = bomb_level(death_cam_who="all")                         # (the host is on the other team)
    host = HostSession(Game(level, World(level, 32), random.Random(1)), net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
    try:
        run([host, client], lambda: client.ready and client.round is not None)
        host.game.hurt(client.id, 1000, 0)
        run([host, client], lambda: client.id not in client.round.alive)
        assert not client.me.alive
        assert [pid for pid, _body, _name in client.watchable()] == [0]
        assert client.labels(hide=0) == []
    finally:
        client.close()
        host.close()


# ------------------------------------------------------------------ the editor

def test_the_sites_layer_paints_a_and_b_and_r_switches(tmp_path):
    ed = map_editor.Editor(str(tmp_path / "m.json"))
    ed.do("layer:site")
    assert ed.layer == "site" and ed.brush_value() == 1
    ed.begin_edit()
    ed.paint_at(3, 3)
    ed.do("dir")
    ed.paint_at(4, 3)
    assert ed.level.get("site", 3, 3) == 1 and ed.level.get("site", 4, 3) == 2
    ed.erase_at(3, 3)
    assert ed.level.get("site", 3, 3) == 0
    assert map_editor.LAYER_KEYS[pygame.K_9] == "site"


def test_the_spawn_tool_gives_spawn_points_a_team(tmp_path):
    ed = map_editor.Editor(str(tmp_path / "m.json"))
    ed.do("spawn_team")
    ed.place_spawner((3, 3))
    assert ed.level.spawners[-1].team == T_TEAM
    ed.do("spawn_team")
    ed.place_spawner((3, 3))                                         # clicking it again gives it the new team
    assert ed.level.spawners[-1].team == CT_TEAM


def test_the_map_settings_show_the_bomb_settings_only_in_bomb_defusal(tmp_path):
    ed = map_editor.Editor(str(tmp_path / "m.json"))
    assert "round_time" not in [f.key for f in ed.rules_fields()]
    ed.level.settings.mode = "bomb"
    keys = [f.key for f in ed.rules_fields()]
    assert {"freeze_time", "round_time", "bomb_time", "plant_time", "defuse_time", "bomb_effect"} <= set(keys)
