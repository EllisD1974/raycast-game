"""Bomb defusal, Counter-Strike's mode: rounds, the bomb, planting and defusing it, the timers and the score. No pygame.

Team 1 (T) attacks: one of them carries the bomb and plants it in a bomb site (the map's site layer) by holding the use
key (E) there. Team 2 (CT) defends: they win by eliminating the Ts before the bomb is planted, by defusing it (holding
E at the bomb), or when the round time runs out without a plant. The Ts win by eliminating the CTs or when the bomb
explodes. A player knocked out stays out until the next round.

A round goes: "freeze" (nobody moves, the buy menu is open) -> "live" (the round timer runs) -> "planted" (the bomb
timer runs instead) -> "over" (the result is shown for a moment) -> the next round. A team that had nobody on it when
the round started cannot be eliminated, so a round can be played alone (plant the bomb, or wait the time out).

The host's Game owns a Round (game.round) and asks it, for each player step, what that player may do (act). What a
player is shown - and what a joiner needs to predict its own movement the way the host will run it - is a RoundView:
the host makes one with Round.view(), and sends it to joiners as a dict (RoundView.to_dict / from_dict).
"""
import math
from dataclasses import dataclass, field

from constants import GRAVITY

from mapfile import CT_TEAM, DEFUSE_KIT, MAX_MONEY, SITE_NAMES, T_TEAM, TEAM_TITLES, grid_name

BOMB_REACH = 0.6                # how close (cells) a T has to walk to a dropped bomb to pick it up
DEFUSE_REACH = 1.0              # how close (cells, across) a CT has to stand to the bomb to defuse it
REACH_UP = 1.0                  # ... and how far above or below it they may be
DROP_COOLDOWN = 1.0             # seconds before a player who dropped the bomb can pick it up again
BOMB_SIZE = 0.35                # the bomb's picture, in cells
BOMB_TILE = 25                  # its picture in the atlas (tile id 26; make_atlas.py / textures.png)
THROW_SPEED = 5.0               # cells / second a bomb dropped with G leaves the hand at, the way the player looks
THROW_HEIGHT = 0.3              # ... from this far above their feet
BOMB_EDGE = 0.1                 # how close (cells) a flying bomb's middle gets to a wall before it bounces off
BOUNCE = 0.3                    # how much of its speed into a wall it keeps, going back the other way
NOTE_TIME = 4.0                 # seconds a round's result stays on screen

# Why a round ended -> what everyone is told (after "<team> win").
REASONS = {"eliminated": "All enemies eliminated", "time": "Target saved", "exploded": "The bomb has exploded",
           "defused": "The bomb has been defused", "left": "The other team left"}


def other_team(team):
    return CT_TEAM if team == T_TEAM else T_TEAM


