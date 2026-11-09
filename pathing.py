"""Finding the way to a target across the map, for enemies. No pygame.

The map is a graph of places: one per floor of each cell that a body can stand in (the floor's room is there, no wall
or glass fills it, it is tall enough, and nothing set with World.set_blocks stops the body). A body can go from a
place to each of the 8 cells around it when the floor at the edge between them is at most a step up (stairs and ramps)
or any distance down (stepping off a ledge), landing on the floor World.span_at would put it on. A diagonal needs
both cells beside it passable too, so nothing cuts a wall's corner.

A FlowField is the distance from every place to one target, worked out once by searching outwards from the target.
Every enemy chasing that target then only looks at the places around it and heads for the nearest one, so many
enemies cost one search per target, not one each. Pathing keeps the graph and the fields, and works them out again
when the world changes (its revision: a door opening, a window boarded up) or a target moves to another place.
"""
import heapq
import math

import numpy as np

from constants import PLAYER_HEIGHT, STEP_HEIGHT
from raykernel import plane_z

EPS = 1e-6
STRAIGHT, DIAGONAL = 10, 14                     # the cost of a move (a diagonal is about sqrt(2) times as far)
UNREACHABLE = np.iinfo(np.int32).max
DIRECT_RANGE = 3.0                              # cells: closer than this and in sight, head straight for the target
# Moves to the 8 cells around, (dx, dy, cost): the 4 straight ones first, as each diagonal needs the two beside it.
MOVES = ((1, 0, STRAIGHT), (-1, 0, STRAIGHT), (0, 1, STRAIGHT), (0, -1, STRAIGHT),
         (1, 1, DIAGONAL), (-1, 1, DIAGONAL), (1, -1, DIAGONAL), (-1, -1, DIAGONAL))


def edge_point(d):
    """Where a move of d (-1, 0 or 1) along one axis leaves its cell, and where it enters the next one."""
    return (0.5, 0.5) if d == 0 else ((1.0, 0.0) if d > 0 else (0.0, 1.0))


class FlowField:
    """The cost (STRAIGHT per cell, DIAGONAL per diagonal step) of the way from every place to the target place,
    UNREACHABLE where there is none. `cost` is indexed [floor, y, x]."""

    def __init__(self, target, cost):
        self.target = target                    # (floor, x, y)
        self.cost = cost

    def at(self, s, cx, cy):
        return int(self.cost[s, cy, cx])

    def reachable(self, s, cx, cy):
        return bool(self.cost[s, cy, cx] < UNREACHABLE)


