"""Scrolling in the editor: the sections shown in place of the map, the Details pane, the Open dialog and the zoomed
atlas show a thin bar when there is more than fits, and the wheel or the bar scrolls them; text too long for its
place is cut short and shown whole on hover; the Details pane widens for long labels and values, and puts a label
that still does not fit on a line of its own."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import details
import map_editor
from mapfile import BuyItem, Entity, Level, MapSettings


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(10, 10)
    editor.level.start_x = editor.level.start_y = 1.5
    editor.show_legend = False
    editor.draw(pygame.display.get_surface())
    return editor


def wheel(ed, y):
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=y))


def drag(ed, start, end):
    ed.on_mouse_down(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=start, button=1))
    ed.on_mouse_move(pygame.event.Event(pygame.MOUSEMOTION, pos=end, rel=(0, 0), buttons=(1, 0, 0)))
    ed.on_mouse_up(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=end, button=1))


@pytest.mark.parametrize("section, add", [("prefabs", "add_prefab"), ("effects", "add_effect"),
                                          ("lights", "add_light")])
def test_a_long_list_in_a_section_shows_a_bar_and_scrolls_with_the_wheel_and_the_bar(ed, section, add):
    ed.do(section)
    assert ed.scrollbar(section) is None                                  # all of it fits: no bar
    for _ in range(25):
        getattr(ed, add)()
    ed.draw(pygame.display.get_surface())
    assert ed.scrollbar(section) is not None
    rows_of = {"prefabs": ed.prefab_rows, "effects": ed.effect_rows, "lights": lambda: ed.light_rows()[1:]}[section]
    first = rows_of()[0][0][0].y
    ed.mouse = ed.map_area().center
    wheel(ed, -2)
    assert getattr(ed, f"{section}_scroll") == 96 and rows_of()[0][0][0].y == first - 96
    wheel(ed, 5)
    assert getattr(ed, f"{section}_scroll") == 0
    track, thumb = ed.scrollbar(section)
    drag(ed, thumb.center, (thumb.centerx, track.bottom + 100))           # the bar dragged to the end
    view, content, scroll = ed.scroll_view(section)
    assert scroll == content - view.h
    assert rows_of()[-1].bottom <= ed.map_area().bottom                 # the Add button is in view
    ed.draw(pygame.display.get_surface())


def test_clicking_a_row_after_scrolling_selects_that_row(ed):
    ed.do("prefabs")
    for _ in range(25):
        ed.add_prefab()
    ed.mouse = ed.map_area().center
    wheel(ed, -10)
    rect, index = next((r, i) for r, i in ed.prefab_rows()[0] if r.top > ed.map_area().top + 100)
    ed.on_mouse_down(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=rect.center, button=1))
    assert ed.prefab_selected == index and index > 5


def test_map_settings_rows_grow_to_fit_a_long_summary_and_the_section_scrolls(ed):
    ed.do("mapsettings")
    short_rules = ed.settings_rows()[0]
    ed.level.settings = MapSettings(mode="bomb", friendly_fire=True, start_money=800, kill_money=300, kill_score=1,
                                    start_gun="Pistol", buy_menu=True, buy_cost="money",
                                    buy_items=[BuyItem(kind="health", amount=40, price=20 + i) for i in range(20)])
    rules, buy, rows, add = ed.settings_rows()
    assert rules.h > short_rules.h                                         # (on more lines, not cut off)
    assert len(ed.summary_lines(ed.rules_summary(), rules.w - 20)) * 17 + 24 <= rules.h + 1
    assert buy.top > rules.bottom and rows[0][0].top > buy.bottom
    ed.draw(pygame.display.get_surface())
    assert ed.scrollbar("settings") is not None
    ed.mouse = ed.map_area().center
    wheel(ed, -100)
    assert ed.settings_scroll == ed.settings_content_bottom() - ed.map_area().bottom
    assert ed.settings_rows()[3].bottom <= ed.map_area().bottom


def test_the_details_pane_widens_for_long_labels_and_values(ed):
    ed.do("tool:entity")
    assert ed.details_rect().w == details.PANE_WIDTH                       # the list of what to place: as it was
    ed.do("effects")
    ed.add_effect()
    rect = ed.details_rect()
    assert details.PANE_WIDTH < rect.w <= details.MAX_PANE_WIDTH
    for row in ed.details_rows():                                          # every label beside its controls
        if row.field.kind in ("num", "enum", "tile", "text"):
            assert not row.wrapped
            assert rect.x + 10 + ed.font.size(row.field.label)[0] <= row.minus.x


def test_a_narrow_pane_puts_a_long_label_on_its_own_line(ed):
    fields = [details.Field("a", "Short", "num", lambda: 1, lambda v: None),
              details.Field("b", "A label too long to share a row", "num", lambda: 1, lambda v: None),
              details.Field("c", "Info", "info", lambda: "a value too long to sit beside its own label", None),
              details.Field("d", "x" * 60, "num", lambda: 1, lambda v: None)]
    rect = pygame.Rect(0, 0, details.PANE_WIDTH, 600)
    rows = details.rows_for(rect, fields, (ed.font, ed.small))
    assert [r.wrapped for r in rows] == [False, True, True, True]
    assert rows[1].rect.h == details.ROW_H + details.LABEL_LINE_H and rows[1].minus.y > rows[1].rect.y + 18
    assert rows[2].rect.top == rows[1].rect.bottom
    surface = pygame.Surface((800, 700))
    theme = {"panel": (0, 0, 0), "grid": (1, 1, 1), "text": (2, 2, 2), "dim": (3, 3, 3), "accent": (4, 4, 4),
             "button": (5, 5, 5), "button_hot": (6, 6, 6), "field": (7, 7, 7), "field_edit": (8, 8, 8),
             "danger": (9, 9, 9), "danger_hot": (10, 10, 10), "button_on": (11, 11, 11)}
    cut = details.draw(surface, rect, "Title", rows, theme, (ed.font, ed.small))
    assert [text for _area, text in cut] == ["x" * 60]                     # (only one too long even for its own line)


def test_text_cut_short_shows_whole_in_a_tooltip_on_hover(ed):
    ed.do("prefabs")
    ed.add_prefab()
    long_name = "A prefab with a name far too long to fit in its row of the list " * 2
    ed.level.prefabs[0].name = long_name
    surface = pygame.display.get_surface()
    ed.draw(surface)
    rect = ed.prefab_rows()[0][0][0]
    tips = [(area, text) for area, text in ed.tips if text == long_name]
    assert tips and tips[0][0].colliderect(rect)
    ed.mouse = tips[0][0].center
    before = surface.copy()
    ed.draw(surface)
    ed.mouse = (0, surface.get_height() - 1)
    ed.draw(before)
    assert pygame.image.tobytes(surface, "RGB") != pygame.image.tobytes(before, "RGB")      # the tooltip shows


def test_the_open_dialog_list_shows_a_bar_that_can_be_dragged(ed, tmp_path):
    ed.open_maps = [f"map{i:02}.json" for i in range(40)]
    ed.open_pick = 0
    track, thumb = ed.scrollbar("open")
    drag(ed, thumb.center, (thumb.centerx, track.bottom + 50))
    assert ed.open_scroll == 40 - map_editor.OPEN_ROWS
    ed.draw(pygame.display.get_surface())


def test_the_zoomed_atlas_shows_its_bars(ed, monkeypatch):
    drawn = []
    monkeypatch.setattr(details, "draw_scrollbar", lambda screen, bar, hot=False: drawn.append(bar))
    view = ed.atlas_rect()
    ed.draw_atlas_scrollbars(pygame.display.get_surface(), view)
    assert drawn == []                                                     # all of it shows: no bars
    for _ in range(3):
        ed.zoom_atlas(view.center, 1)
    ed.draw_atlas_scrollbars(pygame.display.get_surface(), view)
    vertical, horizontal = drawn
    assert vertical[0].h > vertical[0].w and horizontal[0].w > horizontal[0].h
    assert view.contains(vertical[0]) and view.contains(horizontal[0])
