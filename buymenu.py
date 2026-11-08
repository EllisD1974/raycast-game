"""The buy menu (B in the game, on maps whose settings turn it on): the entries of the map's buy menu as buttons, each
with its picture and price.

It is drawn and laid out like the in-game menu (menu.Pages). Clicking an entry returns "buy:<index>": main.py puts the
index in the player's next Inputs, and the game (the host's, for a joiner) gives it if the player has enough money or
score. An entry the player cannot afford is greyed out; one for the other team (in a mode with teams) is not listed. "close" (B, Esc or Close) puts the menu away.
"""
import pygame

from menu import DIM, LIST_ROWS, Pages, cell

PRICE_UNITS = {"money": "${:g}", "score": "{:g} score", "free": "free"}


def price_text(cost, price):
    """An entry's price as shown: "$300", "40 score" or "free"."""
    return "free" if cost == "free" or price <= 0 else PRICE_UNITS[cost].format(price)


def entry_tile(entry, guns):
    """The atlas tile shown beside an entry: its own, or for a gun with none the gun's picture (-1: none)."""
    if entry.tile >= 0:
        return entry.tile
    if entry.kind == "gun":
        gun = next((g for g in guns if g.name == entry.gun), None)
        return gun.tile if gun is not None else -1
    return -1


class BuyMenu(Pages):
    """The buy menu. `level()` is the map being played and `stats()` the player's PlayerStats (both asked for each time,
    as the map can change while the game runs), `tiles()` the atlas's tile pictures for the entries' icons and `team()`
    the player's team (entries for the other team are left out)."""
    TITLES = {"main": "Buy menu"}

    def __init__(self, settings, level, stats, tiles=lambda: [], team=lambda: 0):
        super().__init__(settings)
        self.level, self.stats, self.tiles, self.team = level, stats, tiles, team

    def offered(self):
        """[(index in the map's buy menu, entry)] of the entries this player's team can buy."""
        settings, team = self.level().settings, self.team()
        return [(i, e) for i, e in enumerate(settings.buy_items) if e.offered_to(team, settings.has_teams())]

    def affordable(self, entry):
        settings, stats = self.level().settings, self.stats()
        if settings.buy_cost == "free" or entry.price <= 0:
            return True
        return (stats.money if settings.buy_cost == "money" else stats.score) >= entry.price

    def wallet(self):
        """The line over the entries: what the player has to spend."""
        settings, stats = self.level().settings, self.stats()
        if settings.buy_cost == "free":
            return "Everything here is free"
        if settings.buy_cost == "money":
            return f"You have ${stats.money:g}"
        return f"You have {stats.score:g} score"

    def lines(self):
        settings = self.level().settings
        entries = self.offered()
        rows = [[cell(self.wallet(), color=DIM)]]
        rows += self.scroll_rows([[cell(f"{entry.label()}   {price_text(settings.buy_cost, entry.price)}", f"buy:{i}",
                                        self.affordable(entry))] for i, entry in entries], LIST_ROWS)

        if not entries:
            rows.append([cell("Nothing for sale on this map", color=DIM)])
        if len(entries) > LIST_ROWS:
            rows.append([cell(f"{self.scroll + 1}-{min(len(entries), self.scroll + LIST_ROWS)} of {len(entries)}"
                              "  (the wheel scrolls)", color=DIM)])
        return rows + [[cell("Close (B)", "close")]]

    def handle(self, event, size):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_b:
            return "close"
        return super().handle(event, size)

    def escape(self):
        return "close"

    def bought(self, messages):
        """Show what came of the last purchase (the game's message for it) under the entries."""
        for text in messages:
            if text.startswith("Bought"):
                self.say(text)
            elif text.startswith(("Not enough", "Nothing to buy", "Health is already")) or "not for sale" in text:
                self.say(text, warn=True)

    def draw(self, surface, mouse=(-1, -1), shade=True):
        super().draw(surface, mouse, shade)
        tiles, level = self.tiles(), self.level()
        if not tiles:
            return
        for item in self.items(surface.get_size()):
            if not (item.action or "").startswith("buy:"):
                continue
            entry = level.settings.buy_items[int(item.action[4:])]
            tile = entry_tile(entry, level.guns)
            if 0 <= tile < len(tiles):
                side = item.rect.h - 8
                picture = pygame.transform.scale(tiles[tile], (side, side))
                if not item.enabled:
                    picture.set_alpha(110)
                surface.blit(picture, (item.rect.x + 6, item.rect.y + 4))

