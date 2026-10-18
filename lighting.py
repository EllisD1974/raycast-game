"""Lights in the world: who is carrying one right now, and which of them the picture uses.

No pygame, and nothing here changes the game: like particles, every player works their lights out on their own
machine. A LightSystem is fed the same kinds of source as the particle system:

    flash(name, x, y, z)           once: a light that fades out over its duration (a muzzle flash)
    attach(key, name, x, y, z)     every frame while the thing is there: a light that follows a bullet or sits on
                                   an item; keep(keys) forgets the ones that are gone
    and, found by itself:          the wall tiles that glow (a Light's `wall_tile`) and the particles of any effect
                                   that has a light

update(dt) ages the flashes and runs the flicker clock; prepare(viewer, particles) picks the few strongest lights
near the viewer and returns the Lighting the renderer draws with (None when the map is fully lit and has no lights
to show right now, so such a picture is drawn exactly as before).
"""
import math
from dataclasses import dataclass

import numpy as np

from raylight import build_visibility

MAX_LIGHTS = 12                 # lights used for one picture: the strongest near the viewer
REACH = 24.0                    # lights whose reach is further than this from the viewer are left out
FLASH_DURATION = 0.12
CLUSTER = 0.75                  # particle lights closer than about this (in cells) are merged into one


@dataclass
class Lighting:
    """What the renderer needs to light one picture (see raylight.py for the arrays)."""
    ambient: float
    lights: np.ndarray              # float64 [n, 7]: x, y, z, red, green, blue, radius
    vis: np.ndarray                 # float32 [n, rows, columns]
    occluder: np.ndarray            # uint8 [rows, columns]


