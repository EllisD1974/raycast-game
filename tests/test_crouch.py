"""Crouching: holding Ctrl makes the player shorter, slower and steadier, and lets them under low ceilings."""
import math
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import physics
from constants import CROUCH_HEIGHT, CROUCH_MULTIPLIER, EYE_HEIGHT, MOVE_SPEED, PLAYER_HEIGHT
from character import PICTURES, VIEWS
from game import Inputs, character_sprite, move_body
from main import read_crouch
from mapfile import AmmoType, Gun, Level
from projectiles import Projectiles, struck_player
from session import BODY_FIELDS, body_fields, body_from, sample_body
from test_sprint import keys
from world import World

DT = 1 / 60
TUNNEL = range(4, 7)            # columns with a ceiling too low to stand under
LEDGE = 10                      # columns from here on are a floor too high to jump onto standing


def crouch_world():
    """A 14 x 5 room 2 high: a low tunnel (ceiling 0.65) across columns 4-6, and a ledge 0.8 high from column 10."""
    level = Level.blank(14, 5)
    for y in range(level.height):
        for x in range(level.width):
            level.set("ceil_h", x, y, 0.65 if x in TUNNEL else 2.0)
            level.set("floor_h", x, y, 0.8 if x >= LEDGE else 0.0)
    return World(level, 16)


def run(world, player, ticks, **wish):
    for _ in range(ticks):
        move_body(world, player, Inputs(**wish), DT)
    return player


def test_ctrl_is_crouch_and_it_goes_to_the_host():
    assert read_crouch(keys(pygame.K_LCTRL)) and read_crouch(keys(pygame.K_RCTRL)) and not read_crouch(keys())
    assert Inputs.from_dict(Inputs(crouch=True).to_dict()).crouch
    assert not Inputs.from_dict({}).crouch


def test_crouching_makes_the_body_shorter_and_lowers_the_view_smoothly():
    world = crouch_world()
    player = physics.Player(2.5, 2.5, 0.0)
    assert player.height == PLAYER_HEIGHT and player.eye_z == pytest.approx(EYE_HEIGHT)
    run(world, player, 1, crouch=True)
    assert player.crouched and player.height == CROUCH_HEIGHT
    low = EYE_HEIGHT - (PLAYER_HEIGHT - CROUCH_HEIGHT)
    assert low < player.eye_z < EYE_HEIGHT                         # on its way down, not there in one jump
    run(world, player, 30, crouch=True)
    assert player.eye_z == pytest.approx(low)
    run(world, player, 1)
    assert not player.crouched and low < player.eye_z < EYE_HEIGHT
    run(world, player, 30)
    assert player.eye_z == pytest.approx(EYE_HEIGHT)


def test_crouching_walks_slower_and_never_sprints():
    world = crouch_world()
    for sprint in (False, True):
        player = run(world, physics.Player(1.5, 2.5, 0.0), 30, forward=1, crouch=True, sprint=sprint)
        assert player.vx == pytest.approx(MOVE_SPEED * CROUCH_MULTIPLIER)


def test_only_a_crouching_player_fits_under_a_low_ceiling_and_stands_up_once_out():
    world = crouch_world()
    standing = run(world, physics.Player(2.5, 2.5, 0.0), 120, forward=1)
    assert standing.x < TUNNEL[0]                                  # stopped at the tunnel's mouth
    player = run(world, physics.Player(2.5, 2.5, 0.0), 90, forward=1, crouch=True)
    assert TUNNEL[0] + 0.3 < player.x < TUNNEL[-1] + 1
    run(world, player, 30)                                         # Ctrl let go under the low ceiling
    assert player.crouched and player.x < TUNNEL[-1] + 1           # no room to stand: still crouched
    run(world, player, 120, forward=1)                             # ... walking on out of the tunnel
    assert player.x > TUNNEL[-1] + 1 and not player.crouched       # stands up as soon as it can


def test_a_crouch_jump_clears_a_ledge_a_standing_jump_does_not():
    world = crouch_world()

    def jump(crouch):
        player = physics.Player(LEDGE - 1.3, 2.5, 0.0)
        move_body(world, player, Inputs(forward=1, jump=True), DT)
        run(world, player, 90, forward=1, crouch=crouch)
        return player

    assert jump(False).x < LEDGE                                   # bounced off the ledge
    player = jump(True)
    assert player.x > LEDGE + 0.5 and player.z == pytest.approx(0.8) and player.on_ground


def test_pulling_the_legs_up_in_the_air_keeps_the_view_still():
    world = crouch_world()
    player = physics.Player(2.5, 2.5, 0.0)
    move_body(world, player, Inputs(jump=True), DT)
    run(world, player, 5)
    eye = player.eye_z
    run(world, player, 1, crouch=True)                             # the legs come up: the eye only follows the jump
    assert player.crouched and abs(player.eye_z - eye) < 0.05


def test_a_crouching_player_is_a_smaller_target_and_drawn_crouching():
    body = physics.Player(3.5, 3.5, 0.0, crouched=True)
    assert struck_player([(1, 3.5, 3.5, 0.0, body.height)], None, 3.5, 3.5, 0.7) is None   # over their head
    assert struck_player([(1, 3.5, 3.5, 0.0, body.height)], None, 3.5, 3.5, 0.4) == 1
    assert struck_player([(1, 3.5, 3.5, 0.0)], None, 3.5, 3.5, 0.7) == 1                  # standing: hit
    standing = character_sprite(physics.Player(3.5, 3.5, 0.0), 40, 1)
    crouching = character_sprite(body, 40, 1)
    assert standing[3] == crouching[3] == PLAYER_HEIGHT            # the same size: the crouching figure is shorter
    assert standing[4] == 40 + PICTURES and crouching[4] == 40 + PICTURES + VIEWS     # shirt 1, the crouching set


def test_a_crouching_player_shoots_steadier():
    gun = Gun(name="Smg", spread=6.0)

    def widest(crouched):
        system = Projectiles(rng=random.Random(4))
        body = physics.Player(3.5, 3.5, 0.0, crouched=crouched)
        for _ in range(300):
            system.fire_one(body, gun, AmmoType())
        return max(abs(math.atan2(b.vy, b.vx)) for b in system.bullets)

    assert widest(True) < widest(False) * 0.7


def test_joiners_see_the_crouch():
    body = physics.Player(1.0, 2.0, 0.0, crouched=True, view_h=CROUCH_HEIGHT)
    back = body_from(body_fields(body))
    assert back.crouched and back.view_h == CROUCH_HEIGHT
    assert sample_body(1.0, 2.0, 0.0, 0.0, 0.8).crouched and not sample_body(1.0, 2.0, 0.0, 0.0, 0.2).crouched
    assert sample_body(1.0, 2.0, 0.0).height == PLAYER_HEIGHT
    assert "crouched" in BODY_FIELDS
