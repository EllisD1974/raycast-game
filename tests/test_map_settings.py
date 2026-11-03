"""Map settings: the game mode and rules, the buy menu (saved with the map, edited in the editor's Map settings
section) and buying from it in the game, alone or through a host."""
import json
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import details
import map_editor
import net
from buymenu import BuyMenu, entry_tile, price_text
from entities import PlayerStats
from game import NO_TEAM, Game, Inputs
from mapfile import BUY_KINDS, BuyItem, Gun, Level, MapSettings, level_text, load_level, parse_level, save_level
from session import ClientSession, HostSession
from test_session import FIRST_CHARACTER, make_world, run
from world import World


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


def shop_level(cost="money", **rules):
    level = Level.blank(12, 12)
    level.guns = [Gun(name="Pistol", tile=16), Gun(name="Shotgun", tile=17, start_ammo=8)]
    level.settings = MapSettings(buy_menu=True, buy_cost=cost, buy_items=[
        BuyItem(kind="gun", gun="Shotgun", price=300),
        BuyItem(kind="gun", gun="Pistol", price=50),
        BuyItem(kind="health", amount=40, price=20),
        BuyItem(kind="item", item="Key", amount=2, price=0)], **rules)
    return level


def game_for(level, players=(0,)):
    game = Game(level, World(level, 32), random.Random(1))
    for pid in players:
        game.add_player(pid)
    return game


def buy(game, pid, *indices):
    return game.tick({pid: Inputs(buy=indices)}, 1 / 60)[pid].picked


# ------------------------------------------------------------------ the file

def test_settings_are_saved_with_the_map_and_read_back(tmp_path):
    level = shop_level(mode="teams", friendly_fire=True, max_health=150, start_money=800, kill_score=1,
                       kill_money=300, start_gun="Pistol")
    path = tmp_path / "m.json"
    save_level(str(path), level)
    again = load_level(str(path))
    assert again.settings == level.settings
    assert again.settings.buy_items[1] == BuyItem(kind="gun", gun="Pistol", price=50)


def test_ammo_is_not_sold_and_an_older_maps_ammo_entries_are_left_out():
    assert "ammo" not in BUY_KINDS
    data = json.loads(level_text(shop_level()))
    data["settings"]["buy_items"].insert(1, {"kind": "ammo", "ammo": "9mm", "amount": 30, "price": 50})
    assert [b.label() for b in parse_level(data).settings.buy_items] == ["Shotgun", "Pistol", "+40 health", "2 x Key"]


def test_a_map_with_default_settings_saves_none_and_old_maps_load():
    level = Level.blank(5, 5)
    assert '"settings"' not in level_text(level)
    assert parse_level(json.loads(level_text(level))).settings == MapSettings()


def test_unusable_settings_fall_back_to_the_defaults():
    data = json.loads(level_text(Level.blank(5, 5)))
    data["settings"] = {"mode": "battle royale", "max_health": "lots", "buy_cost": "gold", "start_money": -5,
                        "buy_items": [{"kind": "spaceship", "price": -1}, "nonsense"]}
    settings = parse_level(data).settings
    assert settings.mode == "ffa" and settings.max_health == 100.0 and settings.buy_cost == "money"
    assert settings.start_money == 0.0
    assert settings.buy_items == [BuyItem(kind="gun", price=0.0)]


def test_undo_copies_the_settings():
    level = shop_level()
    copy = level.copy()
    copy.settings.buy_items[0].price = 1
    copy.settings.mode = "coop"
    assert level.settings.buy_items[0].price == 300 and level.settings.mode == "ffa"


# ------------------------------------------------------------------ buying

def test_buying_with_money_gives_the_thing_and_takes_the_price():
    game = game_for(shop_level(start_money=400))
    me = game.players[0]
    assert me.stats.money == 400
    assert buy(game, 0, 0) == ["Bought Shotgun for 300"]
    assert me.inventory.find_gun("Shotgun") is not None and me.stats.money == 100
    assert buy(game, 0, 1) == ["Bought Pistol for 50"]
    assert me.inventory.find_gun("Pistol") is not None and me.stats.money == 50


