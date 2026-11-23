"""Zombies' interact points, counters and triggers (logic.py, with zombies.py and the map file): events, conditions
and actions, the four-fuse quest, loops that stop, and what joiners are told."""
import json
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import net
from game import Game, Inputs
from logic import MAX_DEPTH
from mapfile import (Action, Condition, Counter, Door, Enemy, Entity, Interact, Level, Trigger, level_text,
                     parse_level)
from session import ClientSession, HostSession
from test_session import FIRST_CHARACTER, make_world, run
from test_zombies import DT, go_live, place, play, zombie_level
from world import World
from zombies import ZombieView

GEN = (5.5, 5.5)                                # where the generator (an interact point) stands


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


def logic_game(triggers=(), interacts=(), counters=(), entities=(), doors=(), players=(0,), **rules):
    level = zombie_level(**rules)
    level.triggers, level.interacts, level.counters = list(triggers), list(interacts), list(counters)
    level.entities, level.doors = list(entities), list(doors)
    for door in level.doors:
        for x, y in door.cells():
            level.set("walls", x, y, 0)
    game = Game(level, World(level, 32), random.Random(1), character_tile=FIRST_CHARACTER)
    for pid in players:
        game.add_player(pid)
    return game


def press(game, pid=0):
    """Press the use key once (let go, then hold for a step): what the player was told."""
    said = []
    for wish in (Inputs(), Inputs(use=True)):
        for who, events in game.tick({pid: wish}, DT).items():
            if who == pid:
                said += events.picked
    play(game, DT, {pid: Inputs()})
    return said


def generator(**kwargs):
    return Interact("Generator", *GEN, prompt="start the generator", **kwargs)


# ------------------------------------------------------------------ the map file

def test_interacts_counters_and_triggers_are_saved_and_loaded():
    level = Level.blank(10, 10)
    level.interacts = [generator(cost=500, cost_kind="money", needs="Fuse", needs_amount=4, once=True, tile=12)]
    level.counters = [Counter("fuses", goal=4, label="Fuses")]
    level.triggers = [Trigger("Power", "used:Generator", [Condition("counter_at_least", "fuses", 4)],
                              [Action("open_door", "Vault"), Action("message", text="The power is on", who="everyone")],
                              once=True)]
    again = parse_level(json.loads(level_text(level)))
    assert (again.interacts, again.counters, again.triggers) == (level.interacts, level.counters, level.triggers)
    for key in ("interacts", "counters", "triggers"):
        assert f'"{key}"' not in level_text(Level.blank(5, 5))


def test_unusable_trigger_values_fall_back():
    trigger = Trigger.from_dict({"name": 5, "on": ["x"], "conditions": [{"kind": "magic", "amount": "lots"}, 3],
                                 "actions": [{"kind": "explode", "who": "nobody"}] * 40, "once": 1})
    assert trigger.name == "5" and trigger.on == "game_start" and trigger.once
    assert trigger.conditions == [Condition()] and len(trigger.actions) == 16
    assert trigger.actions[0] == Action()


def test_renaming_follows_through_the_triggers():
    level = Level.blank(10, 10)
    level.interacts = [generator(needs="Fuse")]
    level.triggers = [Trigger("t", "used:Generator", [Condition("team_has", "Fuse", 4), Condition("door_open", "Vault")],
                              [Action("add_counter", "fuses"), Action("effect", "Sparks", at="Generator"),
                               Action("event", "power")]),
                      Trigger("u", "power", [], [Action("close_door", "Vault")])]
    level.rename_reference("interact", "Generator", "Gen")
    level.rename_reference("item", "Fuse", "Cell")
    level.rename_reference("door", "Vault", "Safe")
    level.rename_reference("counter", "fuses", "cells")
    level.rename_reference("event", "power", "lights")
    first, second = level.triggers
    assert first.on == "used:Gen" and [c.name for c in first.conditions] == ["Cell", "Safe"]
    assert [a.name for a in first.actions] == ["cells", "Sparks", "lights"] and first.actions[1].at == "Gen"
    assert second.on == "lights" and second.actions[0].name == "Safe" and level.interacts[0].needs == "Cell"


# ------------------------------------------------------------------ events

