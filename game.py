"""The running game without a window: the world, the players in it and one step of time.

No pygame. Each player is described to tick() by an Inputs (what their keys and mouse asked for this
step), so the same code runs a local game, a host working out everyone's moves, and tests. main.py
only reads the keyboard into an Inputs and draws what the Game holds.
"""
import math
import random
from dataclasses import dataclass, field

from bomb import Round
from character import SHIRTS, VIEWS, character_view
from constants import PLAYER_HEIGHT
from entities import Entities, PlayerStats
from explosions import blast_results
from inventory import Inventory
from koth import HillRound
from mapfile import MAX_BUY_ITEMS, MAX_MONEY
from physics import look, spawn, spawn_at, step
from projectiles import MUZZLE, Projectiles, muzzle_shift


MAX_STEP_DT = 0.05              # longest time one player's step may cover (main.py caps frames at this too)
HIT_FLASH = 0.25                # seconds a player who was hurt shows red to the others
HIT_TINT = (1.0, 0.45, 0.45, 0.0, 0.35, 0.0, 0.0, 0.0, 0.35)   # the color matrix of a player just hurt (red)
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
MAX_PLAYER_NAME = 16            # characters in a player's name
NO_TEAM = 0                     # a player on no team: everyone else is an opponent


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
    buy: tuple = ()                 # entries of the map's buy menu (0 based) to buy, in order
    use: bool = False               # the use key (E) is held: plants or defuses the bomb
    drop: bool = False              # throw the bomb (G), the way the player looks

    def to_dict(self):
        return {"forward": self.forward, "strafe": self.strafe, "turn": self.turn, "tilt": self.tilt,
                "jump": self.jump, "sprint": self.sprint, "fire": self.fire, "reload": self.reload,
                "equip": list(self.equip), "cycle": self.cycle, "buy": list(self.buy), "use": self.use,
                "drop": self.drop}

    @classmethod
    def from_dict(cls, data):
        """Inputs from a message, ignoring anything missing or of the wrong kind (it came off the network)."""
        def number(key, kind, low, high):
            value = data.get(key, 0)
            return kind(max(low, min(high, value))) if isinstance(value, (int, float)) else kind(0)
        equip, buy = data.get("equip", ()), data.get("buy", ())
        return cls(number("forward", int, -1, 1), number("strafe", int, -1, 1),
                   number("turn", float, -3.2, 3.2), number("tilt", float, -3.2, 3.2),
                   bool(data.get("jump")), bool(data.get("sprint")), bool(data.get("fire")),
                   bool(data.get("reload")),
                   tuple(i for i in equip if isinstance(i, int) and 0 <= i < 9)[:9]
                   if isinstance(equip, (list, tuple)) else (),
                   number("cycle", int, -9, 9),
                   tuple(i for i in buy if isinstance(i, int) and not isinstance(i, bool)
                         and 0 <= i < MAX_BUY_ITEMS)[:8] if isinstance(buy, (list, tuple)) else (),
                   bool(data.get("use")), bool(data.get("drop")))


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


def clean_name(text):
    """A player name as it may be used: printable characters only, trimmed, at most MAX_PLAYER_NAME long ("" for
    anything that is not text)."""
    if not isinstance(text, str):
        return ""
    return "".join(c for c in text if c.isprintable()).strip()[:MAX_PLAYER_NAME]


def shown_name(name, player_id):
    """What a player is called on screen: their name, or "Player N" when they have none."""
    return name or f"Player {player_id + 1}"


