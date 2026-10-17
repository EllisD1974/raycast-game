"""Player movement: walls, stairs, ramps, floors above floors, gravity and jumping. No pygame."""
import math
from dataclasses import dataclass

from constants import (EYE_HEIGHT, GRAVITY, JUMP_SPEED, MAX_PITCH_DEG, MOVE_SPEED, PLAYER_HEIGHT,
                       PLAYER_RADIUS, SPRINT_MULTIPLIER, STEP_HEIGHT)

EPS = 1e-6
# The player's box is a hair smaller than PLAYER_RADIUS, so a box that merely touches an edge
# (floating point makes "exactly on the boundary" ambiguous) counts as being on one side of it.
# Every check uses the same corners, so they always agree about which cells the box is in.
SKIN = 1e-3
CORNERS = tuple((ox, oy) for ox in (-(PLAYER_RADIUS - SKIN), PLAYER_RADIUS - SKIN)
                for oy in (-(PLAYER_RADIUS - SKIN), PLAYER_RADIUS - SKIN))

MAX_PITCH = math.radians(MAX_PITCH_DEG)
AIR_ACCEL = 6.0             # cells/s^2 the player can steer toward the keys in the air
PUSH_SPEED = MOVE_SPEED     # cells/s the player is slid sideways out of a ceiling edge
PUSH_STEPS = tuple(round(0.01 * i, 2) for i in range(1, int(PLAYER_RADIUS * 100) + 6))


@dataclass
class Player:
    x: float
    y: float
    z: float                    # height of the feet
    angle: float = 0.0          # radians; 0 faces +x, increasing turns right
    vz: float = 0.0
    on_ground: bool = True
    span: int = 0               # index of the floor under the player's centre; kept while moving
    vx: float = 0.0             # horizontal velocity, cells per second. On the ground it simply
    vy: float = 0.0             # follows the keys; in the air it is momentum (see step)
    pitch: float = 0.0          # radians; positive looks up. Only affects the view

    @property
    def eye_z(self):
        return self.z + EYE_HEIGHT


def look(p, pitch_delta):
    """Tilt the view up (positive) or down by pitch_delta radians, never past MAX_PITCH."""
    p.pitch = max(-MAX_PITCH, min(MAX_PITCH, p.pitch + pitch_delta))


def spawn(level, world):
    """A player standing at the level's start, on the floor (span) the level says."""
    x, y = level.start_x, level.start_y
    span = level.start_span if world.span_on[level.start_span, int(y), int(x)] else 0
    return Player(x, y, world.floor_of(span, x, y), angle=level.start_angle, span=span)


def can_stand(world, x, y, z, span=None, grounded=True):
    """True if the player's box fits at (x, y) with feet at height z: every corner must have
    a floor no higher than a step above the feet, and room for the player's height. Which
    floor a corner stands on depends on z and the floor the player is on (see World.span_at),
    so the player walks under an upper floor at z = 0 and on top of it at its own height."""
    for ox, oy in CORNERS:
        s = world.span_at(x + ox, y + oy, z, span, grounded)
        if s < 0:
            return False
        floor = world.floor_of(s, x + ox, y + oy)
        ceiling = world.ceil_of(s, x + ox, y + oy)
        if floor - z > STEP_HEIGHT + EPS:
            return False
        if ceiling - max(z, floor) < PLAYER_HEIGHT:
            return False
    return True


def ledge_floor(world, x, y, z, span, grounded):
    """Height of the highest floor under any corner of the player's box that still holds the
    player up (no more than a step below their feet), or None if no corner does."""
    best = None
    for ox, oy in CORNERS:
        s = world.span_at(x + ox, y + oy, z, span, grounded)
        if s < 0:
            continue
        floor = world.floor_of(s, x + ox, y + oy)
        if floor >= z - STEP_HEIGHT - EPS and (best is None or floor > best):
            best = floor
    return best


