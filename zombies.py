"""Zombies: everyone on one team against rounds of enemies that come for them. No pygame.

The map defines kinds of enemy (mapfile.Enemy: health, speed, size, attacks, who they chase) and where they come in
(Spawners of team ENEMY_SPAWN). Each round sends a number of them (MapSettings.zombie_count, a curve over the rounds),
tougher as the rounds go on (zombie_health), no more than max_alive at once, one every spawn_interval seconds. They
find their way to the players (pathing.py) and attack whoever they reach. Players earn money for every hit and kill.
When all of a round's enemies are dead the next round starts after the intermission, and the players who were knocked
out come back. When every player is out, the game is over: after a moment a new game starts at round 1.

A round goes: "intermission" (counting down to the next round) -> "live" (enemies come in and attack) -> the
intermission again; "over" when every player is out.

ZombieRound stands in for Game.round (like bomb.Round). Enemies are targets the game's bullets and blasts strike
(targets, hurt_target). What a player is shown, the enemies included, is a ZombieView: the host makes one with
ZombieRound.view() and sends it to joiners as a dict.
"""
import math
from dataclasses import dataclass, field

from constants import PLAYER_HEIGHT, PLAYER_RADIUS
from mapfile import ENEMY_SPAWN, MAX_MONEY, Enemy, curve_at
from pathing import Pathing, STRAIGHT
from physics import Player, can_stand, spawn_at, step

RETHINK = 0.25                  # seconds between an enemy looking again at who to chase
SHIRT = 2                       # the character pictures' shirt color enemies are drawn in (green)
HIT_FLASH = 0.25                # seconds an enemy shows red after being hurt
CROWD = 0.9                     # how hard enemies closer than their two radii push apart (share of the overlap a step)
NOTE_TIME = 3.0                 # seconds a message stays on screen
NO_WAY = 1e9                    # the cost of chasing a player there is no way to


@dataclass
class EnemyBody(Player):
    """An enemy's body: a player's, of its own height and radius."""
    tall: float = PLAYER_HEIGHT
    radius: float = PLAYER_RADIUS

    @property
    def height(self):
        return self.tall


@dataclass
class EnemyState:
    """One enemy in the map."""
    ident: int
    kind: int                   # index into enemy_kinds(level)
    body: EnemyBody
    health: float
    target: int = None          # the player id it chases
    rival: int = None           # sticky pathing: a nearer player it may switch to ...
    rival_for: float = 0.0      # ... who has been nearer for this long
    rethink: float = 0.0        # seconds until it looks again at who to chase
    attack: int = None          # the attack it is winding up (an index into its kind's attacks), or None
    attack_left: float = 0.0    # seconds until that attack lands
    cooldown: float = 0.0       # seconds until it can start another attack
    hit: float = 0.0            # seconds left of showing red


@dataclass
class ZombieView:
    """What the players are shown of the zombies game: the round, the enemies and who is out. Made by the host
    (ZombieRound.view) and sent to joiners."""
    mode = "zombies"
    alive: set = field(default_factory=set)         # ids of the players not out
    teams: dict = field(default_factory=dict)       # player id -> team
    number: int = 0                                 # the round (0 before the first)
    phase: str = "intermission"
    clock: float = 0.0                              # seconds left of the intermission, or of the game over message
    left: int = 0                                   # enemies of this round still to kill (in the map or to come)
    message: str = ""
    message_left: float = 0.0
    enemies: list = field(default_factory=list)     # [kind, x, y, z, angle, red] each
    can_buy: bool = True

    def may_move(self, pid, body, use, level):
        """Whether a player may move this step: anyone not out."""
        return pid in self.alive

    def to_dict(self):
        return {"mode": self.mode, "alive": sorted(self.alive), "number": self.number, "phase": self.phase,
                "clock": round(self.clock, 2), "left": self.left, "msg": self.message,
                "msg_left": round(self.message_left, 2),
                "enemies": [[kind, round(x, 3), round(y, 3), round(z, 3), round(angle, 2), round(red, 2)]
                            for kind, x, y, z, angle, red in self.enemies]}

    @classmethod
    def from_dict(cls, data, teams=None):
        """The view in a snapshot; None if it is not one (it came off the network)."""
        try:
            enemies = []
            for kind, x, y, z, angle, red in data["enemies"]:
                enemies.append((int(kind), float(x), float(y), float(z), float(angle), float(red)))
            phase = data["phase"] if data["phase"] in ("intermission", "live", "over") else "intermission"
            return cls({int(p) for p in data["alive"]}, dict(teams or {}), int(data["number"]), phase,
                       float(data["clock"]), int(data["left"]), str(data["msg"])[:80], float(data["msg_left"]),
                       enemies)
        except (KeyError, IndexError, TypeError, ValueError):
            return None


