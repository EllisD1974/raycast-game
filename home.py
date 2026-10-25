"""The home screen, shown when the game is started on its own (not from the map editor's Play, nor with --map,
--host or --join): Host game, Join game, Settings and Exit.

Host game picks a map from the maps folder, a password (needed) and the most players to let in, and Join game takes
the host's IP address (empty to start with), its port (7777 to start with) and its password. Like the in-game menu (menu.Pages), Home only lays itself
out and says what was asked for: handle() returns "host", "join", "cancel" (stop joining), "settings" or "exit", and
main.py does it, reading what was chosen from the Home and its GameSettings.
"""
import os

from menu import MAX_PLAYERS, MIN_PLAYERS, Pages, cell, map_files
from net import DEFAULT_PORT

ADDRESS_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")   # an IP address or host name
LABEL_W = 130                                   # the label in front of a text box
HOST_LIST_ROWS = 5                              # maps shown at once on the Host page


class Home(Pages):
    TITLES = {"home": "Raycaster", "settings": "Settings", "host": "Host a game", "join": "Join a game",
              "connecting": "Joining"}
    BACK = {"settings": "home", "host": "home", "join": "home", "connecting": "join"}
    FIRST = "home"

    def __init__(self, settings, maps_folder):
        super().__init__(settings)
        self.maps_folder = maps_folder
        self.host_password = ""
        self.join_address = ""                  # the host's IP address, typed in each time
        self.join_port = str(DEFAULT_PORT)      # its port, 7777 unless the host picked another
        self.join_password = ""
        self.open = True

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

    def lines(self):
        if self.page == "home":
            return [[cell("Host game", "page:host")], [cell("Join game", "page:join")],
                    [cell("Settings", "page:settings")], [cell("Exit", "exit")]]
        if self.page == "settings":
            return self.settings_lines()
        if self.page == "host":
            players = self.settings.max_players
            return ([[cell("Map")]]
                    + self.map_list_lines(self.maps(), picked=self.host_map(), rows=HOST_LIST_ROWS)
                    + [[cell("Password", width=LABEL_W),
                        cell(self.shown("host_password", self.host_password, secret=True), "input:host_password")],
                       [cell("Max players", width=LABEL_W),
                        cell("-", "players-", players > MIN_PLAYERS, width=46), cell(str(players)),
                        cell("+", "players+", players < MAX_PLAYERS, width=46)],
                       [cell("Start hosting", "host")], [cell("Back", "back")]])
        if self.page == "join":
            return [[cell("IP address", width=LABEL_W), cell(self.shown("address", self.join_address), "input:address")],
                    [cell("Port", width=LABEL_W), cell(self.shown("port", self.join_port), "input:port")],
                    [cell("Password", width=LABEL_W),
                     cell(self.shown("join_password", self.join_password, secret=True), "input:join_password")],
                    [cell("Join", "join")], [cell("Back", "back")]]
        if self.page == "connecting":
            return [[cell(f"Joining {self.join_address}:{self.join_port}...")], [cell("Cancel", "cancel")]]
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
        if action == "host":
            if not self.host_map():
                self.say("There are no maps to host", warn=True)
                return None
            if not self.host_password:
                self.say("Type a password for the others to join with", warn=True)
                return None
            self.settings.host_map = self.host_map()
            return "host"
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
        if name == "address":
            return self.join_address
        if name == "port":
            return self.join_port
        if name in ("host_password", "join_password"):
            return getattr(self, name)
        return super().field_value(name)

    def field_accepts(self, name, char):
        if name == "address":
            return char in ADDRESS_CHARS
        if name == "port":
            return char.isdigit()
        if name in ("host_password", "join_password"):
            return True
        return super().field_accepts(name, char)

    def field_max(self, name):
        return {"address": 64, "port": 5, "host_password": 32, "join_password": 32}.get(name, super().field_max(name))

    def set_field(self, name, text):
        if name == "address":
            self.join_address = text.strip()
            return None
        if name == "port":
            self.join_port = text
            return None
        if name in ("host_password", "join_password"):
            setattr(self, name, text)
            return None
        return super().set_field(name, text)

    def shown_text(self, item):
        return item.label if item.action != "input:sensitivity" else super().shown_text(item)
