"""Bullets in flight. No pygame: main.py draws them as sprites that face the player.

A projectile flies in a straight line, in small steps so it cannot skip through a thin wall, until
it runs out of range or is no longer in open space (inside a wall, a floor, a ceiling or glass).
Nothing in the game takes damage yet, so a hit only removes the bullet and is reported (position and
the damage it carries) for whatever wants to use it later.
"""
import math
import random
from dataclasses import dataclass

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
    z: float                    # height of the centre of the bullet
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


@dataclass
class Hit:
    x: float
    y: float
    z: float
    damage: float


class Projectiles:
    def __init__(self, rng=None):
        self.bullets = []
        self.next_ident = 1
        self.rng = rng or random.Random()

    def fire(self, player, gun, ammo=None):
        """One pull of the trigger: shoot `gun` from the player's eye, along where they are looking (a
        little off if it has spread). `ammo` is the AmmoType it fires (what the bullet looks like and
        how it flies); None is a plain default bullet. A multi shot sends all its pellets, each aimed on
        its own."""
        ammo = ammo or AmmoType()
        for _ in range(max(1, gun.pellets) if gun.shot == "multi" else 1):
            self.fire_one(player, gun, ammo)

    def fire_one(self, player, gun, ammo):
        yaw, pitch = player.angle, player.pitch
        if gun.spread > 0.0:
            spread = math.radians(gun.spread)
            yaw += self.rng.uniform(-spread, spread)
            pitch += self.rng.uniform(-spread, spread)
        cp = math.cos(pitch)
        dx, dy, dz = math.cos(yaw) * cp, math.sin(yaw) * cp, math.sin(pitch)
        sx, sy, sz = muzzle_shift(gun, player.angle)
        self.bullets.append(Projectile(
            player.x + dx * MUZZLE + sx, player.y + dy * MUZZLE + sy, player.eye_z - 0.03 + dz * MUZZLE + sz,
            dx * ammo.speed, dy * ammo.speed, dz * ammo.speed,
            ammo.tile, ammo.size, gun.damage * ammo.damage_mult, ammo.range, self.next_ident, ammo.trail, ammo.light,
            (ammo.trail_offset_x, ammo.trail_offset_y, ammo.trail_offset_z) if ammo.trail_override else None))
        self.next_ident += 1

    def update(self, world, dt):
        """Move every bullet dt seconds. Returns the Hit of each bullet that struck something."""
        hits, alive = [], []
        for b in self.bullets:
            speed = math.sqrt(b.vx * b.vx + b.vy * b.vy + b.vz * b.vz)
            distance = min(speed * dt, b.range_left)
            steps = max(1, math.ceil(distance / MAX_STEP))
            struck = False
            for _ in range(steps):
                move = distance / steps
                nx, ny, nz = (b.x + b.vx / speed * move, b.y + b.vy / speed * move, b.z + b.vz / speed * move)
                if not world.point_open(nx, ny, nz):
                    hits.append(Hit(b.x, b.y, b.z, b.damage))
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
