"""Menus drawn over the game window: the in-game menu (Esc) and, built the same way, the home screen (home.py).

Pages lays out a page's rows of buttons, text, text boxes and a slider in the middle of the window, draws them, and
turns clicks and keys into actions; a page's rows come from lines(). The in-game Menu has the main page (Resume,
Settings, Host settings for the host, Exit or Leave game), Settings (mouse sensitivity: a slider to drag and a box to
type the number in; fullscreen), Host settings (who is playing, Change map) and the list of maps to change to.
Menu.handle() returns "resume", "exit", "settings" (a setting changed: apply and save them) or "map:<path>" (the
host wants everyone moved to that map), and main.py does it. The player's settings are kept between runs in a
small file (GameSettings).
"""
import json
import os
from dataclasses import asdict, dataclass, fields

import pygame

SETTINGS_PATH = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".config"),
                             "raycast-game", "game.json")
MIN_SENSITIVITY, MAX_SENSITIVITY = 0.1, 5.0     # times the standard mouse sensitivity
SLIDER_STEP = 0.05                              # the slider moves the sensitivity in steps of this
MIN_PLAYERS, MAX_PLAYERS = 2, 16                # the most players a host may let in (themselves included)
BUTTON_W, BUTTON_H, GAP = 360, 46, 12
INPUT_W = 90                                    # the box the sensitivity can be typed into, beside its slider
LIST_ROWS = 8                                   # maps shown at once in a list of maps
SHADE = (0, 0, 0, 160)
PANEL, EDGE = (32, 34, 42, 235), (90, 94, 110)
BUTTON, BUTTON_HOT, BUTTON_OFF, BUTTON_ON = (62, 65, 76), (88, 92, 108), (46, 48, 56), (70, 110, 190)
TRACK, FIELD = (70, 74, 88), (22, 24, 30)
TEXT, DIM, ACCENT, WARN = (230, 230, 235), (150, 152, 162), (255, 205, 60), (255, 120, 100)


