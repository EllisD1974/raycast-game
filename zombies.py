"""Zombies: everyone on one team against rounds of enemies that come for them. No pygame.

The map defines kinds of enemy (mapfile.Enemy: health, speed, size, attacks, who they chase) and where they come in
(Spawners of team ENEMY_SPAWN). Each round sends a number of them (MapSettings.zombie_count, a curve over the rounds),
tougher as the rounds go on (zombie_health), no more than max_alive at once, one every spawn_interval seconds (curves
too; more for more players: extra_per_player), each of a kind picked by the kinds' weights for the round. They
find their way to the players (pathing.py) and attack whoever they reach. Players earn money for every hit and kill.
When all of a round's enemies are dead the next round starts after the intermission, and the players who were knocked
out come back.

A player at 0 health goes down while someone else is still standing: they crawl, can still shoot (if the map says
so), and enemies leave them alone. A teammate holding the use key (E) beside them for a while revives them; otherwise
they bleed out and are out until the next round. When nobody is left standing, the game is over: after a moment a new
game starts at round 1. (Alone, going down is the end.)

Barricades (mapfile.Barricade) board up openings: players can never walk through one, enemies only once its boards
are all torn off; bullets go through. Barricades that touch (side by side or corner to corner) are one
(Level.barricade_groups), with one count of boards. An enemy whose way leads through a boarded one stops at it and tears a board off every break_rate
seconds; a player holding the use key beside one puts a board back every repair_time seconds, for a reward (up to a
cap each round). apply_boards keeps a world (the host's and each joiner's own) showing the boards there are.

A round goes: "intermission" (counting down to the next round) -> "live" (enemies come in and attack) -> the
intermission again; "over" when every player is out.

ZombieRound stands in for Game.round (like bomb.Round). Enemies are targets the game's bullets and blasts strike
(targets, hurt_target). What a player is shown, the enemies included, is a ZombieView: the host makes one with
ZombieRound.view() and sends it to joiners as a dict.
"""
import math
from dataclasses import dataclass, field, replace

from constants import CROUCH_MULTIPLIER, MOVE_SPEED, PLAYER_HEIGHT, PLAYER_RADIUS
from mapfile import ENEMY_SPAWN, MAX_MONEY, Enemy, curve_at
from pathing import Pathing, STRAIGHT
from physics import Player, can_stand, spawn_at, step

RETHINK = 0.25                  # seconds between an enemy looking again at who to chase
SHIRT = 2                       # the character pictures' shirt color enemies are drawn in (green)
HIT_FLASH = 0.25                # seconds an enemy shows red after being hurt
CROWD = 0.9                     # how hard enemies closer than their two radii push apart (share of the overlap a step)
NOTE_TIME = 3.0                 # seconds a message stays on screen
NO_WAY = 1e9                    # the cost of chasing a player there is no way to
REVIVE_REACH = 1.0              # how close (cells, across) a player has to be to a downed one to revive them
REVIVE_UP = 1.0                 # ... and how far above or below
TEAR_REACH = 0.95               # how close (cells) an enemy's middle has to be to a barricade's to tear at it
REPAIR_REACH = 1.3              # how close a player has to be to a barricade's middle to rebuild it
BREAK_COST = 30                 # the extra cost (pathing.STRAIGHT is one cell) of a way through a boarded barricade


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
    tear: float = 0.0           # seconds into tearing the next board off a barricade


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
    downed: dict = field(default_factory=dict)      # player id -> (seconds until they bleed out, x, y, z, name)
    revives: dict = field(default_factory=dict)     # downed player id -> (reviver's id, seconds of reviving done)
    boards: list = field(default_factory=list)      # boards left on each group of barricades (barricade_groups)
    repairs: dict = field(default_factory=dict)     # player id -> (group index, seconds into the next board)
    crawl: float = 0.6                              # how fast the downed crawl (the map's downed_speed)
    can_buy: bool = True

    def may_move(self, pid, body, use, level):
        """Whether a player may move this step: anyone not out (a downed player crawls: see restrict)."""
        return pid in self.alive

    def restrict(self, pid, wish, level):
        """The Inputs a player not out may use: all of them, but a downed player only crawls (see downed_inputs)."""
        return downed_inputs(wish, level.settings) if pid in self.downed else wish

    def speed_of(self, pid):
        return walking_speed(pid in self.downed, self.crawl)

    def to_dict(self):
        return {"mode": self.mode, "alive": sorted(self.alive), "number": self.number, "phase": self.phase,
                "clock": round(self.clock, 2), "left": self.left, "msg": self.message,
                "msg_left": round(self.message_left, 2), "crawl": self.crawl,
                "enemies": [[kind, round(x, 3), round(y, 3), round(z, 3), round(angle, 2), round(red, 2)]
                            for kind, x, y, z, angle, red in self.enemies],
                "downed": [[pid, round(left, 2), round(x, 3), round(y, 3), round(z, 3), name]
                           for pid, (left, x, y, z, name) in sorted(self.downed.items())],
                "revives": [[pid, reviver, round(done, 2)] for pid, (reviver, done) in sorted(self.revives.items())],
                "boards": list(self.boards),
                "repairs": [[pid, index, round(done, 2)] for pid, (index, done) in sorted(self.repairs.items())]}

    @classmethod
    def from_dict(cls, data, teams=None):
        """The view in a snapshot; None if it is not one (it came off the network)."""
        try:
            enemies = [(int(kind), float(x), float(y), float(z), float(angle), float(red))
                       for kind, x, y, z, angle, red in data["enemies"]]
            downed = {int(pid): (float(left), float(x), float(y), float(z), str(name)[:32])
                      for pid, left, x, y, z, name in data["downed"]}
            revives = {int(pid): (int(reviver), float(done)) for pid, reviver, done in data["revives"]}
            boards = [max(0, int(n)) for n in data["boards"]]
            repairs = {int(pid): (int(index), float(done)) for pid, index, done in data["repairs"]}
            phase = data["phase"] if data["phase"] in ("intermission", "live", "over") else "intermission"
            return cls({int(p) for p in data["alive"]}, dict(teams or {}), int(data["number"]), phase,
                       float(data["clock"]), int(data["left"]), str(data["msg"])[:80], float(data["msg_left"]),
                       enemies, downed, revives, boards, repairs, max(0.0, min(3.0, float(data["crawl"]))))
        except (KeyError, IndexError, TypeError, ValueError):
            return None


