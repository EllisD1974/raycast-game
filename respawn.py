"""Waiting to come back in the modes without rounds (free for all, two teams, co-op), on maps with a respawn delay.

No pygame. Respawns stands in for Game.round (like bomb.Round and koth.HillRound) while the map's respawn_delay is
above 0: a knocked-out player is out of the game for that long (not drawn, hit or moved, but able to look around and
watch others through the death camera), then comes back at the next spawn point. Without a delay there is no round
and players come straight back, as before."""
from dataclasses import dataclass, field

RESPAWN_MODES = ("ffa", "teams", "coop")        # the modes the map's respawn_delay applies to


@dataclass
class RespawnView:
    """Who is waiting to come back, and for how long. Made by the host (Respawns.view) and sent to joiners."""
    mode = "respawn"
    alive: set = field(default_factory=set)         # ids of the players not waiting to respawn
    teams: dict = field(default_factory=dict)       # player id -> team
    respawns: dict = field(default_factory=dict)    # player id -> seconds until they come back
    can_buy: bool = True

    def may_move(self, pid, body, use, level):
        """Whether a player may move this step: anyone who is not waiting to respawn."""
        return pid in self.alive

    def to_dict(self):
        return {"mode": self.mode, "alive": sorted(self.alive),
                "respawns": [[pid, round(left, 2)] for pid, left in sorted(self.respawns.items())]}

    @classmethod
    def from_dict(cls, data, teams=None):
        """The view in a snapshot; None if it is not one (it came off the network)."""
        try:
            return cls({int(p) for p in data["alive"]}, dict(teams or {}),
                       {int(pid): float(left) for pid, left in data["respawns"]})
        except (KeyError, IndexError, TypeError, ValueError):
            return None


class Respawns:
    """The waiting players of one game (see the module's description)."""

    def __init__(self, game):
        self.game = game
        self.waiting = {}                       # player id -> seconds until they come back

    def view(self):
        players = self.game.players
        return RespawnView({pid for pid, s in players.items() if s.alive}, {pid: s.team for pid, s in players.items()},
                           dict(self.waiting))

    def can_buy(self):
        return True

    def sprites(self, clock):
        return []

    def update(self, dt):
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
        """The Inputs a player may use this step: only looking around while waiting to respawn."""
        from game import Inputs                         # (game imports this module)
        if not self.game.players[pid].alive:
            return Inputs(turn=wish.turn, tilt=wish.tilt)
        return wish

    def killed(self, pid):
        """A player was knocked out: out of the game for the map's respawn delay, then back at the next spawn point."""
        self.game.players[pid].alive = False
        self.waiting[pid] = self.game.level.settings.respawn_delay

    def joined(self, pid):
        self.game.players[pid].alive = True

    def left(self, pid):
        self.waiting.pop(pid, None)

    def after_leaving(self):
        pass
