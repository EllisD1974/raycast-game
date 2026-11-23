"""Map data and file format, shared by the game (main.py) and the editor (map_editor.py).

A map is a set of same-sized grids ("layers"), one value per cell. A map has one or more
*floors*, named by you ("Ground", "Mezzanine", ...), stacked from the bottom up. Floor 0 (the
ground floor) is open in every cell that is not a wall. Every higher floor exists only in the
cells where you give it a room; between two floors lies solid material (the floor slab).

    walls         tile id of a solid wall; 0 = open space. Which floors of the cell it fills is
                  up to wall_floors (or, for older walls, wall_floor).
    wall_h        height of that wall above the lowest floor beside it; 0 = full height, up to
                  the ceiling. A positive height shorter than the room makes a short wall you can
                  see over. Like walls, it is shared by every floor.
    wall_floor    the lowest floor the wall reaches. Only a wall from the ground floor can be short
                  or see-through.
    wall_floors   the floors the wall fills, as bits (bit N: floor N), so a wall painted on floor 1
                  stands from floor 1's floor up to floor 2's floor and leaves floor 2 free for a
                  room over it. 0 (walls from older maps) = floor wall_floor and every floor above
                  it. A wall painted in the editor fills only the floor being edited; painting the
                  same cell on another floor adds that floor.
    wall_ceil     the ceiling over a wall that is not full height (a short or see-through wall);
                  0 = automatic: the highest ceiling of the open cells beside it.

    per floor (floor 0's grids have plain names; floor N's names end in N + 1, e.g. floor_h2):
    floor_h       floor height
    ceil_h        ceiling height
    floor_tex     tile id of the floor (also the riser of steps up to it)
    ceil_tex      tile id of the ceiling (also the drop where a ceiling gets lower)
    ramp          0 = none, else the direction the floor rises: 1 east, 2 west, 3 south, 4 north
    site          0 = none, else the bomb site the floor belongs to (bomb defusal): 1 A, 2 B. The bomb can be
                  planted standing on it. 3 (HILL_SITE): the capture point of King of the Hill. 4 / 5
                  (BARRIER_SITES, ground floor only): a barrier only team 1 / team 2, and its bullets, get through
                  (spawn protection; see world.World).

Entities (items in the world) are not a grid: the level keeps a list of them, each with a position,
the floor it stands on, a sprite tile, what happens when the player touches it and how it behaves
afterwards (see Entity). They are saved under "entities" in the map file.

A higher floor has a room in a cell where its ceil_h > floor_h (the default 0 / 0 means none).
Floors must be in height order: where several floors have a room in the same cell, each floor
must start at or above the ceiling of the one below it.
Tile ids are 1-based atlas positions, read row by row (id 1 is the top-left tile).

Ramps: a run of ramp cells in a row slopes smoothly from the floor height of the cell just
before the run to the floor height of the cell just after it, whatever its length. A ramp that
climbs to a higher floor ends in a cell whose *lower* floor is raised to that height; that cell
touches a neighboring cell's room on the higher floor, which is how you step across.
"""
import json
import math
import os
from dataclasses import asdict, dataclass, field, replace

from constants import PLAYER_HEIGHT

MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maps", "map.json")
FORMAT_VERSION = 7
MAX_NAME_LENGTH = 24
MIN_WALL_GAP = 0.05             # a wall this close to the ceiling is just a full-height wall

SPAN_LAYERS = ("floor_tex", "ceil_tex", "floor_h", "ceil_h", "ramp", "site")
SITE_NAMES = {1: "A", 2: "B", 3: "Hill", 4: "Barrier 1", 5: "Barrier 2"}    # values of the site layer (0: none)
BOMB_SITES = (1, 2)                                             # ... where the bomb can be planted
HILL_SITE = 3                                                   # ... King of the Hill's capture point
BARRIER_SITES = {4: 1, 5: 2}                                    # ... and barriers: value -> the team they let through
SIDES = "nesw"                                                  # the four sides of a cell: north, east, south, west
SIDE_LAYERS = tuple(f"side_{side}" for side in SIDES)           # a wall's own texture on one side (0: the wall's tile)
# The heights above the wall's base that a side's own texture covers, from and to (to 0: up to the top).
SIDE_BAND_LAYERS = tuple(f"side_{side}_{end}" for side in SIDES for end in ("from", "to"))
SHARED_LAYERS = ("walls", "wall_h", "wall_ceil", "wall_floor", "wall_floors") + SIDE_LAYERS + SIDE_BAND_LAYERS  # one grid for all floors
SIDE_VECTORS = {"n": (0, -1), "e": (1, 0), "s": (0, 1), "w": (-1, 0)}  # which way each side faces on the map
WALL_LABELS = {"": "Free standing", "n": "North wall", "e": "East wall", "s": "South wall", "w": "West wall"}
MAX_ELEVATION = 8.0             # furthest a placed item may be raised or lowered from where its settings put it
WALL_GAP = 0.04                 # how far in front of a wall's face an item hung on it is, in cells
EDIT_LAYERS = ("walls",) + SPAN_LAYERS + ("wall_h",)            # what the editor lets you switch between
RAMP_DIRS = {1: (1, 0), 2: (-1, 0), 3: (0, 1), 4: (0, -1)}      # id -> (dx, dy) the floor rises toward
SOLID_OUTSIDE = 1       # walls value reported outside the grid: a wall

_GROUND_DEFAULTS = {"walls": 0, "wall_h": 0.0, "wall_ceil": 0.0, "wall_floor": 0, "wall_floors": 0, "floor_tex": 5, "ceil_tex": 6,
                    "floor_h": 0.0, "ceil_h": 1.0, "ramp": 0, "site": 0, **{name: 0 for name in SIDE_LAYERS},
                    **{name: 0.0 for name in SIDE_BAND_LAYERS}}
_UPPER_DEFAULTS = {"floor_tex": 3, "ceil_tex": 6, "floor_h": 0.0, "ceil_h": 0.0, "ramp": 0, "site": 0}


ENTITY_MODES = ("once", "respawn", "persistent", "scenery")
PREFAB_FIELDS = ("tile", "mode", "effect", "amount", "respawn", "size", "lift", "item", "gun", "ammo", "price",
                 "shown", "emits", "emits_override", "emits_offset_x", "emits_offset_y", "emits_offset_z", "light",
                 "counter")
ENTITY_EFFECTS = ("none", "score", "health", "item", "gun", "ammo", "counter")
MODE_LABELS = {"once": "Pick up once", "respawn": "Respawns", "persistent": "Stays", "scenery": "Scenery"}
EFFECT_LABELS = {"none": "None", "score": "Score", "health": "Health", "item": "Inventory item",
                 "gun": "Give a gun", "ammo": "Give ammo", "counter": "Add to a counter"}
GUN_MODES = ("single", "semi", "auto")
GUN_MODE_LABELS = {"single": "Single shot", "semi": "Semi-auto", "auto": "Full auto"}
SHOT_TYPES = ("single", "multi", "projectile")
SHOT_LABELS = {"single": "Single bullet", "multi": "Multi bullet", "projectile": "Projectile"}
MIN_AMBIENT = 0.02                              # the darkest a map can be made
EFFECT_KINDS = ("burst", "stream")
EFFECT_COLORS = ("original", "hue", "rgb")
EFFECT_COLOR_LABELS = {"original": "Original", "hue": "Hue shift", "rgb": "RGB tint"}
EFFECT_AIMS = ("auto", "custom")
EFFECT_AIM_LABELS = {"auto": "Automatic", "custom": "Custom"}
EFFECT_KIND_LABELS = {"burst": "Burst", "stream": "Stream"}
MAX_HIT_NAMES = 8                               # effects (and lights) an ammo type plays for one kind of hit
MAX_NAME = 24                                   # longest name of an item, gun or particle effect
ANIMATION_KINDS = ("float", "rotate")
ANIMATION_LABELS = {"float": "Float", "rotate": "Rotate"}


MAX_SPAWN_ORDER = 99
T_TEAM, CT_TEAM = 1, 2                          # bomb defusal: team 1 attacks (plants), team 2 defends (defuses)
TEAM_NAMES = {T_TEAM: "T", CT_TEAM: "CT"}
TEAM_TITLES = {T_TEAM: "Terrorists", CT_TEAM: "Counter-Terrorists"}
SPAWN_TEAMS = (0, T_TEAM, CT_TEAM)
SPAWN_TEAM_LABELS = {0: "Any team", T_TEAM: "T", CT_TEAM: "CT"}
ENEMY_SPAWN = 3                                 # a spawner's team for where enemies come in (zombies), never players
SPAWNER_TEAMS = SPAWN_TEAMS + (ENEMY_SPAWN,)
KOTH_NAMES = {T_TEAM: "RED", CT_TEAM: "BLU"}    # King of the Hill: team 1 is RED, team 2 BLU (as in Team Fortress 2)


@dataclass
class Spawner:
    """A place players come into the game at (joining, after being knocked out, after a map reload).

    x, y     position on the map, in cells (the middle of a cell is .5); span is the floor it stands on
    angle    the way a player there faces, radians (0 faces +x)
    order    which spawners are used first: every player comes in at a spawner of the lowest order that has
             one not yet used in this round, picked at random among those; when all have been used the round
             starts over (see game.SpawnOrder). A map without spawners uses its start instead.
    team     0: anyone comes in here; T_TEAM / CT_TEAM: in a mode with teams, only that team's players (and a
             team with no spawn points of its own uses the others); ENEMY_SPAWN: enemies come in here (zombies),
             players never do
    door     zombies: the name of a Door that has to be open before enemies come in here ("" for always), so the
             rooms behind a door only fill with enemies once the players have opened it"""
    x: float
    y: float
    span: int = 0
    angle: float = 0.0
    order: int = 0
    team: int = 0
    door: str = ""

    @classmethod
    def from_dict(cls, data):
        team = data.get("team", 0)
        return cls(float(data["x"]), float(data["y"]), max(0, int(data.get("span", 0))),
                   float(data.get("angle", 0.0)), max(0, min(MAX_SPAWN_ORDER, int(data.get("order", 0)))),
                   team if team in SPAWNER_TEAMS else 0, str(data.get("door", ""))[:MAX_NAME])


DOOR_TILE = 2                                   # the atlas's wood (make_atlas.py): what a door looks like by default
MAX_DOORS = 64
MAX_DOOR_SIZE = 32                              # cells a door may span across or down


@dataclass
class Door:
    """A door in zombies mode: a rectangle of cells (x, y, width by height) that is a wall filling every floor while
    it is closed, stopping players, enemies and bullets alike, and open cells once it is opened. It opens for good
    (until a new game) when a player buys it, pressing the use key (E) beside it, or when a trigger opens it.

    name           what it is called (spawners and triggers name it)
    tile           the atlas tile it is drawn with while closed
    buyable        whether players can open it themselves; if not, only a trigger can
    cost, cost_kind   what opening it costs: money, score, or free
    prompt         what the HUD says it is ("" for "the door")
    tall           how tall it is: 0 for a wall up to the ceiling on every floor of its cells; above 0, a panel that
                   high on the ground floor, which can be seen (not climbed or shot) over
    open_at_start  open when a game starts (a trigger may close it)
    kind           the DoorKind it is placed from ("" for its own settings): its tile, buyable, cost, cost_kind,
                   prompt and tall come from that type

    Doors that touch (side by side or corner to corner) are one door (Level.door_groups): opening one opens them
    all, and the first of them in the map's list says whether players can open it, what it costs and what it is
    called."""
    name: str = "Door"
    x: int = 0
    y: int = 0
    width: int = 1
    height: int = 1
    tile: int = DOOR_TILE
    buyable: bool = True
    cost: float = 750.0
    cost_kind: str = "money"
    prompt: str = ""
    open_at_start: bool = False
    tall: float = 0.0
    kind: str = ""

    def cells(self):
        return [(x, y) for y in range(self.y, self.y + self.height) for x in range(self.x, self.x + self.width)]

    def label(self):
        return self.prompt or "the door"

    @classmethod
    def from_dict(cls, data):
        def size(key):
            value = data.get(key, 1)
            return max(1, min(MAX_DOOR_SIZE, int(value))) if isinstance(value, (int, float)) else 1
        cost = data.get("cost", 750.0)
        return cls(str(data.get("name", ""))[:MAX_NAME] or "Door", max(0, int(data["x"])), max(0, int(data["y"])),
                   size("width"), size("height"), max(0, min(255, int(data.get("tile", DOOR_TILE)))),
                   bool(data.get("buyable", True)),
                   max(0.0, min(1000000.0, float(cost))) if isinstance(cost, (int, float)) else 750.0,
                   data.get("cost_kind") if data.get("cost_kind") in ("free", "money", "score") else "money",
                   str(data.get("prompt", ""))[:MAX_NAME * 2], bool(data.get("open_at_start", False)),
                   read_tall(data.get("tall")), str(data.get("kind", ""))[:MAX_NAME])


MAX_TALL = 8.0                                  # the tallest a door or barricade can be made (0: to the ceiling)


def read_tall(value):
    """A door's or barricade's height from a file: 0 (to the ceiling) up to MAX_TALL."""
    return max(0.0, min(MAX_TALL, float(value))) if isinstance(value, (int, float)) and not isinstance(value, bool) \
        else 0.0


DOOR_KIND_FIELDS = ("tile", "buyable", "cost", "cost_kind", "prompt", "tall")


@dataclass
class DoorKind:
    """A saved door (a type of door): a name and the settings of a Door that are not its place or own name. Doors
    placed from it (Door.kind) take its settings (Level.apply_door_kinds), so changing it changes them all; it can be
    brought into another map with the editor's Import."""
    name: str = "Door"
    tile: int = DOOR_TILE
    buyable: bool = True
    cost: float = 750.0
    cost_kind: str = "money"
    prompt: str = ""
    tall: float = 0.0

    def clone(self):
        return replace(self)

    @classmethod
    def from_door(cls, name, door):
        return cls(name, **{key: getattr(door, key) for key in DOOR_KIND_FIELDS})

    @classmethod
    def from_dict(cls, data):
        settings = Door.from_dict(dict(data, x=0, y=0, name="x"))
        return cls.from_door(str(data.get("name", ""))[:MAX_NAME] or "Door", settings)


ATTACK_KINDS = ("melee",)
ATTACK_KIND_LABELS = {"melee": "Melee (swing / bite)"}
ENEMY_PATHING = ("sticky", "nearest")
ENEMY_PATHING_LABELS = {"sticky": "Nearest player, sticky", "nearest": "Nearest player"}
MAX_ATTACKS = 4                                 # attacks an enemy kind may have
MAX_ENEMIES = 32                                # enemy kinds a map may define
# Enemy and attack numbers: (lowest, highest).
ENEMY_NUMBERS = {"health": (1.0, 100000.0), "speed": (0.1, 12.0), "height": (0.2, 3.0), "radius": (0.1, 1.0),
                 "switch_margin": (0.0, 50.0), "switch_delay": (0.0, 30.0), "kill_reward": (0.0, 1000000.0),
                 "hit_reward": (0.0, 1000000.0), "break_rate": (0.1, 60.0), "max_per_round": (0.0, 10000.0)}
ATTACK_NUMBERS = {"damage": (0.0, 100000.0), "range": (0.05, 10.0), "windup": (0.0, 10.0), "cooldown": (0.0, 60.0)}


def clamped_numbers(cls, data, ranges):
    """{field: value} of `ranges`' fields read from `data`, each held between its (lowest, highest), and the class's
    default where it is missing or not a number."""
    base = cls()
    out = {}
    for key, (low, high) in ranges.items():
        try:
            out[key] = max(low, min(high, float(data.get(key, getattr(base, key)))))
        except (TypeError, ValueError):
            out[key] = getattr(base, key)
    return out


@dataclass
class Attack:
    """One of an enemy's attacks (Enemy.attacks).

    kind      melee: a swing of the arms or a bite at whoever it chases, once they are within `range`
    damage    health it takes off the player it lands on
    range     cells between the enemy's body and the player's (edge to edge) it reaches across
    windup    seconds from starting the attack to it landing: a player who gets out of range by then is missed
    cooldown  seconds after an attack lands (or misses) before the next can start"""
    kind: str = "melee"
    damage: float = 25.0
    range: float = 0.5
    windup: float = 0.4
    cooldown: float = 1.0

    @classmethod
    def from_dict(cls, data):
        return cls(kind=data.get("kind") if data.get("kind") in ATTACK_KINDS else "melee",
                   **clamped_numbers(cls, data, ATTACK_NUMBERS))


