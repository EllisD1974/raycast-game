"""Placing where a gun's bullets and muzzle effect come from by dragging on the gun picture, with a depth slider, and
scrolling the Guns section.

The handles are drawn on the picture of the live preview, where the bullets and the effect really start: dragging one moves it
sideways and up at the depth it has, and the slider moves it in and out of the screen (further ahead of the gun, or back).
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
from mapfile import Effect, Level

DT = 1 / 60
ORANGE, CYAN = (255, 170, 60), (80, 220, 255)


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1920, 1080), pygame.RESIZABLE)
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


@pytest.fixture
def small_ed(tmp_path):
    """The editor in a window too short for the whole Guns section, so that it has to scroll."""
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(10, 10)
    editor.show_legend = False
    editor.draw(pygame.display.get_surface())
    yield editor
    pygame.display.set_mode((1920, 1080), pygame.RESIZABLE)


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


def card(ed):
    return ed.guns_card_rect()


def layout(ed):
    return ed.gizmo_layout(card(ed))


def pixel(ed, point):
    """Where an (ahead, right, up) offset point from the usual muzzle point shows on the picture."""
    return ed.gizmo_pixel(card(ed), point)


def step(ed, seconds):
    for _ in range(round(seconds / DT)):
        ed.update(DT, pygame.key.get_pressed())


def drag_picture(ed, start, end):
    press(ed, pixel(ed, start))
    drag_to(ed, end)
    release(ed, end)


def slider_at(ed, fraction):
    track = layout(ed)["track"]
    return (track.x + round(fraction * track.w), track.centery)


def depth_of(ed):
    return ed.gizmo_depth(ed.level.guns[0])


# ------------------------------------------------------------------ the layout

def test_the_buttons_and_the_depth_slider_sit_under_the_gun_picture(ed):
    add_gun(ed)
    controls_bottom = ed.gun_controls(card(ed))[1]
    lay = layout(ed)
    assert set(lay["buttons"]) == {"bullet", "effect"}
    assert lay["buttons"]["bullet"].top > controls_bottom - 10
    assert lay["track"].top > lay["buttons"]["bullet"].bottom and lay["track"].width > 100
    assert lay["status"] > lay["track"].bottom and lay["bottom"] > lay["status"]
    assert "views" not in lay                                                          # no separate views any more
    ed.draw(pygame.display.get_surface())


def test_the_handle_is_drawn_on_the_picture_where_the_bullets_start(ed):
    gun = add_gun(ed)
    ed.draw(pygame.display.get_surface())
    c = card(ed)
    x, y = pixel(ed, ed.gizmo_points(gun)["bullet"])
    assert c.collidepoint(x, y) and abs(x - c.centerx) <= 1
    assert y > c.centery                                                               # the muzzle is a little below the eye
    assert tuple(pygame.display.get_surface().get_at((x, y))[:3]) == ORANGE            # the orange disc


def test_offsets_show_on_the_picture_the_way_they_look(ed):
    add_gun(ed)
    x0, y0 = pixel(ed, (1.0, 0.0, 0.0))
    right_x, _ = pixel(ed, (1.0, 0.3, 0.0))
    left_x, _ = pixel(ed, (1.0, -0.3, 0.0))
    _, up_y = pixel(ed, (1.0, 0.0, 0.3))
    _, down_y = pixel(ed, (1.0, 0.0, -0.3))
    assert right_x > x0 > left_x and up_y < y0 < down_y


def test_further_ahead_the_same_offset_moves_toward_the_middle_of_the_picture(ed):
    add_gun(ed)
    c = card(ed)
    near_x, near_y = pixel(ed, (0.5, 0.3, 0.2))
    far_x, far_y = pixel(ed, (2.0, 0.3, 0.2))
    assert abs(far_x - c.centerx) < abs(near_x - c.centerx) and abs(far_y - c.centery) < abs(near_y - c.centery)


def test_a_handle_further_out_than_the_picture_sits_on_its_edge_and_can_still_be_grabbed(ed):
    gun = add_gun(ed)
    gun.bullet_offset_y, gun.bullet_offset_z = 3.0, 3.0
    c = card(ed)
    x, y = pixel(ed, ed.gizmo_points(gun)["bullet"])
    assert (x, y) == (c.right - 1, c.top)
    press(ed, (x, y))
    assert ed.gizmo_drag == "picture" and ed.gizmo_selected == "bullet"
    release(ed, (x, y))


# ------------------------------------------------------------------ dragging on the picture

def test_dragging_a_handle_on_the_picture_sets_right_and_up_and_keeps_its_depth(ed):
    gun = add_gun(ed)
    gun.bullet_offset_x = 0.9
    c = card(ed)
    target = (c.centerx + 70, c.centery - 40)
    drag_picture(ed, (0.9, 0.0, 0.0), target)
    shown = ed.level.guns[0]
    assert shown.bullet_offset_x == 0.9                                                # depth untouched
    assert shown.bullet_offset_y > 0.1 and shown.bullet_offset_z > 0.0                 # right of the middle, above it
    x, y = pixel(ed, ed.gizmo_points(shown)["bullet"])
    assert (x, y) == pytest.approx(target, abs=2)                                      # and it is now under the mouse


def test_dragging_to_the_left_and_down_goes_the_other_way(ed):
    add_gun(ed)
    c = card(ed)
    drag_picture(ed, (0.25, 0.0, 0.0), (c.centerx - 50, c.bottom - 20))
    shown = ed.level.guns[0]
    assert shown.bullet_offset_y < 0 and shown.bullet_offset_z < 0


def test_a_whole_drag_is_one_undo_step_and_marks_the_map_changed(ed):
    gun = add_gun(ed)
    ed.dirty = False
    start = pixel(ed, ed.gizmo_points(gun)["bullet"])
    press(ed, start)
    for i in range(1, 6):
        drag_to(ed, (start[0] + i * 6, start[1] - i * 4))
    release(ed, (start[0] + 30, start[1] - 20))
    assert ed.dirty and ed.level.guns[0].bullet_offset_y != 0.0
    ed.do("undo")
    assert ed.level.guns[0].bullet_offset_y == 0.0 and ed.level.guns[0].bullet_offset_z == 0.0


def test_a_click_on_empty_space_puts_the_picked_handle_there_and_dragging_goes_on(ed):
    add_gun(ed)
    c = card(ed)
    spot = (c.centerx + 90, c.centery - 60)
    press(ed, spot)
    first = (ed.level.guns[0].bullet_offset_y, ed.level.guns[0].bullet_offset_z)
    assert first[0] > 0 and first[1] > 0
    target = (c.centerx - 30, c.centery + 20)
    drag_to(ed, target)
    release(ed, target)
    assert ed.level.guns[0].bullet_offset_y < 0 < first[0]
    assert pixel(ed, ed.gizmo_points(ed.level.guns[0])["bullet"]) == pytest.approx(target, abs=2)


def test_dragging_outside_the_picture_keeps_the_handle_inside_it(ed):
    add_gun(ed)
    press(ed, pixel(ed, (0.0, 0.0, 0.0)))
    drag_to(ed, (5000, 5000))
    release(ed, (5000, 5000))
    c = card(ed)
    x, y = pixel(ed, ed.gizmo_points(ed.level.guns[0])["bullet"])
    assert c.collidepoint(x, y) and (x, y) == pytest.approx((c.right - 1, c.bottom - 1), abs=2)


# ------------------------------------------------------------------ the depth slider

def test_the_slider_ends_are_the_depth_range_and_a_click_sets_the_depth(ed):
    add_gun(ed)
    lo, hi = map_editor.GIZMO_DEPTH
    click(ed, slider_at(ed, 0.0))
    assert depth_of(ed) == pytest.approx(lo, abs=0.02)
    click(ed, slider_at(ed, 1.0))
    assert depth_of(ed) == pytest.approx(hi, abs=0.02)
    click(ed, slider_at(ed, 0.5))
    assert depth_of(ed) == pytest.approx((lo + hi) / 2, abs=0.03)
    assert ed.level.guns[0].bullet_offset_x == pytest.approx((lo + hi) / 2, abs=0.03)


def test_the_slider_moves_the_handle_in_and_out_and_leaves_right_and_up_alone(ed):
    gun = add_gun(ed)
    gun.bullet_offset_y, gun.bullet_offset_z = 0.3, -0.25
    c = card(ed)
    before = pixel(ed, ed.gizmo_points(gun)["bullet"])
    press(ed, slider_at(ed, 0.2))
    for i in range(1, 8):
        drag_to(ed, slider_at(ed, 0.2 + i * 0.1))
    release(ed, slider_at(ed, 0.9))
    shown = ed.level.guns[0]
    assert (shown.bullet_offset_y, shown.bullet_offset_z) == (0.3, -0.25)
    assert shown.bullet_offset_x > 1.5
    after = pixel(ed, ed.gizmo_points(shown)["bullet"])
    assert abs(after[0] - c.centerx) < abs(before[0] - c.centerx) or before[0] == c.right - 1   # further out: nearer the middle


def test_a_slider_drag_is_one_undo_step(ed):
    add_gun(ed)
    press(ed, slider_at(ed, 0.3))
    drag_to(ed, slider_at(ed, 0.6))
    release(ed, slider_at(ed, 0.9))
    assert ed.level.guns[0].bullet_offset_x > 1.0
    ed.do("undo")
    assert ed.level.guns[0].bullet_offset_x == 0.0


def test_the_slider_follows_the_picked_handle(ed):
    gun = gun_with_effect(ed)
    gun.bullet_offset_x, gun.muzzle_override, gun.muzzle_offset_x = 0.5, True, 0.4
    assert depth_of(ed) == pytest.approx(0.5)                                          # the bullets' depth
    click(ed, layout(ed)["buttons"]["effect"].center)
    assert depth_of(ed) == pytest.approx(0.9)                                          # the effect's, from the usual muzzle point
    ed.draw(pygame.display.get_surface())


# ------------------------------------------------------------------ the effect's handle

def test_the_effect_handle_starts_overriding_the_effects_own_offset_as_soon_as_it_moves(ed):
    gun = gun_with_effect(ed, offset_x=0.4, offset_y=0.1, offset_z=0.2)
    assert gun.muzzle_override is False
    points = ed.gizmo_points(gun)
    assert points["effect"] == pytest.approx((0.4, 0.1, 0.2))                          # the effect's own offset, from the bullets
    click(ed, layout(ed)["buttons"]["effect"].center)
    assert ed.gizmo_selected == "effect"
    c = card(ed)
    drag_picture(ed, points["effect"], (c.centerx - 60, c.centery + 10))
    shown = ed.level.guns[0]
    assert shown.muzzle_override is True
    assert shown.muzzle_offset_y < 0 and shown.muzzle_offset_x == pytest.approx(0.4)   # moved sideways; the depth was kept
    assert (shown.bullet_offset_x, shown.bullet_offset_y, shown.bullet_offset_z) == (0.0, 0.0, 0.0)


def test_the_slider_moves_the_effect_in_and_out_relative_to_the_bullets(ed):
    gun = gun_with_effect(ed)
    gun.bullet_offset_x, gun.bullet_offset_y = 0.2, 0.1
    click(ed, layout(ed)["buttons"]["effect"].center)
    click(ed, slider_at(ed, 1.0))
    shown = ed.level.guns[0]
    hi = map_editor.GIZMO_DEPTH[1]
    assert shown.muzzle_override is True
    assert shown.muzzle_offset_x == pytest.approx(hi - 0.2, abs=0.03)                  # the effect's own depth is the slider's
    assert shown.bullet_offset_x == 0.2 and shown.bullet_offset_y == 0.1               # the bullets stayed


def test_moving_the_bullets_handle_carries_the_effects_handle_with_it(ed):
    gun = gun_with_effect(ed)
    gun.muzzle_override, gun.muzzle_offset_x = True, 0.3
    c = card(ed)
    drag_picture(ed, ed.gizmo_points(gun)["bullet"], (c.centerx + 40, c.centery))
    shown = ed.level.guns[0]
    after = ed.gizmo_points(shown)
    assert after["effect"][0] - after["bullet"][0] == pytest.approx(0.3)               # the same offset from the bullets
    assert shown.bullet_offset_y > 0 and shown.muzzle_offset_x == 0.3


def test_the_buttons_pick_which_handle_moves_and_an_effect_needs_a_muzzle_effect(ed):
    add_gun(ed)
    click(ed, layout(ed)["buttons"]["effect"].center)
    assert ed.gizmo_selected == "bullet"                                               # nothing to move: stays on the bullets
    ed.level.effects = [Effect("Puff")]
    ed.set_gun("muzzle", "Puff")
    click(ed, layout(ed)["buttons"]["effect"].center)
    assert ed.gizmo_selected == "effect"
    click(ed, layout(ed)["buttons"]["bullet"].center)
    assert ed.gizmo_selected == "bullet"
    ed.draw(pygame.display.get_surface())


def test_a_click_on_a_handle_picks_it_but_where_they_overlap_the_picked_one_keeps_the_click(ed):
    gun = gun_with_effect(ed)
    gun.bullet_offset_x, gun.muzzle_override, gun.muzzle_offset_y = 1.0, True, 0.4
    c = card(ed)
    press(ed, pixel(ed, ed.gizmo_points(gun)["effect"]))                               # on the effect, apart from the bullets
    release(ed, pixel(ed, ed.gizmo_points(gun)["effect"]))
    assert ed.gizmo_selected == "effect"
    gun.muzzle_offset_y = 0.0                                                          # now they lie on top of each other
    spot = pixel(ed, ed.gizmo_points(gun)["bullet"])
    assert ed.gizmo_hit(c, gun, spot) == "effect"                                      # the picked one wins
    click(ed, layout(ed)["buttons"]["bullet"].center)
    assert ed.gizmo_hit(c, gun, spot) == "bullet"


def test_the_picture_shows_both_handles_in_their_own_colours(ed):
    gun = gun_with_effect(ed)
    gun.bullet_offset_x, gun.muzzle_override, gun.muzzle_offset_y = 1.0, True, 0.5
    ed.draw(pygame.display.get_surface())
    screen = pygame.display.get_surface()
    bullet, effect = (pixel(ed, p) for p in (ed.gizmo_points(gun)["bullet"], ed.gizmo_points(gun)["effect"]))
    assert tuple(screen.get_at(bullet)[:3]) == ORANGE and tuple(screen.get_at(effect)[:3]) == CYAN


# ------------------------------------------------------------------ with the live preview

def test_dragging_moves_the_running_preview_and_it_starts_over_when_the_mouse_is_let_go(ed):
    gun = add_gun(ed)
    controls = ed.gun_controls(card(ed))[0]
    click(ed, controls["continuous"][0].center)
    step(ed, 0.6)
    shots = ed.gun_preview.total_shots
    assert shots > 0
    c = card(ed)
    press(ed, pixel(ed, ed.gizmo_points(gun)["bullet"]))
    target = (c.centerx + 80, c.centery)
    drag_to(ed, target)
    live = ed.gun_preview.session.me.inventory.current().gun
    assert live.bullet_offset_y > 0.02                                                 # the running gun already uses it
    step(ed, 0.2)
    assert ed.gun_preview.total_shots >= shots                                         # (not restarted mid-drag)
    release(ed, target)
    step(ed, 0.1)
    assert ed.gun_preview.total_shots < shots + 5                                      # restarted when let go


def test_the_slider_also_moves_the_running_preview(ed):
    add_gun(ed)
    click(ed, ed.gun_controls(card(ed))[0]["continuous"][0].center)
    step(ed, 0.3)
    press(ed, slider_at(ed, 0.2))
    drag_to(ed, slider_at(ed, 0.8))
    live = ed.gun_preview.session.me.inventory.current().gun
    assert live.bullet_offset_x > 1.2
    release(ed, slider_at(ed, 0.8))


# ------------------------------------------------------------------ scrolling the Guns section

def scroll_to_end(ed):
    ed.mouse = ed.map_area().center
    for _ in range(40):
        wheel(ed, -5)


def test_the_wheel_scrolls_the_guns_section_and_everything_in_it_moves_together(small_ed):
    add_gun(small_ed)
    small_ed.draw(pygame.display.get_surface())
    row_before = small_ed.gun_rows()[0][0][0].y
    card_before = card(small_ed).y
    track_before = layout(small_ed)["track"].y
    small_ed.mouse = small_ed.map_area().center
    wheel(small_ed, -2)
    assert small_ed.guns_scroll > 0
    assert row_before - small_ed.gun_rows()[0][0][0].y == small_ed.guns_scroll
    assert card_before - card(small_ed).y == small_ed.guns_scroll
    assert track_before - layout(small_ed)["track"].y == small_ed.guns_scroll
    small_ed.draw(pygame.display.get_surface())


def test_the_scroll_stays_between_the_top_and_the_end_of_the_content(small_ed):
    add_gun(small_ed)
    small_ed.mouse = small_ed.map_area().center
    wheel(small_ed, 5)
    assert small_ed.guns_scroll == 0
    scroll_to_end(small_ed)
    furthest = small_ed.guns_scroll
    assert furthest == small_ed.guns_content_bottom() - small_ed.map_area().bottom
    wheel(small_ed, -5)
    assert small_ed.guns_scroll == furthest
    wheel(small_ed, 3)
    assert small_ed.guns_scroll < furthest


def test_the_handle_and_the_slider_still_work_after_scrolling(small_ed):
    gun = add_gun(small_ed)
    scroll_to_end(small_ed)
    assert small_ed.guns_scroll > 0
    area = small_ed.map_area()
    track = layout(small_ed)["track"]
    assert area.top <= track.y <= area.bottom                                          # the slider has scrolled into view
    click(small_ed, slider_at(small_ed, 0.9))
    assert small_ed.level.guns[0].bullet_offset_x > 1.8
    small_ed.draw(pygame.display.get_surface())
    assert gun.name == small_ed.level.guns[0].name
