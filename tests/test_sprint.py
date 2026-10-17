"""Sprinting: Shift together with a movement key."""
import math
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import physics
from constants import MOVE_SPEED, SPRINT_MULTIPLIER
from main import read_movement
from test_world_and_physics import platform_world, slot_over_ramp
from world import World

DT = 1 / 60


class FakeKeys(dict):
    """Stands in for pygame.key.get_pressed(): any key not listed is not pressed."""

    def __missing__(self, key):
        return False


def keys(*pressed):
    return FakeKeys({k: True for k in pressed})


def open_world():
    return platform_world()


def walked(world, forward, strafe, sprint, ticks=60, angle=0.0, x=14.0, y=3.0):
    player = physics.Player(x, y, 0.0, angle, span=0)
    for _ in range(ticks):
        physics.step(world, player, forward, strafe, 0.0, False, DT, sprint)
    return math.hypot(player.x - x, player.y - y), player


# ------------------------------------------------------------------ reading the keys

def test_shift_is_sprint_with_either_shift_key():
    assert read_movement(keys(pygame.K_w)) == (1, 0, 0, False)
    assert read_movement(keys(pygame.K_w, pygame.K_LSHIFT)) == (1, 0, 0, True)
    assert read_movement(keys(pygame.K_w, pygame.K_RSHIFT)) == (1, 0, 0, True)
    assert read_movement(keys(pygame.K_LSHIFT)) == (0, 0, 0, True)          # reported; physics ignores it


def test_movement_keys_are_unchanged():
    assert read_movement(keys(pygame.K_UP, pygame.K_d)) == (1, 1, 0, False)
    assert read_movement(keys(pygame.K_s, pygame.K_a, pygame.K_LEFT)) == (-1, -1, -1, False)
    assert read_movement(keys(pygame.K_DOWN, pygame.K_RIGHT)) == (-1, 0, 1, False)
    assert read_movement(keys(pygame.K_w, pygame.K_s)) == (0, 0, 0, False)  # opposite keys cancel


# ------------------------------------------------------------------ speed

@pytest.mark.parametrize("forward, strafe", [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1)])
def test_sprinting_is_faster_in_every_direction(forward, strafe):
    world = open_world()                    # open ground: 15 ticks stay clear of every wall
    walk, _ = walked(world, forward, strafe, False, ticks=15)
    run, _ = walked(world, forward, strafe, True, ticks=15)
    assert walk > 0.7 and run == pytest.approx(walk * SPRINT_MULTIPLIER, rel=1e-6)


def test_walking_speed_is_still_the_default():
    world = open_world()
    distance, _ = walked(world, 1, 0, False, ticks=60)
    assert distance == pytest.approx(MOVE_SPEED * 1.0, rel=1e-6)            # one second of walking
    run, _ = walked(world, 1, 0, True, ticks=60)
    assert run == pytest.approx(MOVE_SPEED * SPRINT_MULTIPLIER, rel=1e-6)


def test_shift_alone_does_not_move_the_player():
    distance, player = walked(open_world(), 0, 0, True)
    assert distance == 0.0 and player.vx == 0.0 and player.vy == 0.0


def test_letting_go_of_shift_returns_to_walking_speed_at_once():
    world = open_world()
    player = physics.Player(8.0, 3.5, 0.0, 0.0, span=0)
    physics.step(world, player, 1, 0, 0.0, False, DT, True)
    assert player.vx == pytest.approx(MOVE_SPEED * SPRINT_MULTIPLIER)
    physics.step(world, player, 1, 0, 0.0, False, DT, False)
    assert player.vx == pytest.approx(MOVE_SPEED)


def test_sprint_is_optional_in_the_physics_step():
    world = open_world()
    a = physics.Player(8.0, 3.5, 0.0, 0.0, span=0)
    b = physics.Player(8.0, 3.5, 0.0, 0.0, span=0)
    physics.step(world, a, 1, 0, 0.0, False, DT)
    physics.step(world, b, 1, 0, 0.0, False, DT, False)
    assert (a.x, a.vx) == (b.x, b.vx)


# ------------------------------------------------------------------ walls, ramps, ledges at sprint speed

def test_a_sprinting_player_cannot_run_through_a_wall():
    _, player = walked(open_world(), 1, 0, True, ticks=240, x=15.0)
    assert player.x < 23.0 - physics.PLAYER_RADIUS + 1e-6
    _, player = walked(open_world(), 1, 0, True, ticks=240, x=15.0, angle=math.pi / 2)
    assert player.y < 6.0 - physics.PLAYER_RADIUS + 1e-6


def test_sprinting_up_stairs_and_ramps():
    world = World(slot_over_ramp(), 256)
    player = physics.Player(5.5, 2.5, 0.0, 0.0, span=0)
    for _ in range(240):
        physics.step(world, player, 1, 0, 0.0, False, DT, True)
    assert player.span == 1 and player.z == pytest.approx(1.75, abs=1e-3) and player.x > 15.0


@pytest.mark.parametrize("y", [2.0, 2.05, 2.15, 2.5, 2.85, 2.95, 2.99])
def test_sprinting_up_the_ramp_along_its_edges_is_not_a_dead_end(y):
    world = World(slot_over_ramp(), 256)
    player = physics.Player(5.5, y, 0.0, 0.0, span=0)
    for _ in range(300):
        physics.step(world, player, 1, 0, 0.0, False, DT, True)
    assert player.span == 1 and player.z == pytest.approx(1.75, abs=1e-3) and player.x > 15.0