DEFAULT_ENEMY_COLOR = (150, 210, 140)           # a sickly green
DEFAULT_ENEMY_SHEET = "zombie"                  # assets/zombie.png (character.sheet_names)


@dataclass
class Enemy:
    """A kind of enemy a map defines (zombies mode). They come in at Spawners of team ENEMY_SPAWN.

    name           what it is called
    health         health in the first round (later rounds multiply it: MapSettings.zombie_health)
    speed          walking speed, cells per second (a player walks at 3)
    height, radius the size of its body: what bullets strike and what has to fit under a ceiling
    attacks        what it does to a player it reaches (Attack); the first that is ready is used
    pathing        who it chases: nearest: whichever standing player is nearest along the way, at every moment;
                   sticky: the same, but it keeps chasing the one it has unless another is nearer by more than
                   switch_margin cells for switch_delay seconds (two players walking past each other do not
                   make it turn back and forth)
    kill_reward, hit_reward   money for the player who kills it, and for each bullet or blast of theirs that hurts it
    break_rate     seconds it takes to tear one board off a barricade
    color          [red, green, blue] 0-255 its picture is tinted with (white: as drawn)
    sheet          the sprite sheet it is drawn from: the name of a picture in assets/ laid out like character.png
                   (character.sheet_names), or "" for the players' own character in a green shirt
    weight         a curve (see curve_at) of round -> how likely each enemy coming in is to be this kind, against the
                   other kinds' weights that round: 0 for none (a tough kind can start at 0 and only rise later)
    max_per_round  at most this many of it in one round (0: no limit)
    in_waves       whether the rounds send it (by its weight); if not, it only comes when a trigger sends it
                   ("Send enemies now"), as a boss or an ambush does"""
    name: str = "Zombie"
    health: float = 100.0
    speed: float = 1.8
    height: float = 0.8
    radius: float = 0.25
    attacks: list = field(default_factory=lambda: [Attack()])
    pathing: str = "sticky"
    switch_margin: float = 3.0
    switch_delay: float = 1.5
    kill_reward: float = 60.0
    hit_reward: float = 10.0
    break_rate: float = 1.0
    color: list = field(default_factory=lambda: list(DEFAULT_ENEMY_COLOR))
    sheet: str = DEFAULT_ENEMY_SHEET
    weight: list = field(default_factory=lambda: [[1, 1.0]])
    max_per_round: float = 0.0
    in_waves: bool = True

    def clone(self):
        return replace(self, attacks=[replace(a) for a in self.attacks], color=list(self.color),
                       weight=[list(p) for p in self.weight])

    @classmethod
    def from_dict(cls, data):
        attacks, color = data.get("attacks"), data.get("color")
        good_color = (isinstance(color, list) and len(color) == 3
                      and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in color))
        return cls(name=str(data.get("name", ""))[:MAX_NAME] or "Zombie",
                   attacks=[Attack.from_dict(a) for a in attacks if isinstance(a, dict)][:MAX_ATTACKS]
                   if isinstance(attacks, list) else [Attack()],
                   pathing=data.get("pathing") if data.get("pathing") in ENEMY_PATHING else "sticky",
                   color=[max(0, min(255, int(c))) for c in color] if good_color else list(DEFAULT_ENEMY_COLOR),
                   sheet=str(data.get("sheet", DEFAULT_ENEMY_SHEET))[:MAX_NAME],
                   weight=read_curve(data.get("weight"), [[1, 1.0]], *CURVE_LIMITS["weight"]),
                   in_waves=bool(data.get("in_waves", True)),
                   **clamped_numbers(cls, data, ENEMY_NUMBERS))


# --------------------------------------------------------------------------- zombies: interact points and triggers

MAX_INTERACTS = 64
MAX_TRIGGERS = 128
MAX_COUNTERS = 32
MAX_CONDITIONS = 8
MAX_ACTIONS = 16
MAX_TEXT = 60                                   # characters in a trigger's message or an event's name


def text_field(data, key, default="", length=MAX_NAME):
    value = data.get(key, default)
    return str(value)[:length] if isinstance(value, (str, int, float)) and not isinstance(value, bool) else default


def number_field(data, key, default, low, high):
    value = data.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return default
    return max(low, min(high, float(value)))


@dataclass
class Interact:
    """A place in zombies mode a player uses by pressing the use key (E) beside it: a button, a lever, a generator.
    Using it fires the event "used:<name>" for triggers (see Trigger).

    x, y, span    where it is (the middle of a cell, on floor span)
    prompt        what the HUD calls it ("Press E to <prompt>"; "" for "use <name>")
    cost, cost_kind   what using it costs: money, score, or free
    needs, needs_amount   an inventory item the player must carry that many of to use it ("" for none) ...
    consume       ... taken from them when they do
    once          it can be used once a game (it then disappears)
    tile, size    the atlas tile it is drawn with (-1 for nothing), and how big, in cells"""
    name: str = "Button"
    x: float = 0.5
    y: float = 0.5
    span: int = 0
    prompt: str = ""
    cost: float = 0.0
    cost_kind: str = "free"
    needs: str = ""
    needs_amount: float = 1.0
    consume: bool = True
    once: bool = False
    tile: int = -1
    size: float = 0.5

    def label(self):
        return self.prompt or f"use {self.name}"

    @classmethod
    def from_dict(cls, data):
        return cls(text_field(data, "name", "Button") or "Button", float(data["x"]), float(data["y"]),
                   max(0, int(data.get("span", 0))), text_field(data, "prompt", "", MAX_TEXT),
                   number_field(data, "cost", 0.0, 0.0, 1000000.0),
                   data.get("cost_kind") if data.get("cost_kind") in ("free", "money", "score") else "free",
                   text_field(data, "needs"), number_field(data, "needs_amount", 1.0, 1.0, 1000.0),
                   bool(data.get("consume", True)), bool(data.get("once", False)),
                   int(number_field(data, "tile", -1, -1, 255)), number_field(data, "size", 0.5, 0.1, 3.0))


@dataclass
class Counter:
    """A number zombies mode keeps through a game, that triggers add to and test (fuses found, switches on).

    start      what it is when a game starts
    goal       what it is counting up to (0: none), shown as "label 2/4"
    show       whether the HUD shows it
    label      what the HUD calls it ("" for its name)"""
    name: str = "Counter"
    start: float = 0.0
    goal: float = 0.0
    show: bool = True
    label: str = ""

    @classmethod
    def from_dict(cls, data):
        return cls(text_field(data, "name", "Counter") or "Counter", number_field(data, "start", 0.0, -1e6, 1e6),
                   number_field(data, "goal", 0.0, 0.0, 1e6), bool(data.get("show", True)),
                   text_field(data, "label", "", MAX_TEXT))


CONDITION_KINDS = ("counter_at_least", "counter_below", "round_at_least", "player_has", "team_has", "door_open",
                   "door_closed")
CONDITION_LABELS = {"counter_at_least": "Counter at least", "counter_below": "Counter below",
                    "round_at_least": "Round at least", "player_has": "The player carries",
                    "team_has": "The team carries", "door_open": "Door open", "door_closed": "Door closed"}


@dataclass
class Condition:
    """One of a trigger's conditions: kind (CONDITION_KINDS) about `name` (a counter, an inventory item or a door)
    and `amount` (the number reached, round, or how many of the item)."""
    kind: str = "counter_at_least"
    name: str = ""
    amount: float = 1.0

    @classmethod
    def from_dict(cls, data):
        return cls(data.get("kind") if data.get("kind") in CONDITION_KINDS else "counter_at_least",
                   text_field(data, "name"), number_field(data, "amount", 1.0, -1e6, 1e6))


ACTION_KINDS = ("open_door", "close_door", "add_counter", "set_counter", "give_money", "give_score", "give_item",
                "take_item", "message", "effect", "light", "spawn_enemies", "event", "win")
ACTION_LABELS = {"open_door": "Open a door", "close_door": "Close a door", "add_counter": "Add to a counter",
                 "set_counter": "Set a counter", "give_money": "Give money", "give_score": "Give score",
                 "give_item": "Give an item", "take_item": "Take an item", "message": "Show a message",
                 "effect": "Play an effect", "light": "Flash a light", "spawn_enemies": "Send enemies now",
                 "event": "Fire an event", "win": "Win the game"}
ACTION_WHO = ("player", "everyone")
ACTION_WHO_LABELS = {"player": "The player who set it off", "everyone": "Everyone"}


@dataclass
class Action:
    """One of a trigger's actions (ACTION_KINDS): `name` is the door, counter, item, effect, light, kind of enemy
    ("" any) or event it is about; `amount` how much (negative takes away); `text` a message (or the winning one);
    `who` gets it: the player who set the trigger off, or everyone; `at` is the interact point an effect or light
    plays at ("" for where the player is)."""
    kind: str = "message"
    name: str = ""
    amount: float = 1.0
    text: str = ""
    who: str = "player"
    at: str = ""

    @classmethod
    def from_dict(cls, data):
        return cls(data.get("kind") if data.get("kind") in ACTION_KINDS else "message", text_field(data, "name"),
                   number_field(data, "amount", 1.0, -1e6, 1e6), text_field(data, "text", "", MAX_TEXT),
                   data.get("who") if data.get("who") in ACTION_WHO else "player", text_field(data, "at"))


@dataclass
class Trigger:
    """When the event `on` happens and every condition holds, run the actions in order (zombies mode). Events:
    "game_start", "round_start", "used:<interact>", "picked:<item>", "door:<door>" (opened), "counter:<counter>"
    (changed), or any name an "event" action fires. `once`: only the first time in a game."""
    name: str = "Trigger"
    on: str = "game_start"
    conditions: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    once: bool = False

    def clone(self):
        return replace(self, conditions=[replace(c) for c in self.conditions],
                       actions=[replace(a) for a in self.actions])

    @classmethod
    def from_dict(cls, data):
        conditions, actions = data.get("conditions"), data.get("actions")
        return cls(text_field(data, "name", "Trigger") or "Trigger", text_field(data, "on", "game_start", MAX_TEXT),
                   [Condition.from_dict(c) for c in conditions if isinstance(c, dict)][:MAX_CONDITIONS]
                   if isinstance(conditions, list) else [],
                   [Action.from_dict(a) for a in actions if isinstance(a, dict)][:MAX_ACTIONS]
                   if isinstance(actions, list) else [],
                   bool(data.get("once", False)))


def pickup_name(entity):
    """The name an item's pickup event is about ("picked:<name>"): its inventory item, else its prefab or own name."""
    if entity.effect == "item" and entity.item:
        return entity.item
    return entity.prefab or entity.name


REWARD_KINDS = ("money", "score")
REWARD_KIND_LABELS = {"money": "Money", "score": "Score"}
BARRICADE_TILE = 2                              # the atlas's wood (make_atlas.py): what boards look like by default
MAX_BARRICADE_BOARDS = 20
MAX_BARRICADE_STAGES = 12
BARRICADE_NUMBERS = {"repair_time": (0.1, 30.0), "reward": (0.0, 1000000.0), "reward_cap": (0.0, 1000000.0)}


