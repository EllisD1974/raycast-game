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
touches a neighboring cell's room on the higher floor, which is how you step across.
"""
import json
import math
import os
from dataclasses import asdict, dataclass, field, replace

from constants import PLAYER_HEIGHT

MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maps", "map.json")
FORMAT_VERSION = 6
MAX_NAME_LENGTH = 24
MIN_WALL_GAP = 0.05             # a wall this close to the ceiling is just a full-height wall

SPAN_LAYERS = ("floor_tex", "ceil_tex", "floor_h", "ceil_h", "ramp")
SIDES = "nesw"                                                  # the four sides of a cell: north, east, south, west
SIDE_LAYERS = tuple(f"side_{side}" for side in SIDES)           # a wall's own texture on one side (0: the wall's tile)
# The heights above the wall's base that a side's own texture covers, from and to (to 0: up to the top).
SIDE_BAND_LAYERS = tuple(f"side_{side}_{end}" for side in SIDES for end in ("from", "to"))
SHARED_LAYERS = ("walls", "wall_h", "wall_ceil", "wall_floor") + SIDE_LAYERS + SIDE_BAND_LAYERS  # one grid for all floors
SIDE_VECTORS = {"n": (0, -1), "e": (1, 0), "s": (0, 1), "w": (-1, 0)}  # which way each side faces on the map
WALL_LABELS = {"": "Free standing", "n": "North wall", "e": "East wall", "s": "South wall", "w": "West wall"}
MAX_ELEVATION = 8.0             # furthest a placed item may be raised or lowered from where its settings put it
WALL_GAP = 0.04                 # how far in front of a wall's face an item hung on it is, in cells
EDIT_LAYERS = ("walls",) + SPAN_LAYERS + ("wall_h",)            # what the editor lets you switch between
RAMP_DIRS = {1: (1, 0), 2: (-1, 0), 3: (0, 1), 4: (0, -1)}      # id -> (dx, dy) the floor rises toward
SOLID_OUTSIDE = 1       # walls value reported outside the grid: a wall

_GROUND_DEFAULTS = {"walls": 0, "wall_h": 0.0, "wall_ceil": 0.0, "wall_floor": 0, "floor_tex": 5, "ceil_tex": 6,
                    "floor_h": 0.0, "ceil_h": 1.0, "ramp": 0, **{name: 0 for name in SIDE_LAYERS},
                    **{name: 0.0 for name in SIDE_BAND_LAYERS}}
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


@dataclass
class Spawner:
    """A place players come into the game at (joining, after being knocked out, after a map reload).

    x, y     position on the map, in cells (the middle of a cell is .5); span is the floor it stands on
    angle    the way a player there faces, radians (0 faces +x)
    order    which spawners are used first: every player comes in at a spawner of the lowest order that has
             one not yet used in this round, picked at random among those; when all have been used the round
             starts over (see game.SpawnOrder). A map without spawners uses its start instead."""
    x: float
    y: float
    span: int = 0
    angle: float = 0.0
    order: int = 0

    @classmethod
    def from_dict(cls, data):
        return cls(float(data["x"]), float(data["y"]), max(0, int(data.get("span", 0))),
                   float(data.get("angle", 0.0)), max(0, min(MAX_SPAWN_ORDER, int(data.get("order", 0)))))


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
    shown: bool = True              # draw the sprite
    emits: str = ""                 # the particle effect it sends out
    emits_override: bool = False    # use emits_offset_* instead of the effect's own start offset
    emits_offset_x: float = 0.0
    emits_offset_y: float = 0.0
    emits_offset_z: float = 0.0
    light: str = ""                 # the light it gives off
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
                       shown=bool(data.get("shown", base.shown)), emits=str(data.get("emits", ""))[:MAX_NAME],
                       emits_override=bool(data.get("emits_override", False)),
                       emits_offset_x=float(data.get("emits_offset_x", 0.0)),
                       emits_offset_y=float(data.get("emits_offset_y", 0.0)),
                       emits_offset_z=float(data.get("emits_offset_z", 0.0)),
                       light=str(data.get("light", ""))[:MAX_NAME],
                       name=str(data.get("name", ""))[:MAX_NAME], prefab=str(data.get("prefab", ""))[:MAX_NAME],
                       wall=data.get("wall") if data.get("wall") in WALL_LABELS else "",
                       elevation=max(-MAX_ELEVATION, min(MAX_ELEVATION, float(data.get("elevation", 0.0)))))


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
                 spawners=None):
        self.grids = grids
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
                     [replace(s) for s in self.spawners])

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
        if self.get("walls", x, y) == 0:
            return False
        return span >= self.get("wall_floor", x, y)

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
    level.apply_prefabs()
    return level


def save_level(path, level):
    with open(path, "w", encoding="utf-8") as f:
        f.write(level_text(level))


def level_text(level):
    """The map file's JSON as text, with one grid row per line so it is easy to read and diff."""
    blocks = []
    for name in level.grid_names():
        if name in SIDE_LAYERS + SIDE_BAND_LAYERS and not any(any(row) for row in level.grids[name]):
            continue                                # (no wall has a texture of its own on that side)
        rows = ",\n".join("      " + json.dumps(row) for row in level.grids[name])
        blocks.append(f'    "{name}": [\n{rows}\n    ]')
    start = {"x": level.start_x, "y": level.start_y, "angle": level.start_angle,
             "span": level.start_span}
    text = (
        f'{{\n  "version": {FORMAT_VERSION},\n'
        f'  "width": {level.width},\n  "height": {level.height},\n'
        f'  "floors": {json.dumps(level.names)},\n'
        f'  "start": {json.dumps(start)},\n'
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
           if level.prefabs else "") +
        '  "grids": {\n' + ",\n".join(blocks) + "\n  }\n}\n"
    )
    return text