@dataclass
class GameSettings:
    """The player's own settings, kept between runs, and what they last chose to host with (passwords are never
    kept)."""
    sensitivity: float = 1.0                    # times the standard mouse sensitivity
    fullscreen: bool = False
    host_map: str = ""                          # the map file (name) last hosted
    max_players: int = 8                        # the most players last allowed in when hosting
    name: str = ""                              # what the player is called in the game

    @classmethod
    def load(cls, path=SETTINGS_PATH):
        """The settings saved at `path`, or the defaults for anything missing or unreadable."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return cls()
        except (OSError, ValueError):
            return cls()
        settings = cls()
        for f in fields(cls):
            value = data.get(f.name, getattr(settings, f.name))
            try:
                setattr(settings, f.name, type(getattr(settings, f.name))(value))
            except (TypeError, ValueError):
                pass
        settings.sensitivity = max(MIN_SENSITIVITY, min(MAX_SENSITIVITY, settings.sensitivity))
        settings.max_players = max(MIN_PLAYERS, min(MAX_PLAYERS, settings.max_players))
        return settings

    def save(self, path=SETTINGS_PATH):
        """Keep the settings at `path`. Not being able to write them changes nothing else."""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f)
        except OSError:
            pass


@dataclass
class Item:
    """One cell of a page: a button (with an action), text (action None), a slider ("slider:<name>") or a text box
    ("input:<name>")."""
    rect: pygame.Rect
    label: str
    action: str = None
    enabled: bool = True
    color: tuple = TEXT
    selected: bool = False

    @property
    def kind(self):
        if not self.action:
            return "text"
        return self.action.split(":")[0] if self.action.startswith(("slider:", "input:")) else "button"


def cell(label, action=None, enabled=True, color=TEXT, width=None, selected=False):
    """One cell of a row in Pages.lines(): `width` in pixels, or None to share what the row has left."""
    return (label, action, enabled, color, width, selected)


def map_files(folder):
    """The map files in `folder`, by name."""
    try:
        return sorted((n for n in os.listdir(folder) if n.lower().endswith(".json")), key=str.lower)
    except OSError:
        return []


class Pages:
    """A set of pages of buttons over the game window. Subclasses give each page's rows (lines()), its title
    (TITLES), where Back goes (BACK) and what their own buttons do (press())."""
    TITLES = {}
    BACK = {}
    FIRST = "main"

    def __init__(self, settings):
        self.settings = settings
        self.open = False
        self.page = self.FIRST
        self.scroll = 0                         # first map shown in a list of maps
        self.message, self.message_color = "", DIM
        self.dragging = False                   # the sensitivity slider is being dragged
        self.typing = None                      # text being typed into a box (None: not typing)
        self.typing_field = None                # ... and which box
        self.font = pygame.font.Font(None, 30)
        self.title_font = pygame.font.Font(None, 46)

    def show(self):
        self.open, self.page, self.message = True, self.FIRST, ""
        self.dragging, self.typing = False, None

    def hide(self):
        self.open = False

    def say(self, text, warn=False):
        self.message, self.message_color = text, WARN if warn else DIM

    def go(self, page):
        self.page, self.message, self.scroll, self.typing = page, "", 0, None

    # ------------------------------------------------------------------ what the pages hold

    def lines(self):
        """The rows of the open page: each a list of cell()s."""
        return []

    def settings_lines(self):
        """The Settings page's rows (both menus have it)."""
        shown = self.typing if self.typing_field == "sensitivity" and self.typing is not None \
            else f"{self.settings.sensitivity:g}"
        return [[cell("Mouse sensitivity")],
                [cell("", "slider:sensitivity", width=BUTTON_W - INPUT_W - GAP),
                 cell(shown, "input:sensitivity", width=INPUT_W)],
                [cell(f"Fullscreen: {'on' if self.settings.fullscreen else 'off'}", "fullscreen")],
                [cell("Back", "back")]]

    def map_list_lines(self, names, current="", picked="", rows=LIST_ROWS, playing_note=""):
        """Rows listing maps (scrolled by the wheel): the one being played greyed out with `playing_note`, the one
        picked highlighted."""
        self.scroll = max(0, min(self.scroll, len(names) - rows))
        out = []
        for name in names[self.scroll:self.scroll + rows]:
            playing = bool(playing_note) and name == current
            out.append([cell(name[:-5] + (f"  ({playing_note})" if playing else ""), f"map:{name}", not playing,
                             selected=name == picked)])
        if not names:
            out.append([cell("No maps found", color=DIM)])
        if len(names) > rows:
            out.append([cell(f"{self.scroll + 1}-{min(len(names), self.scroll + rows)} of {len(names)}"
                             "  (the wheel scrolls)", color=DIM)])
        return out

    def items(self, size):
        """The cells of the open page, laid out in the middle of a window of `size`."""
        rows = self.lines()
        top = size[1] // 2 - (len(rows) * (BUTTON_H + GAP)) // 2 + 30
        x0 = size[0] // 2 - BUTTON_W // 2
        out = []
        for r, row in enumerate(rows):
            fixed = sum(c[4] for c in row if c[4] is not None)
            free = [c for c in row if c[4] is None]
            share = (BUTTON_W - fixed - GAP * (len(row) - 1)) // max(1, len(free))
            x, y = x0, top + r * (BUTTON_H + GAP)
            for label, action, enabled, color, width, selected in row:
                w = width if width is not None else share
                out.append(Item(pygame.Rect(x, y, w, BUTTON_H), label, action, enabled, color, selected))
                x += w + GAP
        return out

    def panel(self, size):
        """The box the page sits in."""
        items = self.items(size)
        top = min(i.rect.top for i in items) - 80
        bottom = max(i.rect.bottom for i in items) + (52 if self.message else 24)
        return pygame.Rect(size[0] // 2 - BUTTON_W // 2 - 30, top, BUTTON_W + 60, bottom - top)

    # ------------------------------------------------------------------ input

    def handle(self, event, size):
        """React to one event while the page is up. Returns what the caller should do, or None."""
        if self.typing is not None:                     # typing into a box takes the keys
            if event.type == pygame.KEYDOWN:
                return self.type_key(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                changed = self.finish_typing(True)       # clicking away keeps what was typed
                return self.handle(event, size) or changed
            return None
        if self.dragging:
            if event.type == pygame.MOUSEMOTION:
                self.slide_to(event.pos[0], size)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.dragging = False
                return "settings"                       # (applied and saved once, when it is let go)
            return None
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return self.escape()
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for item in self.items(size):
                if item.action and item.enabled and item.rect.collidepoint(event.pos):
                    if item.kind == "slider":
                        self.dragging = True
                        self.slide_to(event.pos[0], size)
                        return None
                    if item.kind == "input":
                        self.typing_field = item.action[6:]
                        self.typing = self.field_value(self.typing_field)
                        return None
                    return self.press(item.action)
        return None

    def escape(self):
        """Esc: back a page (the first page's own Esc is the subclass's to say)."""
        if self.page in self.BACK:
            self.go(self.BACK[self.page])
        return None

    def press(self, action):
        """Do what a button says on the pages themselves; return what the caller should do."""
        if action.startswith("page:"):
            self.go(action[5:])
            return None
        if action == "back":
            self.go(self.BACK[self.page])
            return None
        if action == "fullscreen":
            self.settings.fullscreen = not self.settings.fullscreen
            return "settings"
        return action

    # ------------------------------------------------------------------ text boxes

    def field_value(self, name):
        """What a text box holds when typing into it starts."""
        return f"{self.settings.sensitivity:g}" if name == "sensitivity" else ""

    def field_accepts(self, name, char):
        """True if `char` may be typed into box `name`."""
        return char in "0123456789." and (char != "." or "." not in self.typing)

    def field_max(self, name):
        return 6

    def set_field(self, name, text):
        """Use what was typed into box `name`; return what the caller should do."""
        try:
            value = float(text)
        except ValueError:
            self.say("Type a number, like 1.5", warn=True)
            return None
        self.settings.sensitivity = round(max(MIN_SENSITIVITY, min(MAX_SENSITIVITY, value)), 4)
        self.say("")
        return "settings"

    def type_key(self, event):
        """A key while typing: allowed characters add to the box, Enter uses it, Esc forgets it."""
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return self.finish_typing(True)
        if event.key == pygame.K_ESCAPE:
            return self.finish_typing(False)
        if event.key == pygame.K_BACKSPACE:
            self.typing = self.typing[:-1]
        elif getattr(event, "unicode", "") and event.unicode.isprintable() and len(self.typing) < \
                self.field_max(self.typing_field) and self.field_accepts(self.typing_field, event.unicode):
            self.typing += event.unicode
        return None

    def finish_typing(self, keep):
        """Stop typing; keeping it hands the text to set_field (returns what it says to do)."""
        text, name, self.typing = self.typing, self.typing_field, None
        return self.set_field(name, text) if keep else None

    # ------------------------------------------------------------------ the sensitivity slider

    def slider_rect(self, size):
        return next(item.rect for item in self.items(size) if item.kind == "slider")

    @staticmethod
    def track(rect):
        """The part of the slider's rect the handle runs along (x from, x to)."""
        return rect.x + 14, rect.right - 14

    def slide_to(self, x, size):
        """Set the sensitivity from where along the slider screen column `x` is, in steps of SLIDER_STEP."""
        start, end = self.track(self.slider_rect(size))
        fraction = max(0.0, min(1.0, (x - start) / max(1, end - start)))
        value = MIN_SENSITIVITY + fraction * (MAX_SENSITIVITY - MIN_SENSITIVITY)
        value = round(round(value / SLIDER_STEP) * SLIDER_STEP, 4)
        self.settings.sensitivity = max(MIN_SENSITIVITY, min(MAX_SENSITIVITY, value))

    # ------------------------------------------------------------------ drawing

    def shown_text(self, item):
        """What a text box shows (subclasses hide passwords)."""
        if item.action == "input:sensitivity":
            return item.label + ("" if self.typing_field == "sensitivity" and self.typing is not None else "x")
        return item.label

    def draw(self, surface, mouse=(-1, -1), shade=True):
        """Draw the open page over everything on `surface` (the size of the window)."""
        size = surface.get_size()
        if shade:
            veil = pygame.Surface(size, pygame.SRCALPHA)
            veil.fill(SHADE)
            surface.blit(veil, (0, 0))
        box = self.panel(size)
        back = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(back, PANEL, back.get_rect(), border_radius=10)
        surface.blit(back, box)
        pygame.draw.rect(surface, EDGE, box, 1, border_radius=10)
        title = self.title_font.render(self.TITLES.get(self.page, ""), True, ACCENT)
        surface.blit(title, title.get_rect(midtop=(box.centerx, box.y + 22)))
        for item in self.items(size):
            if item.kind == "slider":
                self.draw_slider(surface, item.rect, mouse)
                continue
            if item.kind == "input":
                self.draw_input(surface, item)
                continue
            if item.action:
                hot = item.enabled and item.rect.collidepoint(mouse)
                color = BUTTON_ON if item.selected else (BUTTON_HOT if hot else (BUTTON if item.enabled else BUTTON_OFF))
                pygame.draw.rect(surface, color, item.rect, border_radius=6)
            text = self.font.render(item.label, True, item.color if item.enabled else DIM)
            surface.blit(text, text.get_rect(center=item.rect.center))
        if self.message:
            note = self.font.render(self.message, True, self.message_color)
            surface.blit(note, note.get_rect(midbottom=(box.centerx, box.bottom - 14)))

    def draw_slider(self, surface, rect, mouse):
        """The sensitivity slider: a track filled up to the handle, which sits at the current value."""
        start, end = self.track(rect)
        fraction = (self.settings.sensitivity - MIN_SENSITIVITY) / (MAX_SENSITIVITY - MIN_SENSITIVITY)
        handle = round(start + fraction * (end - start))
        middle = rect.centery
        pygame.draw.rect(surface, TRACK, (start, middle - 3, end - start, 6), border_radius=3)
        pygame.draw.rect(surface, ACCENT, (start, middle - 3, handle - start, 6), border_radius=3)
        hot = self.dragging or rect.collidepoint(mouse)
        pygame.draw.circle(surface, TEXT if hot else (200, 200, 208), (handle, middle), 11)
        pygame.draw.circle(surface, ACCENT, (handle, middle), 11, 2)

    def draw_input(self, surface, item):
        """A text box: what it holds, or what is being typed with a caret (an empty one says to click it)."""
        typing = self.typing is not None and item.action == f"input:{self.typing_field}"
        pygame.draw.rect(surface, FIELD, item.rect, border_radius=6)
        pygame.draw.rect(surface, ACCENT if typing else EDGE, item.rect, 2, border_radius=6)
        if item.label or typing:
            text = self.font.render(self.shown_text(item) + ("|" if typing else ""), True, TEXT)
        else:
            text = self.font.render("(click to type)", True, DIM)
        surface.blit(text, text.get_rect(center=item.rect.center))


class Menu(Pages):
    """The in-game menu."""
    TITLES = {"main": "Paused", "settings": "Settings", "host": "Host settings", "maps": "Change map"}
    BACK = {"settings": "main", "host": "main", "maps": "host"}

    def __init__(self, settings, is_host=False, map_path=None, players=lambda: 1, leave_label="Exit game"):
        """`map_path` is the map being played (its folder holds the maps the host can change to), `players` says
        how many are in the game (shown to the host), and `leave_label` names the button that ends the game."""
        super().__init__(settings)
        self.is_host = is_host
        self.map_path = map_path
        self.players = players
        self.leave_label = leave_label

    def maps(self):
        """The map files in the folder of the map being played, by name."""
        return map_files(os.path.dirname(os.path.abspath(self.map_path))) if self.map_path else []

    def lines(self):
        if self.page == "main":
            rows = [[cell("Resume", "resume")], [cell("Settings", "page:settings")]]
            if self.is_host:
                rows.append([cell("Host settings", "page:host")])
            return rows + [[cell(self.leave_label, "exit")]]
        if self.page == "settings":
            return self.settings_lines()
        if self.page == "host":
            count = self.players()
            return [[cell(f"{count} player{'s' if count != 1 else ''} in the game")],
                    [cell(f"Map: {os.path.basename(self.map_path) if self.map_path else '(none)'}")],
                    [cell("Change map", "page:maps")], [cell("Back", "back")]]
        if self.page == "maps":
            return ([[cell("Everyone moves to the map picked")]]
                    + self.map_list_lines(self.maps(), os.path.basename(self.map_path or ""), playing_note="playing")
                    + [[cell("Back", "back")]])
        return []

    def escape(self):
        if self.page == "main":
            return "resume"
        return super().escape()

    def press(self, action):
        if action.startswith("map:"):
            return "map:" + os.path.join(os.path.dirname(os.path.abspath(self.map_path)), action[4:])
        return super().press(action)                    # pages, settings, resume, exit
