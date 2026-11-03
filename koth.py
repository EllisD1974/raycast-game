"""King of the Hill, Team Fortress 2's mode: two teams fight over one capture point, each with its own clock. No pygame.

Team 1 (RED) and team 2 (BLU) both start with hill_time on their clock, and the point (the site layer's HILL_SITE
cells) neutral and locked for unlock_time. Once it unlocks, a team captures it by standing on it alone for
capture_time (two players take 1 / (1 + 1/2) of that, three 1 / (1 + 1/2 + 1/3) and so on). While a team owns the
point only its own clock runs down, and when it reaches zero that team wins the round. Each capture adds
capture_bonus seconds to the capturing team's clock (up to hill_time), so a team that loses the point late has to
hold it a little longer when it takes it back (Team Fortress 2 does not do this; set the bonus to 0 for its rules).

As in Team Fortress 2:
- with both teams on the point nobody's capture moves (it is contested), though the owner's clock keeps running;
- the owners standing on their point alone push the other team's progress back at their own capture speed, and on a
  neutral point a team first pushes back the other team's progress before it starts its own;
- with nobody on the point, capture progress drains away over decay_time (six times faster in overtime);
- when the owner's clock runs out while the other team has capture progress or stands on the point, the round goes
  into overtime: the owners win as soon as that progress is gone and nobody of the other team is on the point, and
  lose the point (and their clock stops) if the other team completes the capture.

A knocked out player waits respawn_time before coming back at their team's spawn points. A round won shows its
result for round_end_time (the losers cannot shoot meanwhile, Team Fortress 2's humiliation), then everyone starts the
next round at their team's spawn points. The first team to win win_limit rounds wins the match, and a new one starts.

The host's Game owns a HillRound (game.round, as bomb defusal's Round). What players are shown is a HillView: the
host makes one with HillRound.view() and sends it to joiners as a dict (HillView.to_dict / from_dict).
"""
import math
from dataclasses import dataclass, field, replace

from bomb import area_under, clock_text
from mapfile import CT_TEAM, HILL_SITE, KOTH_NAMES, T_TEAM, grid_name

RED, BLU = T_TEAM, CT_TEAM
TEAMS = (RED, BLU)
OVERTIME_DECAY = 6.0            # capture progress drains this many times faster in overtime
NOTE_TIME = 3.0                 # seconds a capture, the unlock or overtime is announced for
HILL_TILES = {0: 26, RED: 27, BLU: 28}          # the point's marker in the atlas (tile ids 27-29), by owner
MARKER_SIZE = 0.4               # the marker over the point, in cells
MARKER_LIFT = 1.0               # ... floating this far above the floor (less under a low ceiling)


def other_team(team):
    return BLU if team == RED else RED


def capture_rate(players, capture_time):
    """The share of a capture `players` standing on the point make in a second: Team Fortress 2's 1 + 1/2 + 1/3 ...
    times what one player alone makes."""
    if players <= 0:
        return 0.0
    return sum(1.0 / i for i in range(1, players + 1)) / max(0.01, capture_time)


def on_hill(level, body):
    """Whether a player stands on the capture point."""
    return area_under(level, body) == HILL_SITE


def hill_cells(level):
    """[(floor, x, y)] of the capture point's cells."""
    cells = []
    for floor in range(level.floor_count):
        name = grid_name("site", floor)
        if name in level.grids:
            cells += [(floor, x, y) for y, row in enumerate(level.grids[name]) for x, v in enumerate(row)
                      if v == HILL_SITE]
    return cells


