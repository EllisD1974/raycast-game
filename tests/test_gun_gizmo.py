"""Placing where a gun's bullets and muzzle effect come from by dragging in the Guns section, and scrolling that section.

Two views share the work: the side view has the gun on the left facing right (across is ahead of the gun, up is up)
and the view from behind has the gun at the bottom middle facing up (across is right of the gun, up is up).
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


def gizmo(ed):
    return ed.gizmo_layout(ed.guns_card_rect())


def pixel(ed, view, point):
    """The pixel in a view of a point given as (ahead, right, up) offsets from the gun's usual muzzle point."""
    return ed.gizmo_pixel(gizmo(ed), view, point)


def step(ed, seconds):
    for _ in range(round(seconds / DT)):
        ed.update(DT, pygame.key.get_pressed())


def drag(ed, view, start, end):
    press(ed, pixel(ed, view, start))
    target = pixel(ed, view, end)
    drag_to(ed, target)
    release(ed, target)


# ------------------------------------------------------------------ the layout

def test_the_two_views_sit_under_the_picture_at_one_scale(ed):
    add_gun(ed)
    layout = gizmo(ed)
    assert set(layout["views"]) == {"side", "back"} and set(layout["buttons"]) == {"bullet", "effect"}
    side, back = layout["views"]["side"], layout["views"]["back"]
    card = ed.guns_card_rect()
    assert side.top > card.bottom and side.height == back.height and back.left > side.right
    assert side.left == card.left and back.right <= card.right
    assert side.width / (map_editor.GIZMO_AHEAD[1] - map_editor.GIZMO_AHEAD[0]) == pytest.approx(layout["scale"], abs=1)
    assert back.width / (map_editor.GIZMO_RIGHT[1] - map_editor.GIZMO_RIGHT[0]) == pytest.approx(layout["scale"], abs=1)
    assert layout["bottom"] > side.bottom
    ed.draw(pygame.display.get_surface())


def test_the_gun_is_on_the_left_in_the_side_view_and_at_the_bottom_middle_from_behind(ed):
    add_gun(ed)
    layout = gizmo(ed)
    side, back = layout["views"]["side"], layout["views"]["back"]
    sx, sy = pixel(ed, "side", (0.0, 0.0, 0.0))                       # the gun's muzzle in each view
    bx, by = pixel(ed, "back", (0.0, 0.0, 0.0))
    assert side.left + side.width * 0.2 < sx < side.left + side.width * 0.5          # near the left, with room for the gun
    assert abs(bx - back.centerx) <= 1                                               # in the middle across
    assert by > back.top + back.height * 0.6                                         # low down: the gun stands at the bottom


def test_across_and_up_go_the_way_they_look(ed):
    add_gun(ed)
    x0, y0 = pixel(ed, "side", (0.0, 0.0, 0.0))
    ahead_x, _ = pixel(ed, "side", (0.5, 0.0, 0.0))
    _, up_y = pixel(ed, "side", (0.0, 0.0, 0.5))
    assert ahead_x > x0 and up_y < y0                                                # more ahead is right, up is up the screen
    bx0, by0 = pixel(ed, "back", (0.0, 0.0, 0.0))
    right_x, _ = pixel(ed, "back", (0.0, 0.5, 0.0))
    left_x, _ = pixel(ed, "back", (0.0, -0.5, 0.0))
    _, up_by = pixel(ed, "back", (0.0, 0.0, 0.5))
    assert right_x > bx0 > left_x and up_by < by0


def test_the_points_are_offsets_from_the_usual_muzzle_point(ed):
    gun = add_gun(ed)
    assert ed.gizmo_points(gun) == {"bullet": (0.0, 0.0, 0.0)}                       # no effect, so no effect handle
    gun.bullet_offset_x, gun.bullet_offset_y, gun.bullet_offset_z = 0.5, 0.3, -0.25
    assert ed.gizmo_points(gun)["bullet"] == pytest.approx((0.5, 0.3, -0.25))        # exactly the pane's rows


def test_a_handle_further_out_than_the_view_reaches_sits_on_its_edge(ed):
    add_gun(ed)
    layout = gizmo(ed)
    x, y = pixel(ed, "side", (4.0, 0.0, 4.0))
    view = layout["views"]["side"]
    assert (x, y) == (view.right, view.top)


# ------------------------------------------------------------------ dragging the bullets' handle

def test_dragging_in_the_side_view_sets_ahead_and_up_and_leaves_right_alone(ed):
    gun = add_gun(ed)
    gun.bullet_offset_y = 0.4
    drag(ed, "side", (0.0, 0.4, 0.0), (0.6, 0.4, -0.3))
    shown = ed.level.guns[0]
    assert (shown.bullet_offset_x, shown.bullet_offset_z) == pytest.approx((0.6, -0.3), abs=0.02)
    assert shown.bullet_offset_y == 0.4


