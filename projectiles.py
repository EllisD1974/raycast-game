"""Bullets in flight. No pygame: main.py draws them as sprites that face the player.

A projectile flies in a straight line, in small steps so it cannot skip through a thin wall, until
it runs out of range or is no longer in open space (inside a wall, a floor, a ceiling or glass).
Nothing in the game takes damage yet, so a hit only removes the bullet and is reported (position and
the damage it carries) for whatever wants to use it later.
"""
import math
import random
from dataclasses import dataclass

MAX_STEP = 0.1                  # cells a bullet moves between collision checks
MUZZLE = 0.25                   # how far in front of the eye a bullet starts


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


@dataclass
class Hit:
    x: float
    y: float
    z: float
    damage: float


class Projectiles:
    def __init__(self, rng=None):
        self.bullets = []
        self.rng = rng or random.Random()

    def fire(self, player, gun):
        """Shoot `gun` from the player's eye, along where they are looking (a little off if it has spread)."""
        yaw, pitch = player.angle, player.pitch
        if gun.spread > 0.0:
            spread = math.radians(gun.spread)
            yaw += self.rng.uniform(-spread, spread)
            pitch += self.rng.uniform(-spread, spread)
        cp = math.cos(pitch)
        dx, dy, dz = math.cos(yaw) * cp, math.sin(yaw) * cp, math.sin(pitch)
        self.bullets.append(Projectile(
            player.x + dx * MUZZLE, player.y + dy * MUZZLE, player.eye_z - 0.03 + dz * MUZZLE,
            dx * gun.proj_speed, dy * gun.proj_speed, dz * gun.proj_speed,
            gun.proj_tile, gun.proj_size, gun.damage, gun.proj_range))

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
        """(x, y, z, size, tile) of every bullet for the renderer (z is the bottom of the sprite)."""
        return [(b.x, b.y, b.z - b.size / 2, b.size, b.tile) for b in self.bullets]