def test_game_start_and_round_start():
    game = logic_game(triggers=[Trigger("hello", "game_start", [], [Action("message", text="Welcome", who="everyone")]),
                                Trigger("r3", "round_start", [Condition("round_at_least", amount=2)],
                                        [Action("give_money", amount=100, who="everyone")])])
    play(game, DT)
    assert game.round.message == "Welcome"
    go_live(game)
    assert game.players[0].stats.money == 0                             # (round 1 is not at least 2)
    game.round.end_round()
    game.round.start_round()
    assert game.players[0].stats.money == 100


def test_using_an_interact_point_counts_and_opens_a_door_at_the_goal():
    game = logic_game(interacts=[Interact("Switch", *GEN)], counters=[Counter("switches", goal=2)],
                      doors=[Door("Vault", 15, 2, cost_kind="free", buyable=False)],
                      triggers=[Trigger("count", "used:Switch", [], [Action("add_counter", "switches", 1)]),
                                Trigger("open", "counter:switches", [Condition("counter_at_least", "switches", 2)],
                                        [Action("open_door", "Vault")], once=True)])
    place(game.players[0].body, 5.5, 6.2)
    press(game)
    assert game.round.logic.counters["switches"] == 1 and not game.round.doors[0]
    press(game)
    assert game.round.doors[0] and game.world.span_at(15.5, 2.5, 0.0) == 0
    assert game.round.view().counters == {"switches": 2}


def test_an_interact_point_costs_needs_items_and_can_be_used_once():
    game = logic_game(interacts=[generator(cost=500, cost_kind="money", needs="Fuse", needs_amount=2, once=True)],
                      triggers=[Trigger("power", "used:Generator", [], [Action("message", text="Power on")])],
                      start_money=600)
    me = game.players[0]
    place(me.body, 5.5, 6.2)
    assert any("2 x Fuse" in text for text in press(game))
    me.inventory.add_item("Fuse", 3)
    assert "Power on" in press(game)
    assert me.stats.money == 100 and me.inventory.count("Fuse") == 1
    assert game.round.view().used == [True] and game.round.sprites(0) == []
    assert "Power on" not in press(game)                                # (used up)


def test_the_four_fuse_quest():
    fuses = [Entity(2.5 + i * 2, 9.5, effect="item", item="Fuse", amount=1, mode="once") for i in range(4)]
    game = logic_game(entities=fuses, counters=[Counter("fuses", goal=4, label="Fuses")],
                      interacts=[generator(needs="Fuse", needs_amount=4)],
                      doors=[Door("Vault", 15, 2, buyable=False)],
                      triggers=[Trigger("found", "picked:Fuse", [], [Action("add_counter", "fuses", 1)]),
                                Trigger("power", "used:Generator", [], [Action("open_door", "Vault"),
                                                                       Action("set_counter", "fuses", 0)])])
    me = game.players[0]
    place(me.body, 5.5, 6.2)
    press(game)
    assert not game.round.doors[0]                                      # (no fuses yet)
    for fuse in fuses:
        place(me.body, fuse.x, fuse.y)
        play(game, 2 * DT)
    assert game.round.logic.counters["fuses"] == 4 and me.inventory.count("Fuse") == 4
    place(me.body, 5.5, 6.2)
    press(game)
    assert game.round.doors[0] and me.inventory.count("Fuse") == 0 and game.round.logic.counters["fuses"] == 0


def test_a_quest_that_finishes_itself_when_the_team_has_everything():
    fuses = [Entity(2.5 + i * 2, 9.5, effect="item", item="Fuse", amount=1, mode="once") for i in range(2)]
    game = logic_game(entities=fuses, doors=[Door("Vault", 15, 2, buyable=False)], players=(0, 1),
                      triggers=[Trigger("all", "picked:Fuse", [Condition("team_has", "Fuse", 2)],
                                        [Action("open_door", "Vault")])])
    place(game.players[0].body, fuses[0].x, fuses[0].y)
    play(game, 2 * DT)
    assert not game.round.doors[0]
    place(game.players[1].body, fuses[1].x, fuses[1].y)
    play(game, 2 * DT)
    assert game.round.doors[0]


