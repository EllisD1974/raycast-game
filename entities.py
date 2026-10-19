"""Items in the world while the game runs: touching them, picking them up, bringing them back.

The map stores Entity records (mapfile.py). Entities turns those into running items for one World:
it knows which are present, when the ones that respawn come back, and applies what a pickup gives
the player (PlayerStats). No pygame: main.py draws the sprites and the HUD.
"""
import math
from dataclasses import dataclass, field

from constants import PLAYER_HEIGHT

TOUCH_RADIUS = 0.45             # how close (in cells, on the map) the player must get to an item
MAX_HEALTH = 100.0


@dataclass
class PlayerStats:
    """What pickups change. (Position and movement live in physics.Player.)"""
    score: float = 0
    health: float = MAX_HEALTH
    max_health: float = MAX_HEALTH


@dataclass
class Item:
    """One running entity: the map record plus whether it is there right now."""
    entity: object
    z: float                    # height of the sprite's bottom
    present: bool = True
    back_at: float = None       # clock time a respawning item comes back
    touching: set = field(default_factory=set)   # who is on it (a persistent item waits for them to step off)


def describe(entity):
    """Short text for the HUD when the item is picked up."""
    amount = f"{entity.amount:g}"
    if entity.effect == "score":
        return f"+{amount} score"
    if entity.effect == "health":
        return f"+{amount} health"
    if entity.effect == "item":
        return f"+{amount} {entity.item or 'Item'}"
    if entity.effect == "gun":
        return f"Picked up {entity.gun or 'a gun'}"
    if entity.effect == "ammo":
        return f"+{amount} {entity.ammo or 'Bullet'} ammo"
    return "Picked up"


class Entities:
    def __init__(self, level, world):
        self.clock = 0.0
        self.items = []
        self.guns = {g.name: g for g in level.guns}          # what a "gun" or "ammo" pickup refers to
        for e in level.entities:
            cx, cy = math.floor(e.x), math.floor(e.y)
            if e.span >= world.floors or not (0 <= cx < world.width and 0 <= cy < world.height):
                continue
            wall_top = level.wall_top_at(cx, cy, e.span)
            if wall_top is not None:                    # standing on top of a wall
                self.items.append(Item(e, wall_top + e.lift))
            elif world.span_on[e.span, cy, cx]:
                self.items.append(Item(e, world.floor_of(e.span, e.x, e.y) + e.lift))

    def sprites(self):
        """(x, y, z, size, tile, spin, alpha, glow) of every item that is there, for the renderer. Animations are
        applied here: a float adds a bob to the height, a rotate sets the spin angle in radians."""
        out = []
        for item in self.items:
            if not item.present or not item.entity.shown:
                continue
            e = item.entity
            z, spin = item.z, 0.0
            # (a phase from the position keeps neighboring items from moving in lockstep)
            phase = (e.x * 7.13 + e.y * 3.71) % 1.0
            for a in e.animations:
                t = (self.clock * a.speed + phase) * math.tau
                if a.kind == "float":
                    z += a.amount * (1.0 + math.sin(t))     # 0 .. 2*amount above its rest height
                elif a.kind == "rotate":
                    spin += t
            out.append((e.x, e.y, z, e.size, e.tile, spin, 1.0, 1.0 if e.light else 0.0))   # (an item with a light glows)
        return out

    @staticmethod
    def _touched(item, player):
        e = item.entity
        if math.hypot(player.x - e.x, player.y - e.y) > TOUCH_RADIUS:
            return False
        return player.z < item.z + e.size and player.z + PLAYER_HEIGHT > item.z      # the heights overlap

    def advance(self, dt):
        """Move the clock on dt seconds and bring back the respawning items whose time is up."""
        self.clock += dt
        for item in self.items:
            if not item.present and item.back_at is not None and self.clock >= item.back_at:
                item.present, item.back_at = True, None

    def touch(self, player, stats, inventory=None, who=None):
        """Pick up what `player` touches. `who` tells players apart (a persistent item counts again for
        each of them separately once they step away and return). Returns the messages of the pickups
        made. Pickups that go in the inventory (an item, a gun, ammo) need `inventory`; without one
        they are still picked up but give nothing."""
        messages = []
        for item in self.items:
            if not item.present or item.entity.mode == "scenery":
                continue
            e = item.entity
            touching = self._touched(item, player)
            if touching and who not in item.touching:
                self._apply(e, stats, inventory, self.guns)
                messages.append(describe(e))
                if e.mode == "once":
                    item.present = False
                elif e.mode == "respawn":
                    item.present, item.back_at = False, self.clock + e.respawn
            if touching:
                item.touching.add(who)
            else:
                item.touching.discard(who)
        return messages

    def update(self, player, stats, dt, inventory=None):
        """Advance dt seconds and pick up what the one player touches: advance() then touch()."""
        self.advance(dt)
        return self.touch(player, stats, inventory)

    @staticmethod
    def _apply(entity, stats, inventory=None, guns=None):
        if entity.effect == "score":
            stats.score += entity.amount
        elif entity.effect == "health":
            stats.health = max(0.0, min(stats.max_health, stats.health + entity.amount))
        elif inventory is None:
            return
        elif entity.effect == "item":
            inventory.add_item(entity.item, entity.amount)
        elif entity.effect == "gun" and guns and entity.gun in guns:
            inventory.give_gun(guns[entity.gun])
        elif entity.effect == "ammo":
            inventory.add_ammo(entity.ammo, entity.amount)