def hill_spot(level, world):
    """(x, y, z, floor) where the point's marker floats: over the point's cell nearest the middle of all of them (None
    when the map has no point)."""
    cells = hill_cells(level)
    if not cells:
        return None
    mx = sum(x + 0.5 for _, x, _ in cells) / len(cells)
    my = sum(y + 0.5 for _, _, y in cells) / len(cells)
    floor, x, y = min(cells, key=lambda c: ((c[1] + 0.5 - mx) ** 2 + (c[2] + 0.5 - my) ** 2, c))
    x, y = (mx, my) if (math.floor(mx), math.floor(my)) == (x, y) else (x + 0.5, y + 0.5)
    ground, ceiling = world.floor_of(floor, x, y), world.ceil_of(floor, x, y)
    return (x, y, max(ground, min(ground + MARKER_LIFT, ceiling - MARKER_SIZE)), floor)


@dataclass
class HillView:
    """What players are shown of the round, and what decides what they may do. Made by the host (HillRound.view) and
    sent to joiners, who draw it and predict their own movement by it (may_move)."""
    mode = "koth"
    phase: str = "setup"            # "setup" (the point is locked), "live" or "over" (a team won the round)
    clock: float = 0.0              # seconds until the point unlocks (setup), or until the next round (over)
    number: int = 1                 # the round being played, from 1
    clocks: dict = field(default_factory=lambda: {RED: 0.0, BLU: 0.0})     # each team's time left to hold the point
    owner: int = 0                  # the team that owns the point (0: neutral)
    capper: int = 0                 # the team whose capture progress it is (0: none)
    progress: float = 0.0           # how far that capture is, 0 to 1
    contested: bool = False         # both teams stand on the point
    overtime: bool = False
    score: dict = field(default_factory=lambda: {RED: 0, BLU: 0})          # rounds won in this match
    win_limit: int = 2
    winner: int = 0                 # the team that won the round (phase "over")
    alive: set = field(default_factory=set)         # ids of the players not waiting to respawn
    teams: dict = field(default_factory=dict)       # player id -> team
    respawns: dict = field(default_factory=dict)    # player id -> seconds until they come back
    spot: tuple = None              # (x, y, z, floor) of the point's marker, None if the map has no point
    message: str = ""
    message_left: float = 0.0
    can_buy: bool = True

    def may_move(self, pid, body, use, level):
        """Whether a player may move this step: anyone who is not waiting to respawn."""
        return pid in self.alive

    def to_dict(self):
        return {"mode": self.mode, "phase": self.phase, "clock": round(self.clock, 2), "n": self.number,
                "clocks": [round(self.clocks[RED], 2), round(self.clocks[BLU], 2)], "owner": self.owner,
                "capper": self.capper, "progress": round(self.progress, 4), "contested": self.contested,
                "ot": self.overtime, "score": [self.score[RED], self.score[BLU]], "win": self.win_limit,
                "winner": self.winner, "alive": sorted(self.alive),
                "respawns": [[pid, round(left, 2)] for pid, left in sorted(self.respawns.items())],
                "spot": [round(v, 3) for v in self.spot] if self.spot else None,
                "msg": self.message, "msg_left": round(self.message_left, 2)}

    @classmethod
    def from_dict(cls, data, teams=None):
        """The view in a snapshot; None if it is not one (it came off the network). `teams` maps player ids to teams
        (they come with the players' names)."""
        try:
            spot = data["spot"]
            return cls(str(data["phase"]), float(data["clock"]), int(data["n"]),
                       {RED: float(data["clocks"][0]), BLU: float(data["clocks"][1])},
                       int(data["owner"]) if data["owner"] in TEAMS else 0,
                       int(data["capper"]) if data["capper"] in TEAMS else 0,
                       max(0.0, min(1.0, float(data["progress"]))), bool(data["contested"]), bool(data["ot"]),
                       {RED: int(data["score"][0]), BLU: int(data["score"][1])}, int(data["win"]),
                       int(data["winner"]) if data["winner"] in TEAMS else 0,
                       {int(p) for p in data["alive"]}, dict(teams or {}),
                       {int(pid): float(left) for pid, left in data["respawns"]},
                       (float(spot[0]), float(spot[1]), float(spot[2]), int(spot[3])) if spot else None,
                       str(data["msg"])[:80], float(data["msg_left"]))
        except (KeyError, IndexError, TypeError, ValueError):
            return None