def downed_inputs(wish, settings):
    """What a downed player may do of what they asked for: crawl (crouched: no jumping or sprinting), look around,
    and shoot, reload and switch guns if the map lets them (downed_can_shoot); not use anything or buy."""
    from game import Inputs                         # (game imports this module)
    shoot = settings.downed_can_shoot
    return Inputs(forward=wish.forward, strafe=wish.strafe, turn=wish.turn, tilt=wish.tilt, crouch=True,
                  fire=wish.fire and shoot, reload=wish.reload and shoot, equip=wish.equip if shoot else (),
                  cycle=wish.cycle if shoot else 0)


def walking_speed(downed, crawl):
    """The speed physics.step is given for a player: MOVE_SPEED, or for a downed one (who is crouched, which slows
    them by CROUCH_MULTIPLIER) whatever makes them crawl at `crawl` cells per second."""
    return crawl / CROUCH_MULTIPLIER if downed else MOVE_SPEED


def apply_boards(world, level, boards):
    """Make `world` show the barricades of `level` with `boards` boards left on each group of them
    (Level.barricade_groups): each cell as a pane of its stage for how torn down the group is, filling the opening
    (or, without stages, of its tile as high as the share of boards left), none once they are all gone; bullets go
    through; always stopping players, stopping enemies while any boards are left, and costing enemies' pathing a
    detour (BREAK_COST) through them. Only what changed is touched, and the world's revision (pathing) only moves when
    a group opens up or closes."""
    shown = world.extras.setdefault("boards", {})
    for g, (group, left) in enumerate(zip(level.barricade_groups(), boards)):
        if shown.get(g) == left:
            continue
        before = shown.get(g)
        shown[g] = left
        total = level.barricades[group[0]].boards
        cells = []
        for i in group:
            barricade = level.barricades[i]
            x, y = barricade.x, barricade.y
            if not (0 <= x < world.width and 0 <= y < world.height):
                continue
            cells.append((x, y))
            floor, ceiling = world.floor_of(0, x + 0.5, y + 0.5), world.ceil_of(0, x + 0.5, y + 0.5)
            if left > 0 and barricade.stages:
                world.set_pane(x, y, barricade.stage_tile(left, total), ceiling, shoot_through=True)
            elif left > 0:
                world.set_pane(x, y, barricade.tile, floor + (ceiling - floor) * left / max(1, total),
                               shoot_through=True)
            else:
                world.set_pane(x, y, -1, 1e9)
        if before is None:
            world.set_cost(cells, BREAK_COST)
        if before is None or (before > 0) != (left > 0):
            world.set_blocks(cells, players=True, enemies=left > 0)