def test_buying_without_enough_money_gives_nothing():
    game = game_for(shop_level(start_money=100))
    me = game.players[0]
    messages = buy(game, 0, 0)
    assert messages[0].startswith("Not enough money")
    assert me.inventory.guns == [] and me.stats.money == 100


def test_buying_with_score_spends_score():
    game = game_for(shop_level("score"))
    me = game.players[0]
    me.stats.score = 25
    me.stats.health = 50
    assert buy(game, 0, 2) == ["Bought +40 health for 20"]
    assert me.stats.health == 90 and me.stats.score == 5
    assert buy(game, 0, 0)[0].startswith("Not enough score")


def test_a_free_menu_costs_nothing():
    game = game_for(shop_level("free"))
    me = game.players[0]
    assert buy(game, 0, 0, 3) == ["Bought Shotgun", "Bought 2 x Key"]
    assert me.inventory.count("Key") == 2 and me.stats.money == 0


def test_nothing_is_bought_when_the_menu_is_off_or_the_entry_is_missing():
    level = shop_level("free")
    level.settings.buy_menu = False
    game = game_for(level)
    assert buy(game, 0, 0) == ["Nothing to buy"]
    game.level.settings.buy_menu = True
    assert buy(game, 0, 9) == ["Nothing to buy"]
    assert game.players[0].inventory.guns == []


def test_full_health_is_not_bought_and_costs_nothing():
    game = game_for(shop_level(start_money=100))
    assert buy(game, 0, 2) == ["Health is already full"]
    assert game.players[0].stats.money == 100


def test_buys_survive_the_network_message():
    wish = Inputs.from_dict(Inputs(buy=(2, 0)).to_dict())
    assert wish.buy == (2, 0)
    assert Inputs.from_dict({"buy": [1, -1, 999, True, "x"]}).buy == (1,)
    assert Inputs.from_dict({"buy": "lots"}).buy == ()


