"""The editor's Details pane: a docked panel listing the editable settings of whatever is selected.

It knows nothing about what is selected. The editor hands it a title and a list of Field records
(a label, a kind and how to read and change the value) and the pane lays them out, draws them and
tells the editor what was hit. Today it shows the settings of one item (entity); selecting other
things later (several items, a wall, a floor) only means giving it different fields.

The pane widens (up to MAX_PANE_WIDTH) for long labels and values; a label that still does not fit
goes on a line of its own above its controls, and text cut short with "..." is handed back to the
editor to show whole on hover. When the rows are taller than the pane they scroll, with a thin bar
at the right, and the Delete button stays at the bottom of the pane until the rows end above it.
scrollbar() / scroll_for() / draw_scrollbar() are the editor's one kind of scroll bar, used for its
other scrolling lists too.

Field kinds:
    num     a number, stepped by - / + buttons, the mouse wheel, or typed in (click the value)
    enum    one of a fixed list of choices, picked from a drop-down list (click the value), or
            stepped through with - / + or the mouse wheel
    tile    an atlas tile index, shown as its picture, stepped with - / +; clicking it makes it the
            field that atlas clicks set (when a pane has more than one tile field)
    text    a name typed in (click it)
    header  a heading row for a group of fields; with an `action` it has a remove button
    info    a read-only row: its label and a value shown dimmed (nothing to click or step)
    menu    a button that opens a drop-down list of choices; picking one calls `set(choice)`
            (used to add things); a menu with no choices is not shown
    button  a full-width button that calls `action`; with `get` it is drawn "on" while that is true,
            and `icon` (an atlas tile index) puts that tile's picture at its left. Used for lists of
            things to pick from.
"""
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Callable

import pygame

PANE_WIDTH = 340                                # the narrowest the pane is
MAX_PANE_WIDTH = 500                            # ... and the widest it grows to for long labels and values
ROW_H = 34
LABEL_LINE_H = 20                               # a label too long for its row goes on a line of its own this tall
VALUE_W, MAX_VALUE_W = 118, 200                 # the value boxes, and the widest they grow to for long values
LABEL_ROOM = 110                                # what a narrow pane keeps for labels beside the controls
NOTE_H = 16                                     # a line of the notes under the rows
SCROLLBAR_W = 5                                 # the bar at the right when the rows are taller than the pane
SCROLL_TRACK, SCROLL_THUMB, SCROLL_THUMB_HOT = (48, 50, 60), (125, 128, 142), (200, 202, 210)
TITLE_H = 34
BUTTON_W = 28
RIGHT_GAP = 12                                  # between a row's + and the pane's right edge (room for the scroll bar)
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
    text_override: str = ""                     # header / menu / button: the text shown
    icon: Any = None                            # button: atlas tile drawn at its left
    wheel: bool = True                          # num / enum / tile: the mouse wheel over the row steps it

    def text(self):
        if self.kind in ("header", "menu", "button"):
            return self.text_override or self.label
        value = self.get()
        if self.kind == "info":
            return str(value)
        if self.kind == "text":
            return str(value)
        if self.kind == "enum":
            return self.labels.get(value, str(value))
        if self.kind == "tile":
            return f"#{value + 1}" if value >= 0 else "none"
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
    wrapped: bool = False                       # the label is on a line of its own above the controls


def fit_text(font, text, width):
    """`text` cut short with "..." so it is at most `width` pixels wide in `font` (all of it if it fits)."""
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text + "...")[0] > width:
        text = text[:-1]
    return text.rstrip() + "..."


def value_width(fields, font):
    """How wide the value boxes are: VALUE_W, or wider (up to MAX_VALUE_W) for a choice or value that would
    not fit in that."""
    widest = 0
    for f in fields:
        if f.kind == "enum":
            texts = [f.labels.get(c, str(c)) for c in f.choices] + [f.text()]
            widest = max(widest, max(font.size(t)[0] for t in texts) + 30)        # (and the drop-down arrow)
        elif f.kind in ("num", "text"):
            widest = max(widest, font.size(f.text())[0] + 16)
    return max(VALUE_W, min(MAX_VALUE_W, widest))


def controls_width(value_w):
    """The width of a row's - / value / + controls, out to the pane's right edge."""
    return BUTTON_W + 4 + value_w + 4 + BUTTON_W + RIGHT_GAP