def hill_sprite(view, clock):
    """(x, y, z, size, tile, spin, alpha, glow) of the marker over the point, in its owner's color (gently bobbing,
    and blinking while it is being captured), or None when the map has no point."""
    if view is None or view.spot is None:
        return None
    x, y, z, _floor = view.spot
    glow = 0.0
    if view.capper and view.progress > 0 and view.phase == "live":
        glow = 1.0 if (clock % 0.5) < 0.25 else 0.0
    bob = 0.04 * math.sin(clock * 2.0)
    return (x, y, max(0.0, z + bob), MARKER_SIZE, HILL_TILES[view.owner], 0.0, 1.0, glow)


class HillRound:
    """The rounds of King of the Hill in a Game (game.round, in place of bomb defusal's Round), which calls:

        act(pid, wish, dt)      for each player step: returns the Inputs the player may actually use (none while
                                waiting to respawn; the losers of a round cannot shoot until the next one)
        update(dt)              once per step of the world: the capture, the clocks, respawning, deciding the round
        killed(pid)             when a player is knocked out: they come back after the respawn time
        joined(pid), left(pid)  when a player comes or goes
        can_buy()               whether the buy menu is open (always)"""

    def __init__(self, game):
        self.game = game
        self.number = 0
        self.score = {RED: 0, BLU: 0}
        self.new_match = False
        self.waiting = {}                       # player id -> seconds until they respawn
        self.message, self.message_left = "", 0.0
        self.spot = hill_spot(game.level, game.world)
        self.new_round()

    @property
    def settings(self):
        return self.game.level.settings

    def say(self, text, seconds=NOTE_TIME):
        self.message, self.message_left = text, seconds

    def note(self, pid, text):
        """A message for one player (shown like a pickup)."""
        self.game.notes.setdefault(pid, []).append(text)

    def view(self):
        return HillView(self.phase, self.clock, max(1, self.number), dict(self.clocks), self.owner, self.capper,
                        self.progress, self.contested, self.overtime, dict(self.score), int(self.settings.win_limit),
                        self.winner, {pid for pid, s in self.game.players.items() if s.alive},
                        {pid: s.team for pid, s in self.game.players.items()}, dict(self.waiting), self.spot,
                        self.message, self.message_left)

    def can_buy(self):
        return True

    def sprites(self, clock):
        marker = hill_sprite(self.view(), clock)
        return [marker] if marker else []

    # ------------------------------------------------------------------ rounds

    def new_round(self):
        """Start the next round (or match): everyone back in at their team's spawn points with what a new player
        carries, both clocks full, the point neutral and locked."""
        game, settings = self.game, self.settings
        if self.new_match:
            self.score = {RED: 0, BLU: 0}
            self.new_match = False
        self.number += 1
        game.spawns.restart()
        for state in [s for _, s in sorted(game.players.items())]:
            game.respawn(state, body=game.spawns.body(game.world, state.team))
            state.alive = True
        self.waiting = {}
        self.clocks = {RED: settings.hill_time, BLU: settings.hill_time}
        self.owner = self.capper = self.winner = 0
        self.progress = 0.0
        self.contested = self.overtime = False
        if settings.unlock_time > 0:
            self.phase, self.clock = "setup", settings.unlock_time
        else:
            self.phase, self.clock = "live", 0.0

    def win(self, team):
        """`team` held the point until its clock ran out: score it and pause before the next round (or match)."""
        self.score[team] += 1
        self.winner = team
        text = f"{KOTH_NAMES[team]} wins the round"
        if self.score[team] >= self.settings.win_limit:
            self.new_match = True
            text = f"{KOTH_NAMES[team]} wins the match {self.score[team]}-{self.score[other_team(team)]}"
        self.say(text, self.settings.round_end_time)
        self.phase, self.clock = "over", self.settings.round_end_time
        self.capper, self.progress, self.contested, self.overtime = 0, 0.0, False, False

    def capture(self, team):
        """`team` completed a capture: the point is theirs, their clock runs (with the capture bonus) and the other
        team's stops."""
        settings = self.settings
        self.owner, self.capper, self.progress, self.overtime = team, 0, 0.0, False
        self.clocks[team] = min(settings.hill_time, self.clocks[team] + settings.capture_bonus)
        self.say(f"{KOTH_NAMES[team]} captured the point")

    def on_point(self):
        """{team: how many of its players (not waiting to respawn) stand on the point}."""
        counts = {RED: 0, BLU: 0}
        for state in self.game.players.values():
            if state.alive and state.team in counts and on_hill(self.game.level, state.body):
                counts[state.team] += 1
        return counts

    def contest(self, on, dt):
        """Move the capture progress for one step, from who stands on the point."""
        settings = self.settings
        present = [team for team in TEAMS if on[team]]
        self.contested = len(present) == 2
        if self.contested:
            pass                                        # (blocked: nobody's progress moves)
        elif present:
            team = present[0]
            step = capture_rate(on[team], settings.capture_time) * dt
            if team == self.owner or (self.capper not in (0, team) and self.progress > 0):
                self.progress -= step                   # pushing the other team's progress back
            else:
                self.capper = team
                self.progress += step
                if self.progress >= 1.0:
                    self.capture(team)
                    return
        else:
            self.progress -= dt / settings.decay_time * (OVERTIME_DECAY if self.overtime else 1.0)
        if self.progress <= 0.0:
            self.progress, self.capper = 0.0, 0

    def update(self, dt):
        self.message_left = max(0.0, self.message_left - dt)
        self.respawn_waiting(dt)
        if self.phase == "setup":
            self.clock -= dt
            if self.clock <= 0:
                self.phase, self.clock = "live", 0.0
                self.say("The point is unlocked")
        elif self.phase == "live":
            on = self.on_point()
            self.contest(on, dt)
            if self.owner:
                self.clocks[self.owner] = max(0.0, self.clocks[self.owner] - dt)
                if self.clocks[self.owner] <= 0.0:
                    enemy = other_team(self.owner)
                    if self.progress > 0 or on[enemy]:
                        if not self.overtime:
                            self.say("Overtime!")
                        self.overtime = True
                    else:
                        self.win(self.owner)
        elif self.phase == "over":
            self.clock -= dt
            if self.clock <= 0:
                self.new_round()

    # ------------------------------------------------------------------ players

    def respawn_waiting(self, dt):
        game = self.game
        for pid in sorted(self.waiting):
            self.waiting[pid] -= dt
            if self.waiting[pid] <= 0:
                del self.waiting[pid]
                state = game.players.get(pid)
                if state is not None:
                    game.respawn(state)
                    state.alive = True

    def act(self, pid, wish, dt):
        """The Inputs a player may use this step: only looking around while waiting to respawn, and no shooting for
        the losers of a round until the next one."""
        from game import Inputs                         # (game imports this module)
        state = self.game.players[pid]
        if not state.alive:
            return Inputs(turn=wish.turn, tilt=wish.tilt)
        if self.phase == "over" and state.team != self.winner and wish.fire:
            return replace(wish, fire=False)
        return wish

    def killed(self, pid):
        """A player was knocked out: they wait the respawn time (out of the game meanwhile), then come back at their
        team's spawn points."""
        state = self.game.players[pid]
        if self.settings.respawn_time <= 0:
            self.game.respawn(state)
            return
        state.alive = False
        self.waiting[pid] = self.settings.respawn_time

    def joined(self, pid):
        state = self.game.players[pid]
        state.alive = True
        if state.team in KOTH_NAMES:
            self.note(pid, f"You are on {KOTH_NAMES[state.team]}: capture the point and hold it")

    def left(self, pid):
        self.waiting.pop(pid, None)

    def after_leaving(self):
        pass