def test_a_joiner_buys_through_the_host_and_sees_the_money_change():
    level = shop_level(start_money=400)
    host = HostSession(Game(level, make_world(level), random.Random(1), character_tile=FIRST_CHARACTER),
                       net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
    try:
        run([host, client], until=lambda: client.ready or client.ended)
        assert client.level.settings.buy_menu and client.me.stats.money == 400
        client.step(Inputs(buy=(0,)), 1 / 60)                       # (one step asks for it, once)
        run([host, client], until=lambda: client.me.stats.money == 100)
        assert host.game.players[client.id].inventory.find_gun("Shotgun") is not None
        assert client.me.inventory.find_gun("Shotgun") is not None
    finally:
        client.close()
        host.close()


# ------------------------------------------------------------------ rules

def test_players_start_and_come_back_with_the_maps_health_and_gun():
    game = game_for(shop_level(max_health=150, start_gun="Pistol", start_money=500))
    me = game.players[0]
    assert me.stats.health == me.stats.max_health == 150
    assert [g.gun.name for g in me.inventory.guns] == ["Pistol"]
    me.stats.money = 120
    game.hurt(0, 1000)
    assert me.stats.health == 150 and me.stats.money == 120          # (the start money only comes once)
    assert [g.gun.name for g in me.inventory.guns] == ["Pistol"]


def test_two_teams_split_the_players_and_coop_puts_everyone_on_one():
    game = game_for(shop_level(mode="teams"), players=(0, 1, 2, 3))
    assert [game.players[p].team for p in range(4)] == [1, 2, 1, 2]
    game = game_for(shop_level(mode="coop"), players=(0, 1))
    assert {game.players[p].team for p in range(2)} == {1}
    game = game_for(shop_level(), players=(0, 1))
    assert {game.players[p].team for p in range(2)} == {NO_TEAM}


def test_a_new_map_deals_the_teams_again():
    game = game_for(shop_level(), players=(0, 1))
    level = shop_level(mode="teams")
    game.load_level(level, World(level, 32))
    assert sorted(game.players[p].team for p in range(2)) == [1, 2]


def test_knocking_out_an_opponent_earns_the_reward_but_not_a_teammate():
    game = game_for(shop_level(mode="teams", friendly_fire=True, kill_score=1, kill_money=300), players=(0, 1, 2))
    game.hurt(1, 1000, attacker=0)                                  # 1 is on the other team
    assert game.players[0].stats.score == 1 and game.players[0].stats.money == 300
    game.hurt(2, 1000, attacker=0)                                  # 2 is a teammate
    assert game.players[0].stats.score == 1 and game.players[0].stats.money == 300
    game.hurt(0, 1000, attacker=0)                                  # nor yourself
    assert game.players[0].stats.score == 1


def test_friendly_fire_off_keeps_teammates_safe():
    game = game_for(shop_level(mode="coop"), players=(0, 1))
    assert not game.can_hurt(0, 1) and game.can_hurt(0, 0)
    game.level.settings.friendly_fire = True
    assert game.can_hurt(0, 1)
    game = game_for(shop_level(), players=(0, 1))
    assert game.can_hurt(0, 1)


# ------------------------------------------------------------------ the buy menu in the game

def test_the_buy_menu_lists_the_entries_and_greys_out_what_cannot_be_afforded():
    level, stats = shop_level(), PlayerStats(money=60)
    menu = BuyMenu(None, lambda: level, lambda: stats)
    menu.show()
    items = menu.items((1280, 800))
    buttons = {i.action: i for i in items if i.action and i.action.startswith("buy:")}
    assert buttons["buy:0"].label == "Shotgun   $300" and not buttons["buy:0"].enabled
    assert buttons["buy:1"].enabled and buttons["buy:3"].label == "2 x Key   free"
    click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=buttons["buy:1"].rect.center, button=1)
    assert menu.handle(click, (1280, 800)) == "buy:1"
    assert menu.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_b, mod=0, unicode="b"), (1280, 800)) == "close"
    surface = pygame.Surface((1280, 800), pygame.SRCALPHA)
    menu.draw(surface)


def test_an_entry_for_one_team_is_only_listed_and_sold_to_that_team(tmp_path):
    level = shop_level(mode="teams")
    level.settings.buy_items[3].team = 2                            # the Key: team 2 only
    game = game_for(level, players=(0, 1))
    assert [game.players[p].team for p in (0, 1)] == [1, 2]
    assert game.buy(0, 3).endswith("not for sale to your team")
    assert game.buy(1, 3) == "Bought 2 x Key"

    def listed(team):
        menu = BuyMenu(None, lambda: level, lambda: PlayerStats(money=1000), team=lambda: team)
        menu.show()
        return {i.action for i in menu.items((1280, 800)) if i.action and i.action.startswith("buy:")}
    assert listed(1) == {"buy:0", "buy:1", "buy:2"} and listed(2) == {"buy:0", "buy:1", "buy:2", "buy:3"}
    level.settings.mode = "ffa"                                     # no teams: everyone sees it
    assert "buy:3" in listed(0) and game.buy(0, 3) == "Bought 2 x Key"

    save_level(tmp_path / "shop.json", level)
    assert [b.team for b in load_level(tmp_path / "shop.json").settings.buy_items] == [0, 0, 0, 2]


def test_prices_and_icons():
    assert price_text("money", 300) == "$300" and price_text("score", 5) == "5 score"
    assert price_text("free", 300) == "free" and price_text("money", 0) == "free"
    guns = [Gun(name="Shotgun", tile=17)]
    assert entry_tile(BuyItem(kind="gun", gun="Shotgun"), guns) == 17
    assert entry_tile(BuyItem(kind="gun", gun="Shotgun", tile=3), guns) == 3
    assert entry_tile(BuyItem(kind="health"), guns) == -1


# ------------------------------------------------------------------ the editor's Map settings section

@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(10, 10)
    editor.level.guns = [Gun(name="Pistol"), Gun(name="Rifle")]
    editor.show_legend = False
    editor.draw(pygame.display.get_surface())
    return editor