def nearest_group(level, groups, boards, x, y):
    """The index of the group of barricades missing boards with a cell within REPAIR_REACH of (x, y), the nearest
    such cell's; None for none."""
    best = None
    for g, group in enumerate(groups):
        if g >= len(boards) or boards[g] >= level.barricades[group[0]].boards:
            continue
        for i in group:
            b = level.barricades[i]
            distance = math.hypot(b.x + 0.5 - x, b.y + 0.5 - y)
            if distance <= REPAIR_REACH and (best is None or distance < best[0]):
                best = (distance, g)
    return None if best is None else best[1]


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
        self.spawned = {}                       # kind index -> how many of it came in this round
        self.downed = {}                        # player id -> seconds until they bleed out
        self.revives = {}                       # downed player id -> [reviver's id, seconds of reviving done]
        self.grace = {}                         # player id -> seconds enemies cannot hurt them (just revived)
        self.groups = game.level.barricade_groups()     # the barricades that act as one
        self.boards = [game.level.barricades[g[0]].boards for g in self.groups]    # boards left on each group
        self.repairs = {}                       # player id -> [group index, seconds into the next board]
        self.repaid = {}                        # player id -> what rebuilding has earned them this round
        self.barricade_cells = {(game.level.barricades[i].x, game.level.barricades[i].y): g
                                for g, group in enumerate(self.groups) for i in group}     # cell -> its group
        apply_boards(game.world, game.level, self.boards)

    # ------------------------------------------------------------------ what Game asks of a round

    def view(self):
        players = self.game.players
        downed = {pid: (left, players[pid].body.x, players[pid].body.y, players[pid].body.z, players[pid].name)
                  for pid, left in self.downed.items()}
        return ZombieView({pid for pid, s in players.items() if s.alive}, {pid: s.team for pid, s in players.items()},
                          self.number, self.phase, self.clock, self.to_spawn + len(self.enemies), self.message,
                          self.message_left, self.shown_enemies(), downed,
                          {pid: tuple(entry) for pid, entry in self.revives.items()}, list(self.boards),
                          {pid: tuple(entry) for pid, entry in self.repairs.items()},
                          self.game.level.settings.downed_speed)

    def can_buy(self):
        return True

    def sprites(self, clock):
        return []

    def enemy_sprites(self, first_tile, viewer_angle=None):
        return enemy_sprites(self.game.level, self.shown_enemies(), first_tile, viewer_angle)

    def act(self, pid, wish, dt):
        """The Inputs a player may use this step: only looking around while out, crawling while down, and not
        shooting while reviving someone (holding the use key beside them, which this step counts toward)."""
        from game import Inputs                         # (game imports this module)
        if not self.game.players[pid].alive:
            return Inputs(turn=wish.turn, tilt=wish.tilt)
        if pid in self.downed:
            return downed_inputs(wish, self.game.level.settings)
        if self.revive_step(pid, wish.use, dt):
            self.repairs.pop(pid, None)
            wish = replace(wish, fire=False)            # (hands busy)
        elif self.repair_step(pid, wish.use, dt):
            wish = replace(wish, fire=False)
        return wish

    def speed_of(self, pid):
        return walking_speed(pid in self.downed, self.game.level.settings.downed_speed)

    def killed(self, pid):
        """A player's health ran out: down, while anyone else is standing to revive them; else out until the next
        round starts (and the game is over if nobody is left standing)."""
        if pid in self.downed:
            return                                  # (already down: hurting them more changes nothing)
        if any(other != pid for other in self.standing()):
            self.downed[pid] = self.game.level.settings.bleed_out
            self.revives.pop(next((d for d, (r, _) in self.revives.items() if r == pid), None), None)
        else:
            self.game.players[pid].alive = False
        self.check_over()

    # ------------------------------------------------------------------ going down and reviving

    def in_reach(self, body, other):
        return (math.hypot(other.x - body.x, other.y - body.y) <= REVIVE_REACH
                and abs(other.z - body.z) <= REVIVE_UP)

    def revive_step(self, pid, use, dt):
        """A standing player's step toward reviving the downed player beside them while they hold the use key.
        True while they are reviving someone."""
        mine = next((d for d, (r, _) in self.revives.items() if r == pid), None)
        players = self.game.players
        body = players[pid].body
        if mine is not None and (not use or mine not in self.downed or not self.in_reach(body, players[mine].body)):
            del self.revives[mine]                  # (let go, or moved away: it starts over)
            mine = None
        if not use:
            return False
        if mine is None:
            free = [d for d in self.downed if d not in self.revives and d in players
                    and self.in_reach(body, players[d].body)]
            if not free:
                return False
            mine = min(free, key=lambda d: math.hypot(players[d].body.x - body.x, players[d].body.y - body.y))
            self.revives[mine] = [pid, 0.0]
        self.revives[mine][1] += dt
        if self.revives[mine][1] >= self.game.level.settings.revive_time:
            self.revive(mine, pid)
        return True

    # ------------------------------------------------------------------ barricades

    def repair_step(self, pid, use, dt):
        """A standing player's step toward putting a board back on the barricade beside them (the nearest missing
        some: a group of them is rebuilt as one) while they hold the use key. True while they are rebuilding."""
        body = self.game.players[pid].body
        level = self.game.level
        if not use or body.span != 0:
            self.repairs.pop(pid, None)
            return False
        index = nearest_group(level, self.groups, self.boards, body.x, body.y)
        if index is None:
            self.repairs.pop(pid, None)
            return False
        entry = self.repairs.get(pid)
        if entry is None or entry[0] != index:
            entry = self.repairs[pid] = [index, 0.0]
        entry[1] += dt
        barricade = level.barricades[self.groups[index][0]]                 # (the group's settings)
        if entry[1] >= barricade.repair_time:
            entry[1] = 0.0
            self.boards[index] += 1
            apply_boards(self.game.world, level, self.boards)
            amount = max(0.0, min(barricade.reward, barricade.reward_cap - self.repaid.get(pid, 0.0)))
            self.repaid[pid] = self.repaid.get(pid, 0.0) + amount
            stats = self.game.players[pid].stats
            if barricade.reward_kind == "score":
                stats.score += amount
            else:
                self.pay(pid, amount)
            if self.boards[index] >= barricade.boards:
                self.repairs.pop(pid, None)
        return True

    def tear(self, enemy, kind, goal, dt):
        """If `enemy`'s way to `goal` (a body) goes next through a boarded barricade it is at, tear at it (a board off
        every break_rate seconds) and say so (True): it stays where it is meanwhile."""
        paths = self.pathing(kind.height)
        here = paths.place_of(enemy.body)
        to = paths.next_place(paths.field(paths.place_of(goal)), here)
        index = self.barricade_cells.get((to[1], to[2])) if to is not None and to[0] == 0 else None
        if index is None or self.boards[index] <= 0:
            enemy.tear = 0.0
            return False
        cx, cy = to[1] + 0.5, to[2] + 0.5                   # (the cell of the group in its way)
        if math.hypot(cx - enemy.body.x, cy - enemy.body.y) > TEAR_REACH + kind.radius:
            return False
        enemy.body.angle = math.atan2(cy - enemy.body.y, cx - enemy.body.x)
        enemy.tear += dt
        if enemy.tear >= kind.break_rate:
            enemy.tear = 0.0
            self.boards[index] -= 1
            apply_boards(self.game.world, self.game.level, self.boards)
        return True

    def revive(self, pid, reviver=None):
        """A downed player gets up: with the map's revive_health, safe from enemies for a moment, and the one who
        revived them is paid."""
        settings = self.game.level.settings
        state = self.game.players[pid]
        self.downed.pop(pid, None)
        self.revives.pop(pid, None)
        state.stats.health = min(state.stats.max_health, settings.revive_health)
        self.grace[pid] = settings.revive_grace
        if reviver is not None:
            self.pay(reviver, settings.revive_reward)
            self.game.notes.setdefault(reviver, []).append(f"Revived {state.name or 'a teammate'}")

    def bleed(self, dt):
        """Downed players' time runs out: out until the next round. Grace after a revive runs out too."""
        for pid in list(self.downed):
            self.downed[pid] -= dt
            if self.downed[pid] <= 0:
                del self.downed[pid]
                self.revives.pop(pid, None)
                self.game.players[pid].alive = False
        for pid in list(self.grace):
            self.grace[pid] -= dt
            if self.grace[pid] <= 0:
                del self.grace[pid]
        self.check_over()

    def joined(self, pid):
        self.game.players[pid].alive = self.phase != "over"

    def left(self, pid):
        self.repairs.pop(pid, None)
        self.downed.pop(pid, None)
        self.grace.pop(pid, None)
        self.revives = {d: entry for d, entry in self.revives.items() if pid not in (d, entry[0])}

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
        """{player id: PlayerState} of the players not out or down."""
        return {pid: s for pid, s in self.game.players.items() if s.alive and pid not in self.downed}

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
        self.repaid = {}
        self.to_spawn = round(curve_at(settings.zombie_count, self.number) * self.player_scale())
        self.spawned = {}                       # kind index -> how many of it came in this round
        self.spawn_wait = 0.0
        self.say(f"Round {self.number}")

    def end_round(self):
        """Every enemy of the round is dead: the downed get up, the players who were out come back (with only what a
        new player carries, unless the map keeps their guns), and the intermission starts."""
        settings = self.game.level.settings
        self.phase = "intermission"
        self.clock = settings.intermission
        self.say(f"Round {self.number} survived")
        for pid in list(self.downed):
            self.revive(pid)
        for state in self.game.players.values():
            if not state.alive:
                kept = state.inventory
                self.game.respawn(state)
                if settings.keep_guns:
                    state.inventory = kept
                state.alive = True

    def new_game(self):
        """After a game over: no enemies, round 0, everyone back in with the map's starting money."""
        game = self.game
        self.enemies = {}
        self.number = 0
        self.phase = "intermission"
        self.clock = game.level.settings.intermission
        self.to_spawn = 0
        self.downed, self.revives, self.grace = {}, {}, {}
        self.boards = [game.level.barricades[g[0]].boards for g in self.groups]
        self.repairs, self.repaid = {}, {}
        apply_boards(game.world, game.level, self.boards)
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
        self.bleed(dt)
        if self.phase == "over":
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

    def player_scale(self):
        """How many times a round's enemies (and the most at once) the players face: 1 for one player, and the map's
        extra_per_player more for each player beyond."""
        return 1.0 + self.game.level.settings.extra_per_player * max(0, len(self.game.players) - 1)

    def pick_kind(self):
        """The index of the kind the next enemy is: picked by the kinds' weights for this round, leaving out kinds
        that have come in their max_per_round times already. When every weight is 0, the first kind not at its most;
        when every kind is, the first."""
        kinds = enemy_kinds(self.game.level)
        open_ = [i for i, k in enumerate(kinds) if k.max_per_round <= 0 or self.spawned.get(i, 0) < k.max_per_round]
        weights = [(i, curve_at(kinds[i].weight, self.number)) for i in open_]
        total = sum(w for _, w in weights)
        if total <= 0:
            return open_[0] if open_ else 0
        roll = self.game.rng.random() * total
        for i, w in weights:
            roll -= w
            if roll < 0 and w > 0:
                return i
        return next(i for i, w in reversed(weights) if w > 0)

    def spawn(self, dt):
        """Bring in the round's next enemies, one every spawn_interval, while fewer than max_alive are in the map."""
        settings, level = self.game.level.settings, self.game.level
        self.spawn_wait -= dt
        places = self.spawners()
        most = max(1, round(curve_at(settings.max_alive, self.number) * self.player_scale()))
        while self.to_spawn > 0 and self.spawn_wait <= 0 and len(self.enemies) < most and places:
            spot = places[self.spawn_turn % len(places)]
            self.spawn_turn += 1
            kind_index = self.pick_kind()
            kind = enemy_kinds(level)[kind_index]
            self.spawned[kind_index] = self.spawned.get(kind_index, 0) + 1
            start = spawn_at(self.game.world, spot.x, spot.y, spot.span, spot.angle)
            body = EnemyBody(start.x, start.y, start.z, angle=start.angle, span=start.span, tall=kind.height,
                             radius=kind.radius)
            health = kind.health * max(0.01, curve_at(settings.zombie_health, self.number))
            enemy = EnemyState(self.next_ident, kind_index, body, health,
                               rethink=self.game.rng.uniform(0.0, RETHINK))
            self.enemies[enemy.ident] = enemy
            self.next_ident += 1
            self.to_spawn -= 1
            self.spawn_wait += curve_at(settings.spawn_interval, self.number)
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
                        if (attack is not None and self.reach(enemy, kind, attack, body)
                                and enemy.target not in self.grace and enemy.target in self.standing()):
                            game.hurt(enemy.target, attack.damage)
                        enemy.cooldown = attack.cooldown if attack is not None else 0.0
                        enemy.attack = None
                else:
                    ready = next((i for i, a in enumerate(kind.attacks) if self.reach(enemy, kind, a, body)), None)
                    if ready is not None and enemy.cooldown <= 0:
                        enemy.attack, enemy.attack_left = ready, kind.attacks[ready].windup
                    elif ready is None and self.tear(enemy, kind, body, dt):
                        pass                            # (tearing the boards off a barricade on its way)
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
