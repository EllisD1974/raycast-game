"""A Level turned into numpy arrays: what the renderer and the physics read."""
import math

import numpy as np

from constants import STEP_HEIGHT
from mapfile import grid_name
from raykernel import plane_z

EPS = 1e-6


class World:
    """Arrays for every floor of a level; the first axis of the per-floor arrays is the floor."""

    def __init__(self, level, tile_count, transparent_tiles=None):
        """`transparent_tiles` is a boolean per atlas tile (see atlas.transparent_tiles): walls
        made from those tiles are see-through panes. None means no tile is transparent."""
        w, h, floors = level.width, level.height, level.floor_count
        self.width, self.height, self.floors = w, h, floors
        self.floor_plane = np.zeros((floors, h, w, 3), np.float32)
        self.ceil_plane = np.zeros((floors, h, w, 3), np.float32)
        self.span_on = np.zeros((floors, h, w), np.uint8)
        self.floor_tex = np.zeros((floors, h, w), np.int32)
        self.ceil_tex = np.zeros((floors, h, w), np.int32)

        def tile_index(grid):           # 1-based map ids -> 0-based atlas indices, clamped
            return np.clip(np.array(grid, np.int64) - 1, 0, tile_count - 1).astype(np.int32)

        for s in range(floors):
            planes, _problems = level.floor_planes(s)
            self.floor_plane[s] = np.array(planes, np.float32).reshape(h, w, 3)
            self.ceil_plane[s, :, :, 0] = np.array(level.grids[grid_name("ceil_h", s)], np.float32)
            self.span_on[s] = [[level.span_present(s, x, y) for x in range(w)] for y in range(h)]
            self.floor_tex[s] = tile_index(level.grids[grid_name("floor_tex", s)])
            self.ceil_tex[s] = tile_index(level.grids[grid_name("ceil_tex", s)])
        self.solid = (np.array(level.grids["walls"]) != 0).astype(np.uint8)   # what the renderer stops at
        self.wall_tex = tile_index(level.grids["walls"])
        self.pane_tex = np.full((h, w), -1, np.int32)           # see-through wall tile per cell, or -1
        self.pane_top = np.full((h, w), 1e9, np.float32)        # how high that pane reaches (a short wall)
        wall_floor = np.array(level.grids["wall_floor"], np.int32)
        self.blocked = (self.solid != 0) & (wall_floor == 0)    # what the player cannot enter on any floor
        transparent = np.zeros(tile_count, bool) if transparent_tiles is None else np.asarray(transparent_tiles, bool)
        self._add_transparent_walls(level, transparent)
        self._add_short_walls(level, transparent)
        self.blocked = self.blocked.astype(np.uint8)
        # Lowest floor each cell is a wall on (`floors` = no wall): a wall that starts on a higher
        # floor leaves the floors below it open. The renderer and span_at read this.
        self.solid_from = np.where(self.solid != 0, wall_floor, floors).astype(np.int32)
        self._hang_upper_walls(level, wall_floor)

    def _hang_upper_walls(self, level, wall_floor):
        """A wall that starts on a higher floor has its base at that floor's floor height. The rooms
        below it stay open but their ceiling stops at that base, so the wall is seen hanging
        from the ceiling instead of vanishing above it.

        The wall's top is the ceiling height stored for it on its own floor (0, or not above the
        base, means full height). A wall shorter than the rooms beside it on that floor becomes a
        raised block there: its floor is the wall's top, so you can see over it and see its top."""
        for y, x in zip(*np.nonzero((self.solid != 0) & (wall_floor > 0))):
            f = int(wall_floor[y, x])
            base = level.grids[grid_name("floor_h", f)][y][x]
            top = level.upper_wall_top(x, y)
            below = [s for s in range(f) if self.span_on[s, y, x]]
            open_to = self.ceil_plane[below[-1], y, x, 0] if below else 0.0    # the room's ceiling, before the wall hangs in it
            for s in range(f):
                if self.span_on[s, y, x]:
                    low = self.floor_plane[s, y, x, 0] + 0.1
                    self.ceil_plane[s, y, x, 0] = min(self.ceil_plane[s, y, x, 0], max(base, low))
            if top is not None:
                self.solid[y, x] = 0
                self.solid_from[y, x] = self.floors
                self.span_on[f, y, x] = 1
                self.floor_plane[f, y, x] = (top, 0.0, 0.0)
                above = level.upper_wall_ceiling(x, y)
                self.ceil_plane[f, y, x] = (max(open_to if above is None else above, top + 0.1), 0.0, 0.0)
                self.floor_tex[f, y, x] = self.wall_tex[y, x]

    def _add_transparent_walls(self, level, transparent):
        """A wall made from a tile with transparent pixels is a see-through pane: the renderer
        looks straight through the cell (it has the floor and ceiling of an open cell, with the
        wall drawn across its face and blended using the texture's alpha), while the player is
        still blocked, as by a fence or a window. It is as tall as the wall's height says (a short
        glass wall can be seen over) but always blocks the player completely: you can neither
        walk through nor hop over a pane."""
        for y in range(level.height):
            for x in range(level.width):
                if not level.walls[y][x] or level.wall_floor(x, y) or not transparent[self.wall_tex[y, x]]:
                    continue
                floor = level.wall_base(x, y)               # the pane stands on the floor beside it
                ceiling = max(level.wall_ceiling(x, y), floor + 0.1)
                top = level.short_wall_top(x, y)       # (a transparent wall is never an upper-floor one)
                self.solid[y, x] = 0
                self.span_on[0, y, x] = 1
                self.floor_plane[0, y, x] = (floor, 0.0, 0.0)
                self.ceil_plane[0, y, x] = (ceiling, 0.0, 0.0)
                self.pane_tex[y, x] = self.wall_tex[y, x]
                if top is not None:
                    self.pane_top[y, x] = top

    def _add_short_walls(self, level, transparent):
        """A wall shorter than its room is not solid: it becomes a raised block on the ground
        floor, with the wall's own texture on its sides and top. Nothing else needs to know about
        short walls: you can see over one and see its top, you cannot walk through it (it is taller
        than a step), you can climb or hop onto a low one, and it has no room above it.
        (See-through walls are handled by _add_transparent_walls, not here.)"""
        for y in range(level.height):
            for x in range(level.width):
                top = level.short_wall_top(x, y)
                if top is None or level.wall_floor(x, y) or transparent[self.wall_tex[y, x]]:
                    continue
                self.solid[y, x] = 0
                self.blocked[y, x] = 0
                self.span_on[0, y, x] = 1
                self.floor_plane[0, y, x] = (top, 0.0, 0.0)
                self.ceil_plane[0, y, x] = (level.wall_ceiling(x, y), 0.0, 0.0)
                self.floor_tex[0, y, x] = self.wall_tex[y, x]       # the top and the sides look like the wall

    def is_blocked(self, cx, cy):
        return not (0 <= cx < self.width and 0 <= cy < self.height) or bool(self.blocked[cy, cx])

    def floor_of(self, s, x, y):
        cx, cy = math.floor(x), math.floor(y)
        return float(plane_z(self.floor_plane, s, cx, cy, x - cx, y - cy))

    def ceil_of(self, s, x, y):
        cx, cy = math.floor(x), math.floor(y)
        return float(plane_z(self.ceil_plane, s, cx, cy, x - cx, y - cy))

    def span_at(self, x, y, z, current=None, grounded=True):
        """The floor (span index) a player with feet at height z stands on at (x, y), or -1 if
        the cell is blocked or every floor there is too high to step onto.

        A floor is reachable if it is no more than a step above z. Among the reachable floors
        the player keeps `current` (the floor they were on) as long as it is still there and
        does not fall away by more than a step; otherwise they take the highest floor that
        continues at about their height, and only if there is none do they drop to the highest
        reachable floor below. Staying on your own floor is what lets you walk down a ramp
        that has another floor's room overhead, and step off a ledge onto the floor below.
        While airborne (grounded False) a point belongs to the floor whose room contains the
        player's feet, preferring `current` if it does. Sticking to the floor under the player's
        centre would be wrong over a hole in one floor: the far side of the hole would then be
        judged against the floor below, whose ceiling there is inside the slab the player is
        jumping onto, and the jump would be stopped dead."""
        cx, cy = math.floor(x), math.floor(y)
        if self.is_blocked(cx, cy):
            return -1
        if current is not None and current >= self.solid_from[cy, cx]:
            return -1                   # a wall that starts on this floor (or one below) fills the cell
        reach = [s for s in range(self.span_on.shape[0] - 1, -1, -1)
                 if self.span_on[s, cy, cx] and self.floor_of(s, x, y) <= z + STEP_HEIGHT + EPS]
        if not reach:
            return -1
        if not grounded:
            inside = [s for s in reach
                      if self.floor_of(s, x, y) - EPS <= z < self.ceil_of(s, x, y)]
            if current in inside:
                return current
            if inside:
                return inside[0]
            return current if current in reach else reach[0]
        if current in reach and self.floor_of(current, x, y) >= z - STEP_HEIGHT - EPS:
            return current
        continuing = [s for s in reach if self.floor_of(s, x, y) >= z - STEP_HEIGHT - EPS]
        return continuing[0] if continuing else reach[0]

    def floor_z(self, x, y, z=0.0, current=None, grounded=True):
        """Floor height under a player at height z; +inf where there is nowhere to stand."""
        s = self.span_at(x, y, z, current, grounded)
        return math.inf if s < 0 else self.floor_of(s, x, y)

    def ceil_z(self, x, y, z=0.0, current=None, grounded=True):
        """Ceiling height above a player at height z; -inf where blocked."""
        s = self.span_at(x, y, z, current, grounded)
        return -math.inf if s < 0 else self.ceil_of(s, x, y)