DEFAULT_KINDS = [Enemy()]


def enemy_kinds(level):
    """The kinds of enemy that come in on `level`: its own, or a plain Zombie when it defines none."""
    return level.enemies or DEFAULT_KINDS


def enemy_tint(color, red):
    """The color matrix of an enemy drawn in `color` ([r, g, b] 0-255), turning red while `red` (0 to 1) lasts."""
    from game import HIT_TINT, IDENTITY             # (game imports this module)
    r, g, b = (c / 255 for c in color)
    own = (r, 0.0, 0.0, 0.0, g, 0.0, 0.0, 0.0, b)
    if red <= 0.0:
        return None if own == IDENTITY else own
    return tuple(o + (t - o) * red for o, t in zip(own, HIT_TINT))


def enemy_sprites(level, enemies, first_tile, viewer_angle=None):
    """The renderer's sprites of `enemies` ([kind, x, y, z, angle, red] each, see ZombieView) seen by someone looking
    along `viewer_angle`: the character pictures in SHIRT's color, as tall as the kind, tinted its color."""
    from game import character_tile_for              # (game imports this module)
    if first_tile is None:
        return []
    out = []
    for kind, x, y, z, angle, red in enemies:
        kinds = enemy_kinds(level)
        enemy = kinds[kind] if 0 <= kind < len(kinds) else None
        if enemy is None:
            continue
        tile = character_tile_for(first_tile, SHIRT, viewer_angle, angle)
        tint = enemy_tint(enemy.color, red)
        out.append((x, y, z, enemy.height, tile) + (() if tint is None else (0.0, 1.0, 0.0, tint)))
    return out