def pane_width(fields, fonts, room=MAX_PANE_WIDTH):
    """How wide the pane wants to be for `fields`: wide enough for each label beside its controls and each
    value in its box, from PANE_WIDTH up to MAX_PANE_WIDTH (and no more than `room`). A label that still
    does not fit goes on a line of its own (rows_for)."""
    font, small = fonts
    controls = controls_width(value_width(fields, font))
    want = PANE_WIDTH
    for f in fields:
        if f.kind in ("num", "enum", "tile", "text"):
            want = max(want, 10 + font.size(f.label)[0] + 10 + controls)
        elif f.kind == "info":
            want = max(want, 10 + font.size(f.label)[0] + 16 + small.size(f.text())[0] + 8)
    return max(PANE_WIDTH, min(want, MAX_PANE_WIDTH, room))


def label_fits(rect, minus, f, fonts):
    """True if the field's label fits on the row beside its controls (or its value, for an info row)."""
    font, small = fonts
    if f.kind == "info":
        return 10 + font.size(f.label)[0] + 16 + small.size(f.text())[0] + 8 <= rect.w
    return rect.x + 10 + font.size(f.label)[0] + 6 <= minus.x


def rows_for(rect, fields, fonts=None, scroll=0):
    """Place one Row per field down the pane (below its title), `scroll` pixels up. With `fonts` the value
    boxes widen for long values, and a label too long for its row goes on a line of its own above the
    controls."""
    rows = []
    value_w = VALUE_W
    if fonts:                                   # (wider for long values, while leaving labels room in a narrow pane)
        value_w = min(value_width(fields, fonts[0]), max(VALUE_W, rect.w - 16 - LABEL_ROOM - controls_width(0)))
    y = rect.y + TITLE_H - scroll
    for f in fields:
        plus = pygame.Rect(rect.right - RIGHT_GAP - BUTTON_W, y + 3, BUTTON_W, ROW_H - 6)
        value = pygame.Rect(plus.x - 4 - value_w, y + 3, value_w, ROW_H - 6)
        minus = pygame.Rect(value.x - 4 - BUTTON_W, y + 3, BUTTON_W, ROW_H - 6)
        wrapped = (fonts is not None and f.kind in ("num", "enum", "tile", "text", "info")
                   and not label_fits(rect, minus, f, fonts))
        if wrapped:
            for box in (plus, value, minus):
                box.y += LABEL_LINE_H
        height = ROW_H + (LABEL_LINE_H if wrapped else 0)
        rows.append(Row(f, pygame.Rect(rect.x, y, rect.w, height), minus, value, plus, wrapped))
        y += height
    return rows


def view_rect(rect):
    """The part of the pane its rows scroll in (all of it below the title)."""
    return pygame.Rect(rect.x, rect.y + TITLE_H, rect.w, max(1, rect.h - TITLE_H))


def note_lines(notes, small, width):
    """The notes under the rows, each wrapped to `width` pixels."""
    lines = []
    for text in notes:
        line = ""
        for word in text.split():
            trial = f"{line} {word}".strip()
            if line and small.size(trial)[0] > width:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


def notes_top(rect, rows, button_label="Delete"):
    """Where the notes start: under the last row and the button (where the button is when not kept at the
    bottom)."""
    y = (rows[-1].rect.bottom if rows else rect.y + TITLE_H) + 10
    return y + 42 if button_label else y


def content_height(rect, rows, notes, small, button_label="Delete"):
    """How tall everything that scrolls in the pane is (rows, button and notes), not scrolled."""
    top = rows[0].rect.y if rows else rect.y + TITLE_H
    bottom = notes_top(rect, rows, button_label) + NOTE_H * len(note_lines(notes, small, rect.w - 20))
    return bottom - top + 6


