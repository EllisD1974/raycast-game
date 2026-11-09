"""The home screen, shown when the game is started on its own (not from the map editor's Play, nor with --map,
--host or --join): the player's name, Host game, Join game, Settings and Exit.

Host game picks a map from the maps folder, a password (needed) and the most players to let in, and Join game takes
the host's IP address (empty to start with), its port (7777 to start with) and its password. Like the in-game menu (menu.Pages), Home only lays itself
out and says what was asked for: handle() returns "host", "join", "cancel" (stop joining), "settings" or "exit", and
main.py does it, reading what was chosen from the Home and its GameSettings.

Both pages can connect by IP address or over Steam (the choice is kept in the settings). Over Steam a joiner picks the
host from their Steam friends in the game (those hosting first) or types its SteamID, and the Host page shows our
SteamID to hand out. `steam` is called for Steam (steamnet.default_network) the first time it is wanted; it raises
OSError when Steam cannot be used, and the pages say why.
"""
import os

import pygame

from game import MAX_PLAYER_NAME, clean_name
from menu import DIM, MAX_PLAYERS, MIN_PLAYERS, WARN, Pages, cell, map_files
from net import DEFAULT_PORT

ADDRESS_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")   # an IP address or host name
LABEL_W = 130                                   # the label in front of a text box
HOST_LIST_ROWS = 4                              # maps shown at once on the Host page (one fewer with Steam's row)
FRIEND_ROWS = 4                                 # Steam friends listed on the Join page
NETWORKS = (("ip", "IP address"), ("steam", "Steam"))


