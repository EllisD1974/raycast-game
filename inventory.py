"""The player's inventory: things picked up and kept, and the guns they can equip and fire.

No pygame. main.py feeds it the trigger and reload buttons each frame and turns what it reports into
projectiles (projectiles.py) and HUD text (hud.py).
"""
from dataclasses import dataclass, field

from mapfile import Gun


@dataclass
class GunState:
    """One gun the player owns: its definition, its magazine and its timers. Spare rounds are not
    kept here: they are the inventory's pool for the gun's ammo type, shared by every gun that uses it."""
    gun: Gun
    mag: int = 0                 # rounds ready to fire
    cooldown: float = 0.0        # seconds until the next shot is allowed
    reload_left: float = 0.0     # seconds left of a reload in progress (0 when not reloading)
    trigger_was_down: bool = False
    inventory: object = field(default=None, repr=False)      # whose pool of spare rounds this draws on

    @property
    def reserve(self):
        """Spare rounds of this gun's ammo type (shared with other guns of the type)."""
        return 0 if self.inventory is None else self.inventory.ammo.get(self.gun.ammo, 0)

    @reserve.setter
    def reserve(self, rounds):
        if self.inventory is not None:
            self.inventory.ammo[self.gun.ammo] = max(0, int(rounds))

    @property
    def reloading(self):
        return self.reload_left > 0.0


@dataclass
class Inventory:
    items: dict = field(default_factory=dict)       # name -> how many
    guns: list = field(default_factory=list)         # GunState, in the order they were picked up
    equipped: int = None                             # index in `guns` of the gun in the player's hands
    ammo: dict = field(default_factory=dict)         # spare rounds per ammo type name (shared by guns)

    # ------------------------------------------------------------------ what is carried

    def add_item(self, name, count=1):
        name = (name or "Item").strip() or "Item"
        self.items[name] = self.items.get(name, 0) + max(0, int(count))
        return self.items[name]

    def count(self, name):
        return self.items.get(name, 0)

    def find_gun(self, name):
        for state in self.guns:
            if state.gun.name == name:
                return state
        return None

    def give_gun(self, gun):
        """Pick up a gun. A new one comes loaded, with its starting spare rounds added to its ammo type's
        pool, and is equipped if nothing is; one already owned just adds the starting rounds again."""
        state = self.find_gun(gun.name)
        if state is not None:
            self.add_ammo(gun.ammo, gun.start_ammo)
            return state
        state = GunState(gun, mag=gun.capacity, inventory=self)
        self.add_ammo(gun.ammo, gun.start_ammo)
        self.guns.append(state)
        if self.equipped is None:
            self.equipped = len(self.guns) - 1
        return state

    def add_ammo(self, ammo_name, rounds):
        """Spare rounds of an ammo type, usable by every gun that fires it, whether the player has one yet or
        not. Returns whether they have a gun that uses it."""
        self.ammo[ammo_name] = self.ammo.get(ammo_name, 0) + max(0, int(rounds))
        return any(state.gun.ammo == ammo_name for state in self.guns)

    # ------------------------------------------------------------------ the gun in hand

    def current(self):
        if self.equipped is None or not 0 <= self.equipped < len(self.guns):
            return None
        return self.guns[self.equipped]

    def equip(self, index):
        """Take out the gun in slot `index` (0 based); asking for the one already out puts it away.
        Switching cancels a reload. Returns True if the slot exists."""
        if not 0 <= index < len(self.guns):
            return False
        current = self.current()
        if current is not None:
            current.reload_left = 0.0
            current.trigger_was_down = False
        self.equipped = None if self.equipped == index else index
        return True

    def cycle(self, step):
        """Wheel through the guns (and the empty hands) one slot at a time."""
        if not self.guns:
            return
        order = [None] + list(range(len(self.guns)))
        here = order.index(self.equipped) if self.equipped in order else 0
        nxt = order[(here + step) % len(order)]
        current = self.current()
        if current is not None:
            current.reload_left = 0.0
        self.equipped = nxt

    def start_reload(self):
        state = self.current()
        if state is None or state.reloading:
            return False
        if state.mag >= state.gun.capacity or state.reserve <= 0:
            return False
        state.reload_left = max(state.gun.reload_time, 1e-6)
        return True

    def update(self, dt, trigger, reload_pressed=False):
        """Advance dt seconds. `trigger` is whether the fire button is held. Returns the list of Gun
        definitions fired this tick (one per round; usually zero or one)."""
        fired = []
        for state in self.guns:                      # guns in the bag still count down their timers
            state.cooldown = max(0.0, state.cooldown - dt)
        state = self.current()
        if state is None:
            return fired
        gun = state.gun
        if state.reloading:
            state.reload_left -= dt
            if state.reload_left <= 0.0:
                state.reload_left = 0.0
                take = min(gun.capacity - state.mag, state.reserve)
                state.mag += take
                state.reserve -= take
            state.trigger_was_down = trigger
            return fired
        if reload_pressed:
            self.start_reload()
            state.trigger_was_down = trigger
            return fired
        wants = trigger and (gun.mode == "auto" or not state.trigger_was_down)
        state.trigger_was_down = trigger
        if wants and state.cooldown <= 0.0:
            if state.mag > 0:
                state.mag -= 1
                state.cooldown = 1.0 / gun.fire_rate
                fired.append(gun)
                if state.mag == 0 or gun.mode == "single":
                    self.start_reload()              # a single shot gun reloads after every round
            else:
                self.start_reload()                  # pulling the trigger on an empty gun reloads it
        return fired
