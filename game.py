"""The running game without a window: the world, the players in it and one step of time.

No pygame. Each player is described to tick() by an Inputs (what their keys and mouse asked for this
step), so the same code runs a local game, a host working out everyone's moves, and tests. main.py
only reads the keyboard into an Inputs and draws what the Game holds.
"""
import math
import random
from dataclasses import dataclass, field

from character import SHIRTS
from constants import PLAYER_HEIGHT
from entities import Entities, PlayerStats
from inventory import Inventory
from physics import look, spawn, step
from projectiles import MUZZLE, Projectiles


MAX_STEP_DT = 0.05              # longest time one player's step may cover (main.py caps frames at this too)


@dataclass
class Inputs:
    """What one player asked for during one step."""
    forward: int = 0                # -1, 0 or 1
    strafe: int = 0
    turn: float = 0.0               # radians to turn this step (keys and mouse, already scaled)
    tilt: float = 0.0               # radians to tilt the view this step
    jump: bool = False
    sprint: bool = False
    fire: bool = False              # the trigger is held
    reload: bool = False
    equip: tuple = ()               # gun slots (0 based) to take out, in order
    cycle: int = 0                  # steps through the guns, as with the mouse wheel

    def to_dict(self):
        return {"forward": self.forward, "strafe": self.strafe, "turn": self.turn, "tilt": self.tilt,
                "jump": self.jump, "sprint": self.sprint, "fire": self.fire, "reload": self.reload,
                "equip": list(self.equip), "cycle": self.cycle}

    @classmethod
    def from_dict(cls, data):
        """Inputs from a message, ignoring anything missing or of the wrong kind (it came off the network)."""
        def number(key, kind, low, high):
            value = data.get(key, 0)
            return kind(max(low, min(high, value))) if isinstance(value, (int, float)) else kind(0)
        equip = data.get("equip", ())
        return cls(number("forward", int, -1, 1), number("strafe", int, -1, 1),
                   number("turn", float, -3.2, 3.2), number("tilt", float, -3.2, 3.2),
                   bool(data.get("jump")), bool(data.get("sprint")), bool(data.get("fire")),
                   bool(data.get("reload")),
                   tuple(i for i in equip if isinstance(i, int) and 0 <= i < 9)[:9]
                   if isinstance(equip, (list, tuple)) else (),
                   number("cycle", int, -9, 9))


def move_body(world, body, wish, dt):
    """Move and turn a player's body by what `wish` asked for over dt seconds. A joiner runs this too,
    ahead of the host, to predict where its own moves will put it."""
    step(world, body, wish.forward, wish.strafe, wish.turn, wish.jump, dt, wish.sprint)
    look(body, wish.tilt)


def muzzle_event(effect, body, offset=None):
    """(effect, x, y, z, dx, dy, dz[, ox, oy, oz]): `effect` played at the muzzle of a gun fired by `body`, along
    its aim, starting at `offset` from the muzzle if the gun overrides the effect's own."""
    cp = math.cos(body.pitch)
    dx, dy, dz = math.cos(body.angle) * cp, math.sin(body.angle) * cp, math.sin(body.pitch)
    event = (effect, body.x + dx * MUZZLE, body.y + dy * MUZZLE, body.eye_z - 0.03 + dz * MUZZLE, dx, dy, dz)
    return event + tuple(offset) if offset is not None else event


def character_tile_for(first_tile, player_id):
    """The picture of a player seen by someone else: the shirt colour follows their id."""
    return first_tile + player_id % len(SHIRTS)


def character_sprite(body, first_tile, player_id):
    """(x, y, z, size, tile) of a player seen by someone else."""
    return (body.x, body.y, body.z, PLAYER_HEIGHT, character_tile_for(first_tile, player_id))


@dataclass
class PlayerState:
    """One player: where they are (body), what pickups changed (stats) and what they carry."""
    body: object
    stats: PlayerStats = field(default_factory=PlayerStats)
    inventory: Inventory = field(default_factory=Inventory)


@dataclass
class Events:
    """What happened to one player during a step, for the screen (recoil, pickup text)."""
    fired: int = 0                  # shots fired
    picked: list = field(default_factory=list)      # messages of the pickups made


class Game:
    def __init__(self, level, world, rng=None, character_tile=None):
        """`character_tile` is the first of the character pictures in the renderer's textures (see
        character.py); without it other players are not drawn."""
        self.character_tile = character_tile
        self.level = level
        self.world = world
        self.items = Entities(level, world)
        self.projectiles = Projectiles(rng or random.Random())
        self.players = {}           # player id -> PlayerState
        self.fx = []                # particle effects to play, (name, x, y, z, dx, dy, dz[, ox, oy, oz]), until take_fx()
        self.flashes = []           # lights to flash, (name, x, y, z), until take_flashes()

    def add_player(self, player_id):
        """Put a new player at the level's start."""
        state = PlayerState(spawn(self.level, self.world))
        self.players[player_id] = state
        return state

    def remove_player(self, player_id):
        self.players.pop(player_id, None)

    def move_player(self, player_id, wish, dt):
        """One player's part of dt seconds: switching guns, moving, looking and firing. Returns how many
        shots they fired. A host calls this for each of a joiner's steps, each with that step's own dt."""
        state = self.players[player_id]
        body, inventory = state.body, state.inventory
        for slot in wish.equip:
            inventory.equip(slot)
        if wish.cycle:
            inventory.cycle(wish.cycle)
        move_body(self.world, body, wish, dt)
        fired = inventory.update(dt, wish.fire, wish.reload)
        for gun in fired:
            self.projectiles.fire(body, gun, self.level.ammo_for(gun))
            if gun.muzzle:
                self.fx.append(muzzle_event(gun.muzzle, body, (gun.muzzle_offset_x, gun.muzzle_offset_y, gun.muzzle_offset_z)
                                            if gun.muzzle_override else None))
            if gun.flash:
                self.flashes.append(muzzle_event(gun.flash, body)[:4])
        return len(fired)

    def take_fx(self):
        """The particle effects to play since the last call (a muzzle flash for each shot fired)."""
        out, self.fx = self.fx, []
        return out

    def take_flashes(self):
        """The lights to flash since the last call (a muzzle flash for each shot fired)."""
        out, self.flashes = self.flashes, []
        return out

    def advance_world(self, dt):
        """The shared part of dt seconds: bullets fly, items come back, players pick up what they touch.
        Returns {player id: pickup messages}."""
        self.projectiles.update(self.world, dt)
        self.items.advance(dt)
        return {pid: self.items.touch(state.body, state.stats, state.inventory, who=pid)
                for pid, state in self.players.items()}

    def tick(self, inputs, dt):
        """Advance everything dt seconds. `inputs` maps a player id to their Inputs (a player left out
        just stands still). Returns {player id: Events}."""
        events = {pid: Events(fired=self.move_player(pid, inputs.get(pid) or Inputs(), dt))
                  for pid in self.players}
        for pid, picked in self.advance_world(dt).items():
            events[pid].picked = picked
        return events

    def sprites(self, viewer=None):
        """Items, bullets and the players other than `viewer` as the renderer wants them."""
        return self.items.sprites() + self.projectiles.sprites() + self.player_sprites(viewer)

    def player_sprites(self, viewer=None):
        if self.character_tile is None:
            return []
        return [character_sprite(state.body, self.character_tile, pid)
                for pid, state in self.players.items() if pid != viewer]