def scrollbar(view, content_h, scroll):
    """(track, thumb) of a thin bar at the right edge of `view` when what scrolls in it (`content_h` pixels
    tall, scrolled up `scroll`) is taller than it, else None."""
    if content_h <= view.h:
        return None
    track = pygame.Rect(view.right - SCROLLBAR_W - 2, view.y + 2, SCROLLBAR_W, view.h - 4)
    height = max(24, track.h * view.h // content_h)
    top = track.y + round((track.h - height) * max(0, min(scroll, content_h - view.h)) / (content_h - view.h))
    return track, pygame.Rect(track.x, top, track.w, height)


def scroll_for(view, content_h, thumb_top):
    """How far to scroll for the bar's thumb to start at screen row `thumb_top`."""
    bar = scrollbar(view, content_h, 0)
    if bar is None:
        return 0
    track, thumb = bar
    fraction = (thumb_top - track.y) / max(1, track.h - thumb.h)
    return max(0, min(content_h - view.h, round(fraction * (content_h - view.h))))


def draw_scrollbar(screen, bar, hot=False):
    track, thumb = bar
    pygame.draw.rect(screen, SCROLL_TRACK, track, border_radius=2)
    pygame.draw.rect(screen, SCROLL_THUMB_HOT if hot else SCROLL_THUMB, thumb, border_radius=2)


def button_box(row):
    """The area of a full-width button row."""
    return pygame.Rect(row.rect.x + 8, row.rect.y + 3, row.rect.w - 16, row.rect.h - 6)


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
    """The Delete button: under the last row, or kept at the bottom of the pane while there are rows below it."""
    y = (rows[-1].rect.bottom if rows else rect.y + TITLE_H) + 10
    return pygame.Rect(rect.x + 10, min(y, rect.bottom - 42), rect.w - 20, 32)


def button_kept(rect, rows):
    """True while the Delete button is kept at the bottom of the pane, over rows scrolled under it."""
    return bool(rows) and button_rect(rect, rows).y < rows[-1].rect.bottom + 10


def draw(screen, rect, title, rows, theme, fonts, editing=None, hover=None, tile_surface=None,
         notes=(), button_label="Delete", open_menu=None, focus=None, scroll=0, scroll_hot=False):
    """Draw the pane. `editing` is (field key, text typed so far) while a number is being typed;
    `hover` is the mouse position; `tile_surface(index)` gives the picture for a tile field;
    `open_menu` is the key of the field whose drop-down list is showing; `focus` the tile field that
    atlas clicks will set; `scroll` how far the rows are scrolled up (`scroll_hot`: its bar is being
    dragged). Returns [(rect, whole text)] of what was cut short to fit, to show whole on hover."""
    font, small = fonts
    cut = []
    pygame.draw.rect(screen, theme["panel"], rect)
    pygame.draw.line(screen, theme["grid"], rect.topleft, rect.bottomleft)
    screen.blit(font.render(fit_text(font, title, rect.w - 20), True, theme["accent"]), (rect.x + 10, rect.y + 8))
    view = view_rect(rect)
    clip = screen.get_clip()
    screen.set_clip(view.clip(clip) if clip else view)

    def box(area, color, border=False):
        pygame.draw.rect(screen, color, area, border_radius=4)
        if border:
            pygame.draw.rect(screen, theme["accent"], area, 1, border_radius=4)

    def hot(area):
        return hover is not None and area.collidepoint(hover) and view.collidepoint(hover)

    def text_in(text, render_font, color, area, align="center", room=None):
        """Draw `text` in `area`, cut short with "..." if wider than `room` (area's width less a margin)."""
        room = room if room is not None else area.w - 12
        shown = fit_text(render_font, text, room)
        if shown != text:
            cut.append((area.clip(view), text))
        surface = render_font.render(shown, True, color)
        if align == "left":
            screen.blit(surface, surface.get_rect(midleft=(area.x + 8, area.centery)))
        elif align == "right":
            screen.blit(surface, surface.get_rect(midright=(area.right - 6, area.centery)))
        else:
            screen.blit(surface, surface.get_rect(center=area.center))

    def label(row, right):
        """The field's label: on its own line when wrapped, else left of the controls (up to `right`)."""
        area = pygame.Rect(rect.x + 10, row.rect.y + (4 if row.wrapped else 8), 0, 18)
        area.w = (rect.right - 10 if row.wrapped else right - 6) - area.x
        shown = fit_text(font, row.field.label, area.w)
        if shown != row.field.label:
            cut.append((area.clip(view), row.field.label))
        screen.blit(font.render(shown, True, theme["text"]), area.topleft)

    for row in rows:
        if row.rect.bottom < view.top or row.rect.top > view.bottom:
            continue
        f = row.field
        if f.kind == "header":
            pygame.draw.line(screen, theme["grid"], (rect.x + 8, row.rect.y + 2), (rect.right - 8, row.rect.y + 2))
            right = row.plus.x - 6 if f.action is not None else rect.right - 10
            text_in(f.text(), font, theme["accent"], pygame.Rect(rect.x + 2, row.rect.y + 6, right - rect.x - 2, 22),
                    "left", right - rect.x - 10)
            if f.action is not None:
                box(row.plus, theme["danger_hot"] if hot(row.plus) else theme["danger"])
                glyph = font.render("x", True, theme["text"])
                screen.blit(glyph, glyph.get_rect(center=row.plus.center))
            continue
        if f.kind == "button":
            wide = button_box(row)
            chosen = f.get() if f.get else False
            box(wide, theme["button_on"] if chosen else (theme["button_hot"] if hot(wide) else theme["button"]))
            x = wide.x + 8
            if f.icon is not None and tile_surface is not None:
                picture = pygame.transform.scale(tile_surface(f.icon), (wide.h - 4, wide.h - 4))
                screen.blit(picture, (x, wide.y + 2))
                x += wide.h + 2
            text_in(f.text(), font, theme["text"], pygame.Rect(x - 8, wide.y, wide.right - x + 8, wide.h), "left",
                    wide.right - x - 8)
            continue
        if f.kind == "menu":
            wide = menu_anchor(row)
            box(wide, theme["button_hot"] if hot(wide) or open_menu == f.key else theme["button"])
            text_in(f.text(), font, theme["text"], wide)
            continue
        if f.kind == "info":                                       # read-only: the label, and the value dimmed on the right
            value = small.render(f.text(), True, theme["dim"])
            if row.wrapped:
                label(row, rect.right - 10)
                text_in(f.text(), small, theme["dim"], pygame.Rect(rect.x + 10, row.value.y, rect.w - 18, row.value.h),
                        "right", rect.w - 26)
            else:
                label(row, row.plus.right - value.get_width() - 10)
                screen.blit(value, value.get_rect(midright=(row.plus.right, row.rect.centery)))
            continue
        label(row, row.minus.x)
        for button, glyph_text in ((row.minus, "-"), (row.plus, "+")):
            box(button, theme["button_hot"] if hot(button) else theme["button"])
            glyph = font.render(glyph_text, True, theme["text"])
            screen.blit(glyph, glyph.get_rect(center=button.center))
        typing = editing is not None and editing[0] == f.key
        box(row.value, theme["field_edit"] if typing else (theme["button_hot"] if hot(row.value) else theme["field"]),
            border=typing or open_menu == f.key or (f.kind == "tile" and focus == f.key))
        if f.kind == "tile" and tile_surface is not None and f.get() >= 0:
            picture = pygame.transform.scale(tile_surface(f.get()), (row.value.h - 4, row.value.h - 4))
            screen.blit(picture, (row.value.x + 4, row.value.y + 2))
            text = small.render(f.text(), True, theme["text"])
            screen.blit(text, text.get_rect(midright=(row.value.right - 6, row.value.centery)))
        elif f.kind == "enum":
            text_in(f.text(), font, theme["accent"], row.value, "left", row.value.w - 26)
            cx, cy = row.value.right - 10, row.value.centery
            pygame.draw.polygon(screen, theme["dim"], ((cx - 4, cy - 2), (cx + 4, cy - 2), (cx, cy + 3)))
        else:
            shown = (editing[1] + "|") if typing else f.text()
            text = font.render(shown, True, theme["text"] if typing else theme["accent"])
            if text.get_width() > row.value.w - 8:                    # a long name: show the end of it
                text = small.render(shown, True, theme["text"] if typing else theme["accent"])
                if not typing and text.get_width() > row.value.w - 8:
                    cut.append((row.value.clip(view), shown))
            screen.set_clip(row.value.inflate(-4, 0).clip(view))
            screen.blit(text, text.get_rect(center=row.value.center) if text.get_width() <= row.value.w - 8
                        else text.get_rect(midright=(row.value.right - 6, row.value.centery)))
            screen.set_clip(view.clip(clip) if clip else view)
    y = notes_top(rect, rows, button_label)
    for line in note_lines(notes, small, rect.w - 20):
        screen.blit(small.render(line, True, theme["dim"]), (rect.x + 10, y))
        y += NOTE_H
    button = button_rect(rect, rows)
    if button_label:
        if button_kept(rect, rows):                         # kept at the bottom: the rows go on under it
            pygame.draw.rect(screen, theme["panel"], (rect.x + 1, button.y - 8, rect.w - 1, rect.bottom - button.y + 8))
            pygame.draw.line(screen, theme["grid"], (rect.x + 8, button.y - 8), (rect.right - 8, button.y - 8))
        box(button, theme["danger_hot"] if hot(button) else theme["danger"])
        text_in(button_label, font, theme["text"], button)
    screen.set_clip(clip)
    bar = scrollbar(view, y + scroll - view.y + 6, scroll)
    if bar is not None:
        draw_scrollbar(screen, bar, scroll_hot or (hover is not None and bar[0].inflate(8, 0).collidepoint(hover)))
    for row in rows:                                        # an open drop-down list goes on top of everything
        if row.field.key == open_menu:
            items = menu_rects(row)
            if items:
                pygame.draw.rect(screen, theme["field"], items[0][0].unionall([r for r, _c in items]).inflate(4, 4))
            for item, choice in items:
                current = row.field.kind == "enum" and row.field.get() == choice
                box(item, theme["button_hot"] if hover is not None and item.collidepoint(hover)
                    else (theme["field_edit"] if current else theme["field"]))
                text = font.render(row.field.labels.get(choice, str(choice)), True,
                                   theme["accent"] if current else theme["text"])
                screen.blit(text, text.get_rect(midleft=(item.x + 8, item.centery)))
    return [(area, text) for area, text in cut if area.w > 0 and area.h > 0]
