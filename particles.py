"""Particles: the little sprites of smoke, sparks and flashes that an Effect (mapfile.py) sends out.

No pygame, and nothing here changes the game: every player works the particles out on their own
machine, and only the picture depends on them. A ParticleSystem is fed three kinds of emitter:

    play(name, x, y, z, direction)    once: a burst, or a stream for its duration (a muzzle flash)
    attach(key, name, x, y, z, ...)   every frame while the thing is there: a stream leaves a trail along
                                      the path the point took, a burst repeats at the effect's interval
    Both take an optional `offset` (x, y, z) that replaces the effect's own start offset: whatever uses an effect
    (a gun, an ammo type, an item) can say where it starts. It is along the heading of the direction the effect is
    played in (x ahead, y to the right), or the map's axes where there is none (an item).
    keep(keys)                        after a frame's attach calls: forget attached emitters not in `keys`

then update(dt) moves everything on and sprites() gives what the renderer draws, as
(x, y, z, size, tile, spin, alpha, glow[, color]) with z the bottom of the sprite (glow is 1 for particles that
carry a light: they are drawn at full brightness). `color` is only there for an effect with a hue or tint: the 9
numbers of a 3 x 3 matrix (rows of red, green, blue) its picture's colors are put through.
"""
import math
import random
from dataclasses import dataclass

MAX_PARTICLES = 600             # the most alive at once; new ones are dropped beyond it
ONE_SHOT_STREAM = 0.15          # seconds a stream played once runs when its effect gives no duration
EMIT_RANGE = 24.0               # emitters further than this from the viewer are not worked out
UP = (0.0, 0.0, 1.0)
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def effect_color(effect):
    """The color matrix an effect's particles are drawn through (IDENTITY for the original colors)."""
    if effect.color == "hue":
        return color_matrix(effect.hue)
    if effect.color == "rgb":
        return color_matrix(0.0, effect.tint_r, effect.tint_g, effect.tint_b)
    return IDENTITY


def color_matrix(hue, r=255, g=255, b=255):
    """The 3 x 3 matrix (9 numbers, row by row) that turns a color's hue by `hue` degrees (keeping how bright it
    looks) and then multiplies it by the tint (r, g, b out of 255)."""
    c, s = math.cos(math.radians(hue)), math.sin(math.radians(hue))
    turn = ((0.213 + c * 0.787 - s * 0.213, 0.715 - c * 0.715 - s * 0.715, 0.072 - c * 0.072 + s * 0.928),
            (0.213 - c * 0.213 + s * 0.143, 0.715 + c * 0.285 + s * 0.140, 0.072 - c * 0.072 - s * 0.283),
            (0.213 - c * 0.213 - s * 0.787, 0.715 - c * 0.715 + s * 0.715, 0.072 + c * 0.928 + s * 0.072))
    matrix = tuple(value * tint / 255.0 for row, tint in zip(turn, (r, g, b)) for value in row)
    return IDENTITY if all(abs(a - b) < 1e-9 for a, b in zip(matrix, IDENTITY)) else matrix


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

    def play(self, name, x, y, z, direction=UP, offset=None):
        """Play an effect once at a point: a burst now, or a stream for its duration."""
        effect = self.effects.get(name)
        if effect is None:
            return
        if effect.kind == "burst":
            self._emit(effect, effect.count, x, y, z, direction, offset)
        else:
            self.streams.append([effect, x, y, z, direction, effect.duration or ONE_SHOT_STREAM, 0.0, offset])

    def attach(self, key, name, x, y, z, direction=UP, dt=0.0, offset=None):
        """An emitter that follows a point, called every frame while it exists. A stream sends out its rate
        a second along the path the point traveled since the last call; a burst plays when first attached
        and again every `interval` seconds (never again if that is 0)."""
        effect = self.effects.get(name)
        if effect is None:
            self.attached.pop(key, None)
            return
        state = self.attached.get(key)
        if state is None or state["name"] != name:
            state = self.attached[key] = {"name": name, "last": (x, y, z), "owed": 0.0, "wait": 0.0}
            if effect.kind == "burst":
                self._emit(effect, effect.count, x, y, z, direction, offset)
            state["wait"] = effect.interval
            return
        if effect.kind == "stream":
            state["owed"] += effect.rate * dt
            n = int(state["owed"])
            state["owed"] -= n
            lx, ly, lz = state["last"]
            for i in range(n):                              # spread along the path, so a fast mover leaves no gaps
                f = (i + 1) / n
                self._emit(effect, 1, lx + (x - lx) * f, ly + (y - ly) * f, lz + (z - lz) * f, direction, offset)
        elif effect.interval > 0:
            state["wait"] -= dt
            if state["wait"] <= 0:
                state["wait"] += effect.interval
                self._emit(effect, effect.count, x, y, z, direction, offset)
        state["last"] = (x, y, z)

    def keep(self, keys):
        """Forget the attached emitters whose key is not in `keys` (their thing is gone), and get ready for
        the next frame's attach calls."""
        keys = set(keys)
        for key in [k for k in self.attached if k not in keys]:
            del self.attached[key]

    def _emit(self, effect, n, x, y, z, direction, offset=None):
        (ox, oy, oz), direction = placement(effect, direction, offset)
        x, y, z = x + ox, y + oy, z + oz
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
            effect, x, y, z, direction, left, owed, offset = stream
            step = min(dt, left)
            owed += effect.rate * step
            n = int(owed)
            stream[5], stream[6] = left - step, owed - n
            self._emit(effect, n, x, y, z, direction, offset)
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
        """(x, y, z, size, tile, spin, alpha, glow[, color]) of every particle, for the renderer."""
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
            sprite = (p.x, p.y, p.z - size / 2, size, e.tile, 0.0, alpha, 1.0 if e.light else 0.0)
            color = effect_color(e)
            out.append(sprite + (color,) if color != IDENTITY else sprite)
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


