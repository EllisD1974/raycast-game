"""A live 3D view of the level being edited, drawn by the game's own renderer.

A Preview owns a camera and a compiled copy of the level. The camera is a physics.Player, so in the
preview you walk exactly as in the game: stairs, ramps and ledges, walls and glass that block you,
jumping and falling. The editor calls sync() with its level and revision number; when the level has
changed the world is rebuilt (at most every REBUILD_INTERVAL seconds while edits keep arriving) and
the camera is kept somewhere it can stand, because an edit can raise a floor into it, lower a ceiling
onto it, or put a wall where it was.
"""
import math
import time

import physics
from atlas import ensure_rgba, transparent_tiles
from entities import Entities
from renderer import Renderer
from world import World

REBUILD_INTERVAL = 0.05        # seconds between rebuilds while edits are still coming in
SEARCH_RADIUS = 8              # cells searched for a place to stand when the camera's spot is lost
WHEEL_TICKS = 12               # physics ticks of walking per notch of the mouse wheel (about half a cell)
FRAME = 1 / 60


class Preview:
    def __init__(self, textures):
        self.textures = ensure_rgba(textures)
        self.transparent = transparent_tiles(self.textures)
        self.renderer = Renderer(self.textures)
        self.world = None
        self.items = None                    # the level's entities, all shown (nothing is picked up here)
        self.player = None
        self.built_revision = None
        self.last_build = -1e9
        self.reset_requested = True          # put the camera at the level's start on the next build
        self.jump_pending = False

    def set_textures(self, textures):
        """Switch to a new texture atlas (after textures.png was edited); the world is rebuilt on
        the next sync because which tiles are see-through may have changed."""
        self.textures = ensure_rgba(textures)
        self.transparent = transparent_tiles(self.textures)
        self.renderer = Renderer(self.textures)
        self.built_revision = None
        self.last_build = -1e9

    @property
    def ready(self):
        return self.world is not None and self.player is not None

    def request_reset(self):
        """Move the camera back to the level's start the next time the world is built."""
        self.reset_requested = True

    # ---------------------------------------------------------------- keeping up with the level

    def sync(self, level, revision, now=None, force=False):
        """Bring the 3D world up to date with the level; True if it was rebuilt.

        While edits keep arriving (the revision changes every frame during a paint stroke) the
        rebuild is throttled to REBUILD_INTERVAL; as soon as they stop, the next call catches up."""
        now = time.perf_counter() if now is None else now
        if self.world is not None and not force:
            if revision == self.built_revision or now - self.last_build < REBUILD_INTERVAL:
                return False
        self.world = World(level, len(self.textures), self.transparent)
        self.items = Entities(level, self.world)
        self.built_revision, self.last_build = revision, now
        if self.player is None or self.reset_requested:
            self.player = physics.spawn(level, self.world)
            self.reset_requested = False
        self._settle()
        return True

    def _settle(self):
        """Make sure the camera is standing somewhere valid in the (new) world."""
        world, p = self.world, self.player
        if p.span >= world.floors:
            p.span = 0
        span = world.span_at(p.x, p.y, p.z, p.span, True)
        if span >= 0 and physics.can_stand(world, p.x, p.y, p.z, span, True):
            p.span = span                    # still fine; if the floor dropped away, gravity will act
            p.z = max(p.z, world.floor_of(span, p.x, p.y))      # a floor raised into the feet lifts them
            return
        spot = self._find_standing(p.x, p.y, p.z)
        if spot is not None:
            p.x, p.y, p.z, p.span = spot
            p.vz, p.on_ground = 0.0, True

    def _find_standing(self, x, y, z):
        """The nearest (x, y, z, span) where the camera fits, searching outward from where it was."""
        world = self.world
        cx0, cy0 = math.floor(x), math.floor(y)
        best = None
        for radius in range(SEARCH_RADIUS + 1):
            ring = [(cx, cy) for cy in range(cy0 - radius, cy0 + radius + 1)
                    for cx in range(cx0 - radius, cx0 + radius + 1)
                    if max(abs(cx - cx0), abs(cy - cy0)) == radius
                    and 0 <= cx < world.width and 0 <= cy < world.height and not world.is_blocked(cx, cy)]
            for cx, cy in sorted(ring, key=lambda c: (c[0] + .5 - x) ** 2 + (c[1] + .5 - y) ** 2):
                for span in sorted(range(world.floors), key=lambda s: abs(world.floor_of(s, cx + .5, cy + .5) - z)):
                    if not world.span_on[span, cy, cx]:
                        continue
                    floor = world.floor_of(span, cx + .5, cy + .5)
                    if physics.can_stand(world, cx + .5, cy + .5, floor, span, True):
                        best = (cx + .5, cy + .5, floor, span)
                        break
                if best:
                    return best
        return None

    # ---------------------------------------------------------------- the camera

    def place(self, x, y, span=0, aim_at=None):
        """Stand the camera at (x, y) on the given floor (or the nearest floor that exists there).
        Returns False, leaving the camera where it was, if that spot cannot be stood on."""
        world = self.world
        if world is None or self.player is None:
            return False
        cx, cy = math.floor(x), math.floor(y)
        if not (0 <= cx < world.width and 0 <= cy < world.height) or world.is_blocked(cx, cy):
            return False
        spans = [s for s in range(world.floors) if world.span_on[s, cy, cx]]
        if not spans:
            return False
        s = span if span in spans else min(spans, key=lambda c: abs(c - span))
        floor = world.floor_of(s, x, y)
        if not physics.can_stand(world, x, y, floor, s, True):
            return False
        p = self.player
        p.x, p.y, p.z, p.span = x, y, floor, s
        p.vx = p.vy = p.vz = 0.0
        p.on_ground = True
        if aim_at is not None:
            self.aim(*aim_at)
        return True

    def aim(self, x, y):
        """Turn the camera to face the point (x, y) in the map, if it is not right on top of it."""
        p = self.player
        if p is not None and math.hypot(x - p.x, y - p.y) > 0.25:
            p.angle = math.atan2(y - p.y, x - p.x)

    def look(self, yaw, pitch):
        """Turn by `yaw` radians (right is positive) and tilt up by `pitch`, within the limits."""
        if self.player is not None:
            self.player.angle += yaw
            physics.look(self.player, pitch)

    def update(self, dt, forward=0, strafe=0, turn=0.0, sprint=False):
        """Walk the camera for dt seconds with the given keys (-1, 0 or 1; turn is in radians).
        Called every frame, even with no keys, so the camera falls and settles like a player."""
        if not self.ready:
            return
        if self.items is not None:
            self.items.clock += dt                      # items animate in the editor's 3D view too
        jump, self.jump_pending = self.jump_pending, False
        physics.step(self.world, self.player, forward, strafe, turn, jump, min(dt, 0.05), sprint)

    def nudge(self, direction, notches=1):
        """Walk forward (+1) or back (-1) about half a cell per notch, as the mouse wheel does."""
        if not self.ready:
            return
        for _ in range(WHEEL_TICKS * max(1, notches)):
            physics.step(self.world, self.player, direction, 0, 0.0, False, FRAME)
        physics.step(self.world, self.player, 0, 0, 0.0, False, FRAME)      # come to rest

    # ---------------------------------------------------------------- drawing

    def render(self):
        """The current view as a WIDTH x HEIGHT surface (the same picture the game would draw)."""
        return self.renderer.draw(self.world, self.player, self.items.sprites() if self.items else ())
