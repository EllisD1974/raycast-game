"""The editor's Details pane: a docked panel listing the editable settings of whatever is selected.

It knows nothing about what is selected. The editor hands it a title and a list of Field records
(a label, a kind and how to read and change the value) and the pane lays them out, draws them and
tells the editor what was hit. Today it shows the settings of one item (entity); selecting other
things later (several items, a wall, a floor) only means giving it different fields.

Field kinds:
    num     a number, stepped by - / + buttons, the mouse wheel, or typed in (click the value)
    enum    one of a fixed list of choices, picked from a drop-down list (click the value), or
            stepped through with - / + or the mouse wheel
    tile    an atlas tile index, shown as its picture, stepped with - / +
    header  a heading row for a group of fields; with an `action` it has a remove button
    menu    a button that opens a drop-down list of choices; picking one calls `set(choice)`
            (used to add things); a menu with no choices is not shown
"""
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Callable

import pygame

PANE_WIDTH = 270
ROW_H = 34
TITLE_H = 34
BUTTON_W = 28
MENU_ITEM_H = 28


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
    action: Callable = None                     # header: called by its remove button
    text_override: str = ""                     # header / menu: the text shown

    def text(self):
        if self.kind in ("header", "menu"):
            return self.text_override or self.label
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
        value = pygame.Rect(plus.x - 4 - 122, y + 3, 122, ROW_H - 6)
        minus = pygame.Rect(value.x - 4 - BUTTON_W, y + 3, BUTTON_W, ROW_H - 6)
        rows.append(Row(f, row, minus, value, plus))
    return rows


def menu_anchor(row):
    """The box a row's drop-down list opens under: the value box (enum) or the whole button (menu)."""
    if row.field.kind == "enum":
        return row.value
    return pygame.Rect(row.minus.x, row.value.y, row.plus.right - row.minus.x, row.value.h)


def menu_rects(row):
    """[(rect, choice)] of the drop-down list that opens under a row."""
    anchor = menu_anchor(row)
    width = max(anchor.w, 130)
    return [(pygame.Rect(anchor.x, anchor.bottom + 2 + i * MENU_ITEM_H, width, MENU_ITEM_H), choice)
            for i, choice in enumerate(row.field.choices)]


def button_rect(rect, rows):
    """The Delete button under the last row."""
    y = (rows[-1].rect.bottom if rows else rect.y + TITLE_H) + 10
    return pygame.Rect(rect.x + 10, y, rect.w - 20, 32)


def draw(screen, rect, title, rows, theme, fonts, editing=None, hover=None, tile_surface=None,
         notes=(), button_label="Delete", open_menu=None):
    """Draw the pane. `editing` is (field key, text typed so far) while a number is being typed;
    `hover` is the mouse position; `tile_surface(index)` gives the picture for a tile field;
    `open_menu` is the key of the field whose drop-down list is showing."""
    font, small = fonts
    pygame.draw.rect(screen, theme["panel"], rect)
    pygame.draw.line(screen, theme["grid"], rect.topleft, rect.bottomleft)
    screen.blit(font.render(title, True, theme["accent"]), (rect.x + 10, rect.y + 8))

    def box(area, colour, border=False):
        pygame.draw.rect(screen, colour, area, border_radius=4)
        if border:
            pygame.draw.rect(screen, theme["accent"], area, 1, border_radius=4)

    def hot(area):
        return hover is not None and area.collidepoint(hover)

    for row in rows:
        f = row.field
        if f.kind == "header":
            pygame.draw.line(screen, theme["grid"], (rect.x + 8, row.rect.y + 2), (rect.right - 8, row.rect.y + 2))
            screen.blit(font.render(f.text(), True, theme["accent"]), (rect.x + 10, row.rect.y + 8))
            if f.action is not None:
                box(row.plus, theme["danger_hot"] if hot(row.plus) else theme["danger"])
                glyph = font.render("x", True, theme["text"])
                screen.blit(glyph, glyph.get_rect(center=row.plus.center))
            continue
        if f.kind == "menu":
            wide = menu_anchor(row)
            box(wide, theme["button_hot"] if hot(wide) or open_menu == f.key else theme["button"])
            label = font.render(f.text(), True, theme["text"])
            screen.blit(label, label.get_rect(center=wide.center))
            continue
        screen.blit(font.render(f.label, True, theme["text"]), (rect.x + 10, row.rect.y + 8))
        for button, label in ((row.minus, "-"), (row.plus, "+")):
            box(button, theme["button_hot"] if hot(button) else theme["button"])
            glyph = font.render(label, True, theme["text"])
            screen.blit(glyph, glyph.get_rect(center=button.center))
        typing = editing is not None and editing[0] == f.key
        box(row.value, theme["field_edit"] if typing else (theme["button_hot"] if hot(row.value) else theme["field"]),
            border=typing or open_menu == f.key)
        if f.kind == "tile" and tile_surface is not None:
            picture = pygame.transform.scale(tile_surface(f.get()), (row.value.h - 4, row.value.h - 4))
            screen.blit(picture, (row.value.x + 4, row.value.y + 2))
            text = small.render(f.text(), True, theme["text"])
            screen.blit(text, text.get_rect(midright=(row.value.right - 6, row.value.centery)))
        elif f.kind == "enum":
            text = font.render(f.text(), True, theme["accent"])
            screen.blit(text, text.get_rect(midleft=(row.value.x + 8, row.value.centery)))
            cx, cy = row.value.right - 10, row.value.centery
            pygame.draw.polygon(screen, theme["dim"], ((cx - 4, cy - 2), (cx + 4, cy - 2), (cx, cy + 3)))
        else:
            shown = (editing[1] + "|") if typing else f.text()
            text = font.render(shown, True, theme["text"] if typing else theme["accent"])
            screen.blit(text, text.get_rect(center=row.value.center))
    button = button_rect(rect, rows)
    box(button, theme["danger_hot"] if hot(button) else theme["danger"])
    label = font.render(button_label, True, theme["text"])
    screen.blit(label, label.get_rect(center=button.center))
    y = button.bottom + 10
    for line in notes:
        screen.blit(small.render(line, True, theme["dim"]), (rect.x + 10, y))
        y += 16
    for row in rows:                                        # an open drop-down list goes on top of everything
        if row.field.key == open_menu:
            items = menu_rects(row)
            if items:
                pygame.draw.rect(screen, theme["field"], items[0][0].unionall([r for r, _c in items]).inflate(4, 4))
            for item, choice in items:
                current = row.field.kind == "enum" and row.field.get() == choice
                box(item, theme["button_hot"] if hot(item) else (theme["field_edit"] if current else theme["field"]))
                text = font.render(row.field.labels.get(choice, str(choice)), True,
                                   theme["accent"] if current else theme["text"])
                screen.blit(text, text.get_rect(midleft=(item.x + 8, item.centery)))
