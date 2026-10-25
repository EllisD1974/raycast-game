"""The in-game menu: Esc opens it over the game.

Pages: the main page (Resume, Settings, Host settings for the host, Exit), Settings (mouse sensitivity: a
slider to drag and a box to type the number in; fullscreen), Host settings (who is playing, Change map) and the list of maps to change to. The menu only
draws itself and says what was asked for: Menu.handle() returns "resume", "exit", "settings" (a setting
changed: apply and save them) or "map:<path>" (the host wants everyone moved to that map), and main.py does
it. The player's settings are kept between runs in a small file (GameSettings).
"""
import json
import os
from dataclasses import asdict, dataclass

import pygame

SETTINGS_PATH = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".config"),
                             "raycast-game", "game.json")
MIN_SENSITIVITY, MAX_SENSITIVITY = 0.1, 5.0     # times the standard mouse sensitivity
SLIDER_STEP = 0.05                              # the slider moves the sensitivity in steps of this
BUTTON_W, BUTTON_H, GAP = 360, 46, 12
INPUT_W = 90                                    # the box the sensitivity can be typed into, beside its slider
LIST_ROWS = 8                                   # maps shown at once in the Change map list
SHADE = (0, 0, 0, 160)
PANEL, EDGE = (32, 34, 42, 235), (90, 94, 110)
BUTTON, BUTTON_HOT, BUTTON_OFF = (62, 65, 76), (88, 92, 108), (46, 48, 56)
TRACK, FIELD = (70, 74, 88), (22, 24, 30)
TEXT, DIM, ACCENT, WARN = (230, 230, 235), (150, 152, 162), (255, 205, 60), (255, 120, 100)
TITLES = {"main": "Paused", "settings": "Settings", "host": "Host settings", "maps": "Change map"}
BACK = {"settings": "main", "host": "main", "maps": "host"}     # where Back (or Esc) goes from each page