# --------------------------------------------------------------------------- copying an area of one floor

WALL_LAYERS = ("walls", "wall_h", "wall_ceil") + SIDE_LAYERS + SIDE_BAND_LAYERS   # what a wall carries with it


@dataclass
class Area:
    """A rectangle of one floor copied out of a map, to paste elsewhere (on any floor, in any map).

    It holds what belongs to that floor only: its span grids (floor and ceiling textures and heights, ramps) and
    the walls that start on it (their tile, height, the ceiling over them and their sides), and the items and spawn
    points standing on it. Walls of other floors - a ground-floor wall fills every floor above it - are not part of
    it. Positions are relative to the area's top-left cell."""
    width: int
    height: int
    floor: int                                  # the floor it was copied from
    span: dict = field(default_factory=dict)    # span layer -> rows of values
    walls: dict = field(default_factory=dict)   # (dx, dy) -> {wall layer: value} of the walls in it
    entities: list = field(default_factory=list)
    spawners: list = field(default_factory=list)


def area_rect(level, a, b):
    """(x0, y0, x1, y1): the cells between corners a and b (inclusive, either way round), kept inside the map."""
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    return max(0, x0), max(0, y0), min(level.width - 1, x1), min(level.height - 1, y1)


def _starts_on(level, x, y, floor):
    """True if the cell holds a wall that starts on `floor` (the walls a floor owns)."""
    return bool(level.walls[y][x]) and level.wall_floor(x, y) == floor


def _in(thing, x0, y0, x1, y1, floor):
    return thing.span == floor and x0 <= math.floor(thing.x) <= x1 and y0 <= math.floor(thing.y) <= y1


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
    return area


def _clear_wall(level, x, y):
    for layer in WALL_LAYERS + ("wall_floor",):
        level.set(layer, x, y, default_for(layer))


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
                _clear_wall(level, x, y)
    level.entities = [e for e in level.entities if not _in(e, x0, y0, x1, y1, floor)]
    level.spawners = [s for s in level.spawners if not _in(s, x0, y0, x1, y1, floor)]


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
    for cy in range(y0, y1 + 1):
        for cx in range(x0, x1 + 1):
            dx, dy = cx - x, cy - y
            for layer in SPAN_LAYERS:
                level.set(grid_name(layer, floor), cx, cy, area.span[layer][dy][dx])
            wall = area.walls.get((dx, dy))
            if wall is not None:
                if level.walls[cy][cx] and level.wall_floor(cx, cy) < floor:
                    continue                            # (a lower floor's wall already fills this cell)
                for layer, value in wall.items():
                    level.set(layer, cx, cy, value)
                level.set("wall_floor", cx, cy, floor)
            elif _starts_on(level, cx, cy, floor):
                _clear_wall(level, cx, cy)
    inside = lambda t: x0 <= math.floor(t.x + x) <= x1 and y0 <= math.floor(t.y + y) <= y1
    level.entities += [e.clone(x=e.x + x, y=e.y + y, span=floor) for e in area.entities if inside(e)]
    level.spawners += [replace(s, x=s.x + x, y=s.y + y, span=floor) for s in area.spawners if inside(s)]
    level.apply_prefabs()


# --------------------------------------------------------------------------- bringing things in from another map

IMPORT_KINDS = {"prefabs": "Prefabs", "lights": "Lights", "effects": "Effects", "guns": "Guns",
                "ammo_types": "Ammo types"}                 # what can be brought in from another map, and its label
IMPORT_ORDER = ("lights", "effects", "ammo_types", "guns", "prefabs")    # each kind only names kinds before it
REFERENCES = {                                              # the fields of each kind that name another thing
    "lights": (),
    "effects": (("light", "lights"),),
    "ammo_types": (("trail", "effects"), ("light", "lights"), ("player_hit_effects", "effects"),
                   ("player_hit_lights", "lights"), ("world_hit_effects", "effects"), ("world_hit_lights", "lights"),
                   ("explosion_effects", "effects"), ("explosion_lights", "lights")),
    "guns": (("ammo", "ammo_types"), ("muzzle", "effects"), ("flash", "lights")),
    "prefabs": (("light", "lights"), ("emits", "effects"), ("gun", "guns"), ("ammo", "ammo_types")),
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
            thing = thing.clone() if kind == "prefabs" else replace(thing)
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
    return result


def load_or_default(path=MAP_PATH):
    return load_level(path) if os.path.exists(path) else default_level()
