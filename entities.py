"""Items in the world while the game runs: touching them, picking them up, bringing them back.

The map stores Entity records (mapfile.py). Entities turns those into running items for one World:
it knows which are present, when the ones that respawn come back, and applies what a pickup gives
the player (PlayerStats). No pygame: main.py draws the sprites and the HUD.
"""
import math
from dataclasses import dataclass

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
    touching: bool = False      # the player is on it (a persistent item waits for them to step off)


def describe(entity):
    """Short text for the HUD when the item is picked up."""
    amount = f"{entity.amount:g}"
    if entity.effect == "score":
        return f"+{amount} score"
    if entity.effect == "health":
        return f"+{amount} health"
    return "Picked up"


class Entities:
    def __init__(self, level, world):
        self.clock = 0.0
        self.items = []
        for e in level.entities:
            cx, cy = math.floor(e.x), math.floor(e.y)
            if e.span < world.floors and 0 <= cx < world.width and 0 <= cy < world.height \
                    and world.span_on[e.span, cy, cx]:
                self.items.append(Item(e, world.floor_of(e.span, e.x, e.y) + e.lift))

    def sprites(self):
        """(x, y, z, size, tile) of every item that is there, for the renderer."""
        return [(i.entity.x, i.entity.y, i.z, i.entity.size, i.entity.tile) for i in self.items if i.present]

    @staticmethod
    def _touched(item, player):
        e = item.entity
        if math.hypot(player.x - e.x, player.y - e.y) > TOUCH_RADIUS:
            return False
        return player.z < item.z + e.size and player.z + PLAYER_HEIGHT > item.z      # the heights overlap

    def update(self, player, stats, dt):
        """Advance dt seconds: bring back respawning items and pick up what the player touches.
        Returns the messages of the pickups made this tick."""
        self.clock += dt
        messages = []
        for item in self.items:
            e = item.entity
            if not item.present:
                if item.back_at is not None and self.clock >= item.back_at:
                    item.present, item.back_at = True, None
                else:
                    continue
            touching = self._touched(item, player)
            if touching and not item.touching:
                self._apply(e, stats)
                messages.append(describe(e))
                if e.mode == "once":
                    item.present = False
                elif e.mode == "respawn":
                    item.present, item.back_at = False, self.clock + e.respawn
            item.touching = touching
        return messages

    @staticmethod
    def _apply(entity, stats):
        if entity.effect == "score":
            stats.score += entity.amount
        elif entity.effect == "health":
            stats.health = max(0.0, min(stats.max_health, stats.health + entity.amount))