@dataclass
class GameSettings:
    """The player's own settings, kept between runs."""
    sensitivity: float = 1.0                    # times the standard mouse sensitivity
    fullscreen: bool = False

    @classmethod
    def load(cls, path=SETTINGS_PATH):
        """The settings saved at `path`, or the defaults if there are none (or they cannot be read)."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            sensitivity = float(data.get("sensitivity", 1.0))
            return cls(max(MIN_SENSITIVITY, min(MAX_SENSITIVITY, sensitivity)), bool(data.get("fullscreen", False)))
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()

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
    """One line of a page: a button (with an action), a line of text (action None), or the sensitivity's slider
    ("slider:") or the box its number is typed into ("input:")."""
    rect: pygame.Rect
    label: str
    action: str = None
    enabled: bool = True
    color: tuple = TEXT

    @property
    def kind(self):
        if not self.action:
            return "text"
        return self.action.split(":")[0] if self.action.startswith(("slider:", "input:")) else "button"


class Menu:
    def __init__(self, settings, is_host=False, map_path=None, players=lambda: 1):
        """`map_path` is the map being played (its folder holds the maps the host can change to), and `players`
        says how many are in the game (shown to the host)."""
        self.settings = settings
        self.is_host = is_host
        self.map_path = map_path
        self.players = players
        self.open = False
        self.page = "main"
        self.scroll = 0                         # first map shown in the Change map list
        self.message, self.message_color = "", DIM
        self.dragging = False                   # the sensitivity slider is being dragged
        self.typing = None                      # text being typed into the sensitivity box (None: not typing)
        self.font = pygame.font.Font(None, 30)
        self.title_font = pygame.font.Font(None, 46)

    def show(self):
        self.open, self.page, self.message = True, "main", ""
        self.dragging, self.typing = False, None

    def hide(self):
        self.open = False

    def say(self, text, warn=False):
        self.message, self.message_color = text, WARN if warn else DIM

    # ------------------------------------------------------------------ what each page holds

    def maps(self):
        """The map files in the folder of the map being played, by name."""
        if not self.map_path:
            return []
        folder = os.path.dirname(os.path.abspath(self.map_path))
        try:
            return sorted((n for n in os.listdir(folder) if n.lower().endswith(".json")), key=str.lower)
        except OSError:
            return []

    def items(self, size):
        """The lines of the open page, laid out in the middle of a window of `size`."""
        lines = []                              # (label, action, enabled, color, half): "left" / "right" share a row
        if self.page == "main":
            lines += [("Resume", "resume"), ("Settings", "page:settings")]
            if self.is_host:
                lines.append(("Host settings", "page:host"))
            lines.append(("Exit game", "exit"))
        elif self.page == "settings":
            shown = self.typing if self.typing is not None else f"{self.settings.sensitivity:g}"
            lines += [("Mouse sensitivity", None),
                      ("", "slider:sensitivity", True, TEXT, "left"),
                      (shown, "input:sensitivity", True, TEXT, "right"),
                      (f"Fullscreen: {'on' if self.settings.fullscreen else 'off'}", "fullscreen"),
                      ("Back", "back")]
        elif self.page == "host":
            count = self.players()
            lines += [(f"{count} player{'s' if count != 1 else ''} in the game", None),
                      (f"Map: {os.path.basename(self.map_path) if self.map_path else '(none)'}", None),
                      ("Change map", "page:maps"), ("Back", "back")]
        elif self.page == "maps":
            names = self.maps()
            current = os.path.basename(self.map_path or "")
            self.scroll = max(0, min(self.scroll, len(names) - LIST_ROWS))
            lines.append(("Everyone moves to the map picked", None))
            for name in names[self.scroll:self.scroll + LIST_ROWS]:
                playing = name == current
                lines.append((name[:-5] + ("  (playing)" if playing else ""), f"map:{name}", not playing))
            if not names:
                lines.append(("No maps found", None))
            if len(names) > LIST_ROWS:
                lines.append((f"{self.scroll + 1}-{min(len(names), self.scroll + LIST_ROWS)} of {len(names)}"
                              "  (the wheel scrolls)", None))
            lines.append(("Back", "back"))
        lines = [tuple(line) + (True, TEXT, None)[len(line) - 2:] for line in lines]
        rows = sum(1 for line in lines if line[4] != "right")
        top = size[1] // 2 - (rows * (BUTTON_H + GAP)) // 2 + 30
        x = size[0] // 2 - BUTTON_W // 2
        out, y = [], top
        for label, action, enabled, color, half in lines:
            if half == "right":
                y -= BUTTON_H + GAP                             # beside the "left" one before it
            left = x + (BUTTON_W - INPUT_W if half == "right" else 0)
            width = {"left": BUTTON_W - INPUT_W - GAP, "right": INPUT_W}.get(half, BUTTON_W)
            out.append(Item(pygame.Rect(left, y, width, BUTTON_H), label, action, enabled, color))
            y += BUTTON_H + GAP
        return out

    def panel(self, size):
        """The box the page sits in."""
        items = self.items(size)
        top = min(i.rect.top for i in items) - 80
        bottom = max(i.rect.bottom for i in items) + (52 if self.message else 24)
        return pygame.Rect(size[0] // 2 - BUTTON_W // 2 - 30, top, BUTTON_W + 60, bottom - top)

    # ------------------------------------------------------------------ input

    def handle(self, event, size):
        """React to one event while the menu is open. Returns what main.py should do, or None."""
        if self.typing is not None:                     # typing the sensitivity takes the keys
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
            if self.page == "main":
                return "resume"
            self.page, self.message = BACK[self.page], ""
        elif event.type == pygame.MOUSEWHEEL and self.page == "maps":
            self.scroll = max(0, self.scroll - event.y)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for item in self.items(size):
                if item.action and item.enabled and item.rect.collidepoint(event.pos):
                    if item.kind == "slider":
                        self.dragging = True
                        self.slide_to(event.pos[0], size)
                        return None
                    if item.kind == "input":
                        self.typing = f"{self.settings.sensitivity:g}"
                        return None
                    return self.press(item.action)
        return None

    # ------------------------------------------------------------------ the sensitivity: slider and typed number

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
        self.settings.sensitivity = round(round(value / SLIDER_STEP) * SLIDER_STEP, 4)
        self.settings.sensitivity = max(MIN_SENSITIVITY, min(MAX_SENSITIVITY, self.settings.sensitivity))

    def type_key(self, event):
        """A key while typing the sensitivity: digits and a point add to it, Enter uses it, Esc forgets it."""
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return self.finish_typing(True)
        if event.key == pygame.K_ESCAPE:
            return self.finish_typing(False)
        if event.key == pygame.K_BACKSPACE:
            self.typing = self.typing[:-1]
        elif getattr(event, "unicode", "") and event.unicode in "0123456789." and len(self.typing) < 6:
            if event.unicode != "." or "." not in self.typing:
                self.typing += event.unicode
        return None

    def finish_typing(self, keep):
        """Stop typing the sensitivity. Keeping it uses the number (held to the slider's range); something that is
        not a number is said so and changes nothing. Returns "settings" if it changed."""
        text, self.typing = self.typing, None
        if not keep:
            return None
        try:
            value = float(text)
        except ValueError:
            self.say("Type a number, like 1.5", warn=True)
            return None
        self.settings.sensitivity = round(max(MIN_SENSITIVITY, min(MAX_SENSITIVITY, value)), 4)
        self.say("")
        return "settings"

    def press(self, action):
        """Do what a button says on the menu itself (pages, settings); return what main.py should do."""
        if action.startswith("page:"):
            self.page, self.message, self.scroll = action[5:], "", 0
            return None
        if action == "back":
            self.page, self.message = BACK[self.page], ""
            return None
        if action == "fullscreen":
            self.settings.fullscreen = not self.settings.fullscreen
            return "settings"
        if action.startswith("map:"):
            return "map:" + os.path.join(os.path.dirname(os.path.abspath(self.map_path)), action[4:])
        return action                                           # resume, exit

    # ------------------------------------------------------------------ drawing

    def draw(self, surface, mouse=(-1, -1)):
        """Draw the open page over everything on `surface` (the size of the window)."""
        size = surface.get_size()
        shade = pygame.Surface(size, pygame.SRCALPHA)
        shade.fill(SHADE)
        surface.blit(shade, (0, 0))
        box = self.panel(size)
        back = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(back, PANEL, back.get_rect(), border_radius=10)
        surface.blit(back, box)
        pygame.draw.rect(surface, EDGE, box, 1, border_radius=10)
        title = self.title_font.render(TITLES[self.page], True, ACCENT)
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
                pygame.draw.rect(surface, BUTTON_HOT if hot else (BUTTON if item.enabled else BUTTON_OFF), item.rect,
                                 border_radius=6)
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
        """The box the sensitivity is typed into: its number, or what is being typed with a caret."""
        typing = self.typing is not None
        pygame.draw.rect(surface, FIELD, item.rect, border_radius=6)
        pygame.draw.rect(surface, ACCENT if typing else EDGE, item.rect, 2, border_radius=6)
        text = self.font.render(item.label + ("|" if typing else "x"), True, TEXT)
        surface.blit(text, text.get_rect(center=item.rect.center))
