"""Bullets in flight. No pygame: main.py draws them as sprites that face the player.

A projectile flies in a straight line, in small steps so it cannot skip through a thin wall, until
it runs out of range or is no longer in open space (inside a wall, a floor, a ceiling, glass or another
team's barrier).
A bullet also stops in any player it passes through other than the one who fired it (a player is an
upright cylinder PLAYER_RADIUS wide and PLAYER_HEIGHT tall). Either way a hit removes the bullet and is
reported (position, the damage it carries, who fired it and who it struck) for the game to act on.
"""
import math
import random
from dataclasses import dataclass

from constants import CROUCH_SPREAD, PLAYER_HEIGHT, PLAYER_RADIUS
from mapfile import AmmoType

MAX_STEP = 0.1                  # cells a bullet moves between collision checks
MUZZLE = 0.25                   # how far in front of the eye a bullet starts


def muzzle_shift(gun, angle):
    """(dx, dy, dz) in the world that moves a bullet's starting point from the usual muzzle point to where the
    gun says bullets come from: its offset is x ahead along the aim `angle`, y to the right of that, z up."""
    c, s = math.cos(angle), math.sin(angle)
    return (c * gun.bullet_offset_x - s * gun.bullet_offset_y, s * gun.bullet_offset_x + c * gun.bullet_offset_y,
            gun.bullet_offset_z)


@dataclass
class Projectile:
    x: float
    y: float
    z: float                    # height of the center of the bullet
    vx: float
    vy: float
    vz: float
    tile: int
    size: float
    damage: float
    range_left: float           # cells it can still fly
    ident: int = 0              # tells bullets apart (for the trail that follows each)
    trail: str = ""             # name of the particle Effect that follows it
    light: str = ""             # name of the Light it carries
    trail_offset: tuple = None  # where its trail starts if the ammo type overrides the effect's offset, else None
    owner: int = None           # id of the player who fired it (it passes through them), None if nobody
    player_effects: tuple = ()  # names of the Effects played and Lights flashed where it strikes a player ...
    player_lights: tuple = ()
    world_effects: tuple = ()   # ... and where it strikes anything else
    world_lights: tuple = ()
    blast: AmmoType = None      # the ammo type it explodes as when it strikes something, None if it does not
    team: int = None            # the team of the player who fired it: that team's barriers let it through (None: none do)


def struck_player(targets, owner, x, y, z):
    """The id of the target (other than `owner`) whose body contains the point, or None. A target is (id, x, y, z of
    the feet[, height[, radius]]): PLAYER_HEIGHT tall unless it says (a crouching player is shorter, an enemy may be
    any size), PLAYER_RADIUS wide unless it says."""
    for pid, tx, ty, tz, *size in targets:
        height = size[0] if size else PLAYER_HEIGHT
        radius = size[1] if len(size) > 1 else PLAYER_RADIUS
        if pid != owner and tz <= z <= tz + height and (x - tx) ** 2 + (y - ty) ** 2 <= radius * radius:
            return pid
    return None


@dataclass
class Hit:
    x: float
    y: float
    z: float
    damage: float
    owner: int = None           # who fired the bullet
    target: int = None          # the player it struck, None if it hit a wall, floor or ceiling
    effects: tuple = ()         # the names of the Effects and Lights to play at the hit
    lights: tuple = ()
    dx: float = 0.0             # the way the bullet was heading (a unit vector)
    dy: float = 0.0
    dz: float = 0.0
    blast: AmmoType = None      # set when the bullet explodes (see explosions.py)


class Projectiles:
    def __init__(self, rng=None):
        self.bullets = []
        self.next_ident = 1
        self.rng = rng or random.Random()

    def fire(self, player, gun, ammo=None, owner=None, team=None):
        """One pull of the trigger: shoot `gun` from the player's eye, along where they are looking (a
        little off if it has spread). `ammo` is the AmmoType it fires (what the bullet looks like and
        how it flies); None is a plain default bullet. A multi shot sends all its pellets, each aimed on
        its own. `owner` is the id of the player firing, `team` their team (its barriers let the bullets through)."""
        ammo = ammo or AmmoType()
        for _ in range(max(1, gun.pellets) if gun.shot == "multi" else 1):
            self.fire_one(player, gun, ammo, owner, team)

    def fire_one(self, player, gun, ammo, owner=None, team=None):
        yaw, pitch = player.angle, player.pitch
        if gun.spread > 0.0:
            steady = getattr(player, "crouched", False) and getattr(player, "on_ground", False)
            spread = math.radians(gun.spread) * (CROUCH_SPREAD if steady else 1.0)     # (crouched: steadier)
            yaw += self.rng.uniform(-spread, spread)
            pitch += self.rng.uniform(-spread, spread)
        cp = math.cos(pitch)
        dx, dy, dz = math.cos(yaw) * cp, math.sin(yaw) * cp, math.sin(pitch)
        sx, sy, sz = muzzle_shift(gun, player.angle)
        self.bullets.append(Projectile(
            player.x + dx * MUZZLE + sx, player.y + dy * MUZZLE + sy, player.eye_z - 0.03 + dz * MUZZLE + sz,
            dx * ammo.speed, dy * ammo.speed, dz * ammo.speed,
            ammo.tile, ammo.size, gun.damage * ammo.damage_mult, ammo.range, self.next_ident, ammo.trail, ammo.light,
            (ammo.trail_offset_x, ammo.trail_offset_y, ammo.trail_offset_z) if ammo.trail_override else None, owner,
            ammo.player_hit_effects, ammo.player_hit_lights, ammo.world_hit_effects, ammo.world_hit_lights,
            ammo if ammo.explodes else None, team))
        self.next_ident += 1

    def update(self, world, dt, targets=()):
        """Move every bullet dt seconds. Returns the Hit of each bullet that struck something. `targets` are
        what a bullet can strike: (id, x, y, z of the feet[, height[, radius]]), see struck_player."""
        hits, alive = [], []
        for b in self.bullets:
            space = world.for_team(b.team)          # (a barrier lets only its own team's bullets through)
            speed = math.sqrt(b.vx * b.vx + b.vy * b.vy + b.vz * b.vz)
            distance = min(speed * dt, b.range_left)
            steps = max(1, math.ceil(distance / MAX_STEP))
            heading = (b.vx / speed, b.vy / speed, b.vz / speed)
            struck = False
            for _ in range(steps):
                move = distance / steps
                nx, ny, nz = (b.x + b.vx / speed * move, b.y + b.vy / speed * move, b.z + b.vz / speed * move)
                if not space.point_open(nx, ny, nz):
                    hits.append(Hit(b.x, b.y, b.z, b.damage, b.owner, None, b.world_effects, b.world_lights, *heading, b.blast))
                    struck = True
                    break
                target = struck_player(targets, b.owner, nx, ny, nz)
                if target is not None:
                    hits.append(Hit(nx, ny, nz, b.damage, b.owner, target, b.player_effects, b.player_lights, *heading, b.blast))
                    struck = True
                    break
                b.x, b.y, b.z = nx, ny, nz
            b.range_left -= distance
            if not struck and b.range_left > 1e-9:
                alive.append(b)
        self.bullets = alive
        return hits

    def sprites(self):
        """(x, y, z, size, tile, spin, alpha, glow) of every bullet for the renderer (z is the bottom of the sprite)."""
        return [(b.x, b.y, b.z - b.size / 2, b.size, b.tile, 0.0, 1.0, 1.0 if b.light else 0.0) for b in self.bullets]