class ZombieRound:
    """The rounds, the enemies and who is out, of one zombies game (see the module's description)."""

    def __init__(self, game):
        self.game = game
        self.number = 0
        self.phase = "intermission"
        self.clock = game.level.settings.intermission
        self.to_spawn = 0                       # enemies of this round still to come in
        self.spawn_wait = 0.0                   # seconds until the next can
        self.enemies = {}                       # ident -> EnemyState
        self.next_ident = 1
        self.message, self.message_left = "", 0.0
        self.paths = {}                         # body height -> Pathing (the places differ with height)
        self.spawn_turn = 0                     # which spawner the next enemy comes in at

    # ------------------------------------------------------------------ what Game asks of a round

    def view(self):
        players = self.game.players
        return ZombieView({pid for pid, s in players.items() if s.alive}, {pid: s.team for pid, s in players.items()},
                          self.number, self.phase, self.clock, self.to_spawn + len(self.enemies), self.message,
                          self.message_left, self.shown_enemies())

    def can_buy(self):
        return True

    def sprites(self, clock):
        return []

    def enemy_sprites(self, first_tile, viewer_angle=None):
        return enemy_sprites(self.game.level, self.shown_enemies(), first_tile, viewer_angle)

    def act(self, pid, wish, dt):
        """The Inputs a player may use this step: only looking around while out."""
        from game import Inputs                         # (game imports this module)
        if not self.game.players[pid].alive:
            return Inputs(turn=wish.turn, tilt=wish.tilt)
        return wish

    def killed(self, pid):
        """A player was knocked out: out until the next round starts (the game is over if nobody is left)."""
        self.game.players[pid].alive = False
        self.check_over()

    def joined(self, pid):
        self.game.players[pid].alive = self.phase != "over"

    def left(self, pid):
        pass

    def after_leaving(self):
        self.check_over()

    def targets(self):
        return [(("z", e.ident), e.body) for e in self.enemies.values()]

    def hurt_target(self, target, damage, attacker, push):
        """A bullet or blast of `attacker`'s hurt an enemy: it loses the health (and is thrown by a blast), and the
        attacker earns the kind's hit reward, or its kill reward when that killed it."""
        enemy = self.enemies.get(target[1]) if isinstance(target, tuple) and len(target) == 2 else None
        if enemy is None or damage <= 0:
            return
        kind = enemy_kinds(self.game.level)[enemy.kind]
        enemy.health -= damage
        enemy.hit = HIT_FLASH
        if push is not None:
            enemy.body.vx += push[0]
            enemy.body.vy += push[1]
            enemy.body.vz += push[2]
            enemy.body.on_ground = False
        killed = enemy.health <= 0
        if killed:
            del self.enemies[enemy.ident]
        self.pay(attacker, kind.kill_reward if killed else kind.hit_reward)

    # ------------------------------------------------------------------ the rounds

    def say(self, text, seconds=NOTE_TIME):
        self.message, self.message_left = text, seconds

    def pay(self, pid, amount):
        state = self.game.players.get(pid)
        if state is not None and amount > 0:
            state.stats.money = min(MAX_MONEY, state.stats.money + amount)

    def standing(self):
        """{player id: PlayerState} of the players not out."""
        return {pid: s for pid, s in self.game.players.items() if s.alive}

    def check_over(self):
        if self.phase != "over" and self.game.players and not self.standing():
            self.phase = "over"
            self.clock = self.game.level.settings.game_over_time
            rounds = max(0, self.number - 1)
            self.say(f"Game over - you survived {rounds} round{'' if rounds == 1 else 's'}", self.clock)

    def start_round(self):
        settings = self.game.level.settings
        self.number += 1
        self.phase = "live"
        self.to_spawn = round(curve_at(settings.zombie_count, self.number))
        self.spawn_wait = 0.0
        self.say(f"Round {self.number}")

    def end_round(self):
        """Every enemy of the round is dead: the players who were out come back, and the intermission starts."""
        self.phase = "intermission"
        self.clock = self.game.level.settings.intermission
        self.say(f"Round {self.number} survived")
        for state in self.game.players.values():
            if not state.alive:
                self.game.respawn(state)
                state.alive = True

    def new_game(self):
        """After a game over: no enemies, round 0, everyone back in with the map's starting money."""
        game = self.game
        self.enemies = {}
        self.number = 0
        self.phase = "intermission"
        self.clock = game.level.settings.intermission
        self.to_spawn = 0
        game.spawns.restart()
        for state in game.players.values():
            state.stats.money = game.level.settings.start_money
            state.stats.score = 0.0
            game.respawn(state)
            state.alive = True

    def update(self, dt):
        self.message_left = max(0.0, self.message_left - dt)
        if self.phase == "over":
            self.clock -= dt
            if self.clock <= 0:
                self.new_game()
            return
        if self.phase == "intermission":
            self.clock -= dt
            if self.clock <= 0 and self.game.players:
                if self.spawners():
                    self.start_round()
                else:
                    self.say("This map has no enemy spawn points", 1.0)     # (said again for as long as that lasts)
            return
        self.spawn(dt)
        self.move_enemies(dt)
        if not self.enemies and self.to_spawn <= 0:
            self.end_round()

    # ------------------------------------------------------------------ enemies

    def spawners(self):
        return [s for s in self.game.level.spawners if s.team == ENEMY_SPAWN]

    def spawn(self, dt):
        """Bring in the round's next enemies, one every spawn_interval, while fewer than max_alive are in the map."""
        settings, level = self.game.level.settings, self.game.level
        self.spawn_wait -= dt
        places = self.spawners()
        while (self.to_spawn > 0 and self.spawn_wait <= 0 and len(self.enemies) < settings.max_alive
               and places):
            spot = places[self.spawn_turn % len(places)]
            self.spawn_turn += 1
            kinds = enemy_kinds(level)
            kind_index = self.game.rng.randrange(len(kinds))
            kind = kinds[kind_index]
            start = spawn_at(self.game.world, spot.x, spot.y, spot.span, spot.angle)
            body = EnemyBody(start.x, start.y, start.z, angle=start.angle, span=start.span, tall=kind.height,
                             radius=kind.radius)
            health = kind.health * max(0.01, curve_at(settings.zombie_health, self.number))
            enemy = EnemyState(self.next_ident, kind_index, body, health,
                               rethink=self.game.rng.uniform(0.0, RETHINK))
            self.enemies[enemy.ident] = enemy
            self.next_ident += 1
            self.to_spawn -= 1
            self.spawn_wait += settings.spawn_interval
        if self.spawn_wait < 0:
            self.spawn_wait = 0.0

    def pathing(self, height):
        paths = self.paths.get(height)
        if paths is None:
            paths = self.paths[height] = Pathing(self.game.world.for_enemies(), height)
        return paths

    def choose_target(self, enemy, kind, dt):
        """Who `enemy` chases: the standing player nearest along the way, and with sticky pathing the one it already
        chases until another has been nearer by more than switch_margin cells for switch_delay seconds."""
        standing = self.standing()
        if enemy.target not in standing:
            enemy.target, enemy.rival, enemy.rethink = None, None, 0.0
        enemy.rethink -= dt
        if enemy.rival is not None:
            enemy.rival_for += dt
        if enemy.rethink > 0 and enemy.target is not None:
            return
        enemy.rethink = RETHINK
        paths = self.pathing(kind.height)
        here = paths.place_of(enemy.body)

        def cost(pid):
            body = standing[pid].body
            found = paths.field(paths.place_of(body))
            if found.reachable(*here):
                return float(found.at(*here))
            # No way there: chosen only if nobody can be reached, then the nearest as the crow flies.
            return NO_WAY + math.hypot(body.x - enemy.body.x, body.y - enemy.body.y) * STRAIGHT

        if not standing:
            return
        costs = {pid: cost(pid) for pid in standing}
        best = min(costs, key=lambda pid: (costs[pid], pid))
        if enemy.target is None or kind.pathing == "nearest":
            enemy.target, enemy.rival = best, None
            return
        if best != enemy.target and costs[best] + kind.switch_margin * STRAIGHT < costs[enemy.target]:
            if enemy.rival != best:
                enemy.rival, enemy.rival_for = best, 0.0
            if enemy.rival_for >= kind.switch_delay:
                enemy.target, enemy.rival = best, None
        else:
            enemy.rival = None

    def reach(self, enemy, kind, attack, body):
        """True if `attack` of `enemy` reaches a player's `body`: within its range edge to edge, at a height where
        the two bodies overlap (give or take the range)."""
        gap = math.hypot(body.x - enemy.body.x, body.y - enemy.body.y) - kind.radius - PLAYER_RADIUS
        return (gap <= attack.range and body.z < enemy.body.z + kind.height + attack.range
                and enemy.body.z < body.z + body.height + attack.range)

    def move_enemies(self, dt):
        game, level = self.game, self.game.level
        world = game.world.for_enemies()
        for enemy in list(self.enemies.values()):
            kind = enemy_kinds(level)[enemy.kind]
            enemy.hit = max(0.0, enemy.hit - dt)
            enemy.cooldown = max(0.0, enemy.cooldown - dt)
            self.choose_target(enemy, kind, dt)
            target = game.players.get(enemy.target)
            forward = 0
            if target is not None:
                body = target.body
                if enemy.attack is not None:            # winding up: it lands, or misses if they got away
                    enemy.attack_left -= dt
                    attack = kind.attacks[enemy.attack] if enemy.attack < len(kind.attacks) else None
                    if enemy.attack_left <= 0:
                        if attack is not None and self.reach(enemy, kind, attack, body):
                            game.hurt(enemy.target, attack.damage)
                        enemy.cooldown = attack.cooldown if attack is not None else 0.0
                        enemy.attack = None
                else:
                    ready = next((i for i, a in enumerate(kind.attacks) if self.reach(enemy, kind, a, body)), None)
                    if ready is not None and enemy.cooldown <= 0:
                        enemy.attack, enemy.attack_left = ready, kind.attacks[ready].windup
                    elif ready is None:
                        point = self.pathing(kind.height).steer(enemy.body, body)
                        if point is not None:
                            enemy.body.angle = math.atan2(point[1] - enemy.body.y, point[0] - enemy.body.x)
                            forward = 1
                    if ready is not None:               # (facing whoever it attacks)
                        enemy.body.angle = math.atan2(body.y - enemy.body.y, body.x - enemy.body.x)
            step(world, enemy.body, forward, 0, 0.0, False, dt, speed=kind.speed)
        self.crowd(world)

    def crowd(self, world):
        """Push enemies that overlap apart (only where they can stand), so a crowd spreads out instead of piling into
        one spot. Neighbors are found by cell, so it is not every enemy against every other."""
        cells = {}
        for enemy in self.enemies.values():
            cells.setdefault((math.floor(enemy.body.x), math.floor(enemy.body.y)), []).append(enemy)
        for (cx, cy), here in cells.items():
            near = [e for dx in (-1, 0, 1) for dy in (-1, 0, 1) for e in cells.get((cx + dx, cy + dy), ())]
            for a in here:
                for b in near:
                    if b.ident <= a.ident or abs(a.body.z - b.body.z) > 0.5:
                        continue
                    dx, dy = b.body.x - a.body.x, b.body.y - a.body.y
                    distance = math.hypot(dx, dy)
                    overlap = a.body.radius + b.body.radius - distance
                    if overlap <= 0:
                        continue
                    if distance < 1e-6:
                        dx, dy, distance = 1.0, 0.0, 1.0
                    push = overlap * CROWD / 2
                    for body, sign in ((a.body, -1), (b.body, 1)):
                        nx, ny = body.x + sign * dx / distance * push, body.y + sign * dy / distance * push
                        if can_stand(world, nx, ny, body.z, body.span, body.on_ground, body.height):
                            body.x, body.y = nx, ny

    def shown_enemies(self):
        """[kind, x, y, z, angle, red] of every enemy, as a ZombieView carries them."""
        return [(e.kind, e.body.x, e.body.y, e.body.z, e.body.angle, min(1.0, e.hit / HIT_FLASH))
                for e in self.enemies.values()]
