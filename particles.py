"""Particles: the little sprites of smoke, sparks and flashes that an Effect (mapfile.py) sends out.

No pygame, and nothing here changes the game: every player works the particles out on their own
machine, and only the picture depends on them. A ParticleSystem is fed three kinds of emitter:

    play(name, x, y, z, direction)    once: a burst, or a stream for its duration (a muzzle flash)
    attach(key, name, x, y, z, ...)   every frame while the thing is there: a stream leaves a trail along
                                      the path the point took, a burst repeats at the effect's interval
    keep(keys)                        after a frame's attach calls: forget attached emitters not in `keys`

then update(dt) moves everything on and sprites() gives what the renderer draws, as
(x, y, z, size, tile, spin, alpha, glow) with z the bottom of the sprite (glow is 1 for particles that
carry a light: they are drawn at full brightness).
"""
import math
import random
from dataclasses import dataclass

MAX_PARTICLES = 600             # the most alive at once; new ones are dropped beyond it
ONE_SHOT_STREAM = 0.15          # seconds a stream played once runs when its effect gives no duration
EMIT_RANGE = 24.0               # emitters further than this from the viewer are not worked out
UP = (0.0, 0.0, 1.0)


@dataclass
class Particle:
    effect: object
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    life: float
    age: float = 0.0


class ParticleSystem:
    def __init__(self, effects=(), world=None, rng=None):
        """`effects` is the level's list of Effect; `world` (optional) lets particles stop at walls."""
        self.effects = {e.name: e for e in effects}
        self.world = world
        self.rng = rng or random.Random()
        self.particles = []
        self.streams = []               # one-shot streams still running: [effect, x, y, z, direction, time left, owed]
        self.attached = {}              # key -> state of an emitter that stays attached

    def count(self):
        return len(self.particles)

    # ------------------------------------------------------------------ emitting

    def play(self, name, x, y, z, direction=UP):
        """Play an effect once at a point: a burst now, or a stream for its duration."""
        effect = self.effects.get(name)
        if effect is None:
            return
        if effect.kind == "burst":
            self._emit(effect, effect.count, x, y, z, direction)
        else:
            self.streams.append([effect, x, y, z, direction, effect.duration or ONE_SHOT_STREAM, 0.0])

    def attach(self, key, name, x, y, z, direction=UP, dt=0.0):
        """An emitter that follows a point, called every frame while it exists. A stream sends out its rate
        a second along the path the point travelled since the last call; a burst plays when first attached
        and again every `interval` seconds (never again if that is 0)."""
        effect = self.effects.get(name)
        if effect is None:
            self.attached.pop(key, None)
            return
        state = self.attached.get(key)
        if state is None or state["name"] != name:
            state = self.attached[key] = {"name": name, "last": (x, y, z), "owed": 0.0, "wait": 0.0}
            if effect.kind == "burst":
                self._emit(effect, effect.count, x, y, z, direction)
            state["wait"] = effect.interval
            return
        if effect.kind == "stream":
            state["owed"] += effect.rate * dt
            n = int(state["owed"])
            state["owed"] -= n
            lx, ly, lz = state["last"]
            for i in range(n):                              # spread along the path, so a fast mover leaves no gaps
                f = (i + 1) / n
                self._emit(effect, 1, lx + (x - lx) * f, ly + (y - ly) * f, lz + (z - lz) * f, direction)
        elif effect.interval > 0:
            state["wait"] -= dt
            if state["wait"] <= 0:
                state["wait"] += effect.interval
                self._emit(effect, effect.count, x, y, z, direction)
        state["last"] = (x, y, z)

    def keep(self, keys):
        """Forget the attached emitters whose key is not in `keys` (their thing is gone), and get ready for
        the next frame's attach calls."""
        keys = set(keys)
        for key in [k for k in self.attached if k not in keys]:
            del self.attached[key]

    def _emit(self, effect, n, x, y, z, direction):
        for _ in range(n):
            if len(self.particles) >= MAX_PARTICLES:
                return
            rng = self.rng
            dx, dy, dz = cone(direction, math.radians(effect.spread), rng)
            speed = effect.speed * (1.0 + effect.speed_var * rng.uniform(-1.0, 1.0))
            life = max(0.02, effect.life * (1.0 + effect.life_var * rng.uniform(-1.0, 1.0)))
            px, py, pz = x, y, z
            if effect.radius > 0:
                ox, oy, oz = cone(UP, math.pi, rng)
                reach = effect.radius * rng.random() ** (1 / 3)
                px, py, pz = x + ox * reach, y + oy * reach, z + oz * reach
            self.particles.append(Particle(effect, px, py, pz, dx * speed, dy * speed, dz * speed, life))

    # ------------------------------------------------------------------ moving

    def update(self, dt):
        """Move every particle on by dt seconds, drop the dead ones and run the one-shot streams."""
        for stream in self.streams:
            effect, x, y, z, direction, left, owed = stream
            step = min(dt, left)
            owed += effect.rate * step
            n = int(owed)
            stream[5], stream[6] = left - step, owed - n
            self._emit(effect, n, x, y, z, direction)
        self.streams = [s for s in self.streams if s[5] > 0]
        alive = []
        world = self.world
        for p in self.particles:
            p.age += dt
            if p.age >= p.life:
                continue
            e = p.effect
            p.vz -= e.gravity * dt
            if e.drag > 0:
                slow = max(0.0, 1.0 - e.drag * dt)
                p.vx, p.vy, p.vz = p.vx * slow, p.vy * slow, p.vz * slow
            nx, ny, nz = p.x + p.vx * dt, p.y + p.vy * dt, p.z + p.vz * dt
            if e.collide and world is not None and not world.point_open(nx, ny, nz):
                continue
            p.x, p.y, p.z = nx, ny, nz
            alive.append(p)
        self.particles = alive

    # ------------------------------------------------------------------ drawing

    def sprites(self):
        """(x, y, z, size, tile, spin, alpha, glow) of every particle, for the renderer."""
        out = []
        for p in self.particles:
            e = p.effect
            t = p.age / p.life
            size = e.size_start + (e.size_end - e.size_start) * t
            if size <= 0.0:
                continue
            alpha = e.alpha_start + (e.alpha_end - e.alpha_start) * t
            if alpha <= 0.0:
                continue
            out.append((p.x, p.y, p.z - size / 2, size, e.tile, 0.0, alpha, 1.0 if e.light else 0.0))
        return out

    def light_sources(self):
        """(x, y, z, light name, strength) of every particle whose effect gives off a light; the light fades
        as the particle does."""
        out = []
        for p in self.particles:
            e = p.effect
            if not e.light:
                continue
            t = p.age / p.life
            strength = e.alpha_start + (e.alpha_end - e.alpha_start) * t
            if strength > 0.0:
                out.append((p.x, p.y, p.z, e.light, strength))
        return out


