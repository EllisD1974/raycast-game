"""A Level turned into numpy arrays: what the renderer and the physics read."""
import copy
import math

import numpy as np

from constants import STEP_HEIGHT
from mapfile import BARRIER_SITES, SIDE_LAYERS, SIDES, grid_name, side_band
from raykernel import plane_z

EPS = 1e-6
BARRIER_TILES = {1: 29, 2: 30}      # the see-through pane a barrier of team 1 / 2 is drawn with (atlas tile ids 30, 31)


class World:
    """Arrays for every floor of a level; the first axis of the per-floor arrays is the floor.

    A barrier (the site layer's BARRIER_SITES on the ground floor; spawn protection) lets only one team through: its
    players walk through it and its bullets fly through it, while it stops everyone and everything else like glass.
    for_team(team) is the world as that team's players and bullets meet it; the World itself (team None) is how
    everything else meets it (blasts, the bomb, particles), which no barrier lets through.

    Some cells change during a game (see close_cells, open_cells and set_blocks): a door closes a cell for
    everyone as a wall, and player_block / enemy_block stop only players or only enemies on one floor of a cell
    (a boarded-up window stops enemies until they break it, and never lets players through). for_enemies() is the
    world as enemies meet it. Every view shares the arrays, so a change shows in all of them, and `revision` counts
    the changes (for whatever caches what it worked out from the cells, such as pathing)."""

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
        # What each wall shows on its north, east, south and west side.
        sides = np.array([level.grids[name] for name in SIDE_LAYERS], np.int64).transpose(1, 2, 0)
        # (tile, from, to) per side: the atlas index of the side's own tile (-1: none), and the world heights
        # it covers (all of it unless a band was set). One array, so the renderers take one more argument, not two.
        self.wall_sides = np.empty((h, w, 4, 3), np.float32)
        self.wall_sides[..., 0] = np.where((sides > 0) & (self.solid[:, :, None] != 0), tile_index(sides), -1)
        self.wall_sides[..., 1], self.wall_sides[..., 2] = -1e9, 1e9
        for y, x, i in zip(*np.nonzero(self.wall_sides[..., 0] >= 0)):
            self.wall_sides[y, x, i, 1:] = side_band(level, x, y, SIDES[i])
        self.pane_tex = np.full((h, w), -1, np.int32)           # see-through wall tile per cell, or -1
        self.pane_top = np.full((h, w), 1e9, np.float32)        # how high that pane reaches (a short wall)
        self.pane_open = np.zeros((h, w), np.uint8)             # 1: that pane lets bullets through (set_pane)
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
        self.team = None                                        # the team this world lets through barriers
        self._teams = {None: self}                              # team -> its for_team view (shared by all views)
        self.barrier = np.zeros((h, w), np.int32)               # the team a ground floor barrier lets through, or 0
        self._add_barriers(level, tile_count)
        self.has_barriers = bool(self.barrier.any())
        self.enemies = False                                    # True in the for_enemies view
        self.player_block = np.zeros((floors, h, w), np.uint8)  # floors of cells players cannot enter (set_blocks)
        self.enemy_block = np.zeros((floors, h, w), np.uint8)   # the same for enemies
        self.light_occluder = (self.solid_from == 0).astype(np.uint8)   # walls that fill every floor stop light
        self.enemy_cost = np.zeros((floors, h, w), np.int32)    # extra cost of pathing through (set_cost)
        self.tile_count = tile_count
        self.extras = {}                                        # what a game mode keeps with the world (shared)
        self.revision = np.zeros(1, np.int64)                   # (an array so every view shares it)
        self._opened = {}                                       # (x, y) -> what close_cells covered up there

    def _add_barriers(self, level, tile_count):
        """Barriers on the ground floor: open cells that only their team gets through, drawn as a see-through pane
        of the team's color (when the atlas has that tile)."""
        for y, row in enumerate(level.grids.get(grid_name("site", 0), [])):
            for x, value in enumerate(row):
                team = BARRIER_SITES.get(value)
                if not team or not self.span_on[0, y, x] or self.solid_from[y, x] == 0:
                    continue
                self.barrier[y, x] = team
                if self.pane_tex[y, x] < 0 and BARRIER_TILES[team] < tile_count:
                    self.pane_tex[y, x] = BARRIER_TILES[team]

    def for_team(self, team):
        """This world as the players and bullets of `team` meet it: its barriers let them through, the others' stop
        them. It shares every array with this one (nothing is copied but the team)."""
        view = self._teams.get(team)
        if view is None:
            view = copy.copy(self)
            view.team = team
            self._teams[team] = view
        return view

    def for_enemies(self):
        """This world as enemies meet it: enemy_block stops them instead of player_block. Barriers stop them as they
        stop everything that is not of the barrier's team."""
        view = self._teams.get("enemies")
        if view is None:
            view = copy.copy(self)
            view.team, view.enemies = None, True
            self._teams["enemies"] = view
        return view

    def close_cells(self, cells, tile):
        """Close each (x, y) of `cells` with a wall of atlas tile `tile` filling every floor, as a door: nothing
        walks, shoots or sees through it until open_cells opens it again."""
        for x, y in cells:
            if (x, y) in self._opened or not (0 <= x < self.width and 0 <= y < self.height):
                continue
            self._opened[(x, y)] = (self.solid[y, x], self.wall_tex[y, x], self.blocked[y, x], self.solid_from[y, x],
                                    self.wall_sides[y, x].copy(), self.pane_tex[y, x], self.light_occluder[y, x])
            self.solid[y, x], self.wall_tex[y, x], self.blocked[y, x], self.solid_from[y, x] = 1, tile, 1, 0
            self.wall_sides[y, x, :, 0] = -1
            self.pane_tex[y, x] = -1
            self.light_occluder[y, x] = 1
        self.revision[0] += 1

    def open_cells(self, cells):
        """Open cells closed by close_cells: each is again what the level made it."""
        for x, y in cells:
            saved = self._opened.pop((x, y), None)
            if saved is None:
                continue
            (self.solid[y, x], self.wall_tex[y, x], self.blocked[y, x], self.solid_from[y, x], self.wall_sides[y, x],
             self.pane_tex[y, x], self.light_occluder[y, x]) = saved
        self.revision[0] += 1

    def is_closed(self, x, y):
        """True if close_cells closed cell (x, y)."""
        return (x, y) in self._opened

    def set_blocks(self, cells, players=None, enemies=None, floor=0):
        """Stop (True) or let through (False) players and/or enemies on `floor` of each (x, y) of `cells`; None
        leaves that one as it is. Bullets, blasts and sight are not stopped."""
        for x, y in cells:
            if players is not None:
                self.player_block[floor, y, x] = players
            if enemies is not None:
                self.enemy_block[floor, y, x] = enemies
        self.revision[0] += 1

    def set_cost(self, cells, cost, floor=0):
        """Make finding the way for enemies through each (x, y) of `cells` on `floor` cost `cost` more (in
        pathing.STRAIGHT steps), and let it through even while enemy_block stops them there: something they can
        break (a boarded-up window), worth the detour only when the way round is longer."""
        for x, y in cells:
            self.enemy_cost[floor, y, x] = cost
        self.revision[0] += 1

    def path_cost(self, s, cx, cy):
        """The extra cost of pathing through floor s of (cx, cy) for this world's movers (only enemies have any)."""
        return int(self.enemy_cost[s, cy, cx]) if self.enemies else 0

    def set_pane(self, x, y, tile, top, shoot_through=False):
        """Show a see-through pane of atlas tile `tile` in open cell (x, y) of the ground floor up to height `top`,
        or none (tile -1). It stops bullets (and sight, and blasts) below its top, like glass, unless shoot_through;
        walking is up to set_blocks."""
        self.pane_tex[y, x] = tile if 0 <= tile < self.tile_count else -1
        self.pane_top[y, x] = top
        self.pane_open[y, x] = shoot_through

    def mover_blocked(self, s, cx, cy):
        """True if set_blocks stops this world's movers (players, or enemies in the for_enemies view) on floor `s`
        of cell (cx, cy)."""
        return bool((self.enemy_block if self.enemies else self.player_block)[s, cy, cx])

    def barred(self, cx, cy):
        """True if a barrier in cell (cx, cy) stops this world's team."""
        team = self.barrier[cy, cx]
        return bool(team) and team != self.team

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

    def point_open(self, x, y, z):
        """True if the point is in open space: inside the height range of some floor's room at that spot,
        and not inside see-through glass (which stops bullets as it stops the player)."""
        cx, cy = math.floor(x), math.floor(y)
        if not (0 <= cx < self.width and 0 <= cy < self.height):
            return False
        if self.barrier[cy, cx]:
            if self.barred(cx, cy) and z < plane_z(self.ceil_plane, 0, cx, cy, x - cx, y - cy):
                return False                    # (a barrier fills the ground floor's room, not the floors above)
        elif self.pane_tex[cy, cx] >= 0 and z < self.pane_top[cy, cx] and not self.pane_open[cy, cx]:
            return False
        fx, fy = x - cx, y - cy
        for s in range(min(self.floors, int(self.solid_from[cy, cx]))):     # (none in a wall, or a closed door)
            if self.span_on[s, cy, cx] and plane_z(self.floor_plane, s, cx, cy, fx, fy) <= z \
                    < plane_z(self.ceil_plane, s, cx, cy, fx, fy):
                return True
        return False

    def line_clear(self, a, b, step=0.1):
        """True if nothing solid is between points a and b (x, y, z): every sample along the line, `step`
        apart, is open space. Walls, glass, floors and ceilings all block it, as they block bullets."""
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        steps = max(1, math.ceil(math.sqrt(dx * dx + dy * dy + dz * dz) / step))
        return all(self.point_open(a[0] + dx * i / steps, a[1] + dy * i / steps, a[2] + dz * i / steps)
                   for i in range(1, steps))

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
        center would be wrong over a hole in one floor: the far side of the hole would then be
        judged against the floor below, whose ceiling there is inside the slab the player is
        jumping onto, and the jump would be stopped dead.

        A barrier that does not let this world's team through blocks the ground floor of its cell (only)."""
        s = self._span_at(x, y, z, current, grounded)
        if s == 0 and self.has_barriers and self.barred(math.floor(x), math.floor(y)):
            return -1
        if s >= 0 and self.mover_blocked(s, math.floor(x), math.floor(y)):
            return -1
        return s

    def _span_at(self, x, y, z, current=None, grounded=True):
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
