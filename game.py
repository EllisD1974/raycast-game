"""The running game without a window: the world, the players in it and one step of time.

No pygame. Each player is described to tick() by an Inputs (what their keys and mouse asked for this
step), so the same code runs a local game, a host working out everyone's moves, and tests. main.py
only reads the keyboard into an Inputs and draws what the Game holds.
"""
import math
import random
from dataclasses import dataclass, field

from character import SHIRTS, VIEWS, character_view
from constants import PLAYER_HEIGHT
from entities import Entities, PlayerStats
from explosions import blast_results
from inventory import Inventory
from physics import look, spawn, spawn_at, step
from projectiles import MUZZLE, Projectiles, muzzle_shift


MAX_STEP_DT = 0.05              # longest time one player's step may cover (main.py caps frames at this too)
HIT_FLASH = 0.25                # seconds a player who was hurt shows red to the others
HIT_TINT = (1.0, 0.45, 0.45, 0.0, 0.35, 0.0, 0.0, 0.0, 0.35)   # the color matrix of a player just hurt (red)
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


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


def muzzle_event(effect, body, offset=None, shift=(0.0, 0.0, 0.0)):
    """(effect, x, y, z, dx, dy, dz[, ox, oy, oz]): `effect` played at the muzzle of a gun fired by `body`, along
    its aim, starting at `offset` from the muzzle if the gun overrides the effect's own. `shift` moves the muzzle
    itself (where the gun's bullets come from: see projectiles.muzzle_shift)."""
    cp = math.cos(body.pitch)
    dx, dy, dz = math.cos(body.angle) * cp, math.sin(body.angle) * cp, math.sin(body.pitch)
    event = (effect, body.x + dx * MUZZLE + shift[0], body.y + dy * MUZZLE + shift[1],
             body.eye_z - 0.03 + dz * MUZZLE + shift[2], dx, dy, dz)
    return event + tuple(offset) if offset is not None else event


def character_tile_for(first_tile, player_id, viewer_angle=None, angle=None):
    """The picture of a player seen by someone else: the shirt color follows their id, the side shown
    which way they face (`angle`) as seen looking along `viewer_angle` (the front if either is unknown)."""
    view = 0 if viewer_angle is None or angle is None else character_view(viewer_angle, angle)
    return first_tile + (player_id % len(SHIRTS)) * VIEWS + view


def hit_tint(hit):
    """The color matrix of a player hurt `hit` seconds of HIT_FLASH ago from the end: red, fading back to their own
    colors as hit runs out (None when it has)."""
    if hit <= 0.0:
        return None
    k = min(1.0, hit / HIT_FLASH)
    return tuple(i + (t - i) * k for i, t in zip(IDENTITY, HIT_TINT))


def character_sprite(body, first_tile, player_id, viewer_angle=None, hit=0.0):
    """(x, y, z, size, tile) of a player seen by someone else, tinted red while `hit` (see hit_tint) lasts."""
    sprite = (body.x, body.y, body.z, PLAYER_HEIGHT, character_tile_for(first_tile, player_id, viewer_angle, body.angle))
    tint = hit_tint(hit)
    return sprite if tint is None else sprite + (0.0, 1.0, 0.0, tint)


class SpawnOrder:
    """Where each player comes into the game, from the map's spawners (mapfile.Spawner).

    A round goes through the spawners from the lowest order up: each player comes in at a spawner of the
    lowest order that still has one not used in this round, picked at random among those. When every spawner
    has been used, a new round starts at the lowest order again. So two order-0 spawners take the first two
    players in a random order, an order-1 spawner the third, and the fourth starts the round over. Joining,
    coming back after being knocked out and a map reload all take the next place. A map without spawners
    puts everyone at its start."""

    def __init__(self, level, rng):
        self.level, self.rng = level, rng
        self.used = set()                   # indices of the spawners used in this round

    def next_index(self):
        """The index of the spawner the next player comes in at (None: the map has none)."""
        spawners = self.level.spawners
        if not spawners:
            return None
        if len(self.used) >= len(spawners):
            self.used.clear()               # every one has been used: a new round
        free = [i for i in range(len(spawners)) if i not in self.used]
        lowest = min(spawners[i].order for i in free)
        pick = self.rng.choice([i for i in free if spawners[i].order == lowest])
        self.used.add(pick)
        return pick

    def body(self, world):
        """A player's body at the next place to come in at."""
        index = self.next_index()
        if index is None:
            return spawn(self.level, world)
        s = self.level.spawners[index]
        return spawn_at(world, s.x, s.y, s.span, s.angle)


@dataclass
class PlayerState:
    """One player: where they are (body), what pickups changed (stats) and what they carry, and how much longer
    they show red to the others after being hurt (hit, seconds)."""
    body: object
    stats: PlayerStats = field(default_factory=PlayerStats)
    inventory: Inventory = field(default_factory=Inventory)
    hit: float = 0.0


@dataclass
class Events:
    """What happened to one player during a step, for the screen (recoil, pickup text)."""
    fired: int = 0                  # shots fired
    picked: list = field(default_factory=list)      # messages of the pickups made
    hurt: float = 0.0               # damage taken (the screen flashes red)