def test_dragging_from_behind_sets_right_and_up_and_leaves_ahead_alone(ed):
    gun = add_gun(ed)
    gun.bullet_offset_x = 0.7
    drag(ed, "back", (0.7, 0.0, 0.0), (0.7, -0.4, 0.5))
    shown = ed.level.guns[0]
    assert (shown.bullet_offset_y, shown.bullet_offset_z) == pytest.approx((-0.4, 0.5), abs=0.02)
    assert shown.bullet_offset_x == 0.7


def test_a_whole_drag_is_one_undo_step_and_marks_the_map_changed(ed):
    gun = add_gun(ed)
    ed.dirty = False
    start = pixel(ed, "side", ed.gizmo_points(gun)["bullet"])
    press(ed, start)
    for i in range(1, 6):
        drag_to(ed, (start[0] + i * 6, start[1] + i * 4))
    release(ed, (start[0] + 30, start[1] + 20))
    assert ed.dirty and ed.level.guns[0].bullet_offset_x != 0.0
    ed.do("undo")
    assert ed.level.guns[0].bullet_offset_x == 0.0 and ed.level.guns[0].bullet_offset_z == 0.0


def test_a_click_on_empty_space_puts_the_picked_handle_there_and_dragging_goes_on(ed):
    add_gun(ed)
    press(ed, pixel(ed, "back", (0.0, 0.6, 0.7)))
    assert (ed.level.guns[0].bullet_offset_y, ed.level.guns[0].bullet_offset_z) == pytest.approx((0.6, 0.7), abs=0.02)
    target = pixel(ed, "back", (0.0, -0.2, 0.1))
    drag_to(ed, target)
    release(ed, target)
    assert (ed.level.guns[0].bullet_offset_y, ed.level.guns[0].bullet_offset_z) == pytest.approx((-0.2, 0.1), abs=0.02)


def test_dragging_outside_a_view_keeps_the_handle_inside_it(ed):
    add_gun(ed)
    press(ed, pixel(ed, "side", (0.0, 0.0, 0.0)))
    drag_to(ed, (5000, 5000))
    release(ed, (5000, 5000))
    gun = ed.level.guns[0]
    assert map_editor.GIZMO_AHEAD[0] <= gun.bullet_offset_x <= map_editor.GIZMO_AHEAD[1]
    assert map_editor.GIZMO_UP[0] <= gun.bullet_offset_z <= map_editor.GIZMO_UP[1]


# ------------------------------------------------------------------ the effect's handle

def test_the_effect_handle_starts_overriding_the_effects_own_offset_as_soon_as_it_moves(ed):
    gun = gun_with_effect(ed, offset_x=0.4, offset_y=0.1, offset_z=0.2)
    assert gun.muzzle_override is False
    points = ed.gizmo_points(gun)
    assert points["effect"] == pytest.approx((0.4, 0.1, 0.2))                        # the effect's own offset, from the bullets
    click(ed, gizmo(ed)["buttons"]["effect"].center)
    assert ed.gizmo_selected == "effect"
    drag(ed, "side", points["effect"], (0.9, 0.1, -0.1))
    shown = ed.level.guns[0]
    assert shown.muzzle_override is True
    assert (shown.muzzle_offset_x, shown.muzzle_offset_z) == pytest.approx((0.9, -0.1), abs=0.02)
    assert shown.muzzle_offset_y == pytest.approx(0.1)                               # the side view leaves right as it was


def test_the_effect_handle_from_behind_sets_right_and_up(ed):
    gun_with_effect(ed)
    click(ed, gizmo(ed)["buttons"]["effect"].center)
    drag(ed, "back", (0.0, 0.0, 0.0), (0.0, -0.5, 0.6))
    shown = ed.level.guns[0]
    assert shown.muzzle_override is True
    assert (shown.muzzle_offset_y, shown.muzzle_offset_z) == pytest.approx((-0.5, 0.6), abs=0.02)
    assert shown.muzzle_offset_x == 0.0


def test_moving_the_bullets_handle_carries_the_effects_handle_with_it(ed):
    gun = gun_with_effect(ed)
    gun.muzzle_override, gun.muzzle_offset_x = True, 0.3
    drag(ed, "side", ed.gizmo_points(gun)["bullet"], (0.5, 0.0, 0.2))
    after = ed.gizmo_points(ed.level.guns[0])
    assert after["effect"][0] - after["bullet"][0] == pytest.approx(0.3)             # the same offset from the bullets
    assert after["bullet"][0] == pytest.approx(0.5, abs=0.02)