def test_buying_a_door_sets_off_its_event():
    game = logic_game(doors=[Door("Gate", 12, 5, cost=100)], start_money=100,
                      triggers=[Trigger("in", "door:Gate", [], [Action("give_score", amount=7)])])
    for y in range(1, 11):
        if y != 5:
            game.level.set("walls", 12, y, 1)
    place(game.players[0].body, 11.5, 5.5)
    press(game)
    assert game.round.doors[0] and game.players[0].stats.score == 7


def test_once_only_triggers_and_a_new_game_resets_them():
    game = logic_game(interacts=[Interact("Switch", *GEN)],
                      triggers=[Trigger("pay", "used:Switch", [], [Action("give_money", amount=10)], once=True)])
    place(game.players[0].body, 5.5, 6.2)
    press(game)
    press(game)
    assert game.players[0].stats.money == 10
    game.round.new_game()
    place(game.players[0].body, 5.5, 6.2)
    press(game)
    assert game.players[0].stats.money == 10                            # (a new game starts at the start money: 0)


# ------------------------------------------------------------------ actions

def test_giving_and_taking_for_the_player_or_everyone():
    game = logic_game(players=(0, 1), interacts=[Interact("Box", *GEN)],
                      triggers=[Trigger("box", "used:Box", [], [
                          Action("give_item", "Key", 2), Action("take_item", "Key", 1),
                          Action("give_money", amount=50, who="everyone"), Action("give_money", amount=-500),
                          Action("give_score", amount=3, who="everyone"),
                          Action("message", text="Only you", who="player"),
                          Action("message", text="All of you", who="everyone")])])
    place(game.players[0].body, 5.5, 6.2)
    said = press(game)
    zero, one = game.players[0], game.players[1]
    assert zero.inventory.count("Key") == 1 and one.inventory.count("Key") == 0
    assert (zero.stats.money, one.stats.money) == (0, 50) and (zero.stats.score, one.stats.score) == (3, 3)
    assert "Only you" in said and game.round.message == "All of you"


def test_effects_and_lights_play_at_an_interact_point_or_the_player():
    game = logic_game(interacts=[generator()],
                      triggers=[Trigger("fx", "used:Generator", [], [Action("effect", "Sparks", at="Generator"),
                                                                     Action("light", "Glow")])])
    me = game.players[0]
    place(me.body, 5.5, 6.2)
    press(game)
    fx, flashes = game.take_fx(), game.take_flashes()
    assert any(e[0] == "Sparks" and e[1:3] == GEN for e in fx)
    assert any(f[0] == "Glow" and f[1:3] == (me.body.x, me.body.y) for f in flashes)


def test_sending_enemies_and_winning():
    game = logic_game(enemies=[Enemy(name="Walker"), Enemy(name="Boss", weight=[[1, 0.0]])], zombie_count=[[1, 1]],
                      interacts=[Interact("Alarm", *GEN), Interact("Exit", 9.5, 5.5)],
                      triggers=[Trigger("alarm", "used:Alarm", [], [Action("spawn_enemies", "Boss", 2)]),
                                Trigger("out", "used:Exit", [], [Action("win", text="You escaped!")])])
    go_live(game)
    place(game.players[0].body, 5.5, 6.2)
    press(game)
    play(game, 3.0)
    assert sorted(e.kind for e in game.round.enemies.values()).count(1) == 2   # (the two bosses, sent)
    place(game.players[0].body, 9.5, 6.2)
    press(game)
    assert game.round.phase == "over" and game.round.message == "You escaped!"


def test_triggers_that_set_each_other_off_stop():
    game = logic_game(interacts=[Interact("Bell", *GEN)], counters=[Counter("rings")],
                      triggers=[Trigger("ring", "used:Bell", [], [Action("event", "ding")]),
                                Trigger("loop", "ding", [], [Action("add_counter", "rings", 1), Action("event", "ding")])])
    place(game.players[0].body, 5.5, 6.2)
    press(game)
    assert game.round.logic.counters["rings"] == MAX_DEPTH - 1
    play(game, 0.5)                                                     # (and the game carries on)


# ------------------------------------------------------------------ what players see