class Game:
    def __init__(self, level, world, rng=None, character_tile=None):
        """`character_tile` is the first of the character pictures in the renderer's textures (see
        character.py); without it other players are not drawn."""
        self.character_tile = character_tile
        self.level = level
        self.world = world
        self.items = Entities(level, world)
        self.rng = rng or random.Random()
        self.projectiles = Projectiles(self.rng)
        self.spawns = SpawnOrder(level, self.rng)       # where players come in
        self.players = {}           # player id -> PlayerState
        self.fx = []                # particle effects to play, (name, x, y, z, dx, dy, dz[, ox, oy, oz]), until take_fx()
        self.hurts = {}             # player id -> damage taken, until take_hurts()
        self.flashes = []           # lights to flash, (name, x, y, z), until take_flashes()

    def load_level(self, level, world, character_tile=None):
        """Swap in a new map while the game runs. Everything in flight is dropped and every player is back at
        the new start with full health and only what a new player carries (their score stays): the old
        inventories name guns and ammo the new map may no longer have."""
        self.level, self.world = level, world
        if character_tile is not None:
            self.character_tile = character_tile
        self.items = Entities(level, world)
        self.projectiles.bullets = []
        self.fx, self.flashes = [], []
        self.spawns = SpawnOrder(level, self.rng)       # a new round of the new map's spawners
        for state in self.players.values():             # in place: sessions hold on to these PlayerStates
            state.body = self.spawns.body(world)
            state.stats = PlayerStats(score=state.stats.score)
            state.inventory = Inventory()

    def add_player(self, player_id):
        """Put a new player in the game, at the next spawner (or the level's start)."""
        state = PlayerState(self.spawns.body(self.world))
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
            self.projectiles.fire(body, gun, self.level.ammo_for(gun), player_id)
            shift = muzzle_shift(gun, body.angle)
            if gun.muzzle:
                self.fx.append(muzzle_event(gun.muzzle, body, (gun.muzzle_offset_x, gun.muzzle_offset_y, gun.muzzle_offset_z)
                                            if gun.muzzle_override else None, shift))
            if gun.flash:
                self.flashes.append(muzzle_event(gun.flash, body, None, shift)[:4])
        return len(fired)

    def hurt(self, player_id, damage):
        """Take `damage` off a player's health. At zero they are out: back in at the next spawner (or the level's
        start), with full health and only what a new player carries (their score stays)."""
        state = self.players[player_id]
        if damage > 0:
            self.hurts[player_id] = self.hurts.get(player_id, 0.0) + damage
            state.hit = HIT_FLASH
        state.stats.health = max(0.0, state.stats.health - damage)
        if state.stats.health <= 0.0:
            state.body = self.spawns.body(self.world)               # in place: sessions hold on to this PlayerState
            state.stats = PlayerStats(score=state.stats.score)
            state.inventory = Inventory()

    def explode(self, hit):
        """A bullet that explodes struck at `hit`: play its explosion, then hurt and throw every player it reaches.
        A player thrown into the air loses the ground under them, so their own momentum takes over."""
        for effect in hit.blast.explosion_effects:
            self.fx.append((effect, hit.x, hit.y, hit.z, -hit.dx, -hit.dy, -hit.dz))
        for light in hit.blast.explosion_lights:
            self.flashes.append((light, hit.x, hit.y, hit.z))
        bodies = [(pid, state.body) for pid, state in self.players.items()]
        for pid, damage, (vx, vy, vz) in blast_results(self.world, hit.blast, hit.x, hit.y, hit.z, hit.owner, bodies):
            state = self.players[pid]
            body = state.body
            self.hurt(pid, damage)
            if state.body is body:                      # (not sent back to the start by it)
                body.vx += vx
                body.vy += vy
                body.vz += vz
                body.on_ground = False

    def take_fx(self):
        """The particle effects to play since the last call (a muzzle flash for each shot fired)."""
        out, self.fx = self.fx, []
        return out

    def take_hurts(self):
        """{player id: damage taken} since the last call (a hit that knocked them out counts too)."""
        out, self.hurts = self.hurts, {}
        return out

    def take_flashes(self):
        """The lights to flash since the last call (a muzzle flash for each shot fired)."""
        out, self.flashes = self.flashes, []
        return out

    def advance_world(self, dt):
        """The shared part of dt seconds: bullets fly (and hurt the players they strike), items come back,
        players pick up what they touch. Returns {player id: pickup messages}."""
        for state in self.players.values():
            state.hit = max(0.0, state.hit - dt)
        targets = [(pid, state.body.x, state.body.y, state.body.z) for pid, state in self.players.items()]
        for hit in self.projectiles.update(self.world, dt, targets):
            for effect in hit.effects:                  # sprays back the way the bullet came
                self.fx.append((effect, hit.x, hit.y, hit.z, -hit.dx, -hit.dy, -hit.dz))
            for light in hit.lights:
                self.flashes.append((light, hit.x, hit.y, hit.z))
            if hit.target in self.players:
                self.hurt(hit.target, hit.damage)
            if hit.blast is not None:
                self.explode(hit)
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
        for pid, damage in self.take_hurts().items():
            if pid in events:
                events[pid].hurt = damage
        return events

    def sprites(self, viewer=None):
        """Items, bullets and the players other than `viewer` as the renderer wants them."""
        return self.items.sprites() + self.projectiles.sprites() + self.player_sprites(viewer)

    def player_sprites(self, viewer=None):
        if self.character_tile is None:
            return []
        looking = self.players[viewer].body.angle if viewer in self.players else None
        return [character_sprite(state.body, self.character_tile, pid, looking, state.hit)
                for pid, state in self.players.items() if pid != viewer]