class Home(Pages):
    TITLES = {"home": "Raycaster", "settings": "Settings", "host": "Host a game", "join": "Join a game",
              "connecting": "Joining"}
    BACK = {"settings": "home", "host": "home", "join": "home", "connecting": "join"}
    FIRST = "home"

    def __init__(self, settings, maps_folder, steam=None):
        super().__init__(settings)
        self.maps_folder = maps_folder
        self.host_password = ""
        self.join_address = ""                  # the host's IP address, typed in each time
        self.join_port = str(DEFAULT_PORT)      # its port, 7777 unless the host picked another
        self.join_password = ""
        self.join_steam_id = ""                 # over Steam: the host's SteamID, picked from the friends or typed
        self.steam_start = steam
        self.steam = None                       # what steam() gave, once asked for
        self.steam_problem = ""                 # why Steam cannot be used, if it could not
        self.friends = []                       # [steamnet.Friend] in the game, as of the last look
        self.open = True

    @property
    def network(self):
        """How to host or join: "ip" or "steam"."""
        return self.settings.network

    def use_steam(self):
        """Start Steam if not yet tried: True if it can be used."""
        if self.steam is None and not self.steam_problem:
            try:
                if self.steam_start is None:
                    raise OSError("not available here")
                self.steam = self.steam_start()
            except OSError as e:
                self.steam_problem = f"Steam: {e}"
        return self.steam is not None

    def look_for_friends(self):
        """Fetch which Steam friends are in the game now."""
        if self.use_steam():
            try:
                self.friends = self.steam.friends_playing()
            except OSError as e:
                self.friends, self.steam_problem = [], f"Steam: {e}"

    def go(self, page):
        super().go(page)
        if page == "join" and self.network == "steam":
            self.look_for_friends()

    def host_name(self):
        """Who we are joining, for the Joining page."""
        if self.network != "steam":
            return f"{self.join_address}:{self.join_port}"
        friend = next((f for f in self.friends if str(f.steam_id) == self.join_steam_id), None)
        return f"{friend.name if friend else self.join_steam_id} on Steam"

    def maps(self):
        return map_files(self.maps_folder)

    def host_map(self):
        """The map picked to host: the one picked last time if it is still there, else the first."""
        names = self.maps()
        return self.settings.host_map if self.settings.host_map in names else (names[0] if names else "")

    def map_path(self):
        return os.path.join(self.maps_folder, self.host_map())

    # ------------------------------------------------------------------ the pages

    def shown(self, name, value, secret=False):
        """What a text box shows: what is being typed into it, or what it holds (a password as stars)."""
        text = self.typing if self.typing is not None and self.typing_field == name else value
        return "*" * len(text) if secret else text

    def network_line(self):
        return [cell("Connect by", width=LABEL_W)] + [cell(label, f"network:{name}", selected=self.network == name)
                                                      for name, label in NETWORKS]

    def steam_problem_lines(self):
        return [[cell(self.steam_problem[:44], color=WARN)]] if self.steam_problem else []

    def steam_host_lines(self):
        if self.network != "steam":
            return []
        if not self.use_steam():
            return self.steam_problem_lines()
        return [[cell("Copy my SteamID", "copy_id")]]

    def steam_join_lines(self):
        if not self.use_steam():
            return self.steam_problem_lines()
        out = [[cell("Friends in the game", color=DIM)]]
        out += self.scroll_rows([[cell(friend.name[:28] + ("  (hosting)" if friend.hosting else ""),
                                       f"friend:{friend.steam_id}", selected=str(friend.steam_id) == self.join_steam_id)]
                                 for friend in self.friends], FRIEND_ROWS)

        if not self.friends:
            out.append([cell("None right now", color=DIM)])
        out.append([cell("SteamID", width=LABEL_W), cell(self.shown("steam_id", self.join_steam_id), "input:steam_id")])
        out.append([cell("Look for friends again", "friends")])
        return out

    def lines(self):
        if self.page == "home":
            return [[cell("Your name", width=LABEL_W), cell(self.shown("name", self.settings.name), "input:name")],
                    [cell("Host game", "page:host")], [cell("Join game", "page:join")],
                    [cell("Settings", "page:settings")], [cell("Exit", "exit")]]
        if self.page == "settings":
            return self.settings_lines()
        if self.page == "host":
            players = self.settings.max_players
            steam_lines = self.steam_host_lines()
            return ([[cell("Map")]]
                    + self.map_list_lines(self.maps(), picked=self.host_map(), rows=HOST_LIST_ROWS - len(steam_lines))
                    + [[cell("Password", width=LABEL_W),
                        cell(self.shown("host_password", self.host_password, secret=True), "input:host_password")],
                       [cell("Max players", width=LABEL_W),
                        cell("-", "players-", players > MIN_PLAYERS, width=46), cell(str(players)),
                        cell("+", "players+", players < MAX_PLAYERS, width=46)],
                       self.network_line()]
                    + steam_lines
                    + [[cell("Start hosting", "host")], [cell("Back", "back")]])
        if self.page == "join":
            if self.network == "steam":
                where = self.steam_join_lines()
            else:
                where = [[cell("IP address", width=LABEL_W), cell(self.shown("address", self.join_address), "input:address")],
                         [cell("Port", width=LABEL_W), cell(self.shown("port", self.join_port), "input:port")]]
            return ([self.network_line()] + where
                    + [[cell("Password", width=LABEL_W),
                        cell(self.shown("join_password", self.join_password, secret=True), "input:join_password")],
                       [cell("Join", "join")], [cell("Back", "back")]])
        if self.page == "connecting":
            return [[cell(f"Joining {self.host_name()}...")], [cell("Cancel", "cancel")]]
        return []

    def escape(self):
        if self.page == "connecting":
            return "cancel"
        return super().escape()

    def press(self, action):
        if action.startswith("map:"):
            self.settings.host_map = action[4:]
            return None
        if action in ("players-", "players+"):
            step = 1 if action.endswith("+") else -1
            self.settings.max_players = max(MIN_PLAYERS, min(MAX_PLAYERS, self.settings.max_players + step))
            return None
        if action.startswith("network:"):
            self.settings.network = action[8:]
            if self.steam is None:
                self.steam_problem = ""                 # (picking Steam again tries again)
            self.go(self.page)
            return "settings"                           # (kept for next time)
        if action.startswith("friend:"):
            self.join_steam_id = action[7:]
            return None
        if action == "friends":
            self.look_for_friends()
            return None
        if action == "copy_id":
            try:
                pygame.scrap.put_text(str(self.steam.steam_id))
                self.say(f"Copied {self.steam.steam_id}")
            except (pygame.error, AttributeError):
                self.say("Could not copy it", warn=True)
            return None
        if action == "host":
            if self.network == "steam" and not self.use_steam():
                self.say(self.steam_problem[:60], warn=True)
                return None
            if not self.host_map():
                self.say("There are no maps to host", warn=True)
                return None
            if not self.host_password:
                self.say("Type a password for the others to join with", warn=True)
                return None
            self.settings.host_map = self.host_map()
            return "host"
        if action == "join" and self.network == "steam":
            if not self.use_steam():
                self.say(self.steam_problem[:60], warn=True)
                return None
            if not self.join_steam_id:
                self.say("Pick a friend or type the host's SteamID", warn=True)
                return None
            if not self.join_password:
                self.say("Type the host's password", warn=True)
                return None
            return "join"
        if action == "join":
            if not self.join_address:
                self.say("Type the host's IP address", warn=True)
                return None
            if self.port() is None:
                self.say("The port is a number from 1 to 65535", warn=True)
                return None
            if not self.join_password:
                self.say("Type the host's password", warn=True)
                return None
            return "join"
        return super().press(action)                    # pages, settings, cancel, exit

    def port(self):
        """The port typed for joining, or None if it is not one."""
        return int(self.join_port) if self.join_port.isdigit() and 1 <= int(self.join_port) <= 65535 else None

    # ------------------------------------------------------------------ text boxes

    def field_value(self, name):
        if name == "name":
            return self.settings.name
        if name == "address":
            return self.join_address
        if name == "port":
            return self.join_port
        if name == "steam_id":
            return self.join_steam_id
        if name in ("host_password", "join_password"):
            return getattr(self, name)
        return super().field_value(name)

    def field_accepts(self, name, char):
        if name == "name":
            return True
        if name == "address":
            return char in ADDRESS_CHARS
        if name in ("port", "steam_id"):
            return char.isdigit()
        if name in ("host_password", "join_password"):
            return True
        return super().field_accepts(name, char)

    def field_max(self, name):
        return {"name": MAX_PLAYER_NAME, "address": 64, "port": 5, "steam_id": 20, "host_password": 32,
                "join_password": 32}.get(name, super().field_max(name))

    def set_field(self, name, text):
        if name == "name":
            self.settings.name = clean_name(text)
            return "settings"                           # (kept for next time)
        if name == "address":
            self.join_address = text.strip()
            return None
        if name == "port":
            self.join_port = text
            return None
        if name == "steam_id":
            self.join_steam_id = text
            return None
        if name in ("host_password", "join_password"):
            setattr(self, name, text)
            return None
        return super().set_field(name, text)

    def shown_text(self, item):
        return item.label if item.action != "input:sensitivity" else super().shown_text(item)