def test_counters_and_used_up_points_go_to_joiners():
    level = zombie_level()
    level.interacts = [generator(once=True, tile=12)]
    level.counters = [Counter("fuses", start=1, goal=4)]
    level.triggers = [Trigger("t", "used:Generator", [], [Action("add_counter", "fuses", 2)])]
    game = Game(level, World(level, 32), random.Random(1), character_tile=FIRST_CHARACTER)
    host = HostSession(game, net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
    try:
        run([host, client], lambda: client.ready and isinstance(client.round, ZombieView))
        assert client.round.counters == {"fuses": 1} and client.round.used == [False]
        assert any(s[4] == 12 for s in client.sprites())
        pid = next(iter(game.players))
        place(game.players[pid].body, 5.5, 6.2)
        assert game.round.try_interact(pid)
        run([host, client], lambda: client.round.used == [True])
        assert client.round.counters == {"fuses": 3} and not any(s[4] == 12 for s in client.sprites())
    finally:
        client.close()
        host.close()


def test_the_hud_shows_counters_and_the_interact_prompt():
    from hud import draw_interact, draw_round
    game = logic_game(interacts=[generator(cost=500, cost_kind="money")], counters=[Counter("fuses", goal=4)])
    me = game.players[0]
    picture = pygame.Surface((640, 360))
    font, big = pygame.font.Font(None, 22), pygame.font.Font(None, 30)
    place(me.body, 5.5, 6.2)
    draw_round(picture, font, big, game.round.view(), 0, me, game.level)
    draw_interact(picture, font, game.round.view(), 0, me, game.level)


# ------------------------------------------------------------------ the editor

@pytest.fixture
def ed(tmp_path):
    import map_editor
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(12, 12)
    editor.level.settings.mode = "zombies"
    editor.show_legend = False
    editor.draw(pygame.display.get_surface())
    return editor


def click(ed, pos):
    ed.on_mouse_down(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    ed.on_mouse_up(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))


def keys(ed):
    return [r.field.key for r in ed.details_rows()]


def test_the_interact_tool_places_and_edits_points(ed):
    ed.level.set("walls", 3, 3, 1)
    ed.do("tool:interact")
    ed.map_click((3, 3), 1)
    assert ed.level.interacts == [] and "open cell" in ed.message
    ed.map_click((5, 5), 1)
    assert [(i.name, i.x, i.y) for i in ed.level.interacts] == [("Button", 5.5, 5.5)]
    assert ed.selected_interact() is ed.level.interacts[0]
    ed.set_interact("needs", "Fuse")
    ed.set_interact("cost_kind", "money")
    assert {"needs_amount", "consume", "cost"} <= set(keys(ed))
    ed.level.triggers = [Trigger("t", "used:Button", [], [Action("effect", "Sparks", at="Button")])]
    ed.set_interact("name", "Generator")
    assert ed.level.triggers[0].on == "used:Generator" and ed.level.triggers[0].actions[0].at == "Generator"
    ed.atlas_drag = ((12, 0), (12, 0))
    ed.finish_atlas_drag()
    assert ed.level.interacts[0].tile == 12
    ed.draw(pygame.display.get_surface())
    assert ed.details_delete_label() == "Delete interact point"
    ed.map_click((5, 5), 3)
    assert ed.level.interacts == []
    ed.do("undo")
    assert ed.level.interacts[0].name == "Generator"


def test_the_triggers_section_adds_and_lists_triggers_and_counters(ed):
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_y, mod=0, unicode="y"))
    assert ed.triggers_mode and ed.section_open()
    _triggers, add_trigger, _counters, add_counter = ed.triggers_rows()
    click(ed, add_counter.center)
    assert [c.name for c in ed.level.counters] == ["Counter"] and ed.selected_counter() is ed.level.counters[0]
    ed.set_counter("name", "fuses")
    ed.set_counter("goal", 4)
    click(ed, ed.triggers_rows()[1].center)
    trigger = ed.level.triggers[0]
    assert ed.selected_trigger() is trigger and {"pick_event", "on", "add_condition", "add_action"} <= set(keys(ed))
    assert "counter:fuses" in ed.known_events()
    ed.set_trigger("on", "counter:fuses")
    ed.add_condition()
    assert trigger.conditions == [Condition("counter_at_least", "fuses", 1.0)]
    ed.set_part("conditions", 0, "amount", 4)
    ed.set_part("actions", 0, "kind", "give_money")
    assert {"a0_amount", "a0_who"} <= set(keys(ed)) and "a0_text" not in keys(ed)
    ed.set_part("actions", 0, "amount", 200)
    ed.add_action()
    ed.remove_part("actions", 1)
    assert "When fuses changes   if fuses >= 4   then give $200" == ed.trigger_summary(trigger)
    ed.draw(pygame.display.get_surface())
    ed.triggers_selected = ("counter", 0)
    ed.set_counter("name", "cells")
    assert trigger.on == "counter:cells" and trigger.conditions[0].name == "cells"
    ed.delete_selected()
    assert ed.level.counters == []
    ed.do("undo")
    assert ed.level.counters[0].name == "cells"
    ed.do("triggers")
    assert not ed.triggers_mode