def placement(effect, direction, offset=None):
    """((x, y, z) offset to start the particles at, direction to send them in) for an effect played in the
    automatic `direction`. The effect's offset and, if it has chosen one, its own direction are along the map's
    axes, or along the automatic direction's heading when `relative` is set (x forward, y to its right).
    An `offset` from whatever uses the effect replaces the effect's own offset, and is always along the heading
    (the map's axes where there is no heading, as for an item)."""
    hx, hy = direction[0], direction[1]
    length = math.hypot(hx, hy)
    if effect.relative and length > 1e-6:
        fx, fy = hx / length, hy / length               # forward on the map; the right of that is (-fy, fx)

        def turned(vx, vy, vz):
            return (fx * vx - fy * vy, fy * vx + fx * vy, vz)
    else:
        def turned(vx, vy, vz):
            return (vx, vy, vz)
    if offset is not None:
        if length > 1e-6:
            fx, fy = hx / length, hy / length
            offset = (fx * offset[0] - fy * offset[1], fy * offset[0] + fx * offset[1], offset[2])
        else:
            offset = tuple(offset)
    elif effect.offset_x or effect.offset_y or effect.offset_z:
        offset = turned(effect.offset_x, effect.offset_y, effect.offset_z)
    else:
        offset = (0.0, 0.0, 0.0)
    if effect.aim == "custom" and (effect.dir_x or effect.dir_y or effect.dir_z):
        direction = turned(effect.dir_x, effect.dir_y, effect.dir_z)
    return offset, direction


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
    vz[, offset]); the trail sprays back along where the bullet came from, and an offset (or None) replaces the
    effect's own start offset."""
    keys = []
    for ident, trail, x, y, z, vx, vy, vz, *offset in bullets:
        if not trail:
            continue
        key = ("bullet", ident)
        keys.append(key)
        system.attach(key, trail, x, y, z, (-vx, -vy, -vz), dt, offset[0] if offset else None)
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
        offset = (e.emits_offset_x, e.emits_offset_y, e.emits_offset_z) if e.emits_override else None
        system.attach(key, e.emits, e.x, e.y, item.z + e.size / 2, UP, dt, offset)
    return keys