class Pathing:
    """The places of `world` (the for_enemies view, for enemies) for bodies `height` tall, and the flow fields to
    targets in it."""

    def __init__(self, world, height=PLAYER_HEIGHT):
        self.world = world
        self.height = height
        self.revision = None
        self.moves = {}                         # (floor, x, y) -> [((floor, x, y), cost)] the moves out of a place
        self.into = {}                          # the same backwards: place -> [(place it can be reached from, cost)]
        self.fields = {}                        # target place -> FlowField

    # ------------------------------------------------------------------ the graph

    def refresh(self):
        """Work the graph out again if the world changed since (and forget the fields made on the old one)."""
        revision = int(self.world.revision[0])
        if revision == self.revision:
            return
        self.revision = revision
        self.fields = {}
        w = self.world
        self.moves, self.into = {}, {}
        for s, cy, cx in zip(*np.nonzero(w.span_on)):
            place = (int(s), int(cx), int(cy))
            if self.open(*place):
                self.moves[place] = []
                self.into.setdefault(place, [])
        for place, out in self.moves.items():
            s, cx, cy = place
            straight = {}
            for dx, dy, cost in MOVES:
                if dx and dy and not (straight.get((dx, 0)) and straight.get((0, dy))):
                    continue                    # (both sides of a diagonal must be passable: no cutting corners)
                to = self.land(s, cx, cy, dx, dy)
                if not dx or not dy:
                    straight[(dx, dy)] = to is not None
                if to is not None:
                    step = cost + w.path_cost(*to)      # (more through something to break)
                    out.append((to, step))
                    self.into[to].append((place, step))

    def open(self, s, cx, cy):
        """True if a body can be on floor s of cell (cx, cy)."""
        w = self.world
        if not (0 <= cx < w.width and 0 <= cy < w.height) or not w.span_on[s, cy, cx]:
            return False
        if w.blocked[cy, cx] or w.solid_from[cy, cx] <= s:
            return False
        if w.mover_blocked(s, cx, cy) and not w.path_cost(s, cx, cy):
            return False                        # (stopped there, and it is nothing they can break)
        if s == 0 and w.has_barriers and w.barred(cx, cy):
            return False
        return plane_z(w.ceil_plane, s, cx, cy, 0.5, 0.5) - plane_z(w.floor_plane, s, cx, cy, 0.5, 0.5) \
            >= self.height - EPS

    def land(self, s, cx, cy, dx, dy):
        """The place a body on floor s of (cx, cy) gets to by moving (dx, dy) one cell, or None if it cannot: the
        floor it keeps or steps up or down onto at the edge between the cells, the way World.span_at picks it."""
        nx, ny = cx + dx, cy + dy
        w = self.world
        if not (0 <= nx < w.width and 0 <= ny < w.height):
            return None
        (fx, tx), (fy, ty) = edge_point(dx), edge_point(dy)
        z = plane_z(w.floor_plane, s, cx, cy, fx, fy)           # the floor's height where the body leaves the cell
        reach = [t for t in range(w.floors - 1, -1, -1)
                 if w.span_on[t, ny, nx] and plane_z(w.floor_plane, t, nx, ny, tx, ty) <= z + STEP_HEIGHT + EPS]
        if not reach:
            return None
        height = {t: plane_z(w.floor_plane, t, nx, ny, tx, ty) for t in reach}
        if s in reach and height[s] >= z - STEP_HEIGHT - EPS:
            to = s
        else:
            continuing = [t for t in reach if height[t] >= z - STEP_HEIGHT - EPS]
            to = continuing[0] if continuing else reach[0]
        place = (to, nx, ny)
        return place if place in self.moves else None

    # ------------------------------------------------------------------ fields

    def place_of(self, body):
        """The place (floor, x, y) a body is in."""
        return (body.span, math.floor(body.x), math.floor(body.y))

    def field(self, target):
        """The FlowField to the place `target` (floor, x, y), worked out the first time it is asked for since the
        world last changed."""
        self.refresh()
        found = self.fields.get(target)
        if found is None:
            found = self.fields[target] = FlowField(target, self.search(target))
        return found

    def search(self, target):
        """The cost from every place to `target`: Dijkstra's search outwards from it along the moves backwards."""
        w = self.world
        cost = np.full((w.floors, w.height, w.width), UNREACHABLE, np.int32)
        if target not in self.moves:
            return cost
        s, cx, cy = target
        cost[s, cy, cx] = 0
        queue = [(0, target)]
        while queue:
            here_cost, (s, cx, cy) = heapq.heappop(queue)
            if here_cost > cost[s, cy, cx]:
                continue
            for (fs, fx, fy), step in self.into[(s, cx, cy)]:
                total = here_cost + step
                if total < cost[fs, fy, fx]:
                    cost[fs, fy, fx] = total
                    heapq.heappush(queue, (total, (fs, fx, fy)))
        return cost

    def next_place(self, field, place):
        """The place to head for from `place` along `field`: the one around it nearest the target, or None if the
        target cannot be reached from there (or `place` is the target)."""
        if place not in self.moves:
            return None
        here = field.cost[place[0], place[2], place[1]]
        best, best_cost = None, here
        for to, _step in self.moves[place]:
            c = field.cost[to[0], to[2], to[1]]
            if c < best_cost:
                best, best_cost = to, c
        return best

    def steer(self, body, goal):
        """The point (x, y) a body should walk toward to reach `goal` (a body too): straight at it when they share a
        place, or it is close by and in sight; else the middle of the next place on the way. None when there is no
        way there."""
        here, there = self.place_of(body), self.place_of(goal)
        if here == there:
            return goal.x, goal.y
        if math.hypot(goal.x - body.x, goal.y - body.y) < DIRECT_RANGE and self.world.line_clear(
                (body.x, body.y, body.z + STEP_HEIGHT + 0.05), (goal.x, goal.y, goal.z + STEP_HEIGHT + 0.05)):
            return goal.x, goal.y
        to = self.next_place(self.field(there), here)
        return None if to is None else (to[1] + 0.5, to[2] + 0.5)