@dataclass
class Barricade:
    """A boarded-up opening in zombies mode: an open ground floor cell (x, y) that players can never walk through
    and enemies only once every board is torn off. Enemies coming that way stop to tear the boards off; players
    rebuild them by holding the use key (E) beside it. Bullets and blasts go through it.

    Barricades in cells that touch (side by side or corner to corner) are one barricade (Level.barricade_groups): torn down and rebuilt together,
    with the boards, rebuild time and reward of the first of them in the map's list; each cell shows its own
    pictures for how far the whole is torn down.

    boards       how many boards it has when whole
    repair_time  seconds of holding E to put one board back
    reward, reward_kind   what each board put back earns (money or score) ...
    reward_cap   ... up to this much per player per round (so a window cannot be farmed)
    tile         the atlas tile the boards are drawn with when it has no stages: a pane as tall as the share of
                 boards left
    stages       atlas tiles it is drawn with as it is torn down, whole first and most damaged last, each filling
                 the opening (give them transparent pixels where boards are missing, to see through the gaps).
                 The share of boards gone picks the stage (see stage_tile); it can only be walked through once
                 every board is gone, whatever the picture shows
    tall         how tall its boards are: 0 for up to the ceiling; above 0, that high (seen over, never climbed)"""
    x: int = 0
    y: int = 0
    boards: int = 6
    repair_time: float = 1.0
    reward: float = 10.0
    reward_kind: str = "money"
    reward_cap: float = 100.0
    tile: int = BARRICADE_TILE
    stages: list = field(default_factory=list)
    kind: str = ""                              # the BarricadeKind it is placed from ("" for its own settings)
    tall: float = 0.0

    def stage_tile(self, left, boards=None):
        """The tile it shows with `left` of `boards` (its own, unless given: a group's) on, left above 0: with stages,
        the one for the share of boards torn off (all on: the first; one left: the last); without, its tile."""
        if not self.stages:
            return self.tile
        boards = max(1, self.boards if boards is None else boards)
        gone = max(0, boards - left)
        return self.stages[min(len(self.stages) - 1, gone * len(self.stages) // boards)]

    @classmethod
    def from_dict(cls, data):
        stages = data.get("stages")
        return cls(max(0, int(data["x"])), max(0, int(data["y"])),
                   boards=max(1, min(MAX_BARRICADE_BOARDS, int(data.get("boards", 6)))),
                   reward_kind=data.get("reward_kind") if data.get("reward_kind") in REWARD_KINDS else "money",
                   tile=max(0, min(255, int(data.get("tile", BARRICADE_TILE)))),
                   stages=read_stages(data.get("stages")), kind=str(data.get("kind", ""))[:MAX_NAME],
                   tall=read_tall(data.get("tall")),
                   **clamped_numbers(cls, data, BARRICADE_NUMBERS))


def read_stages(stages):
    """A barricade's stage tiles from a file: atlas tile indices, at most MAX_BARRICADE_STAGES."""
    if not isinstance(stages, list):
        return []
    return [max(0, min(255, int(t))) for t in stages
            if isinstance(t, (int, float)) and not isinstance(t, bool)][:MAX_BARRICADE_STAGES]


BARRICADE_KIND_FIELDS = ("boards", "repair_time", "reward", "reward_kind", "reward_cap", "tile", "stages", "tall")


@dataclass
class BarricadeKind:
    """A saved barricade (a type of barricade): a name and every setting of a Barricade but its place. Barricades
    placed from it (Barricade.kind) take its settings (Level.apply_barricade_kinds), so changing it changes them
    all; it can be brought into another map with the editor's Import."""
    name: str = "Barricade"
    boards: int = 6
    repair_time: float = 1.0
    reward: float = 10.0
    reward_kind: str = "money"
    reward_cap: float = 100.0
    tile: int = BARRICADE_TILE
    stages: list = field(default_factory=list)
    tall: float = 0.0

    def clone(self):
        return replace(self, stages=list(self.stages))

    @classmethod
    def from_barricade(cls, name, barricade):
        return cls(name, **{key: getattr(barricade, key) for key in BARRICADE_KIND_FIELDS}).clone()

    @classmethod
    def from_dict(cls, data):
        settings = Barricade.from_dict(dict(data, x=0, y=0))
        return cls.from_barricade(str(data.get("name", ""))[:MAX_NAME] or "Barricade", settings)


MAX_CURVE_POINTS = 24
MAX_CURVE_X = 999                               # the last round a curve's point can be at


def curve_at(points, x):
    """The value of a curve at `x`: points are [x, value] pairs in rising order of x, joined by straight lines;
    before the first point it is the first value, after the last it carries on along the last line (or stays level
    with only one point). Never below 0."""
    if not points:
        return 0.0
    if x <= points[0][0] or len(points) == 1:
        return max(0.0, float(points[0][1] if x <= points[0][0] else points[-1][1]))
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return max(0.0, y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    (x0, y0), (x1, y1) = points[-2], points[-1]
    return max(0.0, y1 + (y1 - y0) * (x - x1) / (x1 - x0))


def read_curve(data, default, low, high, max_x=MAX_CURVE_X):
    """A curve (see curve_at) from a file: [x, value] pairs, x whole numbers 1 to max_x in rising order (a point
    not past the one before is dropped), values held between low and high; `default` when no point is usable. A
    lone number (what a setting that became a curve was) is that value for every round."""
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        data = [[1, data]]
    out = []
    for point in data if isinstance(data, list) else []:
        if (isinstance(point, list) and len(point) == 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in point)):
            x = max(1, min(max_x, int(point[0])))
            if not out or x > out[-1][0]:
                out.append([x, max(low, min(high, float(point[1])))])
    return out[:MAX_CURVE_POINTS] or [list(p) for p in default]


@dataclass
class Light:
    """A light that things in the world can carry. The map keeps a list of them (the editor's Lights
    section) and guns, ammo types, particle effects, items and wall tiles refer to them by name, so
    one light is designed once and used anywhere. Like particles, lights only change how things look and
    are worked out on each player's own machine.

    name           what it is called (also how things refer to it)
    r, g, b        its color, 0 to 255 each
    intensity      how bright it is (1 lights a surface next to it as much as it was; more overexposes it)
    radius         how far it reaches, in cells; the light fades smoothly to nothing at that distance
    flicker        0 steady, up to 1 for a light that wobbles all the way down to nothing
    flicker_speed  how fast it wobbles, per second
    duration       a light that flashes once (a gun's muzzle) fades out over this many seconds
    wall_tile      the wall tile (atlas index, -1 for none) that glows with this light: every wall made
                   from it lights up the open cells beside it

    Walls stop light, so a lit room does not light the room behind its wall. Lights do not know about
    floors above or below, so a light reaches through the floor a little."""
    name: str = "Light"
    r: int = 255
    g: int = 200
    b: int = 120
    intensity: float = 1.5
    radius: float = 4.0
    flicker: float = 0.0
    flicker_speed: float = 8.0
    duration: float = 0.12
    wall_tile: int = -1

    @classmethod
    def from_dict(cls, data):
        base = cls()

        def number(key, low, high, cast=float):
            try:
                return cast(max(low, min(high, float(data.get(key, getattr(base, key))))))
            except (TypeError, ValueError):
                return getattr(base, key)
        name = str(data.get("name", base.name)).strip()[:MAX_NAME] or base.name
        return cls(name=name, r=number("r", 0, 255, int), g=number("g", 0, 255, int), b=number("b", 0, 255, int),
                   intensity=number("intensity", 0.0, 20.0), radius=number("radius", 0.5, 20.0),
                   flicker=number("flicker", 0.0, 1.0), flicker_speed=number("flicker_speed", 0.1, 60.0),
                   duration=number("duration", 0.02, 5.0), wall_tile=number("wall_tile", -1, 255, int))


@dataclass
class Effect:
    """A particle effect: what an emitter sends out. The map keeps a list of them (the editor's Effects
    section) and guns, ammo types and items refer to them by name, so one effect is designed once and
    used anywhere. Effects only make things look good: they are worked out on each player's own
    machine and never change the game.

    name         what it is called (also how guns, ammo and items refer to it)
    tile         atlas tile every particle is drawn with (tiles with transparent pixels work best)
    kind         burst: `count` particles at once (a puff, a muzzle flash, an impact);
                 stream: `rate` particles a second (smoke, sparks, a trail)
    count        burst: how many particles
    rate         stream: particles per second
    duration     stream played once (a muzzle flash): seconds it runs (0 is a short default). Streams that
                 stay attached (a trail, an item that emits) run for as long as they are attached
    interval     burst that stays attached (an item that emits): seconds between repeats (0 plays it once)
    life         seconds a particle lives; life_var is how much that varies, as a fraction (0.5 = +-50%)
    speed        cells per second a particle starts with; speed_var varies it the same way
    spread       half angle in degrees of the cone the particles leave in, around the emitter's direction
                 (up for an item, the aim for a gun, backwards for a trail); 180 is every direction
    radius       particles start up to this far (in cells) from the emitter
    gravity      cells per second squared pulling them down (negative: they float up)
    drag         how fast they slow down, per second (0 none, 1 loses most speed in a second)
    size_start, size_end    size in cells at birth and at death (they change smoothly)
    alpha_start, alpha_end  how solid they are at birth and at death (1 opaque, 0 invisible)
    color       original: the particle picture as drawn; hue: its colors turned round the color wheel by `hue`;
                 rgb: its colors multiplied by the tint (tint_r, tint_g, tint_b)
    hue          degrees (-180 to 180) for color "hue": 0 leaves the colors, a red flame at 120 is green
    tint_r, tint_g, tint_b
                 color (0 to 255 each) for color "rgb": 255 each leaves the picture as drawn, a lower channel
                 takes that color out of it, all of them lower darkens it
    collide      particles end when they hit a wall, floor or ceiling
    light        name of the Light every particle carries ("" for none); it fades with the particle, and the
                 particles are drawn at full brightness so they glow in a dark map
    offset_x, offset_y, offset_z
                 where the particles start, in cells, from the point the effect is played at (the muzzle, the
                 bullet, the item); offset_z is height
    aim          auto: leave in the direction the effect is played in (up from an item, along the aim from a
                 gun, back along the path from a bullet); custom: leave in the direction dir_x, dir_y, dir_z
                 (only which way it points matters, not how long it is; all zero means automatic)
    relative     false: the offset and custom direction are along the map's axes (x east, y south, z up);
                 true: x is along the automatic direction's heading and y to the right of it (an item has no
                 heading, so there they are still the map's axes)"""
    name: str = "Effect"
    tile: int = 14
    kind: str = "burst"
    count: int = 12
    rate: float = 30.0
    duration: float = 0.0
    interval: float = 0.0
    life: float = 0.6
    life_var: float = 0.3
    speed: float = 2.0
    speed_var: float = 0.4
    spread: float = 40.0
    radius: float = 0.0
    gravity: float = 0.0
    drag: float = 0.0
    size_start: float = 0.15
    size_end: float = 0.0
    alpha_start: float = 1.0
    alpha_end: float = 0.0
    color: str = "original"
    hue: float = 0.0
    tint_r: int = 255
    tint_g: int = 255
    tint_b: int = 255
    collide: bool = True
    light: str = ""
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0
    aim: str = "auto"
    dir_x: float = 0.0
    dir_y: float = 0.0
    dir_z: float = 1.0
    relative: bool = False

    @classmethod
    def from_dict(cls, data):
        base = cls()

        def number(key, low, high, cast=float):
            try:
                return cast(max(low, min(high, float(data.get(key, getattr(base, key))))))
            except (TypeError, ValueError):
                return getattr(base, key)
        name = str(data.get("name", base.name)).strip()[:MAX_NAME] or base.name
        return cls(name=name, tile=number("tile", 0, 255, int),
                   kind=data.get("kind") if data.get("kind") in EFFECT_KINDS else base.kind,
                   count=number("count", 1, 200, int), rate=number("rate", 0.5, 500.0),
                   duration=number("duration", 0.0, 60.0), interval=number("interval", 0.0, 600.0),
                   life=number("life", 0.05, 30.0), life_var=number("life_var", 0.0, 1.0),
                   speed=number("speed", 0.0, 50.0), speed_var=number("speed_var", 0.0, 1.0),
                   spread=number("spread", 0.0, 180.0), radius=number("radius", 0.0, 5.0),
                   gravity=number("gravity", -50.0, 50.0), drag=number("drag", 0.0, 20.0),
                   size_start=number("size_start", 0.0, 3.0), size_end=number("size_end", 0.0, 3.0),
                   alpha_start=number("alpha_start", 0.0, 1.0), alpha_end=number("alpha_end", 0.0, 1.0),
                   color=data.get("color") if data.get("color") in EFFECT_COLORS else base.color,
                   hue=number("hue", -180.0, 180.0), tint_r=number("tint_r", 0, 255, int),
                   tint_g=number("tint_g", 0, 255, int), tint_b=number("tint_b", 0, 255, int),
                   collide=bool(data.get("collide", base.collide)), light=str(data.get("light", ""))[:MAX_NAME],
                   offset_x=number("offset_x", -10.0, 10.0), offset_y=number("offset_y", -10.0, 10.0),
                   offset_z=number("offset_z", -10.0, 10.0),
                   aim=data.get("aim") if data.get("aim") in EFFECT_AIMS else base.aim,
                   dir_x=number("dir_x", -100.0, 100.0), dir_y=number("dir_y", -100.0, 100.0),
                   dir_z=number("dir_z", -100.0, 100.0), relative=bool(data.get("relative", base.relative)))


@dataclass
class AmmoType:
    """A kind of ammunition. Guns that name the same type share one pool of spare rounds, and what
    they shoot looks and flies like this type says.

    name         what it is called (also how a pickup and a gun refer to it)
    tile         atlas tile of the bullet that flies out
    size         size of that bullet in cells
    speed        how fast it flies, in cells per second
    range        how far it flies before it disappears, in cells
    damage_mult  multiplies the damage of the gun that fires it (1.0 leaves it as it is)
    trail        name of the Effect that follows the bullet through the air ("" for none)
    light        name of the Light the bullet carries as it flies ("" for none)
    player_hit_effects, player_hit_lights
                 names of the Effects played and Lights flashed where the bullet strikes a player (any number,
                 all at once)
    world_hit_effects, world_hit_lights
                 the same where it strikes anything else: a wall, floor, ceiling or glass
    trail_override, trail_offset_x, trail_offset_y, trail_offset_z
                 true: the trail starts at this offset (x along the bullet's heading, y to its right, z up, in
                 cells) instead of the effect's own start offset
    explodes     true: where the bullet strikes anything (or anyone) it explodes, hurting and throwing every player
                 in reach, the one who fired it included; walls shield from the blast
    blast_radius how far the explosion reaches, in cells; damage and knockback fade to nothing at the edge
    blast_damage damage at the very center of the explosion (a player the bullet hits directly takes this on
                 top of the bullet's own damage, so a direct hit does the most)
    knockback    speed in cells per second given to a player at the center of the explosion, along the line from
                 the blast to them; it fades with distance like the damage (about 5 is a rocket jump)
    air_knockback_mult
                 multiplies the knockback of a player who is in the air when it reaches them
    self_damage_mult, self_knockback_mult
                 multiply the damage and the knockback the player who fired it takes from its explosion
    explosion_effects, explosion_lights
                 names of the Effects played and Lights flashed at the explosion (any number, all at once)"""
    name: str = "Bullet"
    tile: int = 14
    size: float = 0.1
    speed: float = 18.0
    range: float = 20.0
    damage_mult: float = 1.0
    trail: str = ""
    light: str = ""
    trail_override: bool = False
    trail_offset_x: float = 0.0
    trail_offset_y: float = 0.0
    trail_offset_z: float = 0.0
    player_hit_effects: tuple = ()
    player_hit_lights: tuple = ()
    world_hit_effects: tuple = ()
    world_hit_lights: tuple = ()
    explodes: bool = False
    blast_radius: float = 3.0
    blast_damage: float = 50.0
    knockback: float = 5.0
    air_knockback_mult: float = 1.5
    self_damage_mult: float = 0.25
    self_knockback_mult: float = 1.0
    explosion_effects: tuple = ()
    explosion_lights: tuple = ()

    @classmethod
    def from_dict(cls, data):
        base = cls()

        def number(key, low, high, cast=float):
            try:
                return cast(max(low, min(high, float(data.get(key, getattr(base, key))))))
            except (TypeError, ValueError):
                return getattr(base, key)

        def names(key, old_key):
            """A list of effect or light names. A map from when there was just one `hit_effect` / `hit_light`
            (for any hit) gives that one to both kinds of hit."""
            value = data.get(key)
            if isinstance(value, (list, tuple)):
                return tuple(n[:MAX_NAME] for n in value if isinstance(n, str) and n)[:MAX_HIT_NAMES]
            old = data.get(old_key)
            return (old[:MAX_NAME],) if key not in data and isinstance(old, str) and old else ()
        name = str(data.get("name", base.name)).strip()[:MAX_NAME] or base.name
        return cls(name=name, tile=number("tile", 0, 255, int), size=number("size", 0.01, 2.0),
                   speed=number("speed", 0.5, 200.0), range=number("range", 0.5, 200.0),
                   damage_mult=number("damage_mult", 0.0, 100.0), trail=str(data.get("trail", ""))[:MAX_NAME],
                   light=str(data.get("light", ""))[:MAX_NAME], trail_override=bool(data.get("trail_override", False)),
                   trail_offset_x=number("trail_offset_x", -10.0, 10.0), trail_offset_y=number("trail_offset_y", -10.0, 10.0),
                   trail_offset_z=number("trail_offset_z", -10.0, 10.0),
                   player_hit_effects=names("player_hit_effects", "hit_effect"),
                   player_hit_lights=names("player_hit_lights", "hit_light"),
                   world_hit_effects=names("world_hit_effects", "hit_effect"),
                   world_hit_lights=names("world_hit_lights", "hit_light"),
                   explodes=bool(data.get("explodes", False)), blast_radius=number("blast_radius", 0.1, 20.0),
                   blast_damage=number("blast_damage", 0.0, 1000.0), knockback=number("knockback", 0.0, 50.0),
                   air_knockback_mult=number("air_knockback_mult", 0.0, 10.0),
                   self_damage_mult=number("self_damage_mult", 0.0, 10.0),
                   self_knockback_mult=number("self_knockback_mult", 0.0, 10.0),
                   explosion_effects=names("explosion_effects", ""), explosion_lights=names("explosion_lights", ""))


@dataclass
class Gun:
    """A weapon the player can pick up, keep in the inventory and equip. The map defines the guns
    (the editor's Guns section); entities hand them out.

    name        what it is called (also how an item that gives it or its ammo refers to it)
    tile        atlas tile drawn at the bottom of the screen while it is equipped
    size        scale of that picture: 1.0 draws the 32 pixel tile at 1 / 8 of the screen's height
    mode        single: one round per trigger pull, reloaded after every shot (the magazine is one
                round); semi: one round per trigger pull, as fast as the fire rate allows;
                auto: keeps firing at the fire rate while the trigger is held
    damage      damage of one round (what hits will do)
    fire_rate   rounds per second
    mag_size    rounds in a magazine (not used by single, which holds one)
    ammo        name of the AmmoType it uses: the bullet it fires and the pool of spare rounds it
                draws on, shared with every other gun of that type ("" is a plain default bullet)
    start_ammo  spare rounds of that ammunition picked up with the gun (again with each copy of it)
    reload_time seconds a reload takes
    spread      random aim error in degrees (0 is dead accurate); each bullet of a multi shot gets its own
    shot        what one pull of the trigger sends out:
                single      one bullet
                multi       `pellets` bullets at once (a shotgun), each aimed a little differently by the spread
                projectile  reserved for things that are not simple bullets (rockets, grenades); it fires
                            like a single bullet until that is built
    pellets     bullets in a multi shot
    muzzle      name of the Effect played at the muzzle each time it fires ("" for none)
    flash       name of the Light that flashes at the muzzle each time it fires ("" for none)
    bullet_offset_x, bullet_offset_y, bullet_offset_z
                where the bullets come from, in cells from the usual muzzle point in front of the eye: x ahead
                along the aim, y to the right, z up (a gun held low and to the right is about 0, 0.3, -0.25).
                The bullets still fly along the aim. The muzzle effect and flash come from this point too.
    muzzle_override, muzzle_offset_x, muzzle_offset_y, muzzle_offset_z
                true: the muzzle effect starts at this offset from the muzzle (x ahead along the aim, y to the
                right, z up, in cells) instead of the effect's own start offset"""
    name: str = "Pistol"
    tile: int = 16
    size: float = 5.0
    mode: str = "semi"
    damage: float = 10.0
    fire_rate: float = 4.0
    mag_size: int = 12
    start_ammo: int = 36
    reload_time: float = 1.5
    ammo: str = ""
    spread: float = 0.0
    shot: str = "single"
    pellets: int = 8
    bullet_offset_x: float = 0.0
    bullet_offset_y: float = 0.0
    bullet_offset_z: float = 0.0
    muzzle: str = ""
    flash: str = ""
    muzzle_override: bool = False
    muzzle_offset_x: float = 0.0
    muzzle_offset_y: float = 0.0
    muzzle_offset_z: float = 0.0

    @property
    def capacity(self):
        """Rounds the gun holds ready to fire."""
        return 1 if self.mode == "single" else max(1, int(self.mag_size))

    @classmethod
    def from_dict(cls, data):
        base = cls()

        def number(key, low, high, cast=float):
            try:
                return cast(max(low, min(high, float(data.get(key, getattr(base, key))))))
            except (TypeError, ValueError):
                return getattr(base, key)
        name = str(data.get("name", base.name)).strip()[:MAX_NAME] or base.name
        return cls(name=name, tile=int(number("tile", 0, 255, int)),
                   size=number("size", 0.2, 20.0), mode=data.get("mode") if data.get("mode") in GUN_MODES else base.mode,
                   damage=number("damage", 0.0, 10000.0), fire_rate=number("fire_rate", 0.1, 100.0),
                   mag_size=number("mag_size", 1, 1000, int), start_ammo=number("start_ammo", 0, 100000, int),
                   reload_time=number("reload_time", 0.0, 60.0), ammo=str(data.get("ammo", ""))[:MAX_NAME],
                   spread=number("spread", 0.0, 45.0),
                   shot=data.get("shot") if data.get("shot") in SHOT_TYPES else base.shot,
                   pellets=number("pellets", 1, 100, int), bullet_offset_x=number("bullet_offset_x", -5.0, 5.0),
                   bullet_offset_y=number("bullet_offset_y", -5.0, 5.0), bullet_offset_z=number("bullet_offset_z", -5.0, 5.0),
                   muzzle=str(data.get("muzzle", ""))[:MAX_NAME],
                   flash=str(data.get("flash", ""))[:MAX_NAME], muzzle_override=bool(data.get("muzzle_override", False)),
                   muzzle_offset_x=number("muzzle_offset_x", -10.0, 10.0), muzzle_offset_y=number("muzzle_offset_y", -10.0, 10.0),
                   muzzle_offset_z=number("muzzle_offset_z", -10.0, 10.0))


@dataclass
class Animation:
    """One motion an item plays all the time. An item has a list of them, and each has its own settings.

    float    bobs gently up and down: `speed` is bobs per second, `amount` how far it rises (in cells)
    rotate   spins around its vertical axis: `speed` is turns per second (`amount` is not used)"""
    kind: str = "float"
    speed: float = 0.5
    amount: float = 0.1

    @classmethod
    def from_dict(cls, data):
        base = cls()
        kind = data.get("kind") if data.get("kind") in ANIMATION_KINDS else base.kind
        return cls(kind, max(0.0, float(data.get("speed", base.speed))),
                   max(0.0, float(data.get("amount", base.amount))))


@dataclass
class Entity:
    """An item standing in the world as a sprite that always faces the player.

    x, y     position on the map, in cells (cell center = .5)
    span     the floor it stands on
    tile     0-based atlas tile drawn as its sprite (tiles with transparent pixels work best)
    mode     what touching it does to the item itself:
             once        picked up and gone for good
             respawn     picked up and gone, back after `respawn` seconds
             persistent  picked up (the effect happens) but it stays where it is; touching it again
                         only counts after you have stepped away from it
    effect   what the player gets: none, score (+amount points) or health (+amount, capped)
    amount   size of the effect
    price    0: touching it picks it up. Above 0: it is for sale: standing by it and pressing the use key (E) buys
             it for that much money (what touching it would give); touching it alone does nothing
    respawn  seconds until a respawning item comes back
    size     sprite height in world units (it is as wide as it is tall)
    lift     height of the sprite's bottom above the floor
    animations  list of Animation (none by default): float and / or rotate, each with its own speed
    item, gun, ammo   what the "item" effect puts in the inventory (amount of it), which gun the "gun"
                effect hands out, and which ammo type the "ammo" effect gives (amount of rounds)
    name, prefab  a prefab is an Entity kept in the level's list of prefabs, with a name and its settings
                (its x, y and span mean nothing). An item placed from it has prefab set to that name and
                takes every setting except its place from it (Level.apply_prefabs), so editing the prefab
                changes all of them at once. Clearing `prefab` detaches an item: it keeps what it had.
    shown    whether the sprite is drawn (an item that only emits particles can hide it)
    emits    name of the particle Effect the item sends out while it is there ("" for none; it points up)
    emits_override, emits_offset_x, emits_offset_y, emits_offset_z
             true: the particles start at this offset from the item (x east, y south, z up, in cells) instead of
             the effect's own start offset
    light    name of the Light the item gives off while it is there ("" for none); with Scenery and a hidden
             sprite an item is just a light placed in the map
    wall     "" for an item standing in its cell, or the side of its cell ("n", "e", "s", "w") whose wall it hangs on:
             it is then a flat picture against that wall, facing into the cell (x, y are just in front of the
             wall: see mounted_position), at `lift` above the floor
    elevation  how much higher (or, below 0, lower) this placed item is than its settings put it. It belongs to
             the place, like x and y: a prefab never sets it, so each copy of a prefab can sit at its own height
    A "scenery" item cannot be touched or picked up: it is only there to look at (a torch, a vent)."""
    x: float
    y: float
    span: int = 0
    tile: int = 10
    mode: str = "once"
    effect: str = "score"
    amount: float = 10.0
    respawn: float = 10.0
    size: float = 0.4
    lift: float = 0.0
    animations: list = field(default_factory=list)
    item: str = ""                  # effect "item": the name of the thing put in the inventory
    gun: str = ""                   # effect "gun": the name of the gun it hands out
    ammo: str = ""                  # effect "ammo": the name of the ammo type it gives (amount rounds)
    price: float = 0.0              # money it costs, bought with E (0: picked up by touching it)
    shown: bool = True              # draw the sprite
    emits: str = ""                 # the particle effect it sends out
    emits_override: bool = False    # use emits_offset_* instead of the effect's own start offset
    emits_offset_x: float = 0.0
    emits_offset_y: float = 0.0
    emits_offset_z: float = 0.0
    light: str = ""                 # the light it gives off
    counter: str = ""               # effect "counter" (zombies): the Counter it adds amount to (negative: takes)
    name: str = ""                  # a prefab's name (an item placed in the map has none)
    prefab: str = ""                # the prefab this item is an instance of ("" for a plain item)
    wall: str = ""                  # the side of its cell whose wall it hangs on ("" for none)
    elevation: float = 0.0          # this placed item's own height above where its settings put it

    def clone(self, **changes):
        """A copy that shares nothing with this entity (its animations are copied too)."""
        changes.setdefault("animations", [replace(a) for a in self.animations])
        return replace(self, **changes)

    @classmethod
    def from_dict(cls, data):
        """Read one entity from a file, replacing anything unusable with the default."""
        base = cls(float(data["x"]), float(data["y"]))
        return replace(base,
                       span=max(0, int(data.get("span", 0))),
                       tile=max(0, int(data.get("tile", base.tile))),
                       mode=data.get("mode") if data.get("mode") in ENTITY_MODES else base.mode,
                       effect=data.get("effect") if data.get("effect") in ENTITY_EFFECTS else base.effect,
                       amount=float(data.get("amount", base.amount)),
                       respawn=max(0.0, float(data.get("respawn", base.respawn))),
                       size=max(0.05, float(data.get("size", base.size))),
                       lift=float(data.get("lift", base.lift)),
                       animations=[Animation.from_dict(a) for a in data.get("animations", [])
                                   if isinstance(a, dict)],
                       item=str(data.get("item", ""))[:MAX_NAME], gun=str(data.get("gun", ""))[:MAX_NAME],
                       ammo=str(data.get("ammo", ""))[:MAX_NAME],
                       price=max(0.0, min(MAX_MONEY, float(data.get("price", 0.0)))),
                       counter=str(data.get("counter", ""))[:MAX_NAME],
                       shown=bool(data.get("shown", base.shown)), emits=str(data.get("emits", ""))[:MAX_NAME],
                       emits_override=bool(data.get("emits_override", False)),
                       emits_offset_x=float(data.get("emits_offset_x", 0.0)),
                       emits_offset_y=float(data.get("emits_offset_y", 0.0)),
                       emits_offset_z=float(data.get("emits_offset_z", 0.0)),
                       light=str(data.get("light", ""))[:MAX_NAME],
                       name=str(data.get("name", ""))[:MAX_NAME], prefab=str(data.get("prefab", ""))[:MAX_NAME],
                       wall=data.get("wall") if data.get("wall") in WALL_LABELS else "",
                       elevation=max(-MAX_ELEVATION, min(MAX_ELEVATION, float(data.get("elevation", 0.0)))))


GAME_MODES = ("ffa", "teams", "coop", "bomb", "koth", "zombies")
GAME_MODE_LABELS = {"ffa": "Free for all", "teams": "Two teams", "coop": "Co-op", "bomb": "Bomb defusal",
                    "koth": "King of the Hill", "zombies": "Zombies"}
BUY_COSTS = ("free", "money", "score")
BUY_COST_LABELS = {"free": "Free", "money": "Money", "score": "Score"}
DEATH_CAM_WHO = ("team", "all")                 # who a knocked-out player may watch (MapSettings.death_cam_who)
DEATH_CAM_WHO_LABELS = {"team": "Teammates only", "all": "All teams"}
BUY_KINDS = ("gun", "item", "health")         # (no ammo: guns come with theirs, filled up each bomb defusal round)
BUY_KIND_LABELS = {"gun": "A gun", "item": "Inventory item", "health": "Health"}
MAX_BUY_ITEMS = 40                              # entries a buy menu may have
MAX_MONEY = 1000000.0
DEFUSE_KIT = "Defuse kit"                       # the inventory item that makes defusing faster (sell it as an item)
# Bomb defusal settings that are numbers: (lowest, highest). Their defaults are Counter-Strike's.
BOMB_NUMBERS = {"freeze_time": (0.0, 120.0), "round_time": (10.0, 1800.0), "buy_time": (0.0, 1800.0),
                "bomb_time": (5.0, 600.0), "plant_time": (0.0, 30.0), "defuse_time": (0.0, 60.0),
                "kit_defuse_time": (0.0, 60.0), "round_end_time": (1.0, 60.0), "max_rounds": (1.0, 99.0),
                "bomb_damage": (0.0, 100000.0), "bomb_radius": (1.0, 200.0), "win_money": (0.0, MAX_MONEY),
                "bomb_win_money": (0.0, MAX_MONEY), "loss_money": (0.0, MAX_MONEY), "loss_bonus": (0.0, MAX_MONEY),
                "max_loss_money": (0.0, MAX_MONEY), "plant_money": (0.0, MAX_MONEY),
                "objective_money": (0.0, MAX_MONEY), "money_cap": (0.0, MAX_MONEY)}
# King of the Hill settings: (lowest, highest). Their defaults are Team Fortress 2's.
KOTH_NUMBERS = {"hill_time": (10.0, 3600.0), "unlock_time": (0.0, 600.0), "capture_time": (0.5, 300.0),
                "capture_bonus": (0.0, 600.0), "decay_time": (1.0, 600.0), "respawn_time": (0.0, 60.0),
                "win_limit": (1.0, 99.0)}
# Zombies settings that are numbers: (lowest, highest).
ZOMBIE_NUMBERS = {"extra_per_player": (0.0, 5.0), "intermission": (0.0, 300.0),
                  "game_over_time": (1.0, 60.0), "bleed_out": (1.0, 600.0), "revive_time": (0.1, 60.0),
                  "revive_reward": (0.0, MAX_MONEY), "revive_health": (1.0, 10000.0), "downed_speed": (0.0, 3.0),
                  "revive_grace": (0.0, 30.0), "round_money": (0.0, MAX_MONEY)}
ZOMBIE_COUNT = [[1, 6], [5, 18], [10, 40], [20, 110]]      # round -> enemies in it
ZOMBIE_HEALTH = [[1, 1.0], [10, 2.0], [20, 4.0]]            # round -> what their health is multiplied by
ZOMBIE_ALIVE = [[1, 12], [10, 30], [20, 60]]                # round -> the most in the map at once
ZOMBIE_INTERVAL = [[1, 2.0], [10, 1.0], [20, 0.5]]          # round -> seconds between one coming in and the next
ZOMBIE_CURVES = {"zombie_count": ZOMBIE_COUNT, "zombie_health": ZOMBIE_HEALTH, "max_alive": ZOMBIE_ALIVE,
                 "spawn_interval": ZOMBIE_INTERVAL}              # MapSettings' curves and their defaults
# Each zombies curve (and an enemy's weight): (lowest, highest) value.
CURVE_LIMITS = {"zombie_count": (0.0, 10000.0), "zombie_health": (0.01, 1000.0), "max_alive": (1.0, 500.0),
                "spawn_interval": (0.0, 60.0), "weight": (0.0, 1000.0)}


@dataclass
class BuyItem:
    """One entry of a map's buy menu (MapSettings.buy_items): what clicking it gives and what it costs.

    name     what the button says ("" names it after what it gives)
    kind     gun: hands out the gun named `gun` (as a "Give a gun" item does); item: `amount` of the inventory item
             `item`; health: +`amount` health (up to the most). Ammo is not sold (an older map's ammo entries are
             left out when it is read)
    price    what it costs, in the menu's currency (MapSettings.buy_cost); nothing when the menu is free
    tile     the atlas tile shown beside it (-1: the gun's own picture, or none)
    team     0: everyone can buy it; T_TEAM / CT_TEAM: in a mode with teams, only that team's players see and can
             buy it (in a mode without teams everyone can)"""
    name: str = ""
    kind: str = "gun"
    gun: str = ""
    item: str = ""
    amount: float = 1.0
    price: float = 100.0
    tile: int = -1
    team: int = 0

    def offered_to(self, team, has_teams):
        """Whether a player on `team` sees and can buy this entry (`has_teams`: the map's mode has teams)."""
        return not has_teams or self.team == 0 or self.team == team

    def label(self):
        """What the button says: its name, or what it gives."""
        if self.name:
            return self.name
        if self.kind == "gun":
            return self.gun or "(no gun)"
        if self.kind == "item":
            return f"{self.amount:g} x {self.item or 'Item'}"
        return f"+{self.amount:g} health"

    @classmethod
    def from_dict(cls, data):
        base = cls()

        def number(key, low, high):
            try:
                return max(low, min(high, float(data.get(key, getattr(base, key)))))
            except (TypeError, ValueError):
                return getattr(base, key)
        return cls(name=str(data.get("name", ""))[:MAX_NAME],
                   kind=data.get("kind") if data.get("kind") in BUY_KINDS else base.kind,
                   gun=str(data.get("gun", ""))[:MAX_NAME],
                   item=str(data.get("item", ""))[:MAX_NAME], amount=number("amount", 0.0, 100000.0),
                   price=number("price", 0.0, MAX_MONEY), tile=int(number("tile", -1, 255)),
                   team=data.get("team") if data.get("team") in SPAWN_TEAMS else 0)


@dataclass
class MapSettings:
    """How a map is played, set in the editor's Map settings section and saved with the map.

    mode           ffa: everyone against everyone; teams: players are split into two teams as they join (a
                   teammate's name shows white); coop: everyone on one team
    friendly_fire  whether bullets and blasts hurt teammates (a player's own blast always hurts them)
    max_health     the health every player starts and comes back with
    start_money    money a player has when they first join (money, like score, is kept when knocked out)
    kill_score, kill_money   what knocking out an opponent earns
    start_gun      the gun every player starts and comes back with ("" for none)
    buy_menu       whether players can open the buy menu (B in the game)
    buy_cost       free: everything in it is free; money / score: each entry costs its price in that, and is
                   only given when the player has enough (score spent on buying goes down)
    buy_items      the menu's entries (BuyItem), in the order they are listed
    respawn_delay  free for all, two teams and co-op: how long a knocked-out player waits before coming back (0: at
                   once). King of the Hill has its own respawn_time
    death_cam      whether a player out of a round (bomb defusal) or waiting to respawn can watch the living players
                   through their eyes; off, they only see where they were knocked out
    death_cam_who  team: only their teammates can be watched; all: their teammates first, then the other team (free
                   for all has no teammates: everyone can be watched)

    Bomb defusal (mode "bomb", see bomb.py): team 1 (T) plants the bomb in a bomb site (the site layer), team 2 (CT)
    stops them or defuses it. Times are in seconds, distances in cells, and the defaults are Counter-Strike's.
    freeze_time      at the start of a round nobody can move (they can look around and buy)
    round_time       how long a round lasts after the freeze time; when it runs out without a plant, CT win
    buy_time         how long after the freeze time the buy menu stays open (it is open during the freeze too)
    bomb_time        a planted bomb explodes this long after it was planted
    plant_time, defuse_time, kit_defuse_time   how long the use key (E) is held to plant, to defuse, and to
                     defuse with a DEFUSE_KIT in the inventory
    round_end_time   the pause after a round is decided, before the next one starts
    max_rounds       rounds in a match: the teams swap sides after half of them, and the first team to win
                     more than half wins the match (a new match then starts)
    bomb_damage, bomb_radius   the explosion: full damage at the bomb, falling away to almost none at the radius;
                     walls do not stop it
    bomb_effect, bomb_light    the particle effect and light the explosion plays ("" for none)
    win_money        every player of the team that won the round gets this (bomb_win_money for winning by the
                     bomb exploding or being defused)
    loss_money, loss_bonus, max_loss_money   the losing team gets loss_money, plus loss_bonus for each round
                     lost in a row before this one, at most max_loss_money
    plant_money      every T gets this when the bomb was planted but they lost the round
    objective_money  the player who plants, or defuses, the bomb gets this
    money_cap        nobody can have more money than this

    King of the Hill (mode "koth", see koth.py): team 1 (RED) and team 2 (BLU) fight over one capture point (the
    site layer's HILL_SITE cells). Owning it runs down the owner's own clock; the first team whose clock reaches
    zero wins the round. Defaults are Team Fortress 2's, but for capture_bonus, which it does not have.
    hill_time        each team's clock at the start of a round
    unlock_time      the point is locked (nobody can capture it) this long after a round starts
    capture_time     how long one player standing on the point alone takes to capture it (more players are faster)
    capture_bonus    seconds added to a team's clock (up to hill_time) each time it captures the point
    decay_time       how long capture progress takes to drain away when nobody stands on the point
    respawn_time     how long a knocked out player waits before coming back at their team's spawn points
    win_limit        rounds a team has to win to win the match (a new match then starts)
    round_end_time   (shared with bomb defusal) the pause after a round is won, before the next one

    Zombies (mode "zombies", see zombies.py): everyone on one team against rounds of enemies (Level.enemies) coming
    in at the ENEMY_SPAWN spawners. A round is over when all its enemies are dead; the game when every player is.
    zombie_count     a curve (see curve_at) of round -> how many enemies come in that round
    zombie_health    a curve of round -> what each enemy's health is multiplied by
    max_alive        a curve of round -> at most this many enemies are in the map at once (the rest wait their turn)
    spawn_interval   a curve of round -> seconds between one enemy coming in and the next
    extra_per_player each player beyond the first adds this share to a round's enemies and to the most at once
                     (0.5: two players face half as many again)
    Which kind each enemy coming in is, is picked by the kinds' weights for the round (Enemy.weight).
    intermission     seconds between rounds (and before the first)
    game_over_time   seconds the game over message shows before a new game starts
    round_money      money every player gets when a round is cleared
    A player at 0 health goes down instead of out while someone else is still standing: they crawl at
    downed_speed (cells per second), can shoot when downed_can_shoot, and are out (until the next round) after
    bleed_out seconds unless a teammate revives them by holding the use key (E) beside them for revive_time.
    The reviver earns revive_reward; the revived player gets up with revive_health and cannot be hurt by enemies for
    revive_grace seconds. Nobody standing is game over (alone, going down is). Players who were out come back at
    the next round with only what a new player carries, unless keep_guns."""
    mode: str = "ffa"
    friendly_fire: bool = False
    max_health: float = 100.0
    start_money: float = 0.0
    kill_score: float = 0.0
    kill_money: float = 0.0
    start_gun: str = ""
    buy_menu: bool = False
    buy_cost: str = "money"
    buy_items: list = field(default_factory=list)
    respawn_delay: float = 0.0
    death_cam: bool = True
    death_cam_who: str = "team"
    freeze_time: float = 15.0
    round_time: float = 115.0
    buy_time: float = 20.0
    bomb_time: float = 40.0
    plant_time: float = 3.2
    defuse_time: float = 10.0
    kit_defuse_time: float = 5.0
    round_end_time: float = 7.0
    max_rounds: float = 24.0
    bomb_damage: float = 500.0
    bomb_radius: float = 27.0
    bomb_effect: str = ""
    bomb_light: str = ""
    win_money: float = 3250.0
    bomb_win_money: float = 3500.0
    loss_money: float = 1400.0
    loss_bonus: float = 500.0
    max_loss_money: float = 3400.0
    plant_money: float = 800.0
    objective_money: float = 300.0
    money_cap: float = 16000.0
    hill_time: float = 180.0
    unlock_time: float = 30.0
    capture_time: float = 10.0
    capture_bonus: float = 10.0
    decay_time: float = 90.0
    respawn_time: float = 5.0
    win_limit: float = 2.0
    zombie_count: list = field(default_factory=lambda: [list(p) for p in ZOMBIE_COUNT])
    zombie_health: list = field(default_factory=lambda: [list(p) for p in ZOMBIE_HEALTH])
    max_alive: list = field(default_factory=lambda: [list(p) for p in ZOMBIE_ALIVE])
    spawn_interval: list = field(default_factory=lambda: [list(p) for p in ZOMBIE_INTERVAL])
    extra_per_player: float = 0.5
    intermission: float = 10.0
    game_over_time: float = 8.0
    round_money: float = 0.0
    bleed_out: float = 30.0
    revive_time: float = 3.0
    revive_reward: float = 100.0
    revive_health: float = 50.0
    downed_speed: float = 0.6
    revive_grace: float = 2.0
    downed_can_shoot: bool = True
    keep_guns: bool = False

    def copy(self):
        return replace(self, buy_items=[replace(b) for b in self.buy_items],
                       **{name: [list(p) for p in getattr(self, name)] for name in ZOMBIE_CURVES})

    def uses_money(self):
        """True if money means anything on this map (so the HUD shows it)."""
        return (self.buy_menu and self.buy_cost == "money") or self.start_money > 0 or self.kill_money > 0 \
            or self.mode == "zombies"                   # (zombies pay for every hit and kill)

    def has_waiting(self):
        """True if knocked-out players are out for a while (bomb defusal, King of the Hill, or a respawn delay), so
        the death camera means something."""
        return self.mode in ("bomb", "koth", "zombies") or (self.mode in ("ffa", "teams", "coop")
                                                            and self.respawn_delay > 0)

    def has_teams(self):
        """True if players are split into two teams (two teams, bomb defusal and King of the Hill)."""
        return self.mode in ("teams", "bomb", "koth")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        """Map settings from a file, replacing anything unusable with the default."""
        base = cls()
        if not isinstance(data, dict):
            return base

        def number(key, low, high):
            try:
                return max(low, min(high, float(data.get(key, getattr(base, key)))))
            except (TypeError, ValueError):
                return getattr(base, key)
        items = data.get("buy_items", [])
        return cls(mode=data.get("mode") if data.get("mode") in GAME_MODES else base.mode,
                   friendly_fire=bool(data.get("friendly_fire", base.friendly_fire)),
                   max_health=number("max_health", 1.0, 10000.0), start_money=number("start_money", 0.0, MAX_MONEY),
                   kill_score=number("kill_score", 0.0, MAX_MONEY), kill_money=number("kill_money", 0.0, MAX_MONEY),
                   start_gun=str(data.get("start_gun", ""))[:MAX_NAME],
                   buy_menu=bool(data.get("buy_menu", base.buy_menu)),
                   buy_cost=data.get("buy_cost") if data.get("buy_cost") in BUY_COSTS else base.buy_cost,
                   buy_items=[BuyItem.from_dict(b) for b in items
                              if isinstance(b, dict) and b.get("kind") != "ammo"][:MAX_BUY_ITEMS]
                   if isinstance(items, list) else [],
                   respawn_delay=number("respawn_delay", 0.0, 60.0),
                   death_cam=bool(data.get("death_cam", base.death_cam)),
                   death_cam_who=data.get("death_cam_who") if data.get("death_cam_who") in DEATH_CAM_WHO
                   else base.death_cam_who,
                   bomb_effect=str(data.get("bomb_effect", ""))[:MAX_NAME],
                   bomb_light=str(data.get("bomb_light", ""))[:MAX_NAME],
                   **{key: number(key, low, high) for key, (low, high) in BOMB_NUMBERS.items()},
                   **{key: number(key, low, high) for key, (low, high) in KOTH_NUMBERS.items()},
                   downed_can_shoot=bool(data.get("downed_can_shoot", base.downed_can_shoot)),
                   keep_guns=bool(data.get("keep_guns", base.keep_guns)),
                   **{name: read_curve(data.get(name), default, *CURVE_LIMITS[name])
                      for name, default in ZOMBIE_CURVES.items()},
                   **{key: number(key, low, high) for key, (low, high) in ZOMBIE_NUMBERS.items()})


def mounted_position(cx, cy, wall):
    """(x, y) of an item in cell (cx, cy) hung on the wall on side `wall` of the cell (its middle for "")."""
    dx, dy = SIDE_VECTORS.get(wall, (0, 0))
    return cx + 0.5 + dx * (0.5 - WALL_GAP), cy + 0.5 + dy * (0.5 - WALL_GAP)


def wall_facing(wall):
    """The map angle an item hung on side `wall` of its cell faces: away from the wall, into the cell."""
    dx, dy = SIDE_VECTORS[wall]
    return math.atan2(-dy, -dx)


def side_band(level, x, y, side):
    """(from, to): the world heights the own texture on side `side` of the wall at (x, y) covers. A band that
    starts at 0 reaches down to the wall's foot, and one that ends at 0 up to its top, whatever those are."""
    low, high = level.get(f"side_{side}_from", x, y), level.get(f"side_{side}_to", x, y)
    floor = level.wall_floor(x, y)
    base = level.wall_base(x, y) if floor == 0 else level.get(grid_name("floor_h", floor), x, y)
    return (base + low if low > 0 else -1e9), (base + high if high > 0 else 1e9)


def grid_name(layer, floor):
    """Name of the stored grid for an edit layer on a floor (walls are shared by all floors)."""
    return layer if layer in SHARED_LAYERS or floor == 0 else f"{layer}{floor + 1}"


def split_grid_name(name):
    """(layer, floor) for a stored grid name, the inverse of grid_name."""
    layer = name.rstrip("0123456789")
    digits = name[len(layer):]
    return layer, (int(digits) - 1 if digits else 0)


def default_for(name):
    """Value of a grid cell that nobody has edited."""
    layer, floor = split_grid_name(name)
    return (_GROUND_DEFAULTS if floor == 0 else _UPPER_DEFAULTS)[layer]


class _Defaults:
    """DEFAULTS["floor_h2"] etc.: the default value for any stored grid name."""

    def __getitem__(self, name):
        return default_for(name)


DEFAULTS = _Defaults()


def default_floor_name(index):
    return f"Floor {index + 1}"


class Level:
    def __init__(self, grids, start_x=1.5, start_y=1.5, start_angle=0.0, start_span=0, names=None,
                 entities=None, guns=None, ammo_types=None, prefabs=None, effects=None, lights=None, ambient=1.0,
                 spawners=None, settings=None, enemies=None, barricades=None, barricade_kinds=None, doors=None,
                 door_kinds=None, interacts=None, counters=None, triggers=None):
        self.grids = grids
        self.interacts = list(interacts or [])      # places players use with E (see Interact; zombies mode)
        self.counters = list(counters or [])        # numbers kept through a game (see Counter)
        self.triggers = list(triggers or [])        # what happens when (see Trigger)
        self.door_kinds = list(door_kinds or [])    # saved doors to place more of (DoorKind)
        self.doors = list(doors or [])              # doors that open during a game (see Door; zombies mode)
        self.barricade_kinds = list(barricade_kinds or [])     # saved barricades to place more of (BarricadeKind)
        self.barricades = list(barricades or [])    # boarded-up openings (see Barricade; zombies mode)
        self.enemies = list(enemies or [])          # kinds of enemy defined for this map (see Enemy; zombies mode)
        self.settings = settings or MapSettings()   # how the map is played (see MapSettings)
        self.spawners = list(spawners or [])        # where players come into the game (see Spawner)
        self.lights = list(lights or [])            # lights defined for this map (see Light)
        self.ambient = ambient                      # how bright the map is without lights: 1 is as before, less is dark
        self.effects = list(effects or [])          # particle effects defined for this map (see Effect)
        self.guns = list(guns or [])                # weapons defined for this map (see Gun)
        self.ammo_types = list(ammo_types or [])    # kinds of ammunition defined for this map (see AmmoType)
        self.prefabs = list(prefabs or [])          # reusable items defined for this map (see Entity)
        self.entities = list(entities or [])        # items in the world (see Entity)
        self.start_x, self.start_y = start_x, start_y
        self.start_angle = start_angle              # radians, 0 faces +x (right on the grid)
        self.start_span = start_span                # index of the floor the player starts on
        if names is None:                           # infer the floors from the grids present
            count = 1 + max((split_grid_name(n)[1] for n in grids), default=0)
            names = [default_floor_name(i) for i in range(count)]
        self.names = list(names)

    # ----------------------------------------------------------- construction

    @classmethod
    def blank(cls, width, height, border=1, floors=1):
        """An empty map: open space, optionally walled in, with `floors` floors (at least 1)."""
        level = cls({name: [[default_for(name)] * width for _ in range(height)] for name in SHARED_LAYERS},
                    names=[])
        for _ in range(max(1, floors)):
            level.add_floor()
        if border:
            level.fill_border(border)
        return level

    def copy(self):
        return Level({k: [row[:] for row in g] for k, g in self.grids.items()},
                     self.start_x, self.start_y, self.start_angle, self.start_span, self.names,
                     [e.clone() for e in self.entities], [replace(g) for g in self.guns],
                     [replace(a) for a in self.ammo_types], [p.clone() for p in self.prefabs],
                     [replace(f) for f in self.effects], [replace(light) for light in self.lights], self.ambient,
                     [replace(s) for s in self.spawners], self.settings.copy(), [e.clone() for e in self.enemies],
                     [replace(b, stages=list(b.stages)) for b in self.barricades],
                     [k.clone() for k in self.barricade_kinds], [replace(d) for d in self.doors],
                     [k.clone() for k in self.door_kinds], [replace(i) for i in self.interacts],
                     [replace(c) for c in self.counters], [t.clone() for t in self.triggers])

    def door_named(self, name):
        return next((d for d in self.doors if d.name == name), None)

    def interact_named(self, name):
        return next((i for i in self.interacts if i.name == name), None)

    def counter_named(self, name):
        return next((c for c in self.counters if c.name == name), None)

    def rename_reference(self, kind, old, new):
        """Something a trigger can name was renamed: "door", "interact", "counter", "item" or "event". Every
        trigger's event, conditions and actions that named it name the new one ("" for deleted: those keep the old
        name, which no longer matches anything)."""
        events = {"door": "door:", "interact": "used:", "counter": "counter:", "item": "picked:", "event": ""}
        about = {"door": ("door_open", "door_closed", "open_door", "close_door"),
                 "counter": ("counter_at_least", "counter_below", "add_counter", "set_counter"),
                 "item": ("player_has", "team_has", "give_item", "take_item"), "event": ("event",), "interact": ()}
        if not new:
            return
        for trigger in self.triggers:
            if trigger.on == events[kind] + old:
                trigger.on = events[kind] + new
            for thing in trigger.conditions + trigger.actions:
                if thing.kind in about[kind] and thing.name == old:
                    thing.name = new
            for action in trigger.actions:
                if kind == "interact" and action.at == old:
                    action.at = new
        if kind == "item":
            for interact in self.interacts:
                if interact.needs == old:
                    interact.needs = new
        if kind == "counter":
            for thing in self.entities + self.prefabs:
                if thing.counter == old:
                    thing.counter = new

    def door_kind_named(self, name):
        return next((k for k in self.door_kinds if k.name == name), None)

    def apply_door_kinds(self):
        """Give every door placed from a saved type that type's settings. One whose type no longer exists is
        detached: it keeps the settings it last had."""
        for door in self.doors:
            kind = self.door_kind_named(door.kind) if door.kind else None
            if kind is None:
                door.kind = ""
                continue
            for key in DOOR_KIND_FIELDS:
                setattr(door, key, getattr(kind, key))

    def door_groups(self):
        """The doors that act as one: [[index, ...], ...], each group the doors whose rectangles touch (side by side
        or corner to corner), in order of their first index, which is the one whose settings count."""
        def touch(a, b):
            return (a.x - 1 <= b.x + b.width - 1 and b.x <= a.x + a.width
                    and a.y - 1 <= b.y + b.height - 1 and b.y <= a.y + a.height)
        seen, groups = set(), []
        for i in range(len(self.doors)):
            if i in seen:
                continue
            group, todo = [], [i]
            seen.add(i)
            while todo:
                j = todo.pop()
                group.append(j)
                for k, other in enumerate(self.doors):
                    if k not in seen and touch(self.doors[j], other):
                        seen.add(k)
                        todo.append(k)
            groups.append(sorted(group))
        return groups

    def door_leader(self, index):
        """The index of the door whose settings count for door `index` (the first of its group)."""
        return next((g[0] for g in self.door_groups() if index in g), index)

    def door_at(self, x, y):
        """The index of the door covering cell (x, y), or None."""
        return next((i for i, d in enumerate(self.doors)
                     if d.x <= x < d.x + d.width and d.y <= y < d.y + d.height), None)

    def barricade_kind_named(self, name):
        return next((k for k in self.barricade_kinds if k.name == name), None)

    def apply_barricade_kinds(self):
        """Give every barricade placed from a saved type that type's settings. One whose type no longer exists is
        detached: it keeps the settings it last had."""
        for barricade in self.barricades:
            kind = self.barricade_kind_named(barricade.kind) if barricade.kind else None
            if kind is None:
                barricade.kind = ""
                continue
            for key in BARRICADE_KIND_FIELDS:
                value = getattr(kind, key)
                setattr(barricade, key, list(value) if isinstance(value, list) else value)

    def barricade_groups(self):
        """The barricades that act as one: [[index, ...], ...], each group the barricades joined cell to cell (side
        by side or corner to corner), in order of their first index, which is the one whose settings count."""
        at = {(b.x, b.y): i for i, b in enumerate(self.barricades)}
        seen, groups = set(), []
        for i, b in enumerate(self.barricades):
            if i in seen:
                continue
            group, todo = [], [(b.x, b.y)]
            seen.add(i)
            while todo:
                x, y = todo.pop()
                group.append(at[(x, y)])
                for nx, ny in ((x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy):
                    j = at.get((nx, ny))
                    if j is not None and j not in seen:
                        seen.add(j)
                        todo.append((nx, ny))
            groups.append(sorted(group))
        return groups

    def barricade_at(self, x, y):
        """The index of the barricade in cell (x, y), or None."""
        return next((i for i, b in enumerate(self.barricades) if (b.x, b.y) == (x, y)), None)

    def enemy_named(self, name):
        return next((e for e in self.enemies if e.name == name), None)

    def uses_money(self):
        """True if money means anything on this map (so the HUD shows it): its settings use it, or an item is for
        sale."""
        return self.settings.uses_money() or any(e.price > 0 for e in self.entities)

    def uses_score(self):
        """True if score means anything on this map (so the HUD shows it): something earns it (knocking out an
        opponent, a score item, a barricade boarded up for score) or the buy menu costs it."""
        rules = self.settings
        return ((rules.kill_score > 0 and rules.mode not in ("coop", "zombies"))
                or (rules.buy_menu and rules.buy_cost == "score")
                or any(e.effect == "score" for e in self.entities)
                or (rules.mode == "zombies" and any(b.reward_kind == "score" and b.reward > 0
                                                    for b in self.barricades)))

    def prefab_named(self, name):
        for prefab in self.prefabs:
            if prefab.name == name:
                return prefab
        return None

    def apply_prefabs(self):
        """Give every item placed from a prefab that prefab's settings (everything but its place). An item
        whose prefab no longer exists is detached: it keeps the settings it last had."""
        for e in self.entities:
            if not e.prefab:
                continue
            prefab = self.prefab_named(e.prefab)
            if prefab is None:
                e.prefab = ""
                continue
            for key in PREFAB_FIELDS:
                setattr(e, key, getattr(prefab, key))
            e.animations = [replace(a) for a in prefab.animations]

    def light_named(self, name):
        """The Light with that name, or None (an empty or unknown name is no light)."""
        for light in self.lights:
            if light.name == name:
                return light
        return None

    def effect_named(self, name):
        """The Effect with that name, or None (an empty or unknown name is no effect)."""
        for effect in self.effects:
            if effect.name == name:
                return effect
        return None

    def ammo_for(self, gun):
        """The AmmoType a gun fires. A gun that names none (or one that no longer exists) fires a plain
        default bullet."""
        for kind in self.ammo_types:
            if kind.name == gun.ammo:
                return kind
        return AmmoType(name=gun.ammo or "Bullet")

    # ----------------------------------------------------------- floors

    @property
    def floor_count(self):
        return len(self.names)

    def grid_names(self):
        """Every stored grid, in file order."""
        return list(SHARED_LAYERS) + [grid_name(layer, f) for f in range(self.floor_count)
                                      for layer in SPAN_LAYERS]

    def _fill_floor(self, floor):
        for layer in SPAN_LAYERS:
            name = grid_name(layer, floor)
            self.grids[name] = [[default_for(name)] * self.width for _ in range(self.height)]

    def _unique_name(self, name, floor):
        """Trim a floor name and make it differ from the other floors' names."""
        name = (name or "").strip()[:MAX_NAME_LENGTH] or default_floor_name(floor)
        others = [n for i, n in enumerate(self.names) if i != floor]
        base, suffix = name, 2
        while name in others:
            name, suffix = f"{base[:MAX_NAME_LENGTH - 3]} {suffix}", suffix + 1
        return name

    def add_floor(self, name=None):
        """Add an empty floor above the existing ones; returns its index."""
        index = self.floor_count
        self.names.append("")
        self._fill_floor(index)
        self.names[index] = self._unique_name(name, index)
        return index

    def remove_floor(self, floor):
        """Delete a floor above the ground floor; floors above it move down one index."""
        if not 1 <= floor < self.floor_count:
            raise ValueError("only floors above the ground floor can be removed")
        for f in range(floor, self.floor_count - 1):
            for layer in SPAN_LAYERS:
                self.grids[grid_name(layer, f)] = self.grids[grid_name(layer, f + 1)]
        for layer in SPAN_LAYERS:
            del self.grids[grid_name(layer, self.floor_count - 1)]
        del self.names[floor]
        self.entities = [e.clone(span=e.span - 1 if e.span > floor else e.span)
                         for e in self.entities if e.span != floor]
        wall_floor, masks = self.grids["wall_floor"], self.grids["wall_floors"]
        for y, row in enumerate(wall_floor):        # walls that began above the removed floor follow it down
            for x, value in enumerate(row):
                row[x] = min(value - 1 if value > floor else value, self.floor_count - 1)
                mask = masks[y][x]
                if mask:                            # the floors a wall fills lose the removed one
                    low = mask & ((1 << floor) - 1)
                    self.set_wall_floors(x, y, low | (mask >> (floor + 1) << floor))
        if self.start_span == floor:
            self.start_span = 0
        elif self.start_span > floor:
            self.start_span -= 1
        self.spawners = [replace(s, span=s.span - 1 if s.span > floor else s.span)
                         for s in self.spawners if s.span != floor]

    def rename_floor(self, floor, name):
        """Rename a floor; returns the name actually used (trimmed, and made unique)."""
        if not name.strip():
            return self.names[floor]                # an empty name keeps the old one
        self.names[floor] = self._unique_name(name, floor)
        return self.names[floor]

    # ----------------------------------------------------------- access

    @property
    def walls(self):
        return self.grids["walls"]

    @property
    def width(self):
        return len(self.walls[0])

    @property
    def height(self):
        return len(self.walls)

    def in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, layer, x, y):
        """Value of a grid's cell; outside the map it reads as a wall / the grid default."""
        if self.in_bounds(x, y):
            return self.grids[layer][y][x]
        return SOLID_OUTSIDE if layer == "walls" else default_for(layer)

    def set(self, layer, x, y, value):
        if self.in_bounds(x, y):
            self.grids[layer][y][x] = value

    def is_solid(self, x, y, span=0):
        """True if a wall blocks this cell on the given floor (outside the map: always)."""
        if not self.in_bounds(x, y):
            return True
        return bool(self.wall_mask(x, y) >> span & 1)

    def wall_mask(self, x, y):
        """The floors the wall in this cell fills, as bits (bit N: floor N); 0 for no wall."""
        if not self.walls[y][x]:
            return 0
        mask = self.grids["wall_floors"][y][x]
        if mask:
            return mask
        low = self.grids["wall_floor"][y][x]           # an older map's wall: its floor and every one above
        return ((1 << self.floor_count) - 1) >> low << low

    def set_wall_floors(self, x, y, mask):
        """Make the wall in this cell fill the floors in `mask` (bits); none removes the wall."""
        mask &= (1 << self.floor_count) - 1
        if not mask:
            for layer in WALL_LAYERS + ("wall_floor", "wall_floors"):
                self.set(layer, x, y, default_for(layer))
            return
        self.set("wall_floors", x, y, mask)
        self.set("wall_floor", x, y, (mask & -mask).bit_length() - 1)

    def wall_floor(self, x, y):
        """Lowest floor a wall in this cell reaches (0 for a wall from the ground)."""
        return self.get("wall_floor", x, y)

    def wall_region(self, x, y):
        """The connected group (4-neighbor) of wall cells that (x, y) belongs to, whatever their
        textures; empty if (x, y) is not a wall."""
        if not self.in_bounds(x, y) or not self.walls[y][x]:
            return []
        seen, stack, cells = set(), [(x, y)], []
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in seen or not self.in_bounds(cx, cy) or not self.walls[cy][cx]:
                continue
            seen.add((cx, cy))
            cells.append((cx, cy))
            stack.extend(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)))
        return cells

    def _beside(self, x, y, layer):
        """Values of a ground-floor grid in the open cells beside a wall cell: the four next to it,
        or if there are none the eight around it. Empty if the wall is boxed in by other walls."""
        for offsets in (((1, 0), (-1, 0), (0, 1), (0, -1)),
                        ((1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1))):
            values = [self.grids[layer][y + dy][x + dx] for dx, dy in offsets
                      if self.in_bounds(x + dx, y + dy) and not self.walls[y + dy][x + dx]]
            if values:
                return values
        return []

    def wall_ceiling(self, x, y):
        """The ceiling above a wall cell, for a wall that stops short of it. It is the value set in
        wall_ceil if there is one; otherwise (automatic) the highest ceiling of the open cells beside
        it, so a short wall in a tall hall has the hall's ceiling over it. A wall with no open
        neighbor falls back to its own ceil_h. The ceil_h stored under a wall is otherwise never
        used: like the floor under a wall, you cannot see it, so it must not decide anything."""
        explicit = self.grids["wall_ceil"][y][x]
        if explicit > 0:
            return explicit
        return self.auto_wall_ceiling(x, y)

    def auto_wall_ceiling(self, x, y):
        """What wall_ceiling gives when nothing is set: the highest ceiling beside the wall."""
        values = self._beside(x, y, "ceil_h")
        return max(values) if values else self.grids["ceil_h"][y][x]

    def has_explicit_wall_ceiling(self, x, y):
        return self.in_bounds(x, y) and bool(self.walls[y][x]) and self.grids["wall_ceil"][y][x] > 0

    def wall_base(self, x, y):
        """The height a wall stands on: the lowest floor of the open cells beside it, so a short
        wall stands on the room's floor (and on a platform when the whole spot around it is a
        platform). The floor value stored under the wall itself is never used, because you cannot
        see it in the editor. A wall boxed in by other walls uses its own floor value."""
        values = self._beside(x, y, "floor_h")
        return min(values) if values else self.grids["floor_h"][y][x]

    def short_wall_top(self, x, y):
        """Absolute height of the top of a wall that is shorter than the room around it, or None
        for a full-height wall. The height in wall_h is measured up from wall_base; 0, or a height
        that reaches the ceiling beside the wall, means a full-height wall."""
        if not self.in_bounds(x, y) or not self.walls[y][x]:
            return None
        if self.grids["wall_floor"][y][x]:
            return self.upper_wall_top(x, y)
        height = self.grids["wall_h"][y][x]
        if height <= 0:
            return None
        top = self.wall_base(x, y) + height
        return top if top < self.wall_ceiling(x, y) - MIN_WALL_GAP else None

    def upper_wall_ceiling(self, x, y):
        """Ceiling over a wall that starts on a higher floor: the highest ceiling of the rooms beside
        it on that floor, or None if it has none."""
        f = self.grids["wall_floor"][y][x]
        values = [self.grids[grid_name("ceil_h", f)][y + dy][x + dx]
                  for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if self.span_present(f, x + dx, y + dy)]
        return max(values) if values else None

    def upper_wall_full_top(self, x, y):
        """Where a full-height wall that starts on a higher floor ends: the ceiling beside it on that
        floor, or, with no room there, the ceiling of the room below it."""
        above = self.upper_wall_ceiling(x, y)
        return above if above is not None else self.grids["ceil_h"][y][x]

    def upper_wall_top(self, x, y):
        """Absolute top of a wall that starts on a higher floor, or None for a full-height one. The
        base is that floor's floor height there. wall_h (WallH layer) is measured up from the base;
        failing that, the ceiling height stored on the wall's floor (CeilH layer) is the top itself."""
        f = self.grids["wall_floor"][y][x]
        base = self.grids[grid_name("floor_h", f)][y][x]
        ceiling = self.upper_wall_ceiling(x, y)
        height = self.grids["wall_h"][y][x]
        top = base + height if height > 0 else self.grids[grid_name("ceil_h", f)][y][x]
        if top <= base + MIN_WALL_GAP:
            return None
        if ceiling is None:                     # no room beside it on this floor: it floats, open above
            return top
        return top if top < ceiling - MIN_WALL_GAP else None

    def wall_top_at(self, x, y, span=0):
        """Height of the top of the wall in this cell as seen from a floor, or None if there is no
        wall there on that floor. A short wall's top is its height; a full-height wall reaches the
        ceiling beside it. (Things such as items can stand on top of a wall.)"""
        if not self.in_bounds(x, y) or not self.is_solid(x, y, span):
            return None
        if self.grids["wall_floor"][y][x]:
            top = self.upper_wall_top(x, y)
            return top if top is not None else self.upper_wall_full_top(x, y)
        top = self.short_wall_top(x, y)
        return top if top is not None else self.wall_ceiling(x, y)

    def span_present(self, span, x, y):
        """True if the cell has an open room on that floor."""
        if not self.in_bounds(x, y) or not 0 <= span < self.floor_count or self.is_solid(x, y, span):
            return False
        if span == 0:
            return True
        return self.grids[grid_name("ceil_h", span)][y][x] > self.grids[grid_name("floor_h", span)][y][x]

    def rooms_at(self, x, y):
        """Indices of the floors that have a room in this cell, lowest first."""
        return [s for s in range(self.floor_count) if self.span_present(s, x, y)]

    # ----------------------------------------------------------- editing helpers

    def resize(self, width, height):
        """Grow or shrink, keeping existing cells at the top-left. New cells get defaults."""
        width, height = max(3, width), max(3, height)
        old_w, old_h = self.width, self.height      # read before the grids change size
        for name in self.grid_names():
            old = self.grids[name]
            fill = default_for(name)
            self.grids[name] = [
                [old[y][x] if x < old_w and y < old_h else fill for x in range(width)]
                for y in range(height)
            ]
        self.start_x = min(self.start_x, width - 0.5)
        self.start_y = min(self.start_y, height - 0.5)
        self.entities = [e for e in self.entities if e.x < width and e.y < height]
        self.spawners = [s for s in self.spawners if s.x < width and s.y < height]
        self.barricades = [b for b in self.barricades if b.x < width and b.y < height]
        self.doors = [replace(d, width=min(d.width, width - d.x), height=min(d.height, height - d.y))
                      for d in self.doors if d.x < width and d.y < height]
        self.interacts = [i for i in self.interacts if i.x < width and i.y < height]

    def resize_edges(self, left=0, right=0, top=0, bottom=0):
        """Add (positive) or remove (negative) columns and rows along each side, keeping the cells
        that remain where they are relative to each other, and the start where it was on the map.
        New cells get defaults. Never shrinks below 3 x 3: a side asking for more than is
        available gives up what it can."""
        left, right = self._fit_sides(left, right, self.width)
        top, bottom = self._fit_sides(top, bottom, self.height)
        width, height = self.width + left + right, self.height + top + bottom
        old_w, old_h = self.width, self.height
        for name in self.grid_names():
            old, fill = self.grids[name], default_for(name)
            self.grids[name] = [
                [old[y - top][x - left] if 0 <= x - left < old_w and 0 <= y - top < old_h else fill
                 for x in range(width)]
                for y in range(height)
            ]
        self.start_x = min(max(self.start_x + left, 0.5), width - 0.5)
        self.start_y = min(max(self.start_y + top, 0.5), height - 0.5)
        self.entities = [e.clone(x=e.x + left, y=e.y + top) for e in self.entities
                         if 0 <= e.x + left < width and 0 <= e.y + top < height]
        self.spawners = [replace(s, x=s.x + left, y=s.y + top) for s in self.spawners
                         if 0 <= s.x + left < width and 0 <= s.y + top < height]
        self.barricades = [replace(b, x=b.x + left, y=b.y + top) for b in self.barricades
                           if 0 <= b.x + left < width and 0 <= b.y + top < height]
        self.interacts = [replace(i, x=i.x + left, y=i.y + top) for i in self.interacts
                          if 0 <= i.x + left < width and 0 <= i.y + top < height]
        self.doors = [replace(d, x=d.x + left, y=d.y + top) for d in self.doors
                      if 0 <= d.x + left and d.x + left + d.width <= width
                      and 0 <= d.y + top and d.y + top + d.height <= height]
        return left, top

    @staticmethod
    def _fit_sides(first, second, size):
        """Trim a pair of side changes so that the size stays at least 3."""
        excess = 3 - (size + first + second)
        if excess > 0:                      # only shrinking can get here; give some back
            first += min(excess, max(0, -first))
            excess = 3 - (size + first + second)
            second += min(excess, max(0, -second)) if excess > 0 else 0
        return first, second

    def fill_border(self, value):
        grid = self.walls
        for x in range(self.width):
            grid[0][x] = grid[-1][x] = value
        for y in range(self.height):
            grid[y][0] = grid[y][-1] = value

    def region(self, layer, x, y):
        """The connected region (4-neighbor) of cells equal to (x, y) in a grid, unchanged."""
        grid = self.grids[layer]
        if not self.in_bounds(x, y):
            return []
        target, stack, seen, cells = grid[y][x], [(x, y)], set(), []
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in seen or not self.in_bounds(cx, cy) or grid[cy][cx] != target:
                continue
            seen.add((cx, cy))
            cells.append((cx, cy))
            stack.extend(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)))
        return cells

    def flood_fill_cells(self, layer, x, y, value):
        """Replace the connected region of equal cells with value; returns the changed cells."""
        if not self.in_bounds(x, y) or self.grids[layer][y][x] == value:
            return []
        cells = self.region(layer, x, y)
        for cx, cy in cells:
            self.grids[layer][cy][cx] = value
        return cells

    def flood_fill(self, layer, x, y, value):
        """Like flood_fill_cells, returning only how many cells changed."""
        return len(self.flood_fill_cells(layer, x, y, value))

    # ----------------------------------------------------------- derived geometry

    def floor_planes(self, span=0):
        """Floor surface of every cell of a floor as (a, bx, by): height = a + bx * fx + by * fy
        over the cell's local coordinates fx, fy in [0, 1]. Returns (planes[y][x], problems).

        Flat cells are (floor_h, 0, 0). Each run of ramp cells becomes a slope.
        """
        planes, issues = self._floor_planes(span)
        return planes, [message for message, _cell in issues]

    def _floor_planes(self, span):
        """floor_planes, with each problem paired with the cell it is about."""
        w, h = self.width, self.height
        floor = self.grids[grid_name("floor_h", span)]
        ramp = self.grids[grid_name("ramp", span)]
        planes = [[(floor[y][x], 0.0, 0.0) for x in range(w)] for y in range(h)]
        problems = []

        def is_ramp(x, y, kind):
            return self.in_bounds(x, y) and ramp[y][x] == kind

        for y in range(h):
            for x in range(w):
                kind = ramp[y][x]
                if kind not in RAMP_DIRS or not self.span_present(span, x, y):
                    continue
                dx, dy = RAMP_DIRS[kind]
                sx, sy = x, y                       # start of the run (low end)
                while is_ramp(sx - dx, sy - dy, kind):
                    sx, sy = sx - dx, sy - dy
                ex, ey = x, y                       # end of the run (high end)
                while is_ramp(ex + dx, ey + dy, kind):
                    ex, ey = ex + dx, ey + dy
                before, after = (sx - dx, sy - dy), (ex + dx, ey + dy)
                if any(not self.span_present(span, *c) or ramp[c[1]][c[0]] for c in (before, after)):
                    problems.append((f"ramp at ({x}, {y}) on {self.names[span]} needs an open, "
                                     "non-ramp cell at both ends", (x, y)))
                    continue
                n = abs(ex - sx) + abs(ey - sy) + 1
                i = abs(x - sx) + abs(y - sy)       # index of this cell within the run
                low, high = floor[before[1]][before[0]], floor[after[1]][after[0]]
                k = (high - low) / n
                if dx > 0:
                    planes[y][x] = (low + k * i, k, 0.0)
                elif dx < 0:
                    planes[y][x] = (low + k * (i + 1), -k, 0.0)
                elif dy > 0:
                    planes[y][x] = (low + k * i, 0.0, k)
                else:
                    planes[y][x] = (low + k * (i + 1), 0.0, -k)
        return planes, problems

    def issues(self):
        """Problems that would break or confuse the game, as (message, cell) pairs. The cell
        is the (x, y) the problem is about, or None."""
        found = []
        places = [("start position", self.start_x, self.start_y, self.start_span)]
        places += [(f"spawner {i + 1} (order {s.order})", s.x, s.y, s.span) for i, s in enumerate(self.spawners)]
        places += [(f"barricade {i + 1}", b.x + 0.5, b.y + 0.5, 0) for i, b in enumerate(self.barricades)]
        for what, x, y, span in places:
            sx, sy = int(x), int(y)
            if self.is_solid(sx, sy, span):
                found.append((f"{what} is inside a wall", (sx, sy)))
            elif not self.span_present(span, sx, sy):
                found.append((f"{what} has no floor here on the chosen floor", (sx, sy)))
            else:
                lo = self.grids[grid_name("floor_h", span)][sy][sx]
                hi = self.grids[grid_name("ceil_h", span)][sy][sx]
                if hi - lo < PLAYER_HEIGHT:
                    found.append((f"{what} is too low for the player to fit", (sx, sy)))

        results = [self._floor_planes(s) for s in range(self.floor_count)]
        for y in range(self.height):
            for x in range(self.width):
                if self.is_solid(x, y):
                    continue
                if self.grids["ceil_h"][y][x] <= self.grids["floor_h"][y][x]:
                    found.append((f"ceiling is not above the floor at ({x}, {y})", (x, y)))
                below = 0                                     # highest room below the current floor
                for s in range(1, self.floor_count):
                    if not self.span_present(s, x, y):
                        continue
                    a, bx, by = results[s][0][y][x]
                    lowest = a + min(0.0, bx) + min(0.0, by)  # plane minimum over the cell
                    if lowest < self.grids[grid_name("ceil_h", below)][y][x]:
                        found.append((f"{self.names[s]} floor is below the ceiling of "
                                      f"{self.names[below]} at ({x}, {y})", (x, y)))
                    below = s
        for _planes, ramp_issues in results:
            found.extend(ramp_issues)
        return found

    def problems(self):
        """Human-readable problems that would break or confuse the game."""
        return [message for message, _cell in self.issues()]

    def problem_cells(self):
        """The cells that have a problem, for highlighting in the editor."""
        return {cell for _message, cell in self.issues() if cell is not None}