def test_renaming_a_door_follows_through_the_triggers(ed):
    ed.level.doors = [Door("Gate", 2, 2)]
    ed.level.triggers = [Trigger("t", "door:Gate", [Condition("door_open", "Gate")], [Action("close_door", "Gate")])]
    ed.do("tool:door")
    ed.map_click((2, 2), 1)
    ed.set_door("name", "Vault")
    t = ed.level.triggers[0]
    assert (t.on, t.conditions[0].name, t.actions[0].name) == ("door:Vault", "Vault", "Vault")


def test_other_sections_and_tools_close_the_triggers_section(ed):
    ed.do("triggers")
    ed.do("mapsettings")
    assert not ed.triggers_mode and ed.settings_mode
    ed.do("triggers")
    assert ed.triggers_mode and not ed.settings_mode
    ed.do("tool:paint")
    assert not ed.triggers_mode


def test_the_minus_and_plus_of_a_text_row_do_nothing(ed):
    ed.do("triggers")
    ed.add_trigger()
    row = next(r for r in ed.details_rows() if r.field.key == "on")
    assert row.field.stepped(1) == ed.level.triggers[0].on
    click(ed, row.plus.center)                              # (was a crash: text does not step)
    click(ed, row.minus.center)
    assert ed.level.triggers[0].on == "game_start"
    ed.draw(pygame.display.get_surface())


# ------------------------------------------------------------------ enemies only triggers send

def test_an_enemy_kept_out_of_the_waves_only_comes_when_a_trigger_sends_it():
    boss = Enemy(name="Boss", weight=[[1, 100.0]], in_waves=False)
    game = logic_game(enemies=[Enemy(name="Walker"), boss], zombie_count=[[1, 6]], spawn_interval=0.0,
                      interacts=[Interact("Alarm", *GEN)],
                      triggers=[Trigger("boss", "used:Alarm", [], [Action("spawn_enemies", "Boss", 1)])])
    go_live(game)
    play(game, 0.5)
    assert sorted(e.kind for e in game.round.enemies.values()) == [0] * 6       # (its weight does not matter)
    place(game.players[0].body, 5.5, 6.2)
    press(game)
    play(game, 0.5)
    assert sorted(e.kind for e in game.round.enemies.values()).count(1) == 1


def test_a_map_whose_enemies_all_come_from_triggers_has_empty_rounds_until_one_sends_them():
    game = logic_game(enemies=[Enemy(name="Boss", in_waves=False)], zombie_count=[[1, 6]],
                      triggers=[Trigger("boss", "round_start", [], [Action("spawn_enemies", "Boss", 2)])])
    go_live(game)
    play(game, 0.5)
    assert sorted(e.kind for e in game.round.enemies.values()) == [0, 0] and game.round.to_spawn == 0


def test_in_waves_is_saved_and_the_editor_hides_the_wave_settings(ed):
    ed.level.enemies = [Enemy(name="Walker"), Enemy(name="Boss", in_waves=False)]
    again = parse_level(json.loads(level_text(ed.level)))
    assert [e.in_waves for e in again.enemies] == [True, False]
    import map_editor
    ed.do("mapsettings")
    ed.settings_selected = map_editor.ENEMY_ROW - 1
    assert "in_waves" in keys(ed) and "max_per_round" not in keys(ed) and "weight0y" not in keys(ed)
    assert "sent by triggers only" in ed.enemy_summary(ed.level.enemies[1])
    ed.curve_shown = "weight"
    assert ed.curve_enemy() == 0                            # (the Enemy mix edits a kind the waves send)
    ed.draw(pygame.display.get_surface())
    assert [i for _rect, i in ed.curve_layout(ed.waves_card_rect())[2]] == [0]
    ed.set_enemy("in_waves", True)
    assert "max_per_round" in keys(ed)