def same_team(a, b):
    """True if two players' teams make them teammates (players on no team have none)."""
    return a != NO_TEAM and a == b


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
        self.used = {}                      # team -> indices of the spawners used in this round

    def restart(self):
        """Start a new round of spawners (bomb defusal does at the start of each of its rounds)."""
        self.used = {}

    def choices(self, team):
        """The spawners a player of `team` may come in at: their team's and those for anyone, or all of them when
        there are none of those (and for a player on no team)."""
        spawners = self.level.spawners
        if team:
            mine = [i for i, s in enumerate(spawners) if s.team in (0, team)]
            if mine:
                return mine
        return list(range(len(spawners)))

    def next_index(self, team=0):
        """The index of the spawner the next player (of `team`) comes in at (None: the map has none)."""
        spawners = self.level.spawners
        if not spawners:
            return None
        allowed = self.choices(team)
        used = self.used.setdefault(team, set())
        if all(i in used for i in allowed):
            used.clear()                    # every one has been used: a new round
        free = [i for i in allowed if i not in used]
        lowest = min(spawners[i].order for i in free)
        pick = self.rng.choice([i for i in free if spawners[i].order == lowest])
        used.add(pick)
        return pick

    def body(self, world, team=0):
        """A player's body at the next place to come in at (one of their team's)."""
        index = self.next_index(team)
        if index is None:
            return spawn(self.level, world)
        s = self.level.spawners[index]
        return spawn_at(world, s.x, s.y, s.span, s.angle)


@dataclass
class PlayerState:
    """One player: where they are (body), what pickups changed (stats) and what they carry, how much longer they
    show red to the others after being hurt (hit, seconds), their name and their team (NO_TEAM for none). `alive` is
    False while they are out of a round (bomb defusal) or waiting to respawn (King of the Hill): they are not drawn,
    hit or moved meanwhile."""
    body: object
    stats: PlayerStats = field(default_factory=PlayerStats)
    inventory: Inventory = field(default_factory=Inventory)
    hit: float = 0.0
    name: str = ""
    team: int = NO_TEAM
    alive: bool = True


@dataclass
class Events:
    """What happened to one player during a step, for the screen (recoil, pickup text)."""
    fired: int = 0                  # shots fired
    picked: list = field(default_factory=list)      # messages of the pickups made
    hurt: float = 0.0               # damage taken (the screen flashes red)