def clock_text(seconds):
    """1:55, 0:07: how a timer shows."""
    seconds = max(0, math.ceil(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def site_under(level, body):
    """The bomb site (1 A, 2 B) of the floor a player stands on, 0 for none."""
    x, y = int(math.floor(body.x)), int(math.floor(body.y))
    name = grid_name("site", body.span)
    if name not in level.grids or not level.in_bounds(x, y):
        return 0
    return level.grids[name][y][x]


def bomb_damage(settings, distance):
    """What the explosion does to a player `distance` cells from the bomb: Counter-Strike's falloff, full at the bomb
    and dropping away (a bell curve a third of the radius wide) to nothing at the radius."""
    if distance >= settings.bomb_radius:
        return 0.0
    sigma = settings.bomb_radius / 3
    return settings.bomb_damage * math.exp(-distance * distance / (2 * sigma * sigma))


@dataclass
class Bomb:
    """Where the bomb is. state: "none" (nobody has it), "carried" (by `carrier`), "dropped" (lying at x, y, z on floor
    `span`, or flying there at (vx, vy, vz) if it was thrown or dropped in the air), "planted" (at x, y, z in bomb
    site `site`, exploding in `left` seconds), "exploded" or "defused"."""
    state: str = "none"
    carrier: int = None
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    span: int = 0
    site: int = 0
    left: float = 0.0
    vx: float = 0.0                 # velocity while flying after a throw or a drop (the host's only: joiners see
    vy: float = 0.0                 # where it is)
    vz: float = 0.0

    def at(self, body):
        self.x, self.y, self.z, self.span = body.x, body.y, body.z, body.span

    def fall(self, world, dt):
        """A dropped bomb in the air flies (with the players' gravity) until it lands on the floor under it, where it
        stops. It bounces back a little off walls and does not go through ceilings."""
        if self.vx or self.vy:
            for axis in (0, 1):                     # axes separately, like the players: it slides along a wall
                v = self.vx if axis == 0 else self.vy
                x = self.x + (v * dt if axis == 0 else 0.0)
                y = self.y + (v * dt if axis == 1 else 0.0)
                ex = x + math.copysign(BOMB_EDGE, v) if axis == 0 else x
                ey = y + math.copysign(BOMB_EDGE, v) if axis == 1 else y
                if world.point_open(ex, ey, self.z + 0.01) and world.point_open(x, y, self.z + 0.01):
                    self.x, self.y = x, y
                elif axis == 0:
                    self.vx = -self.vx * BOUNCE
                else:
                    self.vy = -self.vy * BOUNCE
        span = world.span_at(self.x, self.y, self.z, self.span, grounded=False)
        if span < 0:
            return
        self.span, ground = span, world.floor_of(span, self.x, self.y)
        if self.z <= ground and self.vz <= 0:
            self.z, self.vx, self.vy, self.vz = ground, 0.0, 0.0, 0.0
            return
        self.vz -= GRAVITY * dt
        self.z += self.vz * dt
        ceiling = world.ceil_of(span, self.x, self.y)
        if self.z + BOMB_SIZE > ceiling:            # hit the ceiling: it comes back down
            self.z, self.vz = max(ground, ceiling - BOMB_SIZE), min(self.vz, 0.0)
        if self.z <= ground:                        # landed: it stays where it lands
            self.z, self.vx, self.vy, self.vz = ground, 0.0, 0.0, 0.0

    def throw(self, body, world):
        """Thrown with G: from about the hand, at THROW_SPEED the way the player looks (up / down too), plus the
        player's own speed."""
        up = math.cos(body.pitch)
        self.vx = math.cos(body.angle) * up * THROW_SPEED + body.vx
        self.vy = math.sin(body.angle) * up * THROW_SPEED + body.vy
        self.vz = math.sin(body.pitch) * THROW_SPEED + (0.0 if body.on_ground else body.vz)
        top = world.ceil_of(self.span, self.x, self.y) - BOMB_SIZE
        self.z = max(self.z, min(self.z + THROW_HEIGHT, top))


@dataclass
class RoundView:
    """What players are shown of the round, and what decides what they may do. Made by the host (Round.view) and
    sent to joiners, who draw it and predict their own movement by it (may_move)."""
    phase: str = "freeze"
    clock: float = 0.0              # seconds left of the freeze, the round, or the pause after it
    number: int = 1                 # the round being played, from 1
    max_rounds: int = 24
    score: dict = field(default_factory=lambda: {T_TEAM: 0, CT_TEAM: 0})
    alive: set = field(default_factory=set)         # ids of the players still in the round
    teams: dict = field(default_factory=dict)       # player id -> team
    bomb: Bomb = field(default_factory=Bomb)
    planting: tuple = (None, 0.0)   # (player id, seconds held) of whoever is planting
    defusing: tuple = (None, 0.0)   # likewise for defusing
    defuse_needed: float = 10.0     # seconds the current defuser needs (shorter with a kit)
    can_buy: bool = True
    message: str = ""               # the last round's result, or the match's
    message_left: float = 0.0

    def to_dict(self):
        b = self.bomb
        return {"phase": self.phase, "clock": round(self.clock, 2), "n": self.number, "max": self.max_rounds,
                "score": [self.score[T_TEAM], self.score[CT_TEAM]], "alive": sorted(self.alive),
                "bomb": [b.state, b.carrier, round(b.x, 3), round(b.y, 3), round(b.z, 3), b.span, b.site, round(b.left, 2)],
                "plant": [self.planting[0], round(self.planting[1], 2)],
                "defuse": [self.defusing[0], round(self.defusing[1], 2), self.defuse_needed],
                "buy": self.can_buy, "msg": self.message, "msg_left": round(self.message_left, 2)}

    @classmethod
    def from_dict(cls, data, teams=None):
        """The view in a snapshot; None if it is not one (it came off the network). `teams` maps player ids to teams
        (they come with the players' names)."""
        try:
            b = data["bomb"]
            bomb = Bomb(str(b[0]), b[1] if isinstance(b[1], int) else None, float(b[2]), float(b[3]), float(b[4]),
                        int(b[5]), int(b[6]), float(b[7]))
            plant, defuse = data["plant"], data["defuse"]
            return cls(str(data["phase"]), float(data["clock"]), int(data["n"]), int(data["max"]),
                       {T_TEAM: int(data["score"][0]), CT_TEAM: int(data["score"][1])},
                       {int(p) for p in data["alive"]}, dict(teams or {}), bomb,
                       (plant[0] if isinstance(plant[0], int) else None, float(plant[1])),
                       (defuse[0] if isinstance(defuse[0], int) else None, float(defuse[1])), float(defuse[2]),
                       bool(data["buy"]), str(data["msg"])[:80], float(data["msg_left"]))
        except (KeyError, IndexError, TypeError, ValueError):
            return None


def can_plant(view, pid, body, level):
    """Whether this player may plant the bomb right now: they carry it, the round is on, and they stand on a bomb
    site."""
    return (view.phase == "live" and view.bomb.state == "carried" and view.bomb.carrier == pid
            and pid in view.alive and body.on_ground and site_under(level, body) > 0)


def can_defuse(view, pid, body):
    """Whether this player may defuse the bomb right now: a CT in reach of the planted bomb, nobody else defusing."""
    bomb = view.bomb
    return (view.phase == "planted" and bomb.state == "planted" and view.teams.get(pid) == CT_TEAM
            and pid in view.alive and body.on_ground and view.defusing[0] in (None, pid)
            and math.hypot(body.x - bomb.x, body.y - bomb.y) <= DEFUSE_REACH and abs(body.z - bomb.z) <= REACH_UP)


def may_move(view, pid, body, use, level):
    """Whether a player may move (and shoot) this step: not during the freeze time, not while out of the round, and
    not while holding the use key to plant or defuse. They may always look around."""
    if view.phase == "freeze" or pid not in view.alive:
        return False
    return not (use and (can_plant(view, pid, body, level) or can_defuse(view, pid, body)))


class Round:
    """The rounds of bomb defusal in a Game (game.round), which calls:

        act(pid, wish, dt)      for each player step: plants / defuses / throws the bomb, and returns the Inputs the
                                player may actually use (no moving while frozen, planting or defusing)
        update(dt)              once per step of the world: the timers, picking the bomb up, deciding the round
        killed(pid)             when a player is knocked out: they stay out until the next round
        joined(pid), left(pid)  when a player comes or goes
        can_buy()               whether the buy menu is open"""

    def __init__(self, game):
        self.game = game
        self.number = 0
        self.score = {T_TEAM: 0, CT_TEAM: 0}
        self.losses = {T_TEAM: 0, CT_TEAM: 0}    # rounds lost in a row (for the loss bonus)
        self.phase, self.clock = "over", 0.0
        self.live_time = 0.0                    # seconds since the freeze time ended (the buy time runs out)
        self.bomb = Bomb()
        self.planting, self.defusing = (None, 0.0), (None, 0.0)
        self.dropped_by = (None, 0.0)           # (player id, seconds left) who may not pick the bomb back up yet
        self.started = set()                    # the teams that had players when the round started
        self.message, self.message_left = "", 0.0
        self.swap_sides = self.new_match = False
        self.holding = set()                    # players who held the use key last step (to tell a press)
        self.new_round()

    @property
    def settings(self):
        return self.game.level.settings

    def team_of(self, pid):
        state = self.game.players.get(pid)
        return state.team if state is not None else None

    def alive(self, team=None):
        return [pid for pid, s in self.game.players.items() if s.alive and (team is None or s.team == team)]

    def say(self, text, seconds=NOTE_TIME):
        self.message, self.message_left = text, seconds

    def note(self, pid, text):
        """A message for one player (shown like a pickup)."""
        self.game.notes.setdefault(pid, []).append(text)

    # ------------------------------------------------------------------ what players see

    def view(self):
        return RoundView(self.phase, self.clock, max(1, self.number), int(self.settings.max_rounds), dict(self.score),
                         set(self.alive()), {pid: s.team for pid, s in self.game.players.items()}, self.bomb,
                         self.planting, self.defusing, self.defuse_time(self.defusing[0]), self.can_buy(),
                         self.message, self.message_left)

    def can_buy(self):
        return self.phase == "freeze" or (self.phase in ("live", "planted") and self.live_time < self.settings.buy_time)

    def defuse_time(self, pid):
        state = self.game.players.get(pid)
        if state is not None and state.inventory.count(DEFUSE_KIT) > 0:
            return self.settings.kit_defuse_time
        return self.settings.defuse_time

    # ------------------------------------------------------------------ rounds

    def new_round(self):
        """Start the next round: swap sides at half time, start over after a match, bring everyone back in at their
        team's spawn points (keeping what they carry if they lived through the last round, with their guns' ammo
        filled up again) and hand one T the bomb."""
        game, settings = self.game, self.settings
        if self.new_match:
            self.number = 0
            self.score = {T_TEAM: 0, CT_TEAM: 0}
            self.losses = {T_TEAM: 0, CT_TEAM: 0}
        if self.swap_sides:
            for state in game.players.values():
                state.team = other_team(state.team)
            self.score = {T_TEAM: self.score[CT_TEAM], CT_TEAM: self.score[T_TEAM]}
            self.losses = {T_TEAM: 0, CT_TEAM: 0}
        restart = self.new_match or self.swap_sides     # money and guns start over, as at the start of a match
        self.swap_sides = self.new_match = False
        self.number += 1
        game.spawns.restart()
        for pid, state in sorted(game.players.items()):
            if restart:
                state.stats.money = settings.start_money
            keep = state.alive and not restart and self.number > 1
            body = game.spawns.body(game.world, state.team)
            if keep:
                state.body = body
                state.stats.health = state.stats.max_health = settings.max_health
                state.inventory.refill()
            else:
                game.respawn(state, body=body)
            state.alive = True
        self.bomb = Bomb()
        self.planting, self.defusing, self.dropped_by = (None, 0.0), (None, 0.0), (None, 0.0)
        ts = self.alive(T_TEAM)
        if ts:
            self.bomb = Bomb("carried", game.rng.choice(sorted(ts)))
            self.note(self.bomb.carrier, "You have the bomb: hold E in a bomb site to plant it")
        self.started = {s.team for s in game.players.values()}
        self.live_time = 0.0
        if settings.freeze_time > 0:
            self.phase, self.clock = "freeze", settings.freeze_time
        else:
            self.phase, self.clock = "live", settings.round_time

    def end_round(self, winner, reason):
        """The round is decided: score it, pay everyone, and pause before the next one (or the next match)."""
        settings = self.settings
        loser = other_team(winner)
        planted = self.bomb.state in ("planted", "exploded", "defused")
        self.score[winner] += 1
        objective = reason in ("exploded", "defused")
        for pid, state in self.game.players.items():
            if state.team == winner:
                pay = settings.bomb_win_money if objective else settings.win_money
            elif state.team == loser:
                pay = min(settings.max_loss_money, settings.loss_money + settings.loss_bonus * self.losses[loser])
                if reason == "time" and state.alive:
                    pay = 0.0                   # (Ts who hid out the clock get nothing)
                if state.team == T_TEAM and planted:
                    pay += settings.plant_money
            else:
                continue
            state.stats.money = min(settings.money_cap, MAX_MONEY, state.stats.money + pay)
        self.losses[loser] += 1
        self.losses[winner] = max(0, self.losses[winner] - 1)
        self.planting, self.defusing = (None, 0.0), (None, 0.0)
        half = int(settings.max_rounds) // 2
        played = self.score[T_TEAM] + self.score[CT_TEAM]
        text = f"{TEAM_TITLES[winner]} win - {REASONS[reason]}"
        if self.score[winner] > settings.max_rounds / 2 or played >= settings.max_rounds:
            self.new_match = True
            if self.score[T_TEAM] == self.score[CT_TEAM]:
                text += f".  The match is a draw {self.score[T_TEAM]}-{self.score[CT_TEAM]}"
            else:
                text += f".  {TEAM_TITLES[winner]} win the match {self.score[winner]}-{self.score[loser]}"
        elif half and played == half:
            self.swap_sides = True
            text += ".  Half time: switching sides"
        self.say(text, settings.round_end_time)
        self.phase, self.clock = "over", settings.round_end_time

    def decide(self):
        """End the round if a team has been eliminated (only a team that had players when it started can be)."""
        if self.phase not in ("live", "planted"):
            return
        ts, cts = self.alive(T_TEAM), self.alive(CT_TEAM)
        if CT_TEAM in self.started and not cts:
            self.end_round(T_TEAM, "eliminated")
        elif T_TEAM in self.started and not ts and self.phase == "live":
            self.end_round(CT_TEAM, "eliminated")      # (after the plant the CTs still have to defuse)

    def update(self, dt):
        self.message_left = max(0.0, self.message_left - dt)
        if self.dropped_by[0] is not None:
            self.dropped_by = (self.dropped_by[0], self.dropped_by[1] - dt) if self.dropped_by[1] > dt else (None, 0.0)
        if self.bomb.state == "dropped":
            self.bomb.fall(self.game.world, dt)
        if self.phase == "freeze":
            self.clock -= dt
            if self.clock <= 0:
                self.phase, self.clock = "live", self.settings.round_time
        elif self.phase == "live":
            self.clock -= dt
            self.live_time += dt
            self.pick_up()
            self.decide()
            if self.phase == "live" and self.clock <= 0:
                self.end_round(CT_TEAM, "time")
        elif self.phase == "planted":
            self.live_time += dt
            self.bomb.left -= dt
            self.decide()
            if self.phase == "planted" and self.bomb.left <= 0:
                self.explode()
        elif self.phase == "over":
            self.clock -= dt
            if self.clock <= 0:
                self.new_round()

    # ------------------------------------------------------------------ players

    def act(self, pid, wish, dt):
        """Carry out the bomb part of one player step and return the Inputs they may use for the rest of it."""
        from game import Inputs                         # (game imports this module)
        state = self.game.players[pid]
        if not state.alive:
            return Inputs(turn=wish.turn, tilt=wish.tilt)
        view = self.view()
        body = state.body
        pressed = wish.use and pid not in self.holding
        (self.holding.add if wish.use else self.holding.discard)(pid)
        if wish.use and can_plant(view, pid, body, self.game.level):
            held = (self.planting[1] if self.planting[0] == pid else 0.0) + dt
            self.planting = (pid, held)
            if held >= self.settings.plant_time:
                self.plant(pid)
        elif self.planting[0] == pid:
            self.planting = (None, 0.0)
        elif pressed and self.bomb.carrier == pid and self.phase == "live" and site_under(self.game.level, body) == 0:
            self.note(pid, "The bomb can only be planted in a bomb site")
        if wish.use and can_defuse(view, pid, body):
            held = (self.defusing[1] if self.defusing[0] == pid else 0.0) + dt
            self.defusing = (pid, held)
            if held >= self.defuse_time(pid):
                self.defused(pid)
        elif self.defusing[0] == pid:
            self.defusing = (None, 0.0)
        if wish.drop and self.bomb.state == "carried" and self.bomb.carrier == pid and self.planting[0] != pid:
            self.drop(pid, throw=True)
            self.dropped_by = (pid, DROP_COOLDOWN)
        if may_move(self.view(), pid, body, wish.use, self.game.level):
            return wish
        return Inputs(turn=wish.turn, tilt=wish.tilt, equip=wish.equip, cycle=wish.cycle, buy=wish.buy,
                      reload=wish.reload, use=wish.use)

    def plant(self, pid):
        body = self.game.players[pid].body
        self.bomb.state, self.bomb.carrier = "planted", None
        self.bomb.at(body)
        self.bomb.site, self.bomb.left = site_under(self.game.level, body), self.settings.bomb_time
        self.planting = (None, 0.0)
        self.phase = "planted"
        state = self.game.players[pid]
        state.stats.money = min(self.settings.money_cap, MAX_MONEY, state.stats.money + self.settings.objective_money)
        self.say(f"The bomb has been planted at {SITE_NAMES.get(self.bomb.site, '?')}", 3.0)

    def defused(self, pid):
        self.bomb.state = "defused"
        state = self.game.players[pid]
        state.stats.money = min(self.settings.money_cap, MAX_MONEY, state.stats.money + self.settings.objective_money)
        self.end_round(CT_TEAM, "defused")

    def explode(self):
        """The bomb goes off: the Ts win, and everyone near it is hurt (walls do not stop it)."""
        game, bomb, settings = self.game, self.bomb, self.settings
        bomb.state = "exploded"
        self.end_round(T_TEAM, "exploded")
        if settings.bomb_effect:
            for dx, dy in ((0, 0), (0.8, 0), (-0.8, 0), (0, 0.8), (0, -0.8)):
                game.fx.append((settings.bomb_effect, bomb.x + dx, bomb.y + dy, bomb.z + 0.2, 0.0, 0.0, 1.0))
        if settings.bomb_light:
            game.flashes.append((settings.bomb_light, bomb.x, bomb.y, bomb.z + 0.5))
        for pid, state in list(game.players.items()):
            if not state.alive:
                continue
            body = state.body
            distance = math.sqrt((body.x - bomb.x) ** 2 + (body.y - bomb.y) ** 2 + (body.z - bomb.z) ** 2)
            damage = bomb_damage(settings, distance)
            if damage > 0:
                game.hurt(pid, damage)

    def drop(self, pid, throw=False):
        """The carrier lets go of the bomb (or is knocked out, or leaves): it lies where they stood (in the air it falls
        from there: see Bomb.fall). `throw` (G): it is thrown the way they look instead."""
        state = self.game.players.get(pid)
        bomb = self.bomb
        bomb.state, bomb.carrier, bomb.vx, bomb.vy, bomb.vz = "dropped", None, 0.0, 0.0, 0.0
        if state is not None:
            bomb.at(state.body)
            if throw:
                bomb.throw(state.body, self.game.world)
        if self.planting[0] == pid:
            self.planting = (None, 0.0)

    def pick_up(self):
        """A T walking over the dropped bomb picks it up."""
        if self.bomb.state != "dropped":
            return
        for pid in sorted(self.alive(T_TEAM)):
            body = self.game.players[pid].body
            if pid == self.dropped_by[0]:
                continue
            if math.hypot(body.x - self.bomb.x, body.y - self.bomb.y) <= BOMB_REACH and abs(body.z - self.bomb.z) <= REACH_UP:
                self.bomb.state, self.bomb.carrier = "carried", pid
                self.note(pid, "You picked up the bomb")
                return

    def killed(self, pid):
        """A player was knocked out: they are out until the next round, and drop the bomb if they had it."""
        state = self.game.players[pid]
        state.alive = False
        if self.bomb.state == "carried" and self.bomb.carrier == pid:
            self.drop(pid)
        if self.defusing[0] == pid:
            self.defusing = (None, 0.0)
        self.decide()

    def joined(self, pid):
        """A new player: in during the freeze time, otherwise out until the next round."""
        state = self.game.players[pid]
        state.alive = self.phase == "freeze"
        if state.alive:
            self.started.add(state.team)
            if state.team == T_TEAM and self.bomb.state == "none":
                self.bomb = Bomb("carried", pid)
                self.note(pid, "You have the bomb: hold E in a bomb site to plant it")
        if self.phase in ("live", "planted"):
            self.note(pid, "You join in the next round")

    def left(self, pid):
        if self.bomb.state == "carried" and self.bomb.carrier == pid:
            self.drop(pid)
        if self.planting[0] == pid:
            self.planting = (None, 0.0)
        if self.defusing[0] == pid:
            self.defusing = (None, 0.0)

    def after_leaving(self):
        """Once a player is gone: a team left with nobody loses the round."""
        if self.phase in ("live", "planted"):
            for team in (T_TEAM, CT_TEAM):
                if team in self.started and not any(s.team == team for s in self.game.players.values()):
                    self.end_round(other_team(team), "left")
                    return
            self.decide()

    def sprite(self, tile, clock):
        """The bomb as the renderer draws it, when it lies on the ground or is planted (blinking faster as it runs
        out), else None."""
        return bomb_sprite(self.bomb, tile, clock)


def bomb_sprite(bomb, tile, clock):
    """(x, y, z, size, tile, spin, alpha, glow) of the bomb lying on the ground or planted, else None. A planted bomb
    blinks, faster as its time runs out."""
    if tile is None or bomb.state not in ("dropped", "planted"):
        return None
    glow = 0.0
    if bomb.state == "planted":
        period = max(0.15, min(1.0, bomb.left / 10.0))
        glow = 1.0 if (clock % period) < period * 0.35 else 0.0
    return (bomb.x, bomb.y, bomb.z, BOMB_SIZE, tile, 0.0, 1.0, glow)
