"""Spawn points: where players come into the game, in order."""
import json
import math
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
from game import Game, SpawnOrder
from mapfile import Level, Spawner, level_text, parse_level
from world import World


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1920, 1009), pygame.RESIZABLE)
    yield
    pygame.quit()


def arena(*spawners):
    level = Level.blank(12, 12)
    level.start_x, level.start_y = 1.5, 1.5
    level.spawners = list(spawners)
    return level


TWO_FIRST_ONE_NEXT = (Spawner(2.5, 2.5, order=0), Spawner(9.5, 9.5, order=0), Spawner(5.5, 5.5, order=1))


# ------------------------------------------------------------------ the order players come in at

def test_the_lowest_order_is_used_first_at_random_then_the_next_then_it_starts_over():
    orders_seen = set()
    for seed in range(20):
        spawns = SpawnOrder(arena(*TWO_FIRST_ONE_NEXT), random.Random(seed))
        picks = [spawns.next_index() for _ in range(6)]
        assert set(picks[:2]) == {0, 1} and picks[2] == 2               # both order 0, either way round, then order 1
        assert set(picks[3:5]) == {0, 1} and picks[5] == 2              # and over again
        orders_seen.add(tuple(picks[:2]))
    assert orders_seen == {(0, 1), (1, 0)}                              # which of the two goes first is random


def test_with_only_order_0_the_third_player_picks_from_both_again():
    spawns = SpawnOrder(arena(Spawner(2.5, 2.5), Spawner(9.5, 9.5)), random.Random(1))
    first, second, third = (spawns.next_index() for _ in range(3))
    assert {first, second} == {0, 1} and third in (0, 1)


def test_orders_need_not_be_consecutive():
    spawns = SpawnOrder(arena(Spawner(2.5, 2.5, order=5), Spawner(9.5, 9.5, order=2)), random.Random(0))
    assert [spawns.next_index() for _ in range(3)] == [1, 0, 1]


def test_players_come_in_at_the_spawners_in_order_and_come_back_at_the_next_one():
    level = arena(*TWO_FIRST_ONE_NEXT)
    level.spawners[2].angle = math.pi / 2
    game = Game(level, World(level, 16), random.Random(4))
    places = [(body.x, body.y) for body in (game.add_player(pid).body for pid in (1, 2, 3))]
    assert set(places[:2]) == {(2.5, 2.5), (9.5, 9.5)} and places[2] == (5.5, 5.5)
    assert game.players[3].body.angle == pytest.approx(math.pi / 2)    # facing the way the spawner does
    game.hurt(3, 1000.0)                                               # knocked out: in again at the next place
    assert (game.players[3].body.x, game.players[3].body.y) in ((2.5, 2.5), (9.5, 9.5))


def test_a_new_map_starts_a_new_round_of_its_spawners():
    level = arena(*TWO_FIRST_ONE_NEXT)
    game = Game(level, World(level, 16), random.Random(2))
    for pid in (1, 2, 3):
        game.add_player(pid)
    other = arena(Spawner(4.5, 4.5, order=0), Spawner(7.5, 7.5, order=1))
    game.load_level(other, World(other, 16))
    assert [(p.body.x, p.body.y) for p in game.players.values()] == [(4.5, 4.5), (7.5, 7.5), (4.5, 4.5)]


def test_a_map_without_spawners_puts_everyone_at_its_start():
    level = arena()
    game = Game(level, World(level, 16), random.Random(0))
    assert all((game.add_player(pid).body.x, game.players[pid].body.y) == (1.5, 1.5) for pid in (1, 2))


def test_a_spawner_on_an_upper_floor_puts_the_player_on_that_floor():
    level = arena()
    level.add_floor()
    level.grids["floor_h2"][6][6], level.grids["ceil_h2"][6][6] = 2.0, 3.2       # a room up there in (6, 6)
    level.grids["ceil_h"][6][6] = 1.5
    level.spawners = [Spawner(6.5, 6.5, span=1)]
    game = Game(level, World(level, 16), random.Random(0))
    body = game.add_player(1).body
    assert body.span == 1 and body.z == pytest.approx(2.0)


# ------------------------------------------------------------------ the map file

def test_spawners_are_kept_with_the_map_and_move_with_it():
    level = arena(*TWO_FIRST_ONE_NEXT)
    again = parse_level(json.loads(level_text(level)))
    assert again.spawners == list(TWO_FIRST_ONE_NEXT)
    assert '"spawners"' not in level_text(arena())                     # (a map without them saves nothing extra)
    again.resize_edges(left=2, top=1)
    assert (again.spawners[0].x, again.spawners[0].y) == (4.5, 3.5)
    again.resize_edges(right=-3)                                       # 14 wide to 11: cuts off the one at x 11.5
    assert [s.x for s in again.spawners] == [4.5, 7.5]
    assert again.copy().spawners == again.spawners and again.copy().spawners[0] is not again.spawners[0]


def test_a_spawner_in_a_wall_is_reported():
    level = arena(Spawner(0.5, 5.5))                                   # the border wall
    assert any("spawner 1" in message and "wall" in message for message in level.problems())


# ------------------------------------------------------------------ the editor

@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = arena()
    editor.show_legend = False
    editor.fit_view()
    editor.draw(pygame.display.get_surface())
    return editor


def click(ed, cell, button=1):
    pos = ed.cell_rect(*cell).center
    ed.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
    ed.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))


def key(ed, k, char=""):
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=char))


def test_the_spawn_tool_places_spawners_with_the_chosen_order(ed):
    key(ed, pygame.K_o, "o")
    assert ed.tool == "spawn"
    click(ed, (3, 3))
    ed.do("order+")
    key(ed, pygame.K_RIGHTBRACKET, "]")                                # [ and ] step the order too
    click(ed, (6, 6))
    assert ed.level.spawners == [Spawner(3.5, 3.5, 0, 0.0, 0), Spawner(6.5, 6.5, 0, 0.0, 2)]
    actions = [action for _rect, _label, action in ed.layout()]
    assert {"order-", "order+"} <= set(actions)
    ed.draw(pygame.display.get_surface())


def test_clicking_a_spawner_gives_it_the_order_then_turns_it_and_right_click_removes_it(ed):
    ed.do("tool:spawn")
    click(ed, (3, 3))
    ed.do("order+")
    click(ed, (3, 3))                                                  # takes order 1
    assert len(ed.level.spawners) == 1 and ed.level.spawners[0].order == 1 and ed.level.spawners[0].angle == 0.0
    click(ed, (3, 3))                                                  # has it already: turns
    assert ed.level.spawners[0].angle == pytest.approx(math.pi / 2)
    click(ed, (3, 3), button=3)
    assert ed.level.spawners == []
    ed.do("undo")
    assert len(ed.level.spawners) == 1


def test_a_spawner_needs_open_floor(ed):
    ed.do("tool:spawn")
    click(ed, (0, 5))                                                  # the border wall
    assert ed.level.spawners == []
