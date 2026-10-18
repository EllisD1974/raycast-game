"""Map data and file format, shared by the game (main.py) and the editor (map_editor.py).

A map is a set of same-sized grids ("layers"), one value per cell. A map has one or more
*floors*, named by you ("Ground", "Mezzanine", ...), stacked from the bottom up. Floor 0 (the
ground floor) is open in every cell that is not a wall. Every higher floor exists only in the
cells where you give it a room; between two floors lies solid material (the floor slab).

    walls         tile id of a solid wall that fills every floor of the cell; 0 = open space
    wall_h        height of that wall above the lowest floor beside it; 0 = full height, up to
                  the ceiling. A positive height shorter than the room makes a short wall you can
                  see over. Like walls, it is shared by every floor.
    wall_floor    the lowest floor the wall reaches: 0 = every floor, from the ground up (the wall
                  fills the cell on all floors); N = only floor N and the floors above it, so the
                  floors below stay open there. A wall painted in the editor starts on the floor
                  being edited. Only a wall from the ground floor can be short or see-through.
    wall_ceil     the ceiling over a wall that is not full height (a short or see-through wall);
                  0 = automatic: the highest ceiling of the open cells beside it.

    per floor (floor 0's grids have plain names; floor N's names end in N + 1, e.g. floor_h2):
    floor_h       floor height
    ceil_h        ceiling height
    floor_tex     tile id of the floor (also the riser of steps up to it)
    ceil_tex      tile id of the ceiling (also the drop where a ceiling gets lower)
    ramp          0 = none, else the direction the floor rises: 1 east, 2 west, 3 south, 4 north

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
touches a neighbouring cell's room on the higher floor, which is how you step across.
"""
import json
import os
from dataclasses import asdict, dataclass, field, replace

from constants import PLAYER_HEIGHT

MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maps", "map.json")
FORMAT_VERSION = 6
MAX_NAME_LENGTH = 24
MIN_WALL_GAP = 0.05             # a wall this close to the ceiling is just a full-height wall

SPAN_LAYERS = ("floor_tex", "ceil_tex", "floor_h", "ceil_h", "ramp")
SHARED_LAYERS = ("walls", "wall_h", "wall_ceil", "wall_floor")                # one grid for all floors
EDIT_LAYERS = ("walls",) + SPAN_LAYERS + ("wall_h",)            # what the editor lets you switch between
RAMP_DIRS = {1: (1, 0), 2: (-1, 0), 3: (0, 1), 4: (0, -1)}      # id -> (dx, dy) the floor rises toward
SOLID_OUTSIDE = 1       # walls value reported outside the grid: a wall

_GROUND_DEFAULTS = {"walls": 0, "wall_h": 0.0, "wall_ceil": 0.0, "wall_floor": 0, "floor_tex": 5, "ceil_tex": 6,
                    "floor_h": 0.0, "ceil_h": 1.0, "ramp": 0}
_UPPER_DEFAULTS = {"floor_tex": 3, "ceil_tex": 6, "floor_h": 0.0, "ceil_h": 0.0, "ramp": 0}


ENTITY_MODES = ("once", "respawn", "persistent", "scenery")
PREFAB_FIELDS = ("tile", "mode", "effect", "amount", "respawn", "size", "lift", "item", "gun", "ammo",
                 "shown", "emits", "emits_override", "emits_offset_x", "emits_offset_y", "emits_offset_z", "light")
ENTITY_EFFECTS = ("none", "score", "health", "item", "gun", "ammo")
MODE_LABELS = {"once": "Pick up once", "respawn": "Respawns", "persistent": "Stays", "scenery": "Scenery"}
EFFECT_LABELS = {"none": "None", "score": "Score", "health": "Health", "item": "Inventory item",
                 "gun": "Give a gun", "ammo": "Give ammo"}
