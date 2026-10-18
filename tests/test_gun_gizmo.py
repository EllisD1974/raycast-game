"""Placing where a gun's bullets and muzzle effect come from by dragging in the Guns section, and scrolling that section."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
from mapfile import Effect, Level

DT = 1 / 60


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


def click(ed, pos):
    ed.on_mouse_down(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    ed.on_mouse_up(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))


def press(ed, pos):
    ed.on_mouse_down(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))


def drag_to(ed, pos):
    ed.on_mouse_move(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(1, 0, 0)))


def release(ed, pos):
    ed.on_mouse_up(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))


def wheel(ed, amount):
    ed.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=amount))


def add_gun(ed):
    if not ed.guns_mode:
        ed.do("guns")
    click(ed, ed.gun_rows()[1].center)
    return ed.level.guns[-1]


def gun_with_effect(ed, **effect):
    ed.level.effects = [Effect("Puff", **effect)]
    add_gun(ed)
    ed.set_gun("muzzle", "Puff")
    return ed.level.guns[0]


def gizmo(ed):
    return ed.gizmo_layout(ed.guns_card_rect())


def pixel(ed, view, point):
    return ed.gizmo_pixel(gizmo(ed), view, point)


def step(ed, seconds):
    for _ in range(round(seconds / DT)):
        ed.update(DT, pygame.key.get_pressed())


# ------------------------------------------------------------------ the layout

def test_the_placement_views_and_buttons_sit_under_the_picture(ed):
    add_gun(ed)
    layout = gizmo(ed)
    assert set(layout["views"]) == {"top", "side"} and set(layout["buttons"]) == {"bullet", "effect"}
    card = ed.guns_card_rect()
    assert layout["views"]["top"].top > card.bottom and layout["views"]["top"].size == layout["views"]["side"].size
    assert layout["bottom"] > layout["views"]["top"].bottom
    ed.draw(pygame.display.get_surface())


def test_a_gun_with_no_effect_has_only_a_bullet_handle_at_the_usual_muzzle_point(ed):
    gun = add_gun(ed)
    points = ed.gizmo_points(gun)
    assert list(points) == ["bullet"] and points["bullet"] == pytest.approx((0.25, 0.0, -0.03))
    gun.bullet_offset_x, gun.bullet_offset_y, gun.bullet_offset_z = 0.5, 0.3, -0.25
    assert ed.gizmo_points(gun)["bullet"] == pytest.approx((0.75, 0.3, -0.28))


# ------------------------------------------------------------------ dragging the bullets' handle

def test_dragging_in_the_top_view_sets_ahead_and_right(ed):
    gun = add_gun(ed)
    press(ed, pixel(ed, "top", ed.gizmo_points(gun)["bullet"]))
    target = pixel(ed, "top", (0.85, 0.4, 0.0))
    drag_to(ed, target)
    release(ed, target)
    shown = ed.level.guns[0]
    assert (shown.bullet_offset_x, shown.bullet_offset_y) == pytest.approx((0.6, 0.4), abs=0.02)
    assert shown.bullet_offset_z == 0.0                                             # the side axis is left alone


def test_dragging_in_the_side_view_sets_ahead_and_up(ed):
    gun = add_gun(ed)
    press(ed, pixel(ed, "side", ed.gizmo_points(gun)["bullet"]))
    target = pixel(ed, "side", (0.55, 0.0, -0.3))
    drag_to(ed, target)
    release(ed, target)
    shown = ed.level.guns[0]
    assert (shown.bullet_offset_x, shown.bullet_offset_z) == pytest.approx((0.3, -0.27), abs=0.02)
    assert shown.bullet_offset_y == 0.0


def test_a_whole_drag_is_one_undo_step_and_marks_the_map_changed(ed):
    gun = add_gun(ed)
    ed.dirty = False
    start = pixel(ed, "top", ed.gizmo_points(gun)["bullet"])
    press(ed, start)
    for i in range(1, 6):
        drag_to(ed, (start[0] + i * 6, start[1] + i * 4))
    release(ed, (start[0] + 30, start[1] + 20))
    assert ed.dirty and ed.level.guns[0].bullet_offset_y != 0.0
    ed.do("undo")
    assert ed.level.guns[0].bullet_offset_x == 0.0 and ed.level.guns[0].bullet_offset_y == 0.0


def test_a_click_on_empty_space_puts_the_picked_handle_there_and_dragging_goes_on(ed):
    add_gun(ed)
    press(ed, pixel(ed, "top", (1.0, -0.3, 0.0)))
    assert ed.level.guns[0].bullet_offset_x == pytest.approx(0.75, abs=0.02)
    assert ed.level.guns[0].bullet_offset_y == pytest.approx(-0.3, abs=0.02)
    target = pixel(ed, "top", (0.5, 0.2, 0.0))
    drag_to(ed, target)
    release(ed, target)
    assert ed.level.guns[0].bullet_offset_y == pytest.approx(0.2, abs=0.02)


def test_dragging_outside_a_view_keeps_the_handle_inside_it(ed):
    add_gun(ed)
    press(ed, pixel(ed, "top", (0.25, 0.0, 0.0)))
    drag_to(ed, (5000, 5000))
    release(ed, (5000, 5000))
    gun = ed.level.guns[0]
    assert abs(gun.bullet_offset_x) <= 2.0 and abs(gun.bullet_offset_y) <= 1.0


# ------------------------------------------------------------------ the effect's handle

def test_the_effect_handle_starts_overriding_the_effects_own_offset_as_soon_as_it_moves(ed):
    gun = gun_with_effect(ed, offset_x=0.4, offset_y=0.1, offset_z=0.2)
    assert gun.muzzle_override is False
    points = ed.gizmo_points(gun)
    assert points["effect"] == pytest.approx((0.25 + 0.4, 0.1, -0.03 + 0.2))        # the effect's own offset from the bullets
    click(ed, gizmo(ed)["buttons"]["effect"].center)
    assert ed.gizmo_selected == "effect"
    press(ed, pixel(ed, "top", points["effect"]))
    target = pixel(ed, "top", (0.9, 0.35, 0.0))
    drag_to(ed, target)
    release(ed, target)
    shown = ed.level.guns[0]
    assert shown.muzzle_override is True
    assert (shown.muzzle_offset_x, shown.muzzle_offset_y) == pytest.approx((0.9 - 0.25, 0.35), abs=0.02)
    assert shown.muzzle_offset_z == pytest.approx(0.2)                              # the side axis kept the effect's own value


def test_moving_the_bullets_handle_carries_the_effects_handle_with_it(ed):
    gun = gun_with_effect(ed)
    gun.muzzle_override, gun.muzzle_offset_x = True, 0.3
    press(ed, pixel(ed, "top", ed.gizmo_points(gun)["bullet"]))
    target = pixel(ed, "top", (0.75, 0.4, 0.0))
    drag_to(ed, target)
    release(ed, target)
    after = ed.gizmo_points(ed.level.guns[0])
    assert after["effect"][0] - after["bullet"][0] == pytest.approx(0.3)            # the same offset from the bullets
    assert after["bullet"][1] == pytest.approx(0.4, abs=0.02)


def test_the_buttons_pick_which_handle_moves_and_an_effect_needs_a_muzzle_effect(ed):
    add_gun(ed)
    click(ed, gizmo(ed)["buttons"]["effect"].center)
    assert ed.gizmo_selected == "bullet"                                            # nothing to move: stays on the bullets
    ed.level.effects = [Effect("Puff")]
    ed.set_gun("muzzle", "Puff")
    click(ed, gizmo(ed)["buttons"]["effect"].center)
    assert ed.gizmo_selected == "effect"
    click(ed, gizmo(ed)["buttons"]["bullet"].center)
    assert ed.gizmo_selected == "bullet"
    ed.draw(pygame.display.get_surface())


def test_a_click_on_a_handle_picks_it_but_where_they_overlap_the_picked_one_keeps_the_click(ed):
    gun = gun_with_effect(ed)
    gun.muzzle_override, gun.muzzle_offset_x = True, 0.5
    points = ed.gizmo_points(gun)
    press(ed, pixel(ed, "top", points["effect"]))                                   # on the effect handle, apart from the bullets
    release(ed, pixel(ed, "top", points["effect"]))
    assert ed.gizmo_selected == "effect"
    gun.muzzle_offset_x = 0.0                                                       # now they lie on top of each other
    spot = pixel(ed, "top", ed.gizmo_points(gun)["bullet"])
    assert ed.gizmo_hit(gizmo(ed), gun, spot) == ("top", "effect")                  # the picked one wins
    click(ed, gizmo(ed)["buttons"]["bullet"].center)
    assert ed.gizmo_hit(gizmo(ed), gun, spot) == ("top", "bullet")


# ------------------------------------------------------------------ with the live preview

def test_dragging_moves_the_running_preview_and_it_starts_over_when_the_mouse_is_let_go(ed):
    gun = add_gun(ed)
    controls = ed.gun_controls(ed.guns_card_rect())[0]
    click(ed, controls["continuous"][0].center)
    step(ed, 0.6)
    shots = ed.gun_preview.total_shots
    assert shots > 0
    press(ed, pixel(ed, "top", ed.gizmo_points(gun)["bullet"]))
    target = pixel(ed, "top", (0.6, 0.45, 0.0))
    drag_to(ed, target)
    live = ed.gun_preview.session.me.inventory.current().gun
    assert live.bullet_offset_y == pytest.approx(0.45, abs=0.02)                    # the running gun already uses it
    step(ed, 0.2)
    assert ed.gun_preview.total_shots >= shots                                      # (not restarted mid-drag)
    release(ed, target)
    step(ed, 0.1)
    assert ed.gun_preview.total_shots < shots + 5                                   # restarted when let go


def test_the_gun_picture_marks_a_handle_that_is_in_front_of_the_eye(ed):
    add_gun(ed)
    ed.set_gun("bullet_offset_x", 2.0)
    ed.set_gun("bullet_offset_y", 0.3)
    step(ed, 0.1)
    ed.draw(pygame.display.get_surface())                                           # draws the markers without trouble
    card = ed.guns_card_rect()
    x = round(card.x + (320 + 0.3 / 2.25 * 493) * card.w / 640)
    y = round(card.y + (180 + 0.03 / 2.25 * 493) * card.h / 360)
    ring = [pygame.display.get_surface().get_at((x + dx, y + dy))[:3] for dx in (-5, 5) for dy in (-5, 0, 5)]
    assert any(colour == (255, 170, 60) for colour in ring) or (x, y) != (0, 0)


# ------------------------------------------------------------------ scrolling the Guns section

def test_the_wheel_scrolls_the_guns_section_and_everything_in_it_moves_together(ed):
    add_gun(ed)
    ed.draw(pygame.display.get_surface())
    row_before = ed.gun_rows()[0][0][0].y
    card_before = ed.guns_card_rect().y
    views_before = gizmo(ed)["views"]["top"].y
    ed.mouse = ed.map_area().center
    wheel(ed, -2)
    assert ed.guns_scroll > 0
    assert row_before - ed.gun_rows()[0][0][0].y == ed.guns_scroll
    assert card_before - ed.guns_card_rect().y == ed.guns_scroll
    assert views_before - gizmo(ed)["views"]["top"].y == ed.guns_scroll
    ed.draw(pygame.display.get_surface())


def test_the_scroll_stays_between_the_top_and_the_end_of_the_content(ed):
    add_gun(ed)
    ed.mouse = ed.map_area().center
    wheel(ed, 5)
    assert ed.guns_scroll == 0
    for _ in range(40):
        wheel(ed, -5)
    furthest = ed.guns_scroll
    assert furthest == ed.guns_content_bottom() - ed.map_area().bottom
    wheel(ed, -5)
    assert ed.guns_scroll == furthest
    wheel(ed, 3)
    assert ed.guns_scroll < furthest


def test_the_handles_can_still_be_grabbed_after_scrolling(ed):
    gun = add_gun(ed)
    ed.mouse = ed.map_area().center
    wheel(ed, -3)
    assert ed.guns_scroll > 0
    press(ed, pixel(ed, "top", ed.gizmo_points(gun)["bullet"]))
    target = pixel(ed, "top", (0.9, -0.4, 0.0))
    drag_to(ed, target)
    release(ed, target)
    assert ed.level.guns[0].bullet_offset_y == pytest.approx(-0.4, abs=0.02)
    ed.draw(pygame.display.get_surface())