@pytest.mark.parametrize("name, x, y, angle", [
    ("north edge, heading south", 10.5, 1.5, math.pi / 2),
    ("south edge, heading north", 10.5, 3.5, -math.pi / 2),
    ("west end, heading east", 7.5, 2.5, 0.0),
])
def test_sprinting_off_the_second_floor_never_leaves_the_player_stuck(name, x, y, angle):
    world = World(slot_over_ramp(), 256)
    for walk_ticks in range(0, 40, 2):
        player = physics.Player(x, y, 1.75, angle, span=1)
        for tick in range(240):
            forward = 1.0 if tick < walk_ticks else 0.0
            physics.step(world, player, forward, 0.0, 0.0, False, DT, True)
            assert physics.can_stand(world, player.x, player.y, player.z, player.span, player.on_ground), \
                f"{name}: box inside the geometry after {walk_ticks} ticks sprinting, tick {tick}"
        assert player.on_ground


def test_a_sprinting_random_walk_never_leaves_the_player_wedged():
    rng = random.Random(11)
    world = World(slot_over_ramp(), 256)
    worst = 0
    for _ in range(25):
        player = physics.Player(rng.uniform(4, 6), rng.uniform(1.4, 3.6), 0.0, rng.uniform(0, math.tau), span=0)
        streak = 0
        for tick in range(600):
            if tick % 40 == 0:
                keys_now = (rng.choice((0.0, 1.0, 1.0)), rng.choice((-1.0, 0.0, 1.0)), rng.uniform(-0.05, 0.05))
            physics.step(world, player, keys_now[0], keys_now[1], keys_now[2], rng.random() < 0.01, DT, True)
            fits = physics.can_stand(world, player.x, player.y, player.z, player.span, player.on_ground)
            streak = 0 if fits or not player.on_ground else streak + 1
            worst = max(worst, streak)
    assert worst <= 8, f"wedged for {worst} ticks"


# ------------------------------------------------------------------ in the air

def test_a_sprinting_jump_keeps_the_sprint_speed_and_goes_farther():
    world = open_world()

    def distance(sprint):
        player = physics.Player(8.0, 3.5, 0.0, 0.0, span=0)
        physics.step(world, player, 1, 0, 0.0, True, DT, sprint)             # jump while moving
        start = player.x
        for _ in range(90):
            physics.step(world, player, 0, 0, 0.0, False, DT, False)         # keys released in the air
            if player.on_ground:
                break
        return player.x - start

    assert distance(True) > distance(False) * 1.4


def test_holding_forward_in_the_air_does_not_slow_a_sprinting_jump():
    world = open_world()
    player = physics.Player(8.0, 3.5, 0.0, 0.0, span=0)
    physics.step(world, player, 1, 0, 0.0, True, DT, True)
    sprint_speed = player.vx
    assert sprint_speed == pytest.approx(MOVE_SPEED * SPRINT_MULTIPLIER)
    for _ in range(20):
        physics.step(world, player, 1, 0, 0.0, False, DT, False)             # Shift released, forward held
        if player.on_ground:
            break
        assert player.vx == pytest.approx(sprint_speed, rel=1e-6)


def test_pressing_shift_in_the_air_does_not_add_speed():
    world = open_world()
    player = physics.Player(8.0, 3.5, 0.0, 0.0, span=0)
    physics.step(world, player, 1, 0, 0.0, True, DT, False)                  # walking jump
    for _ in range(20):
        physics.step(world, player, 1, 0, 0.0, False, DT, True)              # Shift pressed mid-air
        if player.on_ground:
            break
        assert player.vx <= MOVE_SPEED + 1e-6


def test_steering_in_the_air_never_exceeds_the_speed_you_left_the_ground_with():
    world = open_world()
    player = physics.Player(8.0, 3.5, 0.0, 0.0, span=0)
    physics.step(world, player, 1, 0, 0.0, True, DT, True)
    limit = math.hypot(player.vx, player.vy)
    for _ in range(25):
        physics.step(world, player, 0, 1, 0.0, False, DT, True)              # strafe sideways in the air
        assert math.hypot(player.vx, player.vy) <= limit + 1e-6
        if player.on_ground:
            break


def test_walking_off_a_ledge_while_sprinting_carries_the_sprint_speed():
    from test_world_and_physics import platform_level
    world = World(platform_level(), 256)
    player = physics.Player(3.0, 3.5, 1.0, 0.0, span=0)
    speed_leaving = None
    for _ in range(240):
        was_grounded = player.on_ground
        physics.step(world, player, 1, 0, 0.0, False, DT, True)
        if was_grounded and not player.on_ground:
            speed_leaving = player.vx
            break
    assert speed_leaving == pytest.approx(MOVE_SPEED * SPRINT_MULTIPLIER)
    for _ in range(60):
        physics.step(world, player, 0, 0, 0.0, False, DT, False)             # let go of everything
        if player.on_ground:
            break
        assert player.vx == pytest.approx(speed_leaving)
