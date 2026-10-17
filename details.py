"""The editor's Details pane: a docked panel listing the editable settings of whatever is selected.

It knows nothing about what is selected. The editor hands it a title and a list of Field records
(a label, a kind and how to read and change the value) and the pane lays them out, draws them and
tells the editor what was hit. Today it shows the settings of one item (entity); selecting other
things later (several items, a wall, a floor) only means giving it different fields.

Field kinds:
    num   a number, stepped by - / + buttons, the mouse wheel, or typed in (click the value)
    enum  one of a fixed list of choices, stepped through with - / + or by clicking the value
    tile  an atlas tile index, shown as its picture, stepped with - / +
"""
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Callable

import pygame

PANE_WIDTH = 270
ROW_H = 34
TITLE_H = 34
BUTTON_W = 28


@dataclass
class Field:
    key: str
    label: str
    kind: str                                   # "num", "enum" or "tile"
    get: Callable[[], Any]
    set: Callable[[Any], None]
    step: float = 1.0                           # num: size of one - / + click or wheel notch
    low: float = 0.0
    high: float = 100.0
    choices: tuple = ()                         # enum: the options, in order
    labels: dict = dataclass_field(default_factory=dict)    # enum: display text per choice
    unit: str = ""                              # num: shown after the value

    def text(self):
        value = self.get()
        if self.kind == "enum":
            return self.labels.get(value, str(value))
        if self.kind == "tile":
            return f"#{value + 1}"
        return f"{value:g}{self.unit}"

    def stepped(self, direction, notches=1):
        """The value after `notches` steps up (direction +1) or down (-1)."""
        value = self.get()
        if self.kind == "enum":
            i = self.choices.index(value) if value in self.choices else 0
            return self.choices[(i + direction * notches) % len(self.choices)]
        if self.kind == "tile":
            return max(self.low, min(self.high, value + direction * notches))
        return round(max(self.low, min(self.high, value + direction * notches * self.step)), 4)

    def parsed(self, text):
        """The number typed for a num field, clamped; None if the text is not a number."""
        try:
            return round(max(self.low, min(self.high, float(text.replace(",", ".")))), 4)
        except ValueError:
            return None


@dataclass
class Row:
    field: Field
    rect: pygame.Rect
    minus: pygame.Rect
    value: pygame.Rect
    plus: pygame.Rect


def rows_for(rect, fields):
    """Place one Row per field down the pane (below its title)."""
    rows = []
    for i, f in enumerate(fields):
        y = rect.y + TITLE_H + i * ROW_H
        row = pygame.Rect(rect.x, y, rect.w, ROW_H)
        plus = pygame.Rect(rect.right - 8 - BUTTON_W, y + 3, BUTTON_W, ROW_H - 6)
        value = pygame.Rect(plus.x - 4 - 84, y + 3, 84, ROW_H - 6)
        minus = pygame.Rect(value.x - 4 - BUTTON_W, y + 3, BUTTON_W, ROW_H - 6)
        rows.append(Row(f, row, minus, value, plus))
    return rows


def button_rect(rect, rows):
    """The Delete button under the last row."""
    y = (rows[-1].rect.bottom if rows else rect.y + TITLE_H) + 10
    return pygame.Rect(rect.x + 10, y, rect.w - 20, 32)


def draw(screen, rect, title, rows, theme, fonts, editing=None, hover=None, tile_surface=None,
         notes=(), button_label="Delete"):
    """Draw the pane. `editing` is (field key, text typed so far) while a number is being typed;
    `hover` is the mouse position; `tile_surface(index)` gives the picture for a tile field."""
    font, small = fonts
    pygame.draw.rect(screen, theme["panel"], rect)
    pygame.draw.line(screen, theme["grid"], rect.topleft, rect.bottomleft)
    screen.blit(font.render(title, True, theme["accent"]), (rect.x + 10, rect.y + 8))
    for row in rows:
        f = row.field
        screen.blit(font.render(f.label, True, theme["text"]), (rect.x + 10, row.rect.y + 8))
        for button, label in ((row.minus, "-"), (row.plus, "+")):
            hot = hover is not None and button.collidepoint(hover)
            pygame.draw.rect(screen, theme["button_hot"] if hot else theme["button"], button, border_radius=4)
            glyph = font.render(label, True, theme["text"])
            screen.blit(glyph, glyph.get_rect(center=button.center))
        typing = editing is not None and editing[0] == f.key
        hot = hover is not None and row.value.collidepoint(hover)
        pygame.draw.rect(screen, theme["field_edit"] if typing else (theme["button_hot"] if hot else theme["field"]),
                         row.value, border_radius=4)
        if typing:
            pygame.draw.rect(screen, theme["accent"], row.value, 1, border_radius=4)
        if f.kind == "tile" and tile_surface is not None and not typing:
            picture = pygame.transform.scale(tile_surface(f.get()), (row.value.h - 4, row.value.h - 4))
            screen.blit(picture, (row.value.x + 4, row.value.y + 2))
            text = small.render(f.text(), True, theme["text"])
            screen.blit(text, text.get_rect(midright=(row.value.right - 6, row.value.centery)))
        else:
            shown = (editing[1] + "|") if typing else f.text()
            text = font.render(shown, True, theme["accent"] if not typing else theme["text"])
            screen.blit(text, text.get_rect(center=row.value.center))
    y = (rows[-1].rect.bottom if rows else rect.y + TITLE_H) + 10
    button = button_rect(rect, rows)
    hot = hover is not None and button.collidepoint(hover)
    pygame.draw.rect(screen, theme["danger_hot"] if hot else theme["danger"], button, border_radius=4)
    label = font.render(button_label, True, theme["text"])
    screen.blit(label, label.get_rect(center=button.center))
    y = button.bottom + 10
    for line in notes:
        screen.blit(small.render(line, True, theme["dim"]), (rect.x + 10, y))
        y += 16