class LightSystem:
    def __init__(self, level, world):
        self.defs = {light.name: light for light in level.lights}
        self.ambient = level.ambient
        self.occluder = (world.solid_from == 0).astype(np.uint8)      # walls that fill every floor stop light
        self.static = self._glowing_walls(level, world)
        self.flashes = []               # [light name, x, y, z, age]
        self.attached = {}              # key -> [light name, x, y, z]
        self.time = 0.0

    @property
    def lit(self):
        """True if there is anything to light a picture with: lights exist or the map is dark."""
        return bool(self.defs) or self.ambient < 1.0

    def _glowing_walls(self, level, world):
        """(x, y, z, light name) beside every wall made from a tile a light makes glow: one light on each open
        side of the wall, just off its face."""
        sources = []
        glowing = {light.wall_tile: light.name for light in level.lights if light.wall_tile >= 0}
        if not glowing:
            return sources
        h, w = self.occluder.shape
        for cy in range(h):
            for cx in range(w):
                name = glowing.get(int(world.wall_tex[cy, cx])) if self.occluder[cy, cx] else None
                if name is None:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not self.occluder[ny, nx]:
                        x, y = cx + 0.5 + dx * 0.85, cy + 0.5 + dy * 0.85
                        sources.append((x, y, world.floor_of(0, nx + 0.5, ny + 0.5) + 0.5, name))
        return sources

    # ------------------------------------------------------------------ sources

    def flash(self, name, x, y, z):
        if name in self.defs:
            self.flashes.append([name, x, y, z, 0.0])

    def attach(self, key, name, x, y, z):
        if name in self.defs:
            self.attached[key] = [name, x, y, z]
        else:
            self.attached.pop(key, None)

    def keep(self, keys):
        """Forget the attached lights whose key is not in `keys` (their thing is gone)."""
        keys = set(keys)
        for key in [k for k in self.attached if k not in keys]:
            del self.attached[key]

    def update(self, dt):
        self.time += dt
        for flash in self.flashes:
            flash[4] += dt
        self.flashes = [f for f in self.flashes if f[4] < self.defs[f[0]].duration]

    # ------------------------------------------------------------------ picking the lights for a picture

    def flicker(self, light, x, y):
        """Brightness multiplier between 1 - light.flicker and 1, wobbling at the light's speed. The place gives
        each light its own phase so neighbours do not flicker in step."""
        if light.flicker <= 0.0:
            return 1.0
        phase = (x * 12.9898 + y * 78.233) % math.tau
        t = self.time * light.flicker_speed * math.tau
        wobble = 0.5 + 0.25 * math.sin(t + phase) + 0.25 * math.sin(t * 2.31 + phase * 1.7)
        return 1.0 - light.flicker * (1.0 - wobble)

    def sources(self, particles=None):
        """Every light that is on right now as (x, y, z, Light, strength)."""
        out = []
        for x, y, z, name in self.static:
            light = self.defs[name]
            out.append((x, y, z, light, self.flicker(light, x, y)))
        for name, x, y, z in self.attached.values():
            light = self.defs[name]
            out.append((x, y, z, light, self.flicker(light, x, y)))
        for name, x, y, z, age in self.flashes:
            light = self.defs[name]
            out.append((x, y, z, light, (1.0 - age / light.duration) * self.flicker(light, x, y)))
        if particles is not None:
            out += self.particle_lights(particles)
        return out

    def particle_lights(self, particles):
        """The lights of the particles, with those close together merged into one: a fire of thirty glowing
        embers is one fire-sized light, not thirty stacked on top of each other. A merged light is as strong as
        its brightest particle and gets stronger towards 1 as more join it (the particles' strengths are
        chances of being lit, combined as 1 - (1 - a)(1 - b)...)."""
        clusters = {}
        for x, y, z, name, strength in particles.light_sources():
            if name not in self.defs:
                continue
            key = (name, int(x // CLUSTER), int(y // CLUSTER), int(z // CLUSTER))
            weight = min(1.0, strength)
            c = clusters.setdefault(key, [0.0, 0.0, 0.0, 0.0, 1.0])       # x, y, z (weighted), total weight, 1 - strength
            c[0] += x * weight
            c[1] += y * weight
            c[2] += z * weight
            c[3] += weight
            c[4] *= 1.0 - weight
        return [(c[0] / c[3], c[1] / c[3], c[2] / c[3], self.defs[key[0]], 1.0 - c[4])
                for key, c in clusters.items() if c[3] > 0.0]

    def prepare(self, viewer, particles=None):
        """The Lighting for a picture seen from `viewer` (x, y, z): the strongest lights in reach of it, with what
        each can see of the map. None if there is nothing to light (full ambient and no lights)."""
        if not self.lit:
            return None
        vx, vy, vz = viewer
        scored = []
        for x, y, z, light, strength in self.sources(particles):
            strength *= light.intensity
            if strength <= 0.01:
                continue
            distance = math.sqrt((x - vx) ** 2 + (y - vy) ** 2 + (z - vz) ** 2)
            if distance - light.radius > REACH:
                continue
            scored.append((strength * light.radius / (1.0 + distance), x, y, z, light, strength))
        scored.sort(key=lambda s: -s[0])
        chosen = scored[:MAX_LIGHTS]
        if not chosen and self.ambient >= 1.0:
            return None                     # nothing is on and nothing is dark: the picture is as drawn
        lights = np.zeros((len(chosen), 7), np.float64)
        for i, (_score, x, y, z, light, strength) in enumerate(chosen):
            lights[i] = (x, y, z, light.r / 255 * strength, light.g / 255 * strength, light.b / 255 * strength,
                         light.radius)
        h, w = self.occluder.shape
        vis = np.zeros((len(chosen), h, w), np.float32)
        build_visibility(lights, self.occluder, vis)
        return Lighting(self.ambient, lights, vis, self.occluder)


def follow(system, bullets):
    """Attach each bullet's light to it. `bullets` yields (id, light name, x, y, z). Returns their keys."""
    keys = []
    for ident, light, x, y, z in bullets:
        if light:
            key = ("bullet", ident)
            keys.append(key)
            system.attach(key, light, x, y, z)
    return keys


def item_lights(system, items, viewer):
    """Attach the lights of the items that give one off, for the items that are there and near enough the viewer
    (x, y). Returns their keys."""
    keys = []
    for index, item in enumerate(items.items):
        e = item.entity
        if not e.light or not item.present:
            continue
        if viewer is not None and math.hypot(e.x - viewer[0], e.y - viewer[1]) > REACH:
            continue
        key = ("item", index)
        keys.append(key)
        system.attach(key, e.light, e.x, e.y, item.z + e.size / 2)
    return keys