GUN_MODES = ("single", "semi", "auto")
GUN_MODE_LABELS = {"single": "Single shot", "semi": "Semi-auto", "auto": "Full auto"}
SHOT_TYPES = ("single", "multi", "projectile")
SHOT_LABELS = {"single": "Single bullet", "multi": "Multi bullet", "projectile": "Projectile"}
MIN_AMBIENT = 0.02                              # the darkest a map can be made
EFFECT_KINDS = ("burst", "stream")
EFFECT_AIMS = ("auto", "custom")
EFFECT_AIM_LABELS = {"auto": "Automatic", "custom": "Custom"}
EFFECT_KIND_LABELS = {"burst": "Burst", "stream": "Stream"}
MAX_NAME = 24                                   # longest name of an item, gun or particle effect
ANIMATION_KINDS = ("float", "rotate")
ANIMATION_LABELS = {"float": "Float", "rotate": "Rotate"}


@dataclass
class Light:
    """A light that things in the world can carry. The map keeps a list of them (the editor's Lights
    section) and guns, ammo types, particle effects, items and wall tiles refer to them by name, so
    one light is designed once and used anywhere. Like particles, lights only change how things look and
    are worked out on each player's own machine.

    name           what it is called (also how things refer to it)
    r, g, b        its colour, 0 to 255 each
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
    hit_effect   name of the Effect played where the bullet strikes a wall or a player ("" for none)
    hit_light    name of the Light that flashes there ("" for none)
    trail_override, trail_offset_x, trail_offset_y, trail_offset_z
                 true: the trail starts at this offset (x along the bullet's heading, y to its right, z up, in
                 cells) instead of the effect's own start offset"""
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
    hit_effect: str = ""
    hit_light: str = ""

    @classmethod
    def from_dict(cls, data):
        base = cls()

        def number(key, low, high, cast=float):
            try:
                return cast(max(low, min(high, float(data.get(key, getattr(base, key))))))
            except (TypeError, ValueError):
                return getattr(base, key)
        name = str(data.get("name", base.name)).strip()[:MAX_NAME] or base.name
        return cls(name=name, tile=number("tile", 0, 255, int), size=number("size", 0.01, 2.0),
                   speed=number("speed", 0.5, 200.0), range=number("range", 0.5, 200.0),
                   damage_mult=number("damage_mult", 0.0, 100.0), trail=str(data.get("trail", ""))[:MAX_NAME],
                   light=str(data.get("light", ""))[:MAX_NAME], trail_override=bool(data.get("trail_override", False)),
                   trail_offset_x=number("trail_offset_x", -10.0, 10.0), trail_offset_y=number("trail_offset_y", -10.0, 10.0),
                   trail_offset_z=number("trail_offset_z", -10.0, 10.0),
                   hit_effect=str(data.get("hit_effect", ""))[:MAX_NAME], hit_light=str(data.get("hit_light", ""))[:MAX_NAME])


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

    x, y     position on the map, in cells (cell centre = .5)
    span     the floor it stands on
    tile     0-based atlas tile drawn as its sprite (tiles with transparent pixels work best)
    mode     what touching it does to the item itself:
             once        picked up and gone for good
             respawn     picked up and gone, back after `respawn` seconds
             persistent  picked up (the effect happens) but it stays where it is; touching it again
                         only counts after you have stepped away from it
    effect   what the player gets: none, score (+amount points) or health (+amount, capped)
    amount   size of the effect
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
    shown: bool = True              # draw the sprite
    emits: str = ""                 # the particle effect it sends out
    emits_override: bool = False    # use emits_offset_* instead of the effect's own start offset
    emits_offset_x: float = 0.0
    emits_offset_y: float = 0.0
    emits_offset_z: float = 0.0
    light: str = ""                 # the light it gives off
    name: str = ""                  # a prefab's name (an item placed in the map has none)
    prefab: str = ""                # the prefab this item is an instance of ("" for a plain item)

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
                       shown=bool(data.get("shown", base.shown)), emits=str(data.get("emits", ""))[:MAX_NAME],
                       emits_override=bool(data.get("emits_override", False)),
                       emits_offset_x=float(data.get("emits_offset_x", 0.0)),
                       emits_offset_y=float(data.get("emits_offset_y", 0.0)),
                       emits_offset_z=float(data.get("emits_offset_z", 0.0)),
                       light=str(data.get("light", ""))[:MAX_NAME],
                       name=str(data.get("name", ""))[:MAX_NAME], prefab=str(data.get("prefab", ""))[:MAX_NAME])


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
                 entities=None, guns=None, ammo_types=None, prefabs=None, effects=None, lights=None, ambient=1.0):
        self.grids = grids
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
        level = cls({"walls": [[0] * width for _ in range(height)],
                     "wall_h": [[0.0] * width for _ in range(height)],
                     "wall_ceil": [[0.0] * width for _ in range(height)],
                     "wall_floor": [[0] * width for _ in range(height)]}, names=[])
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
                     [replace(f) for f in self.effects], [replace(light) for light in self.lights], self.ambient)

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
        wall_floor = self.grids["wall_floor"]
        for row in wall_floor:                      # walls that began above the removed floor follow it down
            for x, value in enumerate(row):
                row[x] = min(value - 1 if value > floor else value, self.floor_count - 1)
        if self.start_span == floor:
            self.start_span = 0
        elif self.start_span > floor:
            self.start_span -= 1

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
        if self.get("walls", x, y) == 0:
            return False
        return span >= self.get("wall_floor", x, y)

    def wall_floor(self, x, y):
        """Lowest floor a wall in this cell reaches (0 for a wall from the ground)."""
        return self.get("wall_floor", x, y)

    def wall_region(self, x, y):
        """The connected group (4-neighbour) of wall cells that (x, y) belongs to, whatever their
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
        neighbour falls back to its own ceil_h. The ceil_h stored under a wall is otherwise never
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
        """The connected region (4-neighbour) of cells equal to (x, y) in a grid, unchanged."""
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
        sx, sy = int(self.start_x), int(self.start_y)
        span = self.start_span
        if self.is_solid(sx, sy, span):
            found.append(("start position is inside a wall", (sx, sy)))
        elif not self.span_present(span, sx, sy):
            found.append(("start position has no floor here on the chosen floor", (sx, sy)))
        else:
            lo = self.grids[grid_name("floor_h", span)][sy][sx]
            hi = self.grids[grid_name("ceil_h", span)][sy][sx]
            if hi - lo < PLAYER_HEIGHT:
                found.append(("start position is too low for the player to fit", (sx, sy)))

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
    start = data.get("start", {})
    level.start_x, level.start_y = float(start.get("x", 1.5)), float(start.get("y", 1.5))
    level.start_angle = float(start.get("angle", 0.0))
    level.start_span = min(int(start.get("span", 0)), count - 1)
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
    level.apply_prefabs()
    return level


def save_level(path, level):
    with open(path, "w", encoding="utf-8") as f:
        f.write(level_text(level))


def level_text(level):
    """The map file's JSON as text, with one grid row per line so it is easy to read and diff."""
    blocks = []
    for name in level.grid_names():
        rows = ",\n".join("      " + json.dumps(row) for row in level.grids[name])
        blocks.append(f'    "{name}": [\n{rows}\n    ]')
    start = {"x": level.start_x, "y": level.start_y, "angle": level.start_angle,
             "span": level.start_span}
    text = (
        f'{{\n  "version": {FORMAT_VERSION},\n'
        f'  "width": {level.width},\n  "height": {level.height},\n'
        f'  "floors": {json.dumps(level.names)},\n'
        f'  "start": {json.dumps(start)},\n'
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
           if level.prefabs else "") +
        '  "grids": {\n' + ",\n".join(blocks) + "\n  }\n}\n"
    )
    return text


def load_or_default(path=MAP_PATH):
    return load_level(path) if os.path.exists(path) else default_level()
