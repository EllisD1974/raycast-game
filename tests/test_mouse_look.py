"""The center crosshair, and looking around with the mouse (including up and down)."""
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import main
import physics
from atlas import atlas_array, unpack_atlas
from constants import HEIGHT, MAX_PITCH_DEG, MOUSE_SENSITIVITY, WIDTH
from mapfile import Level
from world import World

GRAY = (100, 100, 100)


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1280, 800), pygame.RESIZABLE)
    yield
    pygame.quit()


@pytest.fixture(scope="module")
def renderer():
    return main.Renderer(atlas_array(unpack_atlas()))


def motion(dx, dy):
    return pygame.event.Event(pygame.MOUSEMOTION, pos=(0, 0), rel=(dx, dy), buttons=(0, 0, 0))


# ------------------------------------------------------------------ fitting the picture to the window

@pytest.mark.parametrize("size", [(1920, 1009), (1280, 800), (640, 400), (1000, 1000), (3000, 500),
                                  (500, 3000), (1, 1), (7, 5)])
def test_the_picture_keeps_its_aspect_ratio_and_is_centerd(size):
    rect = main.fit_rect(size)
    window = pygame.Rect(0, 0, *size)
    assert window.contains(rect)
    ratio = WIDTH / HEIGHT                                      # off by at most one pixel's rounding
    assert abs(rect.w / rect.h - ratio) <= ratio / min(rect.size) + 0.01
    assert abs(rect.centerx - window.centerx) <= 1 and abs(rect.centery - window.centery) <= 1
    assert rect.w == size[0] or rect.h == size[1] or min(size) < 3                 # as large as it can be


def test_a_window_of_the_picture_size_is_filled_exactly():
    assert tuple(main.fit_rect((WIDTH, HEIGHT))) == (0, 0, WIDTH, HEIGHT)


# ------------------------------------------------------------------ the crosshair