# ------------------------------------------------------------------ items that add to a counter

def test_picking_up_an_item_adds_to_its_counter_and_sets_off_the_counters_triggers():
    parts = [Entity(2.5 + i * 2, 9.5, effect="counter", counter="parts", amount=1, mode="once")
             for i in range(3)]
    game = logic_game(entities=parts, counters=[Counter("parts", goal=3)],
                      triggers=[Trigger("all", "counter:parts", [Condition("counter_at_least", "parts", 3)],
                                        [Action("message", text="All parts!", who="everyone")])])
    me = game.players[0]
    for part in parts:
        place(me.body, part.x, part.y)
        play(game, 2 * DT)
    assert game.round.logic.counters["parts"] == 3 and game.round.message == "All parts!"


def test_copies_of_a_prefab_add_to_its_counter_and_a_bought_one_counts_too():
    level_prefab = Entity(0, 0, name="Part", effect="counter", counter="parts", amount=2, mode="once")
    copy = Entity(4.5, 9.5, prefab="Part")
    bought = Entity(8.5, 9.5, effect="counter", counter="parts", amount=5, price=100, mode="once")
    game = logic_game(entities=[copy, bought], counters=[Counter("parts")], start_money=100)
    game.level.prefabs = [level_prefab]
    game.level.apply_prefabs()
    assert game.level.entities[0].counter == "parts"
    from entities import Entities
    game.items = Entities(game.level, game.world)
    me = game.players[0]
    place(me.body, 4.5, 9.5)
    play(game, 2 * DT)
    assert game.round.logic.counters["parts"] == 2
    place(me.body, 8.5, 9.5)
    press(game)
    play(game, DT)
    assert game.round.logic.counters["parts"] == 7


def test_an_item_naming_a_counter_the_map_does_not_have_changes_nothing():
    game = logic_game(entities=[Entity(4.5, 9.5, effect="counter", counter="gone", mode="once")])
    place(game.players[0].body, 4.5, 9.5)
    play(game, 2 * DT)
    assert game.round.logic.counters == {}


def test_the_counter_setting_is_saved_shown_in_the_editor_and_follows_renames(ed):
    ed.level.counters = [Counter("parts")]
    ed.level.entities = [Entity(3.5, 3.5, effect="counter", counter="parts", amount=2)]
    ed.level.prefabs = [Entity(0, 0, name="Part", effect="counter", counter="parts")]
    again = parse_level(json.loads(level_text(ed.level)))
    assert again.entities[0].effect == "counter" and again.entities[0].counter == "parts"
    assert again.entities[0].amount == 2
    ed.level.entities.append(Entity(5.5, 5.5))
    ed.do("tool:entity")
    ed.select_entity(ed.level.entities[1])
    assert "counter" not in keys(ed)                        # (only for that effect)
    ed.set_entity("effect", "counter")
    plain = ed.level.entities[1]
    assert (plain.counter, plain.amount) == ("parts", 1.0) and {"counter", "amount"} <= set(keys(ed))
    ed.set_entity("amount", -2)
    assert plain.amount == -2
    ed.do("triggers")
    ed.triggers_selected = ("counter", 0)
    ed.set_counter("name", "pieces")
    assert ed.level.entities[0].counter == "pieces" and ed.level.prefabs[0].counter == "pieces"


def test_add_to_a_counter_is_offered_only_on_maps_with_counters(ed):
    ed.level.entities = [Entity(3.5, 3.5)]
    ed.do("tool:entity")
    ed.select_entity(ed.level.entities[0])
    effect = next(r.field for r in ed.details_rows() if r.field.key == "effect")
    assert "counter" not in effect.choices
    ed.level.counters = [Counter("parts")]
    effect = next(r.field for r in ed.details_rows() if r.field.key == "effect")
    assert "counter" in effect.choices