def test_the_buttons_pick_which_handle_moves_and_an_effect_needs_a_muzzle_effect(ed):
    add_gun(ed)
    click(ed, gizmo(ed)["buttons"]["effect"].center)
    assert ed.gizmo_selected == "bullet"                                             # nothing to move: stays on the bullets
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
    press(ed, pixel(ed, "side", points["effect"]))                                   # on the effect handle, apart from the bullets
    release(ed, pixel(ed, "side", points["effect"]))
    assert ed.gizmo_selected == "effect"
    gun.muzzle_offset_x = 0.0                                                        # now they lie on top of each other
    spot = pixel(ed, "side", ed.gizmo_points(gun)["bullet"])
    assert ed.gizmo_hit(gizmo(ed), gun, spot) == ("side", "effect")                  # the picked one wins
    click(ed, gizmo(ed)["buttons"]["bullet"].center)
    assert ed.gizmo_hit(gizmo(ed), gun, spot) == ("side", "bullet")


def test_the_views_draw_with_both_handles_and_while_dragging(ed):
    gun = gun_with_effect(ed)
    gun.muzzle_override, gun.muzzle_offset_x, gun.muzzle_offset_z = True, 0.4, 0.3
    ed.draw(pygame.display.get_surface())
    press(ed, pixel(ed, "back", ed.gizmo_points(gun)["bullet"]))
    ed.draw(pygame.display.get_surface())
    release(ed, pixel(ed, "back", ed.gizmo_points(gun)["bullet"]))


# ------------------------------------------------------------------ with the live preview

def test_dragging_moves_the_running_preview_and_it_starts_over_when_the_mouse_is_let_go(ed):
    gun = add_gun(ed)
    controls = ed.gun_controls(ed.guns_card_rect())[0]
    click(ed, controls["continuous"][0].center)
    step(ed, 0.6)
    shots = ed.gun_preview.total_shots
    assert shots > 0
    press(ed, pixel(ed, "back", ed.gizmo_points(gun)["bullet"]))
    target = pixel(ed, "back", (0.0, 0.45, 0.0))
    drag_to(ed, target)
    live = ed.gun_preview.session.me.inventory.current().gun
    assert live.bullet_offset_y == pytest.approx(0.45, abs=0.02)                     # the running gun already uses it
    step(ed, 0.2)
    assert ed.gun_preview.total_shots >= shots                                       # (not restarted mid-drag)
    release(ed, target)
    step(ed, 0.1)
    assert ed.gun_preview.total_shots < shots + 5                                    # restarted when let go


def test_the_gun_picture_marks_a_handle_that_is_in_front_of_the_eye(ed):
    add_gun(ed)
    ed.set_gun("bullet_offset_x", 2.0)
    ed.set_gun("bullet_offset_y", 0.3)
    step(ed, 0.1)
    ed.draw(pygame.display.get_surface())                                            # draws the markers without trouble


# ------------------------------------------------------------------ scrolling the Guns section

def test_the_wheel_scrolls_the_guns_section_and_everything_in_it_moves_together(small_ed):
    add_gun(small_ed)
    small_ed.draw(pygame.display.get_surface())
    row_before = small_ed.gun_rows()[0][0][0].y
    card_before = small_ed.guns_card_rect().y
    views_before = gizmo(small_ed)["views"]["side"].y
    small_ed.mouse = small_ed.map_area().center
    wheel(small_ed, -2)
    assert small_ed.guns_scroll > 0
    assert row_before - small_ed.gun_rows()[0][0][0].y == small_ed.guns_scroll
    assert card_before - small_ed.guns_card_rect().y == small_ed.guns_scroll
    assert views_before - gizmo(small_ed)["views"]["side"].y == small_ed.guns_scroll
    small_ed.draw(pygame.display.get_surface())


def test_the_scroll_stays_between_the_top_and_the_end_of_the_content(small_ed):
    add_gun(small_ed)
    small_ed.mouse = small_ed.map_area().center
    wheel(small_ed, 5)
    assert small_ed.guns_scroll == 0
    for _ in range(40):
        wheel(small_ed, -5)
    furthest = small_ed.guns_scroll
    assert furthest == small_ed.guns_content_bottom() - small_ed.map_area().bottom
    wheel(small_ed, -5)
    assert small_ed.guns_scroll == furthest
    wheel(small_ed, 3)
    assert small_ed.guns_scroll < furthest


def test_the_handles_can_still_be_grabbed_after_scrolling(small_ed):
    gun = add_gun(small_ed)
    small_ed.mouse = small_ed.map_area().center
    for _ in range(40):
        wheel(small_ed, -5)
    assert small_ed.guns_scroll > 0
    drag(small_ed, "back", small_ed.gizmo_points(gun)["bullet"], (0.0, -0.4, 0.3))
    assert small_ed.level.guns[0].bullet_offset_y == pytest.approx(-0.4, abs=0.02)
    small_ed.draw(pygame.display.get_surface())