def make_round(game):
    """The rounds of the game's map mode: bomb defusal's Round, King of the Hill's HillRound, or None."""
    mode = game.level.settings.mode
    if mode == "bomb":
        return Round(game)
    if mode == "koth":
        return HillRound(game)
    return None


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
        self.notes = {}             # player id -> messages for them (what they bought), until advance_world()
        self.clock = 0.0            # seconds the world has run (the planted bomb blinks by it)
        self.round = make_round(self)       # bomb defusal's or King of the Hill's rounds (None in the other modes)

    def load_level(self, level, world, character_tile=None):
        """Swap in a new map while the game runs. Everything in flight is dropped and every player is back at
        the new start with full health and only what a new player carries (their score and money stay): the old
        inventories name guns and ammo the new map may no longer have. Teams are dealt out again, as the new map
        may be played in another mode."""
        self.level, self.world = level, world
        if character_tile is not None:
            self.character_tile = character_tile
        self.items = Entities(level, world)
        self.projectiles.bullets = []
        self.fx, self.flashes = [], []
        self.spawns = SpawnOrder(level, self.rng)       # a new round of the new map's spawners
        self.notes = {}
        for state in self.players.values():             # in place: sessions hold on to these PlayerStates
            state.team = NO_TEAM
            state.alive = True
        for pid, state in sorted(self.players.items()):
            state.team = self.team_for(pid)
            self.respawn(state)
        self.round = make_round(self)                   # a new match

    def add_player(self, player_id):
        """Put a new player in the game, at the next spawner (or the level's start), on a team if the map's mode
        has them, with the map's starting money and gun."""
        team = self.team_for(player_id)
        state = PlayerState(self.spawns.body(self.world, team))
        state.team = team
        state.stats.money = self.level.settings.start_money
        self.respawn(state, body=state.body)
        self.players[player_id] = state
        if self.round is not None:
            self.round.joined(player_id)
        return state

    def team_for(self, player_id):
        """The team a player joining now goes on: none in free for all, team 1 for everyone in co-op, and in two
        teams the one with fewer players (team 1 when they are even)."""
        mode = self.level.settings.mode
        if mode == "coop":
            return 1
        if not self.level.settings.has_teams():
            return NO_TEAM
        counts = {1: 0, 2: 0}
        for pid, state in self.players.items():
            if pid != player_id and state.team in counts:
                counts[state.team] += 1
        return 1 if counts[1] <= counts[2] else 2

    def respawn(self, state, body=None):
        """Bring a player (back) in, at the next spawner unless `body` is given, with the map's full health and only
        what a new player carries: the map's starting gun, if it has one. Their score and money stay."""
        settings = self.level.settings
        state.body = body or self.spawns.body(self.world, state.team)
        state.stats = PlayerStats(score=state.stats.score, health=settings.max_health, max_health=settings.max_health,
                                  money=state.stats.money)
        state.inventory = Inventory()
        gun = next((g for g in self.level.guns if g.name == settings.start_gun), None) if settings.start_gun else None
        if gun is not None:
            state.inventory.give_gun(gun)

    def can_hurt(self, attacker, target):
        """Whether `attacker`'s bullets and blasts hurt `target`: always themselves and opponents, teammates only
        with the map's friendly fire on."""
        if attacker is None or attacker == target or self.level.settings.friendly_fire:
            return True
        a, b = self.players.get(attacker), self.players.get(target)
        return a is None or b is None or not same_team(a.team, b.team)

    def buy(self, player_id, index):
        """Buy entry `index` of the map's buy menu for a player: they get what it gives if the menu is on and they
        have enough money or score for it (which it then costs them). Returns the message to show them."""
        settings, state = self.level.settings, self.players[player_id]
        if not settings.buy_menu or not 0 <= index < len(settings.buy_items):
            return "Nothing to buy"
        if self.round is not None and not self.round.can_buy():
            return "The buy time is over"
        entry = settings.buy_items[index]
        if not entry.offered_to(state.team, settings.has_teams()):
            return f"{entry.label()} is not for sale to your team"
        price = 0.0 if settings.buy_cost == "free" else entry.price
        have = state.stats.money if settings.buy_cost == "money" else state.stats.score
        if price > 0 and have < price:
            return f"Not enough {settings.buy_cost} for {entry.label()} ({price:g})"
        if entry.kind == "gun":
            gun = next((g for g in self.level.guns if g.name == entry.gun), None)
            if gun is None:
                return f"{entry.label()} is not for sale"
            state.inventory.give_gun(gun)
        elif entry.kind == "item":
            state.inventory.add_item(entry.item, entry.amount)
        elif entry.kind == "health":
            if state.stats.health >= state.stats.max_health:
                return "Health is already full"
            state.stats.health = min(state.stats.max_health, state.stats.health + entry.amount)
        if price > 0 and settings.buy_cost == "money":
            state.stats.money -= price
        elif price > 0:
            state.stats.score -= price
        return f"Bought {entry.label()}" + (f" for {price:g}" if price > 0 else "")

    def remove_player(self, player_id):
        if self.round is not None and player_id in self.players:
            self.round.left(player_id)
        self.players.pop(player_id, None)
        if self.round is not None:
            self.round.after_leaving()

    def move_player(self, player_id, wish, dt):
        """One player's part of dt seconds: switching guns, moving, looking and firing. Returns how many
        shots they fired. A host calls this for each of a joiner's steps, each with that step's own dt."""
        state = self.players[player_id]
        if self.round is not None:
            wish = self.round.act(player_id, wish, dt)     # (no moving while frozen, planting or out of the round)
        for index in wish.buy:
            self.notes.setdefault(player_id, []).append(self.buy(player_id, index))
        body, inventory = state.body, state.inventory
        for slot in wish.equip:
            inventory.equip(slot)
        if wish.cycle:
            inventory.cycle(wish.cycle)
        move_body(self.world.for_team(state.team), body, wish, dt)     # (through their own team's barriers only)
        fired = inventory.update(dt, wish.fire, wish.reload)
        for gun in fired:
            self.projectiles.fire(body, gun, self.level.ammo_for(gun), player_id, state.team)
            shift = muzzle_shift(gun, body.angle)
            if gun.muzzle:
                self.fx.append(muzzle_event(gun.muzzle, body, (gun.muzzle_offset_x, gun.muzzle_offset_y, gun.muzzle_offset_z)
                                            if gun.muzzle_override else None, shift))
            if gun.flash:
                self.flashes.append(muzzle_event(gun.flash, body, None, shift)[:4])
        return len(fired)

    def hurt(self, player_id, damage, attacker=None):
        """Take `damage` off a player's health. At zero they are out: back in at the next spawner (or the level's
        start), with full health and only what a new player carries (their score and money stay), and `attacker`,
        if that was an opponent, earns the map's score and money for knocking someone out."""
        state = self.players[player_id]
        if not state.alive:
            return                                      # (out of the round: nothing reaches them)
        if damage > 0:
            self.hurts[player_id] = self.hurts.get(player_id, 0.0) + damage
            state.hit = HIT_FLASH
        state.stats.health = max(0.0, state.stats.health - damage)
        if state.stats.health <= 0.0:
            settings = self.level.settings
            winner = self.players.get(attacker)
            if winner is not None and attacker != player_id and not same_team(winner.team, state.team):
                winner.stats.score += settings.kill_score
                cap = min(MAX_MONEY, settings.money_cap) if settings.mode == "bomb" else MAX_MONEY
                winner.stats.money = min(cap, winner.stats.money + settings.kill_money)
            if self.round is not None:
                self.round.killed(player_id)            # out until the next round (or the respawn time)
            else:
                self.respawn(state)                     # in place: sessions hold on to this PlayerState

    def explode(self, hit):
        """A bullet that explodes struck at `hit`: play its explosion, then hurt and throw every player it reaches.
        A player thrown into the air loses the ground under them, so their own momentum takes over."""
        for effect in hit.blast.explosion_effects:
            self.fx.append((effect, hit.x, hit.y, hit.z, -hit.dx, -hit.dy, -hit.dz))
        for light in hit.blast.explosion_lights:
            self.flashes.append((light, hit.x, hit.y, hit.z))
        bodies = [(pid, state.body) for pid, state in self.players.items() if state.alive]
        for pid, damage, (vx, vy, vz) in blast_results(self.world, hit.blast, hit.x, hit.y, hit.z, hit.owner, bodies):
            if not self.can_hurt(hit.owner, pid):
                continue                                # a teammate's blast, without friendly fire
            state = self.players[pid]
            body = state.body
            self.hurt(pid, damage, hit.owner)
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
        self.clock += dt
        for state in self.players.values():
            state.hit = max(0.0, state.hit - dt)
        targets = [(pid, state.body.x, state.body.y, state.body.z) for pid, state in self.players.items() if state.alive]
        for hit in self.projectiles.update(self.world, dt, targets):
            for effect in hit.effects:                  # sprays back the way the bullet came
                self.fx.append((effect, hit.x, hit.y, hit.z, -hit.dx, -hit.dy, -hit.dz))
            for light in hit.lights:
                self.flashes.append((light, hit.x, hit.y, hit.z))
            if hit.target in self.players and self.can_hurt(hit.owner, hit.target):
                self.hurt(hit.target, hit.damage, hit.owner)
            if hit.blast is not None:
                self.explode(hit)
        self.items.advance(dt)
        if self.round is not None:
            self.round.update(dt)
        notes, self.notes = self.notes, {}
        return {pid: notes.get(pid, []) + (self.items.touch(state.body, state.stats, state.inventory, who=pid)
                                           if state.alive else [])
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

    def sprites(self, viewer=None, hide=None):
        """Items, bullets, the bomb (or the hill's marker) and the players other than `viewer` (and `hide`: the one
        being watched, whose eyes the picture is seen from) as the renderer wants them."""
        return (self.items.sprites() + self.projectiles.sprites() + self.player_sprites(viewer, hide)
                + (self.round.sprites(self.clock) if self.round is not None else []))

    def labels(self, viewer=None, hide=None):
        """(x, y, z of the top of the head, name, team) of each player other than `viewer`, for their names."""
        return [(s.body.x, s.body.y, s.body.z + PLAYER_HEIGHT, shown_name(s.name, pid), s.team)
                for pid, s in self.players.items() if pid not in (viewer, hide) and s.alive]

    def player_sprites(self, viewer=None, hide=None):
        if self.character_tile is None:
            return []
        looking = self.players[viewer].body.angle if viewer in self.players else None
        return [character_sprite(state.body, self.character_tile, pid, looking, state.hit)
                for pid, state in self.players.items() if pid not in (viewer, hide) and state.alive]
