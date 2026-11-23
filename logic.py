"""Zombies' triggers: what the map makes happen when something happens. No pygame.

Things that happen are events, plain names: "game_start", "round_start", "used:<interact>" (a player used an interact
point), "picked:<item>" (picked up, or bought, an item: mapfile.pickup_name), "door:<door>" (a door opened),
"counter:<counter>" (a counter changed), and any name an "event" action fires. Each of the map's triggers
(mapfile.Trigger) waiting for an event runs its actions, in order, when every one of its conditions holds. Counters
(mapfile.Counter) are numbers kept through a game that actions change and conditions test.

Logic belongs to a zombies.ZombieRound, and works through it: its doors, its enemies, its messages. Events set off by
actions are handled at once (an action can open a door whose opening sets off another trigger), but no deeper than
MAX_DEPTH and no more than MAX_PER_STEP in one step of the game, so triggers that set each other off cannot hang it.
"""
from mapfile import MAX_MONEY

MAX_DEPTH = 16                  # events set off by events set off by ... at most this deep
MAX_PER_STEP = 256              # triggers run in one step of the game at most


class Logic:
    def __init__(self, round_):
        self.round = round_
        self.reset()

    @property
    def game(self):
        return self.round.game

    @property
    def level(self):
        return self.round.game.level

    def reset(self):
        """A new game: the counters at their start, every trigger and interact point ready again."""
        self.counters = {c.name: c.start for c in self.level.counters}
        self.done = set()                       # indices of the once-only triggers that have run
        self.used = set()                       # indices of the once-only interact points that have been used
        self.depth = 0
        self.ran = 0                            # triggers run this step

    def step(self):
        self.ran = 0

    # ------------------------------------------------------------------ events

    def fire(self, event, pid=None):
        """`event` happened (set off by player `pid`, if anyone): run every trigger waiting for it whose conditions
        all hold."""
        if not event or self.depth >= MAX_DEPTH:
            return
        self.depth += 1
        try:
            for i, trigger in enumerate(self.level.triggers):
                if trigger.on != event or (trigger.once and i in self.done) or self.ran >= MAX_PER_STEP:
                    continue
                if all(self.holds(c, pid) for c in trigger.conditions):
                    self.ran += 1
                    if trigger.once:
                        self.done.add(i)
                    for action in trigger.actions:
                        self.run(action, pid)
        finally:
            self.depth -= 1

    def holds(self, condition, pid):
        kind, name, amount = condition.kind, condition.name, condition.amount
        if kind == "counter_at_least":
            return self.counters.get(name, 0.0) >= amount
        if kind == "counter_below":
            return self.counters.get(name, 0.0) < amount
        if kind == "round_at_least":
            return self.round.number >= amount
        if kind == "player_has":
            state = self.game.players.get(pid)
            return state is not None and state.inventory.count(name) >= amount
        if kind == "team_has":
            return sum(s.inventory.count(name) for s in self.game.players.values() if s.alive) >= amount
        if kind in ("door_open", "door_closed"):
            index = next((i for i, d in enumerate(self.level.doors) if d.name == name), None)
            return index is not None and self.round.doors[index] == (kind == "door_open")
        return False

    # ------------------------------------------------------------------ actions

    def who(self, action, pid):
        """The players an action gives to (or takes from): the one who set it off, or everyone."""
        players = self.game.players
        if action.who == "everyone":
            return list(players.values())
        return [players[pid]] if pid in players else []

    def run(self, action, pid):
        kind, name, amount = action.kind, action.name, action.amount
        if kind in ("open_door", "close_door"):
            index = next((i for i, d in enumerate(self.level.doors) if d.name == name), None)
            if index is not None:
                self.round.open_door(index, kind == "open_door", pid)
        elif kind in ("add_counter", "set_counter"):
            self.set_counter(name, (self.counters.get(name, 0.0) if kind == "add_counter" else 0.0) + amount, pid)
        elif kind == "give_money":
            for state in self.who(action, pid):
                state.stats.money = max(0.0, min(MAX_MONEY, state.stats.money + amount))
        elif kind == "give_score":
            for state in self.who(action, pid):
                state.stats.score += amount
        elif kind in ("give_item", "take_item"):
            count = int(amount) if kind == "give_item" else -int(amount)
            for state in self.who(action, pid):
                give_item(state.inventory, name, count)
        elif kind == "message":
            if action.who == "everyone" or pid is None:
                self.round.say(action.text)
            else:
                self.game.notes.setdefault(pid, []).append(action.text)
        elif kind in ("effect", "light"):
            spot = self.spot(action, pid)
            if spot is not None and name:
                if kind == "effect":
                    self.game.fx.append((name, *spot, 0.0, 0.0, 1.0))
                else:
                    self.game.flashes.append((name, *spot))
        elif kind == "spawn_enemies":
            self.round.send_enemies(max(0, int(amount)), name)
        elif kind == "event":
            self.fire(name, pid)
        elif kind == "win":
            self.round.win(action.text or "You made it!")

    def set_counter(self, name, value, pid=None):
        if self.counters.get(name) != value:
            self.counters[name] = value
            self.fire(f"counter:{name}", pid)

    def spot(self, action, pid):
        """Where an effect or light action plays: at its interact point, else at the player who set it off."""
        interact = self.level.interact_named(action.at) if action.at else None
        if interact is not None:
            world = self.game.world
            return interact.x, interact.y, world.floor_of(interact.span, interact.x, interact.y) + interact.size / 2
        state = self.game.players.get(pid)
        return None if state is None else (state.body.x, state.body.y, state.body.z + state.body.height / 2)


def give_item(inventory, name, count):
    """Add `count` of an item to an inventory, or take -count away (never below none)."""
    if count > 0:
        inventory.add_item(name, count)
    elif count < 0 and name in inventory.items:
        left = inventory.items[name] + count
        if left > 0:
            inventory.items[name] = left
        else:
            del inventory.items[name]