# --------------------------------------------------------------------------- files

def default_level():
    rows = [
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
        [1, 0, 2, 2, 0, 0, 3, 3, 0, 1],
        [1, 0, 2, 0, 0, 0, 0, 3, 0, 1],
        [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
        [1, 0, 0, 4, 4, 0, 0, 0, 0, 1],
        [1, 0, 0, 0, 0, 0, 2, 0, 0, 1],
        [1, 0, 3, 0, 0, 0, 2, 0, 0, 1],
        [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    ]
    level = Level.blank(10, 10, border=0)
    level.grids["walls"] = rows
    level.start_x, level.start_y = 1.5, 4.5
    return level


def load_level(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return parse_level(data, path)


def parse_level(data, label="level"):
    """The Level for the JSON data of a map file (already parsed). `label` names it in error messages."""
    path = label
    if "grids" in data:
        raw = data["grids"]
    else:                                           # version 1: only the walls grid
        raw = {"walls": data["cells"]}
    walls = [[int(v) for v in row] for row in raw["walls"]]
    if not walls or any(len(row) != len(walls[0]) for row in walls):
        raise ValueError(f"{path}: 'walls' must be a non-empty rectangular grid")
    w, h = len(walls[0]), len(walls)

    names = data.get("floors")
    if names:
        count = len(names)
    else:                                           # older files: floors are those that have grids
        count = 1
        while f"floor_h{count + 1}" in raw:
            count += 1
        names = [default_floor_name(i) for i in range(count)]
    grids = {"walls": walls}
    level = Level(grids, names=[str(n)[:MAX_NAME_LENGTH] or default_floor_name(i)
                                for i, n in enumerate(names)])
    for name in level.grid_names()[1:]:             # grids missing from the file take defaults
        grid = raw.get(name)
        cast = type(default_for(name))
        if grid is None:
            grid = [[default_for(name)] * w for _ in range(h)]
        if len(grid) != h or any(len(row) != w for row in grid):
            raise ValueError(f"{path}: grid '{name}' must be {w}x{h} like 'walls'")
        grids[name] = [[cast(v) for v in row] for row in grid]
    grids["wall_floor"] = [[max(0, min(v, count - 1)) for v in row] for row in grids["wall_floor"]]
    for y, row in enumerate(grids["wall_floors"]):  # (a mask may name floors the file does not have)
        for x, mask in enumerate(row):
            if mask and walls[y][x]:
                level.set_wall_floors(x, y, max(0, mask))
    start = data.get("start", {})
    level.start_x, level.start_y = float(start.get("x", 1.5)), float(start.get("y", 1.5))
    level.start_angle = float(start.get("angle", 0.0))
    level.start_span = min(int(start.get("span", 0)), count - 1)
    for item in data.get("spawners", []):
        if isinstance(item, dict):
            spawner = Spawner.from_dict(item)
            if 0 <= spawner.x < w and 0 <= spawner.y < h and spawner.span < count:
                level.spawners.append(spawner)
    for item in data.get("entities", []):
        entity = Entity.from_dict(item)
        if 0 <= entity.x < w and 0 <= entity.y < h and entity.span < count:
            level.entities.append(entity)
    for item in data.get("ammo_types", []):
        if isinstance(item, dict):
            level.ammo_types.append(AmmoType.from_dict(item))
    for item in data.get("guns", []):
        if not isinstance(item, dict):
            continue
        gun = Gun.from_dict(item)
        if "ammo_types" not in data and any(k.startswith("proj_") for k in item):
            # An older map kept the bullet on the gun: each gun gets an ammo type of its own from it.
            names = {a.name for a in level.ammo_types}
            name, n = f"{gun.name} ammo"[:MAX_NAME], 2
            while name in names:
                name, n = f"{gun.name} ammo {n}"[:MAX_NAME], n + 1
            level.ammo_types.append(AmmoType.from_dict({
                "name": name, "tile": item.get("proj_tile", 14), "size": item.get("proj_size", 0.1),
                "speed": item.get("proj_speed", 18.0), "range": item.get("proj_range", 20.0)}))
            gun.ammo = name
        level.guns.append(gun)
    try:
        level.ambient = max(MIN_AMBIENT, min(1.0, float(data.get("ambient", 1.0))))
    except (TypeError, ValueError):
        level.ambient = 1.0
    for item in data.get("lights", []):
        if isinstance(item, dict):
            light = Light.from_dict(item)
            if level.light_named(light.name) is None:
                level.lights.append(light)
    for item in data.get("effects", []):
        if isinstance(item, dict):
            effect = Effect.from_dict(item)
            if level.effect_named(effect.name) is None:
                level.effects.append(effect)
    for item in data.get("prefabs", []):
        if isinstance(item, dict) and "x" in item:
            prefab = Entity.from_dict(item)
            if prefab.name and level.prefab_named(prefab.name) is None:
                prefab.prefab = ""
                level.prefabs.append(prefab)
    for entity in level.entities:                   # ammo pickups used to name a gun, not an ammo type
        if entity.effect == "ammo" and not entity.ammo and entity.gun:
            entity.ammo = next((g.ammo for g in level.guns if g.name == entity.gun), "")
    for item in data.get("enemies", []):
        if isinstance(item, dict) and len(level.enemies) < MAX_ENEMIES:
            enemy = Enemy.from_dict(item)
            if level.enemy_named(enemy.name) is None:
                level.enemies.append(enemy)
    for key, cls, most, named in (("interacts", Interact, MAX_INTERACTS, "interact_named"),
                                  ("counters", Counter, MAX_COUNTERS, "counter_named")):
        for item in data.get(key, []):
            try:
                thing = cls.from_dict(item)
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            if len(getattr(level, key)) < most and getattr(level, named)(thing.name) is None:
                getattr(level, key).append(thing)
    for item in data.get("triggers", []):
        if isinstance(item, dict) and len(level.triggers) < MAX_TRIGGERS:
            level.triggers.append(Trigger.from_dict(item))
    for item in data.get("door_kinds", []):
        if isinstance(item, dict):
            kind = DoorKind.from_dict(item)
            if level.door_kind_named(kind.name) is None:
                level.door_kinds.append(kind)
    for item in data.get("doors", []):
        try:
            door = Door.from_dict(item)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if (len(level.doors) < MAX_DOORS and level.in_bounds(door.x, door.y) and level.door_named(door.name) is None
                and not any(level.door_at(x, y) is not None for x, y in door.cells())):
            door.width = min(door.width, level.width - door.x)
            door.height = min(door.height, level.height - door.y)
            level.doors.append(door)
    for item in data.get("barricade_kinds", []):
        if isinstance(item, dict):
            kind = BarricadeKind.from_dict(item)
            if level.barricade_kind_named(kind.name) is None:
                level.barricade_kinds.append(kind)
    for item in data.get("barricades", []):
        try:
            barricade = Barricade.from_dict(item)
        except (KeyError, TypeError, ValueError):
            continue
        if level.in_bounds(barricade.x, barricade.y) and level.barricade_at(barricade.x, barricade.y) is None:
            level.barricades.append(barricade)
    level.settings = MapSettings.from_dict(data.get("settings", {}))
    level.apply_prefabs()
    level.apply_barricade_kinds()
    level.apply_door_kinds()
    return level


def save_level(path, level):
    with open(path, "w", encoding="utf-8") as f:
        f.write(level_text(level))


def level_text(level):
    """The map file's JSON as text, with one grid row per line so it is easy to read and diff."""
    blocks = []
    for name in level.grid_names():
        if (name in SIDE_LAYERS + SIDE_BAND_LAYERS or split_grid_name(name)[0] == "site") \
                and not any(any(row) for row in level.grids[name]):
            continue                                # (no wall has a texture of its own on that side; no site)
        rows = ",\n".join("      " + json.dumps(row) for row in level.grids[name])
        blocks.append(f'    "{name}": [\n{rows}\n    ]')
    start = {"x": level.start_x, "y": level.start_y, "angle": level.start_angle,
             "span": level.start_span}
    text = (
        f'{{\n  "version": {FORMAT_VERSION},\n'
        f'  "width": {level.width},\n  "height": {level.height},\n'
        f'  "floors": {json.dumps(level.names)},\n'
        f'  "start": {json.dumps(start)},\n'
        + (f'  "settings": {json.dumps(level.settings.to_dict())},\n' if level.settings != MapSettings() else "")
        + ('  "spawners": [\n' + ",\n".join("    " + json.dumps(asdict(s)) for s in level.spawners) + "\n  ],\n"
           if level.spawners else "")
        + ('  "entities": [\n' + ",\n".join("    " + json.dumps(asdict(e)) for e in level.entities) + "\n  ],\n"
           if level.entities else "")
        + ('  "ammo_types": [\n' + ",\n".join("    " + json.dumps(asdict(a)) for a in level.ammo_types) + "\n  ],\n"
           if level.ammo_types else "")
        + ('  "guns": [\n' + ",\n".join("    " + json.dumps(asdict(g)) for g in level.guns) + "\n  ],\n"
           if level.guns else "")
        + (f'  "ambient": {level.ambient:g},\n' if level.ambient < 1.0 else "")
        + ('  "lights": [\n' + ",\n".join("    " + json.dumps(asdict(light)) for light in level.lights) + "\n  ],\n"
           if level.lights else "")
        + ('  "effects": [\n' + ",\n".join("    " + json.dumps(asdict(f)) for f in level.effects) + "\n  ],\n"
           if level.effects else "")
        + ('  "prefabs": [\n' + ",\n".join("    " + json.dumps(asdict(p)) for p in level.prefabs) + "\n  ],\n"
           if level.prefabs else "")
        + ('  "enemies": [\n' + ",\n".join("    " + json.dumps(asdict(e)) for e in level.enemies) + "\n  ],\n"
           if level.enemies else "")
        + ('  "interacts": [\n' + ",\n".join("    " + json.dumps(asdict(i)) for i in level.interacts) + "\n  ],\n"
           if level.interacts else "")
        + ('  "counters": [\n' + ",\n".join("    " + json.dumps(asdict(c)) for c in level.counters) + "\n  ],\n"
           if level.counters else "")
        + ('  "triggers": [\n' + ",\n".join("    " + json.dumps(asdict(t)) for t in level.triggers) + "\n  ],\n"
           if level.triggers else "")
        + ('  "door_kinds": [\n' + ",\n".join("    " + json.dumps(asdict(k)) for k in level.door_kinds)
           + "\n  ],\n" if level.door_kinds else "")
        + ('  "doors": [\n' + ",\n".join("    " + json.dumps(asdict(d)) for d in level.doors) + "\n  ],\n"
           if level.doors else "")
        + ('  "barricade_kinds": [\n' + ",\n".join("    " + json.dumps(asdict(k)) for k in level.barricade_kinds)
           + "\n  ],\n" if level.barricade_kinds else "")
        + ('  "barricades": [\n' + ",\n".join("    " + json.dumps(asdict(b)) for b in level.barricades) + "\n  ],\n"
           if level.barricades else "") +
        '  "grids": {\n' + ",\n".join(blocks) + "\n  }\n}\n"
    )
    return text


# --------------------------------------------------------------------------- copying an area of one floor

WALL_LAYERS = ("walls", "wall_h", "wall_ceil") + SIDE_LAYERS + SIDE_BAND_LAYERS   # what a wall carries with it


@dataclass
class Area:
    """A rectangle of one floor copied out of a map, to paste elsewhere (on any floor, in any map).

    It holds what belongs to that floor only: its span grids (floor and ceiling textures and heights, ramps) and
    the walls on it (their tile, height, the ceiling over them and their sides), and the items and spawn
    points standing on it. Walls of other floors - and an older map's ground-floor wall, which fills every floor
    above it - are not part of it. Positions are relative to the area's top-left cell."""
    width: int
    height: int
    floor: int                                  # the floor it was copied from
    span: dict = field(default_factory=dict)    # span layer -> rows of values
    walls: dict = field(default_factory=dict)   # (dx, dy) -> {wall layer: value} of the walls in it
    entities: list = field(default_factory=list)
    spawners: list = field(default_factory=list)
    barricades: list = field(default_factory=list)      # (only ever on the ground floor)


def area_rect(level, a, b):
    """(x0, y0, x1, y1): the cells between corners a and b (inclusive, either way round), kept inside the map."""
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    return max(0, x0), max(0, y0), min(level.width - 1, x1), min(level.height - 1, y1)


def _starts_on(level, x, y, floor):
    """True if the cell holds a wall that belongs to `floor`: one painted on it, or an older map's wall that starts
    on it (the walls a floor owns)."""
    if not level.walls[y][x]:
        return False
    if level.grids["wall_floors"][y][x]:
        return bool(level.grids["wall_floors"][y][x] >> floor & 1)
    return level.wall_floor(x, y) == floor


def _drop_floor(level, x, y, floor):
    """Take `floor` out of the floors the wall in this cell fills (the whole wall, for an older map's wall)."""
    mask = level.grids["wall_floors"][y][x]
    level.set_wall_floors(x, y, mask & ~(1 << floor) if mask else 0)


def _in(thing, x0, y0, x1, y1, floor):
    return thing.span == floor and x0 <= math.floor(thing.x) <= x1 and y0 <= math.floor(thing.y) <= y1


def _barricade_in(barricade, x0, y0, x1, y1, floor):
    return floor == 0 and x0 <= barricade.x <= x1 and y0 <= barricade.y <= y1


def copy_area(level, a, b, floor):
    """The Area of `floor` between cells a and b."""
    x0, y0, x1, y1 = area_rect(level, a, b)
    area = Area(x1 - x0 + 1, y1 - y0 + 1, floor)
    for layer in SPAN_LAYERS:
        grid = level.grids[grid_name(layer, floor)]
        area.span[layer] = [row[x0:x1 + 1] for row in grid[y0:y1 + 1]]
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if _starts_on(level, x, y, floor):
                area.walls[(x - x0, y - y0)] = {layer: level.grids[layer][y][x] for layer in WALL_LAYERS}
    area.entities = [e.clone(x=e.x - x0, y=e.y - y0) for e in level.entities if _in(e, x0, y0, x1, y1, floor)]
    area.spawners = [replace(s, x=s.x - x0, y=s.y - y0) for s in level.spawners if _in(s, x0, y0, x1, y1, floor)]
    area.barricades = [replace(b, x=b.x - x0, y=b.y - y0) for b in level.barricades
                       if _barricade_in(b, x0, y0, x1, y1, floor)]
    return area


def clear_area(level, a, b, floor):
    """Empty `floor` between cells a and b: its span grids back to the floor's defaults (no room on a higher floor),
    its walls, items and spawn points gone. Other floors' walls stay."""
    x0, y0, x1, y1 = area_rect(level, a, b)
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            for layer in SPAN_LAYERS:
                name = grid_name(layer, floor)
                level.set(name, x, y, default_for(name))
            if _starts_on(level, x, y, floor):
                _drop_floor(level, x, y, floor)
    level.entities = [e for e in level.entities if not _in(e, x0, y0, x1, y1, floor)]
    level.spawners = [s for s in level.spawners if not _in(s, x0, y0, x1, y1, floor)]
    level.barricades = [b for b in level.barricades if not _barricade_in(b, x0, y0, x1, y1, floor)]


def paste_area(level, area, x, y, floor):
    """Put `area` onto `floor` with its top-left cell at (x, y), in place of what that floor had there (cells off the
    map are left out). Its walls start on `floor`; a wall of this floor where the area has none goes; walls of other
    floors stay. Items and spawn points that stood there on this floor make way for the area's."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(level.width - 1, x + area.width - 1), min(level.height - 1, y + area.height - 1)
    if x1 < x0 or y1 < y0:
        return
    level.entities = [e for e in level.entities if not _in(e, x0, y0, x1, y1, floor)]
    level.spawners = [s for s in level.spawners if not _in(s, x0, y0, x1, y1, floor)]
    level.barricades = [b for b in level.barricades if not _barricade_in(b, x0, y0, x1, y1, floor)]
    for cy in range(y0, y1 + 1):
        for cx in range(x0, x1 + 1):
            dx, dy = cx - x, cy - y
            for layer in SPAN_LAYERS:
                level.set(grid_name(layer, floor), cx, cy, area.span[layer][dy][dx])
            wall = area.walls.get((dx, dy))
            if wall is not None:
                if level.is_solid(cx, cy, floor) and not _starts_on(level, cx, cy, floor):
                    continue                            # (an older map's lower wall already fills this cell)
                mask = level.grids["wall_floors"][cy][cx] if level.walls[cy][cx] else 0
                for layer, value in wall.items():
                    level.set(layer, cx, cy, value)
                level.set_wall_floors(cx, cy, mask | 1 << floor)
            elif _starts_on(level, cx, cy, floor):
                _drop_floor(level, cx, cy, floor)
    inside = lambda t: x0 <= math.floor(t.x + x) <= x1 and y0 <= math.floor(t.y + y) <= y1
    level.entities += [e.clone(x=e.x + x, y=e.y + y, span=floor) for e in area.entities if inside(e)]
    level.spawners += [replace(s, x=s.x + x, y=s.y + y, span=floor) for s in area.spawners if inside(s)]
    if floor == 0:                                      # (a barricade only stands on the ground floor)
        level.barricades += [replace(b, x=b.x + x, y=b.y + y) for b in area.barricades
                             if x0 <= b.x + x <= x1 and y0 <= b.y + y <= y1]
    level.apply_prefabs()


# --------------------------------------------------------------------------- bringing things in from another map

IMPORT_KINDS = {"prefabs": "Prefabs", "lights": "Lights", "effects": "Effects", "guns": "Guns",
                "ammo_types": "Ammo types",
                "barricade_kinds": "Barricade types",
                "door_kinds": "Door types"}                 # what can be brought in from another map, and its label
IMPORT_ORDER = ("lights", "effects", "ammo_types", "guns", "prefabs",
                "barricade_kinds", "door_kinds")            # each kind only names kinds before it
REFERENCES = {                                              # the fields of each kind that name another thing
    "lights": (),
    "effects": (("light", "lights"),),
    "ammo_types": (("trail", "effects"), ("light", "lights"), ("player_hit_effects", "effects"),
                   ("player_hit_lights", "lights"), ("world_hit_effects", "effects"), ("world_hit_lights", "lights"),
                   ("explosion_effects", "effects"), ("explosion_lights", "lights")),
    "guns": (("ammo", "ammo_types"), ("muzzle", "effects"), ("flash", "lights")),
    "prefabs": (("light", "lights"), ("emits", "effects"), ("gun", "guns"), ("ammo", "ammo_types")),
    "barricade_kinds": (),
    "door_kinds": (),
}
TAKEN_CHOICES = ("keep", "replace", "copy")                 # what to do when an imported name is already used


def things_named(level, kind):
    """{name: the thing} of one kind (IMPORT_KINDS) in a level."""
    return {thing.name: thing for thing in getattr(level, kind)}


def references(thing, kind):
    """[(kind, name)] of the other things `thing` names (empty names left out)."""
    out = []
    for field_name, other in REFERENCES[kind]:
        value = getattr(thing, field_name)
        for name in (value if isinstance(value, (list, tuple)) else (value,)):
            if name:
                out.append((other, name))
    return out


def with_needs(source, picks):
    """`picks` ({(kind, name)}) and everything they name, and everything those name, as far as `source` has them."""
    found, todo = set(), list(picks)
    while todo:
        kind, name = todo.pop()
        thing = things_named(source, kind).get(name)
        if thing is None or (kind, name) in found:
            continue
        found.add((kind, name))
        todo += references(thing, kind)
    return found


@dataclass
class ImportResult:
    added: list = field(default_factory=list)       # (kind, name) brought in under their own name
    replaced: list = field(default_factory=list)    # (kind, name) that replaced this map's thing of that name
    kept: list = field(default_factory=list)        # (kind, name) left out: this map's thing of that name is used
    same: list = field(default_factory=list)        # (kind, name) this map already has, just the same
    renamed: dict = field(default_factory=dict)     # (kind, old name) -> new name, for copies of taken names
    needed: int = 0                                 # how many came in only because a picked thing names them

    def summary(self):
        count = len(self.added) + len(self.replaced) + len(self.renamed)
        parts = [f"Imported {count} thing{'s' if count != 1 else ''}"]
        if self.same:
            parts.append(f"{len(self.same)} already here")
        if self.needed:
            parts.append(f"{self.needed} of them needed by the ones picked")
        if self.replaced:
            parts.append(f"{len(self.replaced)} replaced")
        if self.renamed:
            parts.append(f"{len(self.renamed)} added as copies")
        if self.kept:
            parts.append(f"{len(self.kept)} kept as they were")
        return ", ".join(parts)


def unique_thing_name(name, taken):
    """`name` with " 2", " 3"... added until it is not in `taken` (kept within MAX_NAME)."""
    number = 2
    while True:
        suffix = f" {number}"
        candidate = name[:MAX_NAME - len(suffix)] + suffix
        if candidate not in taken:
            return candidate
        number += 1


def import_things(level, source, picks, taken="copy"):
    """Copy the things in `picks` ({(kind, name)}) from the level `source` into `level`, with everything they name
    (a prefab's light and effect, a gun's ammo type, an ammo type's effects...). A thing whose name `level` already
    uses is kept as it is ("keep": the import uses this map's one), replaces it ("replace") or comes in as a copy
    under a new name ("copy"), and the imported things that name it are changed to name the copy. A thing this map
    already has exactly the same is left as it is whatever `taken` says, and a copy is not made twice: one already
    here under another name (from an earlier import) is used instead. Returns what was done (ImportResult)."""
    result = ImportResult()
    wanted = with_needs(source, picks)
    result.needed = len(wanted - set(picks))
    copies = {}
    for kind in IMPORT_ORDER:
        mine = getattr(level, kind)
        for name in sorted(n for k, n in wanted if k == kind):
            thing = things_named(source, kind)[name]
            thing = thing.clone() if kind in ("prefabs", "barricade_kinds", "door_kinds") else replace(thing)
            existing = things_named(level, kind)
            if name in existing and taken == "keep":
                result.kept.append((kind, name))
                continue
            for field_name, other in REFERENCES[kind]:          # name the copies made above, not the originals
                value = getattr(thing, field_name)
                if isinstance(value, (list, tuple)):
                    setattr(thing, field_name, type(value)(copies.get((other, v), v) for v in value))
                else:
                    setattr(thing, field_name, copies.get((other, value), value))
            if name in existing and existing[name] == thing:
                result.same.append((kind, name))                    # nothing to bring in
                continue
            if name in existing and taken == "replace":
                mine[mine.index(existing[name])] = thing
                result.replaced.append((kind, name))
            elif name in existing:
                twin = next((t for t in mine if replace(t, name=name) == thing), None)
                if twin is not None:                                    # (an earlier import's copy, just the same)
                    copies[(kind, name)] = twin.name
                    result.same.append((kind, name))
                    continue
                thing.name = unique_thing_name(name, set(existing))
                copies[(kind, name)] = thing.name
                result.renamed[(kind, name)] = thing.name
                mine.append(thing)
            else:
                mine.append(thing)
                result.added.append((kind, name))
    level.apply_prefabs()                                       # (copies placed from a replaced prefab follow it)
    level.apply_barricade_kinds()                               # (and barricades from a replaced type)
    level.apply_door_kinds()                                    # (and doors)
    return result


def load_or_default(path=MAP_PATH):
    return load_level(path) if os.path.exists(path) else default_level()