def crosshair_surface(arm, thickness, size=(101, 101)):
    surface = pygame.Surface(size)
    surface.fill(GRAY)
    main.draw_crosshair(surface, (size[0] // 2, size[1] // 2), arm, thickness)
    return surface


def test_the_crosshair_is_a_plus_centerd_on_the_given_point():
    surface = crosshair_surface(arm=8, thickness=1)
    cx, cy = 50, 50
    white = main.CROSSHAIR
    assert surface.get_at((cx, cy))[:3] == white
    for d in range(-8, 9):                                      # both bars, tip to tip
        assert surface.get_at((cx + d, cy))[:3] == white
        assert surface.get_at((cx, cy + d))[:3] == white
    assert surface.get_at((cx + 9, cy))[:3] == main.CROSSHAIR_OUTLINE       # a one pixel dark edge
    assert surface.get_at((cx, cy - 9))[:3] == main.CROSSHAIR_OUTLINE
    assert surface.get_at((cx + 11, cy))[:3] == GRAY                         # nothing further out
    assert surface.get_at((cx + 4, cy + 4))[:3] == GRAY                      # and nothing off the axes
    assert surface.get_at((cx - 4, cy - 4))[:3] == GRAY


def test_the_crosshair_is_symmetric_and_thin():
    surface = crosshair_surface(arm=8, thickness=1)
    for dx in range(-12, 13):
        for dy in range(-12, 13):
            assert surface.get_at((50 + dx, 50 + dy)) == surface.get_at((50 - dx, 50 - dy))
            assert surface.get_at((50 + dx, 50 + dy)) == surface.get_at((50 + dy, 50 + dx))   # same both ways
    white = sum(1 for x in range(101) for y in range(101) if surface.get_at((x, y))[:3] == main.CROSSHAIR)
    assert white == 2 * (2 * 8 + 1) - 1                          # two one pixel bars crossing once


def test_a_thicker_crosshair_is_still_a_plus():
    surface = crosshair_surface(arm=10, thickness=2)
    white = [(x, y) for x in range(101) for y in range(101) if surface.get_at((x, y))[:3] == main.CROSSHAIR]
    xs, ys = [p[0] for p in white], [p[1] for p in white]
    assert min(xs) == 40 and max(xs) == 60 and min(ys) == 40 and max(ys) == 60
    assert surface.get_at((43, 43))[:3] == GRAY


@pytest.mark.parametrize("size", [(1920, 1009), (1280, 800), (640, 400), (900, 1200)])
def test_the_crosshair_is_drawn_in_the_middle_of_the_window(size):
    screen = pygame.Surface(size)
    frame = pygame.Surface((WIDTH, HEIGHT))
    frame.fill((30, 60, 90))
    main.present(screen, frame)
    rect = main.fit_rect(size)
    cx, cy = rect.center
    assert screen.get_at((cx, cy))[:3] == main.CROSSHAIR
    assert abs(cx - size[0] // 2) <= 1 and abs(cy - size[1] // 2) <= 1
    white = [(x, y) for x in range(rect.left, rect.right) for y in range(rect.top, rect.bottom)
             if screen.get_at((x, y))[:3] == main.CROSSHAIR]
    assert white and all(abs(x - cx) <= rect.height // 60 + 1 or abs(y - cy) <= rect.height // 60 + 1 for x, y in white)
    assert len(white) < rect.w * rect.h * 0.002                  # thin: a tiny part of the picture


def test_present_scales_the_picture_into_the_fitted_rectangle():
    size = (1000, 1000)
    screen = pygame.Surface(size)
    frame = pygame.Surface((WIDTH, HEIGHT))
    frame.fill((200, 40, 40))
    main.present(screen, frame)
    rect = main.fit_rect(size)
    assert screen.get_at((rect.left + 2, rect.top + 2))[:3] == (200, 40, 40)
    assert screen.get_at((rect.right - 3, rect.bottom - 3))[:3] == (200, 40, 40)
    assert screen.get_at((5, 5))[:3] == (0, 0, 0)                # letterbox bar above the picture
    assert screen.get_at((5, size[1] - 5))[:3] == (0, 0, 0)


# ------------------------------------------------------------------ capturing the mouse and turning

def test_mouse_movement_turns_and_tilts_with_the_right_signs():
    look = main.MouseLook()
    look.set_captured(True)
    look.handle_event(motion(40, 0))
    turn, tilt = look.take()
    assert turn == pytest.approx(40 * MOUSE_SENSITIVITY) and tilt == 0        # right turns right (positive)
    look.handle_event(motion(0, -30))
    turn, tilt = look.take()
    assert turn == 0 and tilt == pytest.approx(30 * MOUSE_SENSITIVITY)        # up tilts the view up
    look.handle_event(motion(-10, 20))
    turn, tilt = look.take()
    assert turn == pytest.approx(-10 * MOUSE_SENSITIVITY) and tilt == pytest.approx(-20 * MOUSE_SENSITIVITY)


def test_movement_between_frames_adds_up_and_is_consumed_once():
    look = main.MouseLook()
    look.set_captured(True)
    for _ in range(5):
        look.handle_event(motion(3, -2))
    turn, tilt = look.take()
    assert turn == pytest.approx(15 * MOUSE_SENSITIVITY) and tilt == pytest.approx(10 * MOUSE_SENSITIVITY)
    assert look.take() == (0.0, -0.0) or look.take() == (0.0, 0.0)


def test_an_uncaptured_mouse_does_not_turn_the_view():
    look = main.MouseLook()
    look.set_captured(False)
    look.handle_event(motion(500, 500))
    assert look.take() == (0.0, 0.0) or look.take() == (0.0, -0.0)


def test_capturing_hides_and_grabs_the_cursor_and_forgets_old_movement():
    look = main.MouseLook()
    look.set_captured(True)
    look.handle_event(motion(99, 99))
    assert look.captured and pygame.event.get_grab() and not pygame.mouse.get_visible()
    look.set_captured(False)
    assert not look.captured and not pygame.event.get_grab() and pygame.mouse.get_visible()
    look.set_captured(True)
    assert look.take() == (0.0, 0.0) or look.take() == (0.0, -0.0)            # movement from before is gone


def test_clicking_takes_the_mouse_back_and_losing_focus_lets_go():
    look = main.MouseLook()
    look.set_captured(False)
    look.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(10, 10), button=1))
    assert look.captured
    look.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
    assert not look.captured and pygame.mouse.get_visible()


def test_sensitivity_does_not_depend_on_the_window_size():
    """Mouse movement is in screen pixels (the picture is scaled by us, not by pygame), so the
    same hand movement turns the view the same amount in a small window and a maximized one."""
    look = main.MouseLook()
    look.set_captured(True)
    for size in ((640, 400), (1920, 1009)):
        pygame.display.set_mode(size, pygame.RESIZABLE)
        look.handle_event(motion(100, 0))
        assert look.take()[0] == pytest.approx(100 * MOUSE_SENSITIVITY)
    pygame.display.set_mode((1280, 800), pygame.RESIZABLE)


# ------------------------------------------------------------------ the pitch limit

def test_looking_up_and_down_is_clipped_to_the_maximum_angle():
    player = physics.Player(1.5, 1.5, 0.0)
    limit = math.radians(MAX_PITCH_DEG)
    assert limit == physics.MAX_PITCH and MAX_PITCH_DEG == 90.0
    physics.look(player, 0.3)
    assert player.pitch == pytest.approx(0.3)
    physics.look(player, 0.3)
    assert player.pitch == pytest.approx(0.6)                    # adds up
    physics.look(player, 10.0)
    assert player.pitch == pytest.approx(limit)                  # clipped at the top
    physics.look(player, 0.5)
    assert player.pitch == pytest.approx(limit)                  # and stays there
    physics.look(player, -20.0)
    assert player.pitch == pytest.approx(-limit)                 # clipped at the bottom
    physics.look(player, 0.2)
    assert player.pitch == pytest.approx(-limit + 0.2)           # and comes back the other way


def test_a_big_mouse_swing_cannot_go_past_straight_up_or_down():
    player = physics.Player(1.5, 1.5, 0.0)
    look = main.MouseLook()
    look.set_captured(True)
    for dy in (-5000, 5000):
        look.handle_event(motion(0, dy))
        physics.look(player, look.take()[1])
        assert abs(player.pitch) == pytest.approx(physics.MAX_PITCH)


def test_mouse_turning_adds_to_the_players_heading_through_the_physics_step():
    level = Level.blank(10, 10)
    level.set("ceil_h", 5, 5, 3.0)
    world = World(level, 256)
    player = physics.Player(5.5, 5.5, 0.0, angle=1.0)
    look = main.MouseLook()
    look.set_captured(True)
    look.handle_event(motion(80, 0))
    turn, _ = look.take()
    physics.step(world, player, 0, 0, turn, False, 1 / 60)
    assert player.angle == pytest.approx(1.0 + 80 * MOUSE_SENSITIVITY)
    assert (player.x, player.y) == (5.5, 5.5)                    # turning does not move you


# ------------------------------------------------------------------ what looking up and down shows

def test_the_horizon_moves_down_when_looking_up_and_up_when_looking_down(renderer):
    player = physics.Player(1.5, 1.5, 0.0)
    assert renderer.horizon(player) == pytest.approx(HEIGHT / 2)
    horizons = []
    for pitch in (-physics.MAX_PITCH, -0.3, 0.0, 0.3, physics.MAX_PITCH):
        player.pitch = pitch
        horizons.append(renderer.horizon(player))
    assert horizons == sorted(horizons)                          # up (positive pitch) = larger row
    assert horizons[4] - HEIGHT / 2 == pytest.approx(HEIGHT / 2 - horizons[0])             # symmetric
    assert horizons[4] == pytest.approx(HEIGHT / 2 + math.tan(physics.MAX_PITCH) * renderer.focal)


def room_world():
    level = Level.blank(16, 16)
    for y in range(1, 15):
        for x in range(1, 15):
            level.set("ceil_h", x, y, 1.6)
    return World(level, 256)


def render(renderer, world, pitch):
    player = physics.Player(8.5, 8.5, 0.0, angle=0.7, pitch=pitch)
    return renderer.draw(world, player), np.array(renderer.framebuffer)


def test_the_view_at_the_pitch_limit_is_all_ceiling_or_all_floor_with_no_gaps(renderer):
    world = room_world()
    sentinel = np.array((255, 0, 255), np.uint8)
    for pitch in (physics.MAX_PITCH, -physics.MAX_PITCH):
        player = physics.Player(8.5, 8.5, 0.0, angle=0.7, pitch=pitch)
        renderer.framebuffer[:] = sentinel
        renderer.draw(world, player)
        assert not (renderer.framebuffer == sentinel).all(axis=2).any()


def test_the_crosshair_is_not_part_of_the_rendered_view(renderer):
    """It is drawn on the window, at screen resolution, so snapshots and the scaled picture stay clean."""
    world = room_world()
    surface, frame = render(renderer, world, 0.0)
    cx, cy = WIDTH // 2, HEIGHT // 2
    assert tuple(frame[cx, cy]) != main.CROSSHAIR or tuple(frame[cx + 6, cy]) != main.CROSSHAIR
    assert surface.get_size() == (WIDTH, HEIGHT)


# ------------------------------------------------------------------ the game window

def red_frame():
    frame = pygame.Surface((WIDTH, HEIGHT))
    frame.fill((200, 40, 40))
    return frame


def white_pixels(surface):
    return {(x, y) for x in range(surface.get_width()) for y in range(surface.get_height())
            if surface.get_at((x, y))[:3] == main.CROSSHAIR}


def test_the_screen_shows_the_picture_fitted_with_the_crosshair_through_its_renderer():
    size = (1000, 1000)
    screen = main.Screen("test", size)
    try:
        assert screen.gpu is not None
        screen.show(red_frame())
        shown = screen.gpu.to_surface()
        rect = main.fit_rect(size)
        assert shown.get_at((rect.left + 2, rect.top + 2))[:3] == (200, 40, 40)
        assert shown.get_at((rect.right - 3, rect.bottom - 3))[:3] == (200, 40, 40)
        assert shown.get_at((5, 5))[:3] == (0, 0, 0)            # letterbox bars
        assert shown.get_at((5, size[1] - 5))[:3] == (0, 0, 0)
        cpu = pygame.Surface(size)
        main.present(cpu, red_frame())
        assert white_pixels(shown) == white_pixels(cpu)         # the same crosshair as the CPU way draws
    finally:
        screen.window.destroy()


def test_without_a_renderer_the_screen_scales_the_picture_itself(monkeypatch):
    def no_renderer(*args, **kwargs):
        raise main.sdl2.error("Couldn't find matching render driver")
    monkeypatch.setattr(main.video, "Renderer", no_renderer)
    size = (1000, 1000)
    screen = main.Screen("test", size)
    try:
        assert screen.gpu is None
        screen.show(red_frame())
        shown = screen.window.get_surface()
        rect = main.fit_rect(size)
        assert shown.get_at((rect.left + 2, rect.top + 2))[:3] == (200, 40, 40)
        assert shown.get_at(rect.center)[:3] == main.CROSSHAIR
    finally:
        screen.window.destroy()


def test_f11_fills_the_screen_and_back_and_the_title_shows_what_it_is_given():
    screen = main.Screen("test", (800, 450))
    try:
        screen.toggle_fullscreen()
        assert screen.fullscreen
        screen.toggle_fullscreen()
        assert not screen.fullscreen and screen.window.size == (800, 450)
        screen.title = "simple raycaster - 120 fps"
        assert screen.window.title == screen.title == "simple raycaster - 120 fps"
    finally:
        screen.window.destroy()


def test_the_mouse_is_held_in_the_game_window_while_captured():
    screen = main.Screen("test", (800, 450))
    try:
        look = main.MouseLook(screen.window)
        look.set_captured(True)
        assert screen.window.grab_mouse and not pygame.mouse.get_visible()
        look.set_captured(False)
        assert not screen.window.grab_mouse and pygame.mouse.get_visible()
    finally:
        screen.window.destroy()