def click(ed, pos, button=1):
    ed.on_mouse_down(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
    ed.on_mouse_up(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))


def row(ed, name):
    return next(r for r in ed.details_rows() if r.field.key == name)


def choose(ed, name, choice):
    r = row(ed, name)
    click(ed, details.menu_anchor(r).center)
    assert ed.menu_open == name
    for rect, option in details.menu_rects(r):
        if option == choice:
            click(ed, rect.center)
            return
    raise AssertionError(f"{choice} is not in {name}")


def test_j_opens_the_section_on_the_game_rules(ed):
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j, mod=0, unicode="j"))
    assert ed.settings_mode and ed.section_open()
    assert [r.field.key for r in ed.details_rows()][:1] == ["mode"]
    choose(ed, "mode", "teams")
    assert ed.level.settings.mode == "teams"
    assert "friendly_fire" in [r.field.key for r in ed.details_rows()]
    choose(ed, "start_gun", "Rifle")
    assert ed.level.settings.start_gun == "Rifle"
    ed.do("undo")
    assert ed.level.settings.start_gun == ""
    ed.draw(pygame.display.get_surface())


def test_adding_entries_turns_the_menu_on_and_they_can_be_edited(ed):
    ed.do("mapsettings")
    _rules, _buy, _rows, add = ed.settings_rows()
    click(ed, add.center)
    click(ed, ed.settings_rows()[3].center)
    items = ed.level.settings.buy_items
    assert ed.level.settings.buy_menu
    assert [(b.kind, b.gun) for b in items] == [("gun", "Pistol"), ("gun", "Rifle")]
    assert ed.selected_buy_item() is items[1]
    choose(ed, "kind", "health")
    assert items[1].kind == "health" and items[1].amount == 50
    click(ed, row(ed, "price").plus.center)
    assert items[1].price == 150
    click(ed, details.button_box(row(ed, "move_up")).center)
    assert items[0].kind == "health" and ed.settings_selected == 0
    ed.draw(pygame.display.get_surface())
    ed.delete_selected()
    assert [b.gun for b in ed.level.settings.buy_items] == ["Pistol"]


def test_the_buy_menu_row_adds_any_gun(ed):
    ed.do("mapsettings")
    click(ed, ed.settings_rows()[1].center)
    assert ed.settings_row() == map_editor.BUY_ROW
    choose(ed, "buy_cost", "score")
    choose(ed, "add_buy", "gun:Rifle")
    assert ed.level.settings.buy_cost == "score"
    assert ed.level.settings.buy_items == [BuyItem(kind="gun", gun="Rifle")]
    assert ed.selected_buy_item() is ed.level.settings.buy_items[0]
    add = next(f for f in ed.buy_menu_fields() if f.key == "add_buy")
    assert not any(c.startswith("ammo:") for c in add.choices)             # ammo is not sold
    kind = next(f for f in ed.buy_item_fields(ed.selected_buy_item()) if f.key == "kind")
    assert "ammo" not in kind.choices


def test_renaming_or_deleting_a_gun_follows_into_the_settings(ed):
    ed.level.settings = MapSettings(start_gun="Pistol", buy_items=[BuyItem(kind="gun", gun="Pistol"),
                                                                     BuyItem(kind="gun", gun="Rifle")])
    ed.do("guns")
    ed.gun_selected = 0
    ed.set_gun("name", "Sidearm")
    assert ed.level.settings.start_gun == "Sidearm" and ed.level.settings.buy_items[0].gun == "Sidearm"
    ed.delete_gun()
    assert ed.level.settings.start_gun == ""
    assert [b.gun for b in ed.level.settings.buy_items] == ["Rifle"]


def test_an_atlas_click_sets_the_selected_entrys_icon(ed):
    ed.do("mapsettings")
    ed.add_buy_item()
    atlas = ed.atlas_rect()
    click(ed, (atlas.x + 40, atlas.y + 5))
    assert ed.level.settings.buy_items[0].tile == 1