def cone(direction, half_angle, rng):
    """A random unit vector within `half_angle` radians of `direction`, evenly spread over that cap."""
    dx, dy, dz = direction
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length == 0.0:
        dx, dy, dz, length = 0.0, 0.0, 1.0, 1.0
    dx, dy, dz = dx / length, dy / length, dz / length
    if half_angle <= 0.0:
        return dx, dy, dz
    cos_theta = 1.0 - rng.random() * (1.0 - math.cos(min(half_angle, math.pi)))
    sin_theta = math.sqrt(max(0.0, 1.0 - cos_theta * cos_theta))
    phi = rng.random() * math.tau
    ax, ay, az = (1.0, 0.0, 0.0) if abs(dz) > 0.9 else (0.0, 0.0, 1.0)      # any vector that is not along `direction`
    ux, uy, uz = dy * az - dz * ay, dz * ax - dx * az, dx * ay - dy * ax    # perpendicular to it
    ul = math.sqrt(ux * ux + uy * uy + uz * uz)
    ux, uy, uz = ux / ul, uy / ul, uz / ul
    vx, vy, vz = dy * uz - dz * uy, dz * ux - dx * uz, dx * uy - dy * ux    # perpendicular to both
    cx, cy = sin_theta * math.cos(phi), sin_theta * math.sin(phi)
    return (dx * cos_theta + ux * cx + vx * cy,
            dy * cos_theta + uy * cx + vy * cy,
            dz * cos_theta + uz * cx + vz * cy)


def follow(system, bullets, viewer=None, dt=0.0):
    """Attach each bullet's trail effect to it. `bullets` yields (id, trail effect name, x, y, z, vx, vy,
    vz); the trail sprays back along where the bullet came from."""
    keys = []
    for ident, trail, x, y, z, vx, vy, vz in bullets:
        if not trail:
            continue
        key = ("bullet", ident)
        keys.append(key)
        system.attach(key, trail, x, y, z, (-vx, -vy, -vz), dt)
    return keys


def emitters_in_view(system, items, viewer, dt):
    """Attach the effects of the items that emit, for the items that are there and near enough the viewer
    (x, y) to be seen. Returns their keys."""
    keys = []
    for index, item in enumerate(items.items):
        e = item.entity
        if not e.emits or not item.present:
            continue
        if viewer is not None and math.hypot(e.x - viewer[0], e.y - viewer[1]) > EMIT_RANGE:
            continue
        key = ("item", index)
        keys.append(key)
        system.attach(key, e.emits, e.x, e.y, item.z + e.size / 2, UP, dt)
    return keys