def push_out(world, p, dt):
    """Slide a player whose box no longer fits sideways to the nearest place where it does.

    This happens when a ramp rises under a player who is hugging its edge: the body overlaps
    the next cell, whose ceiling (for example the underside of a floor slab) comes down to meet
    the head. Nothing is wrong with walking on, only with where the player is standing, so
    they are nudged toward the middle instead of being left wedged between ramp and ceiling.
    Any sideways direction is allowed, even against the way the player is pressing (into the
    wall that wedges them), but never one that lowers them: backing down the ramp would only
    let them walk up into the same spot again. The push is limited in speed."""
    best = None
    for ux, uy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        for m in PUSH_STEPS:
            nx, ny = p.x + ux * m, p.y + uy * m
            span = world.span_at(nx, ny, p.z, p.span, True)
            if span < 0:
                continue
            z = world.floor_of(span, nx, ny)        # they would be standing on the floor there
            if z < p.z - 0.005:
                continue                            # that is a way back down, not a way out
            if z - p.z <= STEP_HEIGHT and can_stand(world, nx, ny, z, p.span, True):
                if best is None or m < best[0]:
                    best = (m, ux, uy)
                break
    if best is not None:
        m, ux, uy = best
        m = min(m, PUSH_SPEED * dt)
        p.x += ux * m
        p.y += uy * m


def step(world, p, forward, strafe, turn, jump, dt, sprint=False):
    """Advance the player by dt seconds. forward/strafe/turn are in -1..1.

    On the ground the horizontal velocity follows the keys at once, SPRINT_MULTIPLIER times
    faster while `sprint` is held together with a movement key. In the air it is momentum:
    leaving a ledge or jumping keeps the speed you had (sprint speed included), you can steer
    toward the keys at AIR_ACCEL, and letting go of the keys does not stop you. You cannot
    start sprinting in the air. Hitting a wall stops that component of the velocity."""
    p.angle += turn
    wish_x = math.cos(p.angle) * forward - math.sin(p.angle) * strafe
    wish_y = math.sin(p.angle) * forward + math.cos(p.angle) * strafe
    if p.on_ground:
        speed = MOVE_SPEED * (SPRINT_MULTIPLIER if sprint and (forward or strafe) else 1.0)
        p.vx, p.vy = wish_x * speed, wish_y * speed
    elif wish_x or wish_y:
        # Steer toward the keys. Walking speed is the target, but a player already moving
        # faster (a sprinting jump) keeps that speed instead of being slowed by the keys.
        top = max(MOVE_SPEED, math.hypot(p.vx, p.vy))
        ax, ay = wish_x * top - p.vx, wish_y * top - p.vy
        gap = math.hypot(ax, ay)
        if gap > 0:
            scale = min(1.0, AIR_ACCEL * dt / gap)
            p.vx, p.vy = p.vx + ax * scale, p.vy + ay * scale

    dx, dy = p.vx * dt, p.vy * dt
    if can_stand(world, p.x + dx, p.y, p.z, p.span, p.on_ground):   # axes separately: slide along walls
        p.x += dx
    else:
        p.vx = 0.0
    if can_stand(world, p.x, p.y + dy, p.z, p.span, p.on_ground):
        p.y += dy
    else:
        p.vy = 0.0

    span = world.span_at(p.x, p.y, p.z, p.span, p.on_ground)       # the floor under the centre
    if span < 0:                                    # nowhere to stand (should not happen)
        return
    p.span = span
    ground = world.floor_of(span, p.x, p.y)
    ceiling = world.ceil_of(span, p.x, p.y)
    if p.on_ground and p.z - ground > STEP_HEIGHT + EPS:
        # The centre is past an edge. Only fall once the whole box is off it: while any corner
        # is still on the ledge the player stays up. Otherwise they would drop into the gap with
        # part of their body still inside the floor slab they walked off.
        held = ledge_floor(world, p.x, p.y, p.z, p.span, True)
        if held is not None and can_stand(world, p.x, p.y, held, p.span, True):
            ground = held       # (only if that is a place the box fits: else falling clears the ceiling)
    if p.on_ground and jump:
        p.vz, p.on_ground = JUMP_SPEED, False
    if p.on_ground:
        if p.z - ground <= STEP_HEIGHT + EPS:       # follow ramps and stairs, up or down
            p.z, p.vz = ground, 0.0
        else:                                       # walked off a ledge
            p.on_ground = False
    if not p.on_ground:
        p.vz -= GRAVITY * dt
        p.z += p.vz * dt
        if p.z <= ground:
            p.z, p.vz, p.on_ground = ground, 0.0, True
        elif p.z + PLAYER_HEIGHT > ceiling:         # bumped the head
            p.z = ceiling - PLAYER_HEIGHT
            p.vz = min(p.vz, 0.0)

    if p.on_ground and not can_stand(world, p.x, p.y, p.z, p.span, True):
        push_out(world, p, dt)                      # wedged between a rising ramp and a ceiling edge
