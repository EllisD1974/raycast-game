"""Map editor for the simple raycaster.

Run:  python map_editor.py [maps/map.json]      (opens maximized)
      Without a map it opens the one edited last (made, opened or given here), or maps/map.json the first
      time. Which one that was is kept in %LOCALAPPDATA%/raycast-game/editor.json.

A map has any number of floors stacked on top of each other. The ground floor exists everywhere;
higher floors have a room only where you paint one. Pick the floor you are editing from the
dropdown at the top left (or press Tab / Shift+Tab to step through them). "+Floor" adds a new
floor on top, "Rename" (F2) renames the selected floor, and "Del" removes it (not the ground
floor). The floors below the one you edit are shown faded.

A map has several layers; you edit one at a time (keys 1-7 or the Layer buttons):
  1 Walls      solid wall tiles (0 = open space). A wall painted on a higher floor stands on that
               floor and the ones above it; the floors below stay open under it. A wall painted
               on the ground floor fills every floor.
  2 FloorTex   floor texture of each cell (also the riser texture of stairs / raised blocks)
  3 CeilTex    ceiling texture of each cell
  4 FloorH     floor height of each cell (stairs, platforms, pits); [ ] change the brush value,
               or click the value (or press Enter) and type one
  5 CeilH      ceiling height of each cell (tall rooms, low tunnels)
  6 Ramps      ramp direction; a run of ramp cells slopes from the floor before it to the floor
               after it. R rotates the direction.
  8 WallSide   the texture on one side of a wall: the side nearest the mouse in a wall cell is the one
               painted (Paint, or a Shape: the side picked where the drag starts), right-click / Erase
               puts the wall's own tile back on it, Fill does that side of the whole wall, Pick takes it.
               From / To (second toolbar row) limit it to a band of heights above the wall's foot, with
               the wall's own tile above and below: From 0 starts at the foot, To "top" ends at the top
               ("Full height" sets both back).

A higher floor starts empty. Painting FloorH or CeilH on it creates the room in that cell, using
the other brush value for the missing height, and lowers the ceiling of the floor below there to
leave a thin slab. Erasing a height on a higher floor removes the room. To climb to a higher
floor, end a ramp on a cell of the floor below that is raised to the higher floor's height (with a
tall ceiling) and touches a room of the higher floor.

The WallH layer (key 7) sets how tall each wall is: paint a height onto wall cells (Val-/Val+ or
[ ] change it; Fill sets the whole connected wall; Erase puts a wall back to full height). A wall
stands on the lowest floor of the open cells beside it and a height of 0, or one that reaches
the ceiling beside it, is a full-height wall like any other (the number turns red). A shorter wall is one you can see over, and see
the top of; you can't walk through it, but you can hop onto a low one. Short walls carry a cyan
bar on the map.

The ceiling over a short (or see-through) wall is automatic, the highest ceiling of the open cells
beside it, until you set it: on the CeilH layer, paint a wall cell to set the ceiling over it and
erase to go back to automatic. Those cells show the number, in (brackets) while it is automatic.
The ceiling stored under a wall by other tools is never used, since you can't see it.

Left panel: the texture atlas. Click a tile, drag a rectangle, or Ctrl+click/drag to add more
tiles (Ctrl+click a selected tile removes it). On the texture layers the selection is a stamp:
it keeps its layout from the atlas, with its top-left at the cursor. The wheel over the atlas zooms
into it (around the cursor); while zoomed, middle-drag or Space+drag moves it around.
Map: left-drag paints, right-drag erases (back to the layer's default), wheel zooms,
middle-drag or Space+drag pans.

Textures: edit textures.png in any image editor and the editor picks the change up by itself
within a moment (the atlas, the map and the 3D view all update); F6 or the "Reload tex" button
does it on demand. A file that can't be read leaves the old textures in place.

Rulers along the top and left of the map count the cells (a tick on every grid line, numbers as often as
they fit), light up the cell under the mouse, and mark the middle of the map on each axis with a triangle,
as do small triangles on the map's border.

Map size: the Edge buttons add (+) or remove (-) a column or row on one side: L left, R right,
T top, B bottom. Cells, the start and the 3D camera stay where they are on the map.

Tools: B paint, E erase, F fill, I pick from the map, S set the start (on the floor you are
editing; click it again to rotate, drag it to move it), T stairs (drag a line on the FloorH layer: heights rise by
the Step each cell, starting at the brush value; on the WallH layer it builds the steps from short walls
instead, each keeping the ceiling of the room it stands in), H shapes (drag a line, box or ellipse, outline
or filled, chosen on the second toolbar row; it paints what the brush paints on the layer you are
on, right-drag erases the shape, Shift makes a square or circle, Esc cancels).
Ctrl+Z / Ctrl+Y undo / redo, Ctrl+S save,
F5 save and play, Home reset view, Tab / Shift+Tab switch floor, F2 rename floor.

New asks for the new map's name and saves a blank map as <name>.json in the folder of the map being
edited, so every new map is its own file (an existing file is never overwritten). Open (Ctrl+O) lists
the maps in that folder to switch to another one: click one and Open, double-click it, or pick with the
arrow keys and Enter. Save, Reload and Play work on the map that was made or opened last.
Import brings prefabs, lights, effects, guns and ammo types in from another map in that folder: pick the map,
tick what to bring (a group's heading ticks it all), and choose what happens when a name is already used here:
keep this map's, replace it, or add the imported one as a copy with a new name. Whatever the picked things use
comes too (a prefab's light and effect, a gun's ammo type and its effects), and anything this map already has
exactly the same is left alone. One undo step takes the whole import back.

Items hang on a wall when added with a click near the side of the cell that has the wall (the edge lights
up): they are then a flat picture against the wall, facing into the cell, at their Lift above the floor.
The item's "On wall" setting moves it onto another wall of its cell, or off the wall.

Copy and paste (the Select tool, M): drag a rectangle on the map to select it, then Ctrl+C copies it, Ctrl+X
cuts it and Delete clears it; Ctrl+A selects the whole map. Ctrl+V (or Paste) carries the copy under the mouse:
each click puts it down there (centered on the mouse), until Esc or a right-click. Only the floor being edited
is copied: its floor and ceiling textures and heights and its ramps, the walls that start on it (with their
heights and sides), and the items and spawn points on it; walls of other floors stay where they are. It pastes
onto the floor being edited, which may be another floor, and stays copied when another map is opened.

Spawn points (the Spawn tool, O): where players come into the game. Click an open cell to put one there
with the Order shown on the second toolbar row (Order- / Order+, or [ and ]); click one again to give it
that order, or (if it has it already) to turn it a quarter; drag one to move it; right-click removes it. Players come in at the
lowest order that has a spawn point not yet used, picked at random among those; once all have been used it
starts over. A map with no spawn points uses the Start (S).

Each placed item has an Elevation of its own ("This copy only" in its pane, or [ and ] with the item
selected; Shift for bigger steps): how much higher or lower than its settings put it this one copy sits, on
a wall or not. A prefab never changes it, and changing it moves no other copy.

Items (the Entity tool, N): click an empty cell to add an item there (in the middle of the cell, on
the floor you are editing), or click an existing item to select it; drag an item to move it to another
cell (it stays on its wall if the new cell has a wall on that side). A selected item opens the
Details pane, docked beside the map, where you change it in place: Sprite (or click a tile in the
atlas), Mode ("Pick up once": touching it gives the effect and it is gone; "Respawns": gone, then
back after the set seconds; "Stays": the effect counts each visit but it is never removed),
Effect (a drop-down list: none, score or health) and its Amount, Size, and Lift (how far it floats
above the floor). "+ Add animation" adds a Float and / or Rotate animation; each one in the list
has its own speed (and Float its height) and an x to remove it. Values step with - / +, the wheel
over a row, or by clicking the number and typing. Esc closes the pane, Delete or the Delete button
removes the item (so does right click on it). Items show on the map ringed white / cyan / green by
mode, and in the 3D view as sprites that face you.

The Prefabs section (P or the Prefabs button) is where you make reusable items: "+ Add prefab", then
set its name, Icon (click a tile in the atlas), mode, effect, size and animations in the Details pane,
exactly as for a placed item. With the Entity tool and nothing selected, the pane on the right lists
"Plain item" and every prefab: pick one and click cells to place it. An item placed from a prefab
follows it: change the prefab and every copy changes. Selecting a placed copy lets you point it at
another prefab or choose (none) to detach it, which keeps its settings and makes it editable on its
own. A plain item's pane has "Save as a new prefab" to turn it into one.

The Guns section (G or the Guns button) replaces the map with the list of the map's guns: add one
with "+ Add gun", click one to edit it in the Details pane (name, picture and its size, fire mode,
damage, fire rate, magazine, spare ammunition, reload time, spread and its ammo type). Ammunition
is listed under the guns: an ammo type is the bullet (picture, size, speed, range) and a damage
multiplier, and guns of the same type share one pool of spare rounds. The picture under the list is the game
itself firing the selected gun down a corridor (fire rate, magazine, reload, recoil, muzzle effect and light, bullets
with their trails and lights): tick "Fire continuously" to keep it shooting and reloading, press "Fire once" for a
single pull, and tick "Dark room" to see flashes and bullet lights. It starts over whenever you change anything.
On the picture itself, an orange disc is where the bullets come from and a cyan diamond is where the muzzle effect
starts, drawn where they really are: drag one to move it sideways and up, or click the picture to put the picked one
there, and use the Depth slider to move it in and out of the screen (further ahead of the gun, or back). The white ring
and the highlighted button show which one you are moving. The effect's handle starts overriding the effect's own offset
as soon as you move it. A gun's "Bullets ahead / right / up" say where
its bullets come from (in cells from the usual muzzle point in front
of the eye; a gun held low and to the right is about 0, 0.3, -0.25), and its muzzle effect and flash come from there
too; the bullets still fly along the aim. A gun's Muzzle effect, an ammo type's Trail effect and an item's Emits each have a "Start offset" row: leave it on
"Effect's own", or choose "Override" to say where that effect starts for this gun, ammo type or item (a gun's and an
ammo type's are ahead, to the right and up of the muzzle or bullet; an item's are east, south and up). Click a Sprite row and then a tile in the atlas to set that picture. Hand a gun
out with an item whose effect is "Give a gun" (or "Give ammo"); an "Inventory item" effect puts a
named thing in the player's inventory instead. Choosing a map tool goes back to the map.

The Effects section (X or the Effects button) is where you design particle effects: "+ Add effect", then
shape it in the Details pane (the particle picture from the atlas, a burst or a stream, how many, how long
they live, speed, spread, gravity, drag, size and fade, and Color: a hue shift or an RGB tint of the particle
picture) while a live side view plays it. Effects are
saved in the map and reused by name (Start offset X / Y / height move where the particles start, and Direction
"Custom" sends them in a direction of your own instead of the automatic one; Offset / dir. axes chooses map
axes or the heading's): a gun's "Muzzle effect" plays where it fires, an ammo type's "Trail
effect" follows its bullets, and an item's "Emits" sends the effect up from the item (set its Mode to
Scenery so it cannot be picked up, and Sprite to Hidden to see only the particles). They are only for looks
and are worked out on each player's own machine.

The Lights section (L or the Lights button) is where you design lights: "+ Add light", then set its color,
brightness, reach, flicker and flash length in the Details pane while a preview shows it from above. Lights
are saved in the map and used by name: a gun's "Muzzle light" flashes where it fires, an ammo type's "Bullet
light" travels with its bullets and its Player and World hit lights flash where they strike a player or anything else (add as many as you like: each filled row gets an empty one below it; pick (none) to remove one), an effect's "Particle light" makes every particle glow (and be drawn at full
brightness), and an item's "Light" lights up around it (a Scenery item with a hidden sprite is just a light
placed in the map). "Glowing wall tile" makes every wall made from that atlas tile light the open cells beside
it. The first row, "Map ambient light", sets how bright the map is without lights: lower it to make the map
dark so lights show. Walls stop light. Lights only change how things look and are worked out on each player's
own machine.

The Map settings section (J or the Map settings button) says how this map is played, and holds its buy menu.
"Game rules": the Game mode (Free for all; Two teams, which splits the players as they join; Co-op, everyone on one
team), Friendly fire (whether bullets and blasts hurt teammates), Max health, Start money, what knocking out an
opponent earns (Score / kill, Money / kill) and a Starting gun every player comes in with. "Buy menu": turn it on
(players then open it with B in the game) and choose what it costs: Free, Money or Score. "+ Add to buy menu" (or the
pane's "+ Add" list of the map's guns) adds an entry: what it gives (a gun, an inventory item or health; ammo is not
sold, guns come with theirs), how much, its price and its icon (none: a gun shows its own picture); Move up / down orders the menu. On the
right is the menu as a player who just joined sees it (entries they cannot afford yet are greyed out). In the game,
clicking an entry gives it to the player when they have enough money or score, and takes the price off it.

The 3D view (V or the 3D button shows and hides it) is a live picture of the level at the right of
the window, drawn by the game's own renderer, and it follows every edit as you make it, even
mid-stroke. Drag inside it to look around; with the mouse over it, W A S D / arrows walk and turn
(Shift sprints, Space jumps) and the wheel walks forward and back, with the game's own physics.
The camera shows on the map as a cyan wedge. The Camera tool (C) places it: click a cell on the
map (on the floor you are editing) and drag to aim. Cam->Start returns it to the player start.

The Key panel (K or the Key button shows and hides it) sits in the left panel under the tile
preview, or floats over the map's bottom-right corner in a window too short for that. It explains
the small marks drawn on the map: the orange dot for a room on a floor above, the start marker (a
ring when the start is on another floor), red outlines on problem cells, faded floors and walls,
ramp arrows and height colors.
"""
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import astuple

import numpy as np
import pygame

from atlas import ATLAS_PATH, atlas_array, transparent_tiles, unpack_atlas
from character import sheet_names
from constants import FOV_DEG, HEIGHT, MOUSE_SENSITIVITY, PLAYER_HEIGHT, TILE, WIDTH
from mapfile import (ANIMATION_KINDS, ANIMATION_LABELS, DEFAULTS, EDIT_LAYERS, EFFECT_LABELS, ENTITY_EFFECTS,
                     ENTITY_MODES, GUN_MODE_LABELS, GUN_MODES, MAP_PATH, MAX_HIT_NAMES, MAX_NAME, MAX_NAME_LENGTH, MIN_WALL_GAP,
                     EFFECT_AIM_LABELS, EFFECT_AIMS, EFFECT_COLOR_LABELS, EFFECT_COLORS, EFFECT_KIND_LABELS, EFFECT_KINDS, MIN_AMBIENT, MODE_LABELS, SHOT_LABELS, SHOT_TYPES, Animation, AmmoType, Effect,
                     Entity, Gun, Level, Light, MAX_ELEVATION, MAX_SPAWN_ORDER, Spawner, SIDE_VECTORS, SIDES, WALL_LABELS, default_level, mounted_position,
                     IMPORT_KINDS, TAKEN_CHOICES, grid_name, import_things, load_level, save_level, split_grid_name,
                     things_named, with_needs, area_rect, clear_area, copy_area, paste_area,
                     BUY_COST_LABELS, BUY_COSTS, BUY_KIND_LABELS, BUY_KINDS, GAME_MODE_LABELS, GAME_MODES, MAX_BUY_ITEMS,
                     DEATH_CAM_WHO, DEATH_CAM_WHO_LABELS,
                     BOMB_NUMBERS, SITE_NAMES, SPAWN_TEAMS, SPAWN_TEAM_LABELS, CT_TEAM, T_TEAM,
                     ATTACK_KINDS, ATTACK_KIND_LABELS, ATTACK_NUMBERS, ENEMY_NUMBERS, ENEMY_PATHING,
                     ENEMY_PATHING_LABELS, ENEMY_SPAWN, MAX_ATTACKS, MAX_ENEMIES, SPAWNER_TEAMS, ZOMBIE_NUMBERS,
                     Attack, Barricade, BarricadeKind, BARRICADE_TILE, Enemy, unique_thing_name,
                     CURVE_LIMITS, MAX_CURVE_POINTS, MAX_CURVE_X, curve_at, BARRICADE_NUMBERS, MAX_BARRICADE_BOARDS, MAX_BARRICADE_STAGES,
                     REWARD_KINDS,
                     REWARD_KIND_LABELS,
                     BARRIER_SITES, HILL_SITE, KOTH_NAMES, KOTH_NUMBERS,
                     MAX_MONEY, BuyItem)
from buymenu import entry_tile, price_text
import details
import hud
from entities import describe
from details import PANE_WIDTH, Field
from inventory import GunState
from gunpreview import GunPreview
from projectiles import MUZZLE
from particles import UP, ParticleSystem, placement
from preview import Preview
from version import label as version_label
from window import maximize

TOOLBAR_H, STATUS_H = 128, 26
ROW_Y = (6, 47, 88)                             # top of each of the three toolbar rows
TEXTURE_CHECK_SECONDS = 0.5                    # how often textures.png is checked for changes
REFIT_SECONDS = 1.5                             # after startup, resizes re-fit the map to the window
RESIZE_EVENTS = tuple(getattr(pygame, name) for name in
                      ("VIDEORESIZE", "WINDOWRESIZED", "WINDOWSIZECHANGED", "WINDOWMAXIMIZED")
                      if hasattr(pygame, name))
DROPDOWN_W, ITEM_H = 230, 30
ATLAS_X, ATLAS_Y = 8, TOOLBAR_H + 8
PANEL_W = 512 + 2 * 8
ATLAS_ZOOMS = (1.0, 1.5, 2.0, 3.0, 4.0)        # how far the atlas panel zooms in (the wheel over it)
DEFAULT_SHOW_PREVIEW = True                     # the live 3D view opens with the editor (V toggles it)
PREVIEW_MIN_W, PREVIEW_MAX_W = 240, 640         # width of the 3D view's column, at the window's right
PREVIEW_TITLE_H = 24
CAMERA = (80, 220, 240)                         # the 3D view's camera marker on the map
PREVIEW_KEYS = (pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d, pygame.K_UP, pygame.K_DOWN,
                pygame.K_LEFT, pygame.K_RIGHT, pygame.K_SPACE)      # walk the camera while over the view
MAX_SIZE = 128
MAX_UNDO = 100
VALUE_STEP = 0.25
MIN_SPAN = PLAYER_HEIGHT + 0.1                  # smallest room the editor creates by itself
SLAB = 0.25                                     # thickness of the slab between the floors
HEIGHT_RANGE = {"floor_h": (-1.0, 3.0), "ceil_h": (0.0, 5.0),
                "wall_h": (0.0, 3.0)}           # color scale of the height views
VALUE_LIMITS = {"floor_h": (-4.0, 8.0), "ceil_h": (-4.0, 8.0),
                "wall_h": (VALUE_STEP, 8.0)}    # a wall height of 0 would mean "full": erase for that
WALL_FULL = (150, 70, 60)                       # color of a full-height wall on the WallH layer
SHORT_WALL = (90, 220, 230)                     # the bar on a short wall (and its key icon)

BG = (30, 31, 36)
PANEL_BG = (38, 40, 46)
EMPTY_CELL = (58, 60, 68)
GRID = (80, 82, 92)
TEXT = (225, 225, 230)
DIM = (140, 142, 152)
ACCENT = (255, 205, 60)
UPPER_MARK = (255, 150, 60)
START_FILL, START_EDGE = (60, 220, 110), (10, 60, 30)
LEGEND_ROW, LEGEND_ICON = 28, 24                # key panel: row height and icon box size
LEGEND_TITLE = 28                               # height of the key's title line
WARN = (255, 120, 100)
BUTTON = (62, 65, 76)
BUTTON_HOT = (88, 92, 108)
BUTTON_ON = (70, 110, 190)
SHADE = (0, 0, 0, 150)                          # dims the editor behind a dialog
MAP_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_")
MAX_MAP_NAME = 40                               # characters in a map's file name (without .json)
SETTINGS_PATH = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".config"),
                             "raycast-game", "editor.json")    # remembers the map edited last
OPEN_ROWS, OPEN_ROW_H = 12, 26                  # Open dialog: map names shown at once, and their row height
DOUBLE_CLICK = 0.4                              # seconds between two clicks on a map that open it

STAMP_LAYERS = ("walls", "floor_tex", "ceil_tex")
ROOM_HEIGHT_LAYERS = ("floor_h", "ceil_h")                  # heights that make up a floor's rooms
VALUE_LAYERS = ROOM_HEIGHT_LAYERS + ("wall_h",)             # every layer painted with a number
LAYER_LABELS = {"walls": "Walls", "floor_tex": "FloorTex", "ceil_tex": "CeilTex",
                "floor_h": "FloorH", "ceil_h": "CeilH", "ramp": "Ramps", "site": "Sites", "wall_h": "WallH",
                "sides": "WallSide"}
SITE_COLORS = {1: (255, 150, 40), 2: (60, 200, 255), HILL_SITE: (110, 225, 110),      # bomb sites A, B, the hill
               4: (235, 80, 60), 5: (70, 120, 255)}                                     # and the barriers
SITE_MARKS = {1: "A", 2: "B", HILL_SITE: "H", 4: "|1", 5: "|2"}  # ... and their marks on the Sites layer
SITE_BRUSHES = {1: "bomb site A", 2: "bomb site B", HILL_SITE: "the hill (King of the Hill's capture point)",
                4: "a barrier only team 1 (T, RED) and its bullets get through (ground floor)",
                5: "a barrier only team 2 (CT, BLU) and its bullets get through (ground floor)"}
SPAWN_TEAM_FILLS = {0: (90, 170, 255), T_TEAM: (235, 160, 60), CT_TEAM: (80, 140, 255),
                    ENEMY_SPAWN: (120, 210, 90)}                                          # spawn points by team
# Bomb defusal settings in the Map settings section: (label, step) for each number, in the order shown.
BOMB_FIELDS = (("freeze_time", "Freeze time (s)", 1.0), ("round_time", "Round time (s)", 5.0),
               ("buy_time", "Buy time (s)", 5.0), ("bomb_time", "Bomb timer (s)", 5.0),
               ("plant_time", "Plant time (s)", 0.1), ("defuse_time", "Defuse time (s)", 0.5),
               ("kit_defuse_time", "Defuse with kit (s)", 0.5), ("round_end_time", "Round end pause (s)", 1.0),
               ("max_rounds", "Rounds in a match", 2.0), ("bomb_damage", "Bomb damage", 50.0),
               ("bomb_radius", "Bomb radius (cells)", 1.0), ("win_money", "Money / round won", 50.0),
               ("bomb_win_money", "Money / bomb won", 50.0), ("loss_money", "Money / round lost", 50.0),
               ("loss_bonus", "Loss bonus per loss", 50.0), ("max_loss_money", "Most for a loss", 50.0),
               ("plant_money", "T money if planted", 50.0), ("objective_money", "Plant / defuse bonus", 50.0),
               ("money_cap", "Most money", 500.0))
# King of the Hill settings in the Map settings section, likewise.
KOTH_FIELDS = (("hill_time", "Time to hold (s)", 10.0), ("unlock_time", "Point unlocks after (s)", 5.0),
               ("capture_time", "Capture time (s)", 1.0), ("capture_bonus", "Time added / capture (s)", 5.0),
               ("decay_time", "Capture decay (s)", 5.0), ("respawn_time", "Respawn time (s)", 1.0),
               ("win_limit", "Rounds to win", 1.0))
# Zombies settings in the Map settings section, likewise.
ZOMBIE_FIELDS = (("extra_per_player", "More per extra player", 0.1),
                 ("intermission", "Between rounds (s)", 1.0), ("game_over_time", "Game over pause (s)", 1.0),
                 ("bleed_out", "Downed bleed out (s)", 5.0), ("downed_speed", "Downed crawl (cells/s)", 0.1),
                 ("revive_time", "Revive takes (s)", 0.5), ("revive_reward", "Money / revive", 10.0),
                 ("revive_health", "Health after revive", 5.0), ("revive_grace", "Safe after revive (s)", 0.5))
# An enemy kind's numbers in the Details pane, and its attacks'.
ENEMY_FIELDS = (("health", "Health", 10.0), ("speed", "Speed (cells/s)", 0.1), ("height", "Height", 0.05),
                ("radius", "Radius", 0.05), ("kill_reward", "Money / kill", 10.0), ("hit_reward", "Money / hit", 5.0),
                ("break_rate", "Board pull time (s)", 0.1))
ATTACK_FIELDS = (("damage", "Damage", 5.0), ("range", "Reach (cells)", 0.05), ("windup", "Wind-up (s)", 0.05),
                 ("cooldown", "Cooldown (s)", 0.1))
ENEMY_COLOR_NAMES = ("Tint red", "Tint green", "Tint blue")
CURVE_TABS = (("zombie_count", "Zombies"), ("zombie_health", "Health x"), ("max_alive", "At once"),
              ("spawn_interval", "Spawn gap (s)"), ("weight", "Enemy mix"))    # the Waves card's curves
CURVE_STEPS = {"zombie_count": 1, "zombie_health": 0.05, "max_alive": 1, "spawn_interval": 0.05, "weight": 0.1}
WAVES_CARD_W, WAVES_CARD_H = 480, 330
CURVE_MIN_ROUNDS = 20                           # the graph shows at least this many rounds
CURVE_HIT = 9                                   # how close (pixels) a click must be to grab a point
BARRICADE_FILL, BARRICADE_PLANK = (120, 80, 40), (200, 150, 90)     # a barricade on the map
EDITOR_LAYERS = tuple(name for name in EDIT_LAYERS if name != "site") + ("sides", "site")   # the stored layers, the
                                                            # sides of walls, and bomb sites last (keys 1-9)
TILE_LAYERS = STAMP_LAYERS + ("sides",)                     # layers painted with atlas tiles
LAYER_KEYS = {pygame.K_1 + i: name for i, name in enumerate(EDITOR_LAYERS)}
SIDE_STEP = 0.1                                 # From- / From+ / To- / To+ change a wall side's band by this
MAX_SIDE_BAND = 8.0
PARTIAL_SIDE = (90, 220, 230)                   # outline of a wall side whose own tile covers only a band of it
RULER = 22                                      # width of the rulers along the map's top and left, in pixels
RULER_LABEL_STEPS = (1, 2, 5, 10, 20, 50, 100)   # cells between ruler numbers: the first that leaves room
ELEVATION_STEP = 0.05                           # [ / ] and the Elevation row move a placed item up or down this much
SPAWN_FILL, SPAWN_EDGE = (90, 170, 255), (15, 40, 90)   # a spawn point on the map
MOUNT_ZONE = 0.3                                # an item clicked this close (in cells) to a walled side hangs on it
TOOLS = {"paint": "B", "erase": "E", "fill": "F", "pick": "I", "start": "S", "spawn": "O", "stairs": "T",
         "shape": "H", "select": "M", "camera": "C", "entity": "N", "barricade": "U"}
TOOL_KEYS = {pygame.K_b: "paint", pygame.K_e: "erase", pygame.K_f: "fill",
             pygame.K_i: "pick", pygame.K_s: "start", pygame.K_o: "spawn", pygame.K_t: "stairs", pygame.K_h: "shape",
             pygame.K_m: "select", pygame.K_c: "camera", pygame.K_n: "entity", pygame.K_u: "barricade"}
SHAPES = {"line": "Line", "box": "Box", "filled_box": "Filled box", "ellipse": "Ellipse",
          "filled_ellipse": "Filled ellipse"}           # what the Shape tool draws, and its button
ENTITY_MODE_COLORS = {"once": (255, 255, 255), "respawn": (90, 210, 255), "persistent": (110, 230, 120),
                       "scenery": (200, 150, 255)}
FX_CELL = 70                                    # pixels a cell is drawn at in an effect's preview
FX_BASE = 0.35                                  # cells above the preview's floor that the effect starts
FX_CAP = 400                                    # particles drawn in the preview at most
LIGHT_CELL = 44                                 # pixels a cell is drawn at in a light's preview
EYE_DROP = 0.03                                 # bullets start this far below the eye height (see projectiles.py)
GIZMO_DEPTH = (-0.15, 2.5)                        # cells ahead of the gun's usual muzzle point that the depth slider covers
GIZMO_NEAR = 0.1                                # the nearest to the eye (cells) that a handle is drawn at
GUN_CARD_WIDTH = 540                             # the widest the gun picture and its placement views are drawn
GIZMO_HIT = 13                                  # how close (pixels) a click must be to grab a handle
GIZMO_COLORS = {"bullet": (255, 170, 60), "effect": (80, 220, 255)}
GIZMO_NAMES = {"bullet": "Bullets", "effect": "Effect"}
AMBIENT_ROW = -1                                # light_selected value for the map's ambient light, listed first
RULES_ROW, BUY_ROW = -1, -2                     # settings_selected values for the game rules and the buy menu's own
ENEMY_ROW = -100                                # settings_selected for enemy kind i (zombies) is ENEMY_ROW - i
BUY_AMOUNTS = {"gun": 1.0, "item": 1.0, "health": 50.0}   # what an entry gives when its kind is chosen


def recolored(picture, matrix):
    """A copy of a picture with its colors put through a particle's 3 x 3 color matrix (9 numbers, see
    particles.color_matrix), as the game draws a hue shifted or tinted particle."""
    picture = picture.copy()
    rgb = pygame.surfarray.pixels3d(picture)
    out = np.clip(rgb.astype(np.float64) @ np.array(matrix, np.float64).reshape(3, 3).T, 0, 255)
    rgb[...] = out.astype(np.uint8)
    del rgb
    return picture


class PreviewFloor:
    """The only thing in an effect's preview for particles to hit: a floor at height 0."""

    @staticmethod
    def point_open(x, y, z):
        return z > 0.0
ENTITY_FIRST_TILE = 10                          # the first item sprite in the stock atlas (the gem)
RAMP_NAMES = {1: "East", 2: "West", 3: "South", 4: "North"}
RAMP_VECTORS = {1: (1, 0), 2: (-1, 0), 3: (0, 1), 4: (0, -1)}


def square_end(a, b):
    """`b` moved so that the box from `a` to it is square (as big as the longer side), for Shift."""
    side = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
    return (a[0] + (side if b[0] >= a[0] else -side), a[1] + (side if b[1] >= a[1] else -side))


def shape_cells(kind, a, b):
    """The grid cells of a shape (one of SHAPES) dragged from cell a to cell b. Boxes and ellipses fill the
    box with a and b at opposite corners; an ellipse is the cells whose centers are inside it, and its
    outline the ones of those next to (or diagonal to) the outside. Lines and outlines join cells side to side,
    never only at a corner, so a wall drawn with them has no diagonal gap for light (or a player) to slip through."""
    if kind == "line":
        cells = line_cells(a, b)
        joined = cells[:1]
        for (px, py), (x, y) in zip(cells, cells[1:]):
            if px != x and py != y:
                joined.append((x, py))                  # a diagonal step: fill the corner
            joined.append((x, y))
        return joined
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    box = [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    if kind == "filled_box":
        return box
    if kind == "box":
        return [(x, y) for x, y in box if x in (x0, x1) or y in (y0, y1)]
    rx, ry = (x1 - x0 + 1) / 2, (y1 - y0 + 1) / 2
    cx, cy = x0 + rx, y0 + ry
    inside = {(x, y) for x, y in box if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1.0}
    if kind == "filled_ellipse":
        return [cell for cell in box if cell in inside]
    return [(x, y) for x, y in box if (x, y) in inside
            and any((x + dx, y + dy) not in inside for dx in (-1, 0, 1) for dy in (-1, 0, 1))]


def line_cells(a, b):
    """Grid cells on the line from a to b (Bresenham), so fast drags leave no gaps."""
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err, cells = dx + dy, []
    while True:
        cells.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return cells
        e2 = 2 * err
        if e2 >= dy:
            err, x0 = err + dy, x0 + sx
        if e2 <= dx:
            err, y0 = err + dx, y0 + sy


def heat(value, lo, hi):
    """Color for a height: blue (low) through green to yellow (high)."""
    t = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    stops = ((40, 60, 150), (50, 160, 120), (240, 200, 60))
    a, b, f = (stops[0], stops[1], t * 2) if t < 0.5 else (stops[1], stops[2], t * 2 - 1)
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def fmt(value):
    return f"{value:g}"


def barricade_icon(barricade):
    """The atlas tile that pictures a barricade or saved type: its first (whole) stage, or its tile."""
    return barricade.stages[0] if barricade.stages else barricade.tile


def curve_text(points):
    """A curve of rounds (mapfile.curve_at) in words: "6 in round 1, 18 in round 5, 40 in round 10"."""
    return ", ".join(f"{value:g} in round {x}" for x, value in points)


# The small marks drawn on the map. Both the map and the key panel draw them through these
# functions, so the key always shows exactly what is on the map.

def draw_upper_mark(screen, rect):
    """Orange dot in a cell's corner: a room exists on a floor above."""
    pygame.draw.circle(screen, UPPER_MARK, (rect.right - 6, rect.top + 6), 3)


def draw_short_wall_mark(screen, rect):
    """Cyan bar along a wall's bottom edge: this wall is shorter than its room (see the WallH layer)."""
    pygame.draw.rect(screen, SHORT_WALL, (rect.left + 3, rect.bottom - 8, max(2, rect.w - 6), 5))


def draw_problem_outline(screen, rect):
    """Red outline: this cell has a problem the status bar warns about."""
    pygame.draw.rect(screen, WARN, rect, 3)


def draw_start_icon(screen, cx, cy, radius, angle, length, width, filled=True):
    """The player start: a filled circle with a facing line, or a hollow ring when the start
    is on a different floor from the one being edited."""
    if filled:
        tip = (cx + math.cos(angle) * length, cy + math.sin(angle) * length)
        pygame.draw.circle(screen, START_FILL, (cx, cy), radius)
        pygame.draw.circle(screen, START_EDGE, (cx, cy), radius, 2)
        pygame.draw.line(screen, (255, 255, 255), (cx, cy), tip, width)
    else:
        pygame.draw.circle(screen, START_FILL, (cx, cy), radius, 2)


def draw_camera_icon(screen, cx, cy, angle, size, filled=True):
    """A dot with a wedge pointing the way the 3D camera faces (angle 0 faces right)."""
    spread = math.radians(33)
    left = (cx + math.cos(angle - spread) * size, cy + math.sin(angle - spread) * size)
    right = (cx + math.cos(angle + spread) * size, cy + math.sin(angle + spread) * size)
    pygame.draw.polygon(screen, CAMERA, ((cx, cy), left, right), 0 if filled else 1)
    pygame.draw.circle(screen, (255, 255, 255), (round(cx), round(cy)), max(3, round(size * 0.18)))


def default_brush(grid):
    """Starting brush value for a height grid: the first room of each floor is 1.5 tall,
    and a higher floor starts a step above the one below it."""
    layer, floor = split_grid_name(grid)
    if layer == "wall_h":
        return 0.5                                  # a waist-high wall
    if floor == 0:
        return 0.5 if layer == "floor_h" else 2.0
    return 1.5 * floor if layer == "floor_h" else 1.5 * floor + 1.5


def last_map(settings=SETTINGS_PATH):
    """The map edited last, as remembered in `settings`, or None if there is none or it is gone."""
    try:
        with open(settings, encoding="utf-8") as f:
            path = json.load(f).get("last_map")
    except (OSError, ValueError, AttributeError):
        return None
    return path if isinstance(path, str) and os.path.isfile(path) else None


def remember_map(path, settings=SETTINGS_PATH):
    """Remember `path` in `settings` as the map edited last. Not being able to write it changes nothing else."""
    try:
        os.makedirs(os.path.dirname(settings), exist_ok=True)
        with open(settings, "w", encoding="utf-8") as f:
            json.dump({"last_map": os.path.abspath(path)}, f)
    except OSError:
        pass


class Editor:
    def __init__(self, path, settings=None):
        """Edit the map at `path` (a blank one if the file is not there yet). `settings` is the file to remember
        the map being edited in (see last_map), or None not to remember it."""
        self.path = path
        self.settings = settings
        if settings:
            remember_map(path, settings)
        self._scaled = {}
        self._atlas_stamp = None                # modification time of textures.png when last loaded
        self._atlas_check = 0.0                 # when textures.png was last checked for changes
        self.load_textures()
        self.font = pygame.font.SysFont("consolas,dejavusansmono,monospace", 15)
        self.small = pygame.font.SysFont("consolas,dejavusansmono,monospace", 13)

        if os.path.exists(path):
            self.level, note = load_level(path), f"Loaded {os.path.basename(path)}"
        else:
            self.level, note = default_level(), "New map (not saved yet)"
        self.undo, self.redo = [], []
        self.dirty = False
        self.revision = 0                       # bumps on every edit; keys the problems cache
        self._problems_cache = (None, [])
        self._short_cache = (None, False)
        self._trans_cache = (None, None)
        self._ceiling_cache = (None, False)
        self._width_cache = (None, 0)           # (what it was for, the Details pane's width)

        self.floor = 0                        # index of the floor being edited (0 = ground)
        self.dropdown_open = False
        self.show_legend = True                 # the key to the marks on the map (K toggles)
        self.rename = None                      # text being typed while renaming a floor
        self.value_edit = None                  # brush value being typed into the toolbar (None: not typing)
        self.new_name = None                    # name being typed in the New map dialog (None: closed)
        self.new_error = ""                     # why the typed name can't be used, shown in the dialog
        self.importing = None                   # the Import dialog (an ImportDialog), while it is open
        self.open_maps = None                   # file names listed in the Open dialog (None: closed)
        self.open_pick = 0                      # index of the picked one
        self.open_scroll = 0                    # index of the first one shown
        self.open_error = ""                    # why the picked map can't be opened, shown in the dialog
        self.open_click = (None, 0.0)           # (index, time) of the last click on the list, for double-clicks
        self.layer = "walls"
        self.tool = "paint"
        self.entity_brush = Entity(0.0, 0.0, tile=ENTITY_FIRST_TILE)   # settings new items start with
        self.selected = None                    # index in level.entities of the selected item, or None
        self.field_edit = None                  # [field key, text] while a number is typed in the Details pane
        self.menu_open = None                   # key of the Details field whose drop-down list is open
        self.guns_mode = False                  # the Guns section is showing instead of the map
        self.gun_selected = None                # index in level.guns of the gun being edited
        self.ammo_selected = None               # index in level.ammo_types of the ammo type being edited
        self.prefabs_mode = False               # the Prefabs section is showing instead of the map
        self.prefab_selected = None             # index in level.prefabs of the prefab being edited
        self.gun_preview = None                 # the live gun in the Guns section (a GunPreview), built when needed
        self.gun_preview_key = None             # what it was built for: (revision, gun, dark room)
        self.gun_continuous = False             # the Guns preview keeps firing and reloading
        self.gun_dark = False                   # ... in a dark room, so flashes and bullet lights show
        self.gizmo_selected = "bullet"          # which handle the placement views move: "bullet" or "effect"
        self.gizmo_drag = None                  # "picture" or "slider" while a handle is being dragged there
        self.guns_scroll = 0                    # how far the Guns section is scrolled up, in pixels (the wheel)
        self.hud_font = pygame.font.Font(None, 22)      # the game's own HUD font, for the text in the picture
        self.lights_mode = False                # the Lights section is showing instead of the map
        self.light_selected = None              # index in level.lights of the light being edited, or AMBIENT_ROW
        self.light_clock = 0.0                  # time for the flicker in a light's preview
        self.effects_mode = False               # the Effects section is showing instead of the map
        self.settings_mode = False              # the Map settings section is showing instead of the map
        self.settings_selected = None           # RULES_ROW, BUY_ROW or the index of a buy menu entry being edited
        self.settings_scroll = 0                # how far the Map settings section is scrolled up, in pixels
        self.prefabs_scroll = self.effects_scroll = self.lights_scroll = 0      # ... and the other sections
        self.details_scroll = 0                 # how far the Details pane's rows are scrolled up, in pixels
        self.details_for = None                 # what the pane last showed (another thing starts at the top)
        self.scroll_drag = None                 # (what, how far down its thumb it was grabbed) while a bar is dragged
        self.tips = []                          # [(rect, whole text)] of text drawn cut short, shown whole on hover
        self.effect_selected = None             # index in level.effects of the effect being edited
        self.barricade_selected = None          # index in level.barricades of the one being edited (Barricade tool)
        self.place_barricade_kind = ""          # the saved barricade type the Barricade tool places ("": plain)
        self.curve_shown = "zombie_count"       # the curve the Waves card shows (CURVE_TABS)
        self.curve_drag = None                  # the index of the point of it being dragged ...
        self.curve_drag_scale = None            # ... and the graph's scale, held while it is
        self.fx_sim = None                      # [ParticleSystem, settings it was made from, time to next burst]
        self.fx_scaled = {}                     # (tile, pixels) -> a particle picture at that size
        self.place_prefab = ""                  # the prefab the Entity tool places ("" = a plain item)
        self.tile_target = "tile"               # the tile field the atlas sets while a pane is open
        self.selection = {0}                    # selected atlas tile indices (0-based)
        self.value = {}                         # height brush per stored grid; see brush()
        self.ramp_dir = 1
        self.site_brush = 1                     # what the Sites layer paints (1 bomb site A, 2 B, HILL_SITE the hill)
        self.stair_step = 0.25
        self.atlas_drag = None                  # (start_cell, current_cell) while dragging
        self.atlas_pan = False                  # middle-drag / Space+drag in the zoomed atlas
        self.stairs_drag = None                 # (start_cell, current_cell) while dragging
        self.move_drag = None                   # (kind, thing, from_cell, cell) while dragging an item, spawn point or the start
        self.shape = "box"                      # what the Shape tool draws (one of SHAPES)
        self.shape_drag = None                  # (start_cell, current_cell, erasing) while dragging a shape
        self.shape_side = None                  # the wall side under the mouse where that drag started
        self.side_lock = None                   # the wall side a whole shape paints (None: the one at the mouse)
        self.spawn_order = 0                    # the order the Spawn tool gives the spawn points it places
        self.spawn_team = 0                     # ... and the team (0 anyone, T_TEAM, CT_TEAM)
        self.area = None                        # Select tool: the cells selected, (x0, y0, x1, y1), or None
        self.area_drag = None                   # (start cell, current cell) while dragging a selection
        self.clip = None                        # what was copied (mapfile.Area); kept across maps
        self.pasting = False                    # the copy follows the mouse; a click puts it down
        self.side_from = 0.0                    # the band a wall side's own tile covers, above the wall's foot
        self.side_to = 0.0                      # (0: up to the top)
        self.stroke = None                      # "paint" / "erase" while drawing on the map
        self.last_cell = None
        self.pan_drag = False
        self.zoom, self.pan = 32, [0, 0]
        self.mouse = pygame.mouse.get_pos()
        self.buttons, self.readouts = [], []
        self.confirm = None                     # action awaiting a second click
        self.message, self.message_until = note, time.time() + 4
        self.quit_armed = False
        self.running = True
        self.refit_until = 0.0                  # see start_maximized
        self.show_preview = DEFAULT_SHOW_PREVIEW
        self.preview = None                     # the live 3D view; built the first time it is shown
        self.look_drag = False                  # dragging inside the 3D view turns the camera
        self.camera_drag = False                # Camera tool: placing / aiming from the map
        self.fit_view()

    # ---------------------------------------------------------------- textures

    def load_textures(self):
        """(Re)read textures.png: the tiles, the atlas picture and everything derived from them."""
        tiles = unpack_atlas(ATLAS_PATH)
        atlas_img = pygame.image.load(ATLAS_PATH).convert_alpha()           # keeps transparent pixels
        self.tiles, self.atlas_img = tiles, atlas_img
        self.transparent = transparent_tiles(atlas_array(tiles))           # per tile: any see-through pixel?
        self.atlas_backdrop = self._make_backdrop(atlas_img.get_size())
        self.atlas_cols = atlas_img.get_width() // TILE
        self.atlas_rows = atlas_img.get_height() // TILE
        self.atlas_grid = self._make_atlas_grid()
        self.atlas_zoom = getattr(self, "atlas_zoom", 1.0)              # (a reload keeps the atlas zoom)
        self.atlas_scroll = getattr(self, "atlas_scroll", [0, 0])       # zoomed atlas pixels left of / above the view
        self._atlas_zoomed = {}                                         # zoom -> (backdrop, picture, grid)
        self.clamp_atlas_scroll()
        self._scaled = {}
        self._trans_cache = (None, None)
        self._atlas_stamp = self._atlas_mtime()
        self.gun_preview = self.gun_preview_key = None      # the live gun is drawn with the old textures
        self.selection = {i for i in getattr(self, "selection", {0}) if i < len(tiles)} or {0}
        if getattr(self, "preview", None) is not None:
            self.preview.set_textures(atlas_array(tiles))

    @staticmethod
    def _atlas_mtime():
        try:
            return os.stat(ATLAS_PATH).st_mtime_ns
        except OSError:
            return None

    def reload_textures(self, automatic=False):
        """Reload textures.png after it was edited. A file that cannot be read (missing, or caught
        half-written) leaves the textures as they were."""
        try:
            self.load_textures()
        except (pygame.error, OSError, ValueError) as error:
            if not automatic:
                self.say(f"Could not reload the textures: {error}")
            return False
        self.say("Textures reloaded" + (" (textures.png changed)" if automatic else ""))
        return True

    def watch_textures(self, now=None):
        """Reload by itself when textures.png changes on disk, checking twice a second."""
        now = time.time() if now is None else now
        if now - self._atlas_check < TEXTURE_CHECK_SECONDS:
            return
        self._atlas_check = now
        stamp = self._atlas_mtime()
        if stamp is not None and stamp != self._atlas_stamp:
            self._atlas_stamp = stamp               # a failed attempt is retried only after another change
            self.reload_textures(automatic=True)

    def start_maximized(self):
        """Maximize the window and fit the map to its new size. The size changes through
        resize events a moment later, so for the next REFIT_SECONDS each one re-fits the view;
        after that the view is the user's (panning and zooming are never undone)."""
        self.refit_until = time.time() + REFIT_SECONDS
        return maximize()

    # ---------------------------------------------------------------- layout

    def _size(self):
        return pygame.display.get_surface().get_size()

    def preview_width(self):
        """Width of the 3D view's column at the window's right; 0 while the view is hidden. It stays beside the
        Prefabs and Effects sections, so editing a prefab or an effect shows it changing in the world (an effect
        on the items, guns and bullets that use it); the Guns and Lights sections have previews of their own."""
        if not self.show_preview or (self.section_open() and not (self.prefabs_mode or self.effects_mode)):
            return 0
        return int(min(PREVIEW_MAX_W, max(PREVIEW_MIN_W, (self._size()[0] - PANEL_W) * 0.4)))

    def map_area(self):
        w, h = self._size()
        return pygame.Rect(PANEL_W, TOOLBAR_H, max(1, w - PANEL_W - self.preview_width() - self.details_width()),
                           max(1, h - TOOLBAR_H - STATUS_H))

    # ---------------------------------------------------------------- the Details pane

    def selected_gun(self):
        """The gun being edited in the Guns section, or None."""
        if self.guns_mode and self.gun_selected is not None and 0 <= self.gun_selected < len(self.level.guns):
            return self.level.guns[self.gun_selected]
        return None

    def selected_ammo(self):
        """The ammo type being edited in the Guns section, or None."""
        if self.guns_mode and self.ammo_selected is not None and 0 <= self.ammo_selected < len(self.level.ammo_types):
            return self.level.ammo_types[self.ammo_selected]
        return None

    def section_open(self):
        """True while a section (Guns, Prefabs, Effects, Lights, Map settings) is showing in place of the map."""
        return self.guns_mode or self.prefabs_mode or self.effects_mode or self.lights_mode or self.settings_mode

    def selected_prefab(self):
        """The prefab being edited in the Prefabs section, or None."""
        if self.prefabs_mode and self.prefab_selected is not None and 0 <= self.prefab_selected < len(self.level.prefabs):
            return self.level.prefabs[self.prefab_selected]
        return None

    def selected_light(self):
        """The light being edited in the Lights section, or None (also None while the map's ambient is chosen)."""
        if self.lights_mode and self.light_selected is not None and 0 <= self.light_selected < len(self.level.lights):
            return self.level.lights[self.light_selected]
        return None

    def ambient_chosen(self):
        return self.lights_mode and self.light_selected == AMBIENT_ROW

    def selected_effect(self):
        """The particle effect being edited in the Effects section, or None."""
        if self.effects_mode and self.effect_selected is not None and 0 <= self.effect_selected < len(self.level.effects):
            return self.level.effects[self.effect_selected]
        return None

    def editing_entity(self):
        """The thing whose item settings the pane edits: the selected prefab, or the selected item if it
        is a plain one (an item placed from a prefab takes its settings from the prefab)."""
        prefab = self.selected_prefab()
        if prefab is not None:
            return prefab
        e = self.selected_entity()
        return e if e is not None and not e.prefab else None

    def palette_active(self):
        """The Entity tool with nothing selected shows the list of prefabs to place."""
        return self.tool == "entity" and not self.section_open() and self.selected_entity() is None

    def selected_entity(self):
        """The selected item, or None (nothing selected, or the selection no longer exists)."""
        if self.section_open():
            return None
        if self.selected is not None and 0 <= self.selected < len(self.level.entities):
            return self.level.entities[self.selected]
        return None

    def details_width(self):
        chosen = (self.selected_entity() or self.selected_gun() or self.selected_ammo() or self.selected_prefab()
                  or self.selected_effect() or self.selected_light() or (self.ambient_chosen() or None)
                  or self.selected_buy_item() or self.selected_enemy() or self.selected_barricade()
                  or (self.settings_row() or None))
        if chosen is None and not self.palette_active() and not self.barricade_palette_active():
            return 0
        key = (self.revision, id(self.level), id(chosen), self.section_name(), self.place_prefab,
               self.place_barricade_kind, self.tool, self._size())
        if self._width_cache[0] != key:                 # (asked for all the time: worked out once per change)
            self._width_cache = (key, details.pane_width(self.details_fields(), (self.font, self.small),
                                                         max(PANE_WIDTH, self._size()[0] // 3)))
        return self._width_cache[1]

    def details_rect(self):
        """The docked Details pane, or None while nothing is selected."""
        width = self.details_width()
        if not width:
            return None
        w, h = self._size()
        return pygame.Rect(w - self.preview_width() - width, TOOLBAR_H, width, max(1, h - TOOLBAR_H - STATUS_H))

    def details_fields(self):
        """Fields describing the selected thing: a gun in the Guns section, else an item."""
        if self.settings_row() == RULES_ROW:
            return self.rules_fields()
        if self.settings_row() == BUY_ROW:
            return self.buy_menu_fields()
        entry = self.selected_buy_item()
        if entry is not None:
            return self.buy_item_fields(entry)
        enemy = self.selected_enemy()
        if enemy is not None:
            return self.enemy_fields(enemy)
        barricade = self.selected_barricade()
        if barricade is not None:
            return self.barricade_fields(barricade)
        light = self.selected_light()
        if light is not None:
            return self.light_fields(light)
        if self.ambient_chosen():
            return self.ambient_fields()
        effect = self.selected_effect()
        if effect is not None:
            return self.effect_fields(effect)
        gun = self.selected_gun()
        if gun is not None:
            return self.gun_fields(gun)
        ammo = self.selected_ammo()
        if ammo is not None:
            return self.ammo_fields(ammo)
        prefab = self.selected_prefab()
        if prefab is not None:
            return self.entity_fields(prefab, is_prefab=True)
        if self.barricade_palette_active():
            return self.barricade_palette_fields()
        e = self.selected_entity()
        if e is None:
            return self.palette_fields() if self.palette_active() else []
        return self.linked_fields(e) if e.prefab else self.entity_fields(e)

    def palette_fields(self):
        """The Entity tool's list of what to place: a plain item, or one of the map's prefabs."""
        def pick(name):
            return lambda: setattr(self, "place_prefab", name)

        fields = [Field("palette", "Place", "header", None, None),
                  Field("pick_plain", "Plain item", "button", (lambda: self.place_prefab == ""), None,
                        action=pick(""), icon=self.entity_brush.tile)]
        for i, p in enumerate(self.level.prefabs):
            fields.append(Field(f"pick_{i}", p.name, "button", (lambda n=p.name: self.place_prefab == n), None,
                                action=pick(p.name), icon=p.tile))
        return fields

    def placement_fields(self, e):
        """The settings that belong to where one placed item is, not to what it is: which wall of its cell it hangs
        on (when it has walls) and its elevation. Changing them moves this copy only, never a prefab or other copies."""
        fields = [Field("this_copy", "This copy only", "header", None, None)]
        cx, cy = math.floor(e.x), math.floor(e.y)
        walls = tuple(side for side in SIDES
                      if self.level.is_solid(cx + SIDE_VECTORS[side][0], cy + SIDE_VECTORS[side][1], e.span))
        if walls or e.wall:
            fields.append(Field("wall", "On wall", "enum", lambda: e.wall, lambda v: self.mount_entity(e, v),
                                choices=("",) + tuple(side for side in SIDES if side in walls or side == e.wall),
                                labels=WALL_LABELS))
        fields.append(Field("elevation", "Elevation", "num", lambda: e.elevation, lambda v: self.set_elevation(e, v),
                            step=ELEVATION_STEP, low=-MAX_ELEVATION, high=MAX_ELEVATION))
        return fields

    def set_elevation(self, e, value):
        """Raise or lower one placed item (one undo step). Only this item moves: not its prefab, not other copies."""
        value = round(max(-MAX_ELEVATION, min(MAX_ELEVATION, value)), 4)
        if value == e.elevation:
            return
        self.begin_edit()
        e.elevation = value
        self.say(f"Elevation {fmt(value)} (this copy only)")

    def linked_fields(self, e):
        """An item placed from a prefab: which prefab it is (change it, or choose none to detach it), buttons to edit
        that prefab or detach this item, and the item's settings, read-only because they come from the prefab."""
        names = ("",) + tuple(p.name for p in self.level.prefabs)

        def info(key, label, text):
            return Field(key, label, "info", (lambda t=text: t), None)

        fields = [Field("prefab", "Prefab", "enum", (lambda: e.prefab), self.set_instance_prefab, choices=names,
                        labels={"": "(none: detach)", **{n: n for n in names}}, wheel=False),
                  Field("edit_prefab", "Edit prefab", "button", None, None, action=lambda: self.edit_prefab(e.prefab),
                        text_override=f"Edit {e.prefab} in the Prefabs section"),
                  Field("detach", "Detach", "button", None, None, action=lambda: self.set_instance_prefab(""),
                        text_override="Detach: edit this item on its own"),
                  *self.placement_fields(e),
                  Field("from_prefab", "This item (set by its prefab)", "header", None, None),
                  info("where", "Where", f"cell {math.floor(e.x)}, {math.floor(e.y)} on {self.level.names[e.span]}"),
                  info("sprite", "Sprite", f"#{e.tile + 1}" + ("" if e.shown else "  (hidden)")),
                  info("mode", "Mode", MODE_LABELS[e.mode]),
                  info("effect", "Effect", self.effect_text(e))]
        if e.mode == "respawn":
            fields.append(info("respawn", "Respawns after", f"{e.respawn:g} s"))
        fields += [info("size", "Size", f"{e.size:g}"), info("lift", "Lift", f"{e.lift:g}"),
                   info("emits", "Emits", (e.emits or "none") + (f"  from {e.emits_offset_x:g}, {e.emits_offset_y:g}, "
                                                                  f"{e.emits_offset_z:g}" if e.emits and e.emits_override else "")),
                   info("light", "Light", e.light or "none"),
                   info("animations", "Animations", ", ".join(ANIMATION_LABELS[a.kind] for a in e.animations) or "none")]
        return fields

    @staticmethod
    def effect_text(e):
        """What an item gives, in words: 'Give a gun: Shotgun', 'Health: +25', 'Give ammo: 24 9mm rounds'..."""
        label = EFFECT_LABELS[e.effect]
        detail = {"score": f"+{e.amount:g}", "health": f"+{e.amount:g}", "item": f"{e.amount:g} x {e.item or 'Item'}",
                  "gun": e.gun or "(no gun)", "ammo": f"{e.amount:g} {e.ammo or 'default'} rounds"}.get(e.effect)
        return f"{label}: {detail}" if detail else label

    def edit_prefab(self, name):
        """Open the Prefabs section with the named prefab selected, to change what every copy of it looks like."""
        for i, prefab in enumerate(self.level.prefabs):
            if prefab.name == name:
                self.guns_mode = self.effects_mode = self.lights_mode = self.settings_mode = False
                self.prefabs_mode = True
                self.deselect()
                self.prefab_selected = i
                self.tile_target = "tile"
                self.say(f"Editing {name}: every item placed from it follows")
                return

    def entity_fields(self, e, is_prefab=False):
        """The settings of an item, or of a prefab (which also has a name and calls its picture an icon)."""
        def field(name, label, kind, **options):
            return Field(name, label, kind, (lambda n=name: getattr(e, n)),
                         (lambda v, n=name: self.set_entity(n, v)), **options)

        fields = [field("name", "Name", "text")] if is_prefab else             self.placement_fields(e) + [Field("item_settings", "Item settings", "header", None, None)]
        fields += [field("tile", "Icon" if is_prefab else "Sprite", "tile", low=0, high=len(self.tiles) - 1),
                   field("mode", "Mode", "enum", choices=ENTITY_MODES, labels=MODE_LABELS),
                   field("effect", "Effect", "enum", choices=ENTITY_EFFECTS, labels=EFFECT_LABELS)]
        if e.effect == "item":
            fields.append(field("item", "Item name", "text"))
        if e.effect == "gun":
            names = tuple(g.name for g in self.level.guns) or ("",)
            fields.append(field("gun", "Gun", "enum", choices=names,
                                labels={"": "(no guns yet)", **{n: n for n in names}}))
        if e.effect == "ammo":
            names = ("",) + tuple(a.name for a in self.level.ammo_types)
            fields.append(field("ammo", "Ammo type", "enum", choices=names,
                                labels={"": "(default bullet)", **{n: n for n in names}}))
        if e.effect in ("score", "health", "item", "ammo"):
            step = {"score": 5.0, "health": 5.0, "item": 1.0, "ammo": 6.0}[e.effect]
            fields.append(field("amount", "Amount" if e.effect != "ammo" else "Rounds", "num", step=step,
                                low=0.0, high=1000.0))
        if e.mode == "respawn":
            fields.append(field("respawn", "Respawn", "num", step=1.0, low=0.0, high=600.0, unit="s"))
        fields += [field("size", "Size", "num", step=0.1, low=0.1, high=3.0),
                   field("lift", "Lift", "num", step=0.1, low=-2.0, high=5.0),
                   field("shown", "Sprite", "enum", choices=(True, False), labels={True: "Shown", False: "Hidden"}),
                   field("emits", "Emits", "enum", choices=self.effect_choices(), labels=self.effect_labels()),
                   *(self.offset_fields(field, "emits", ("Offset x (east)", "Offset y (south)", "Offset up")) if e.emits else []),
                   field("light", "Light", "enum", choices=self.light_choices(), labels=self.light_labels())]
        fields.append(Field("animations", "Animations (none)" if not e.animations else "Animations",
                            "header", None, None))
        for i, a in enumerate(e.animations):
            fields.append(Field(f"a{i}", ANIMATION_LABELS[a.kind], "header", None, None,
                                action=(lambda i=i: self.remove_animation(i))))
            fields.append(Field(f"a{i}_speed", "Speed", "num", (lambda i=i: e.animations[i].speed),
                                (lambda v, i=i: self.set_animation(i, "speed", v)),
                                step=0.1, low=0.0, high=10.0, unit="/s"))
            if a.kind == "float":
                fields.append(Field(f"a{i}_amount", "Height", "num", (lambda i=i: e.animations[i].amount),
                                    (lambda v, i=i: self.set_animation(i, "amount", v)),
                                    step=0.05, low=0.0, high=2.0))
        unused = tuple(k for k in ANIMATION_KINDS if k not in {a.kind for a in e.animations})
        if unused:
            fields.append(Field("add_animation", "Add animation", "menu", None, self.add_animation,
                                choices=unused, labels=ANIMATION_LABELS, text_override="+ Add animation"))
        if not is_prefab:
            fields.append(Field("make_prefab", "Save as prefab", "button", None, None,
                                action=self.make_prefab, text_override="Save as a new prefab"))
        return fields

    def gun_fields(self, g):
        """The settings of one gun, for the Details pane in the Guns section."""
        def field(name, label, kind, cast=None, **options):
            return Field(name, label, kind, (lambda n=name: getattr(g, n)),
                         (lambda v, n=name, c=cast: self.set_gun(n, c(v) if c else v)), **options)

        fields = [field("name", "Name", "text"),
                  field("tile", "Sprite", "tile", int, low=0, high=len(self.tiles) - 1),
                  field("size", "Sprite size", "num", step=0.5, low=0.2, high=20.0),
                  field("mode", "Fire mode", "enum", choices=GUN_MODES, labels=GUN_MODE_LABELS),
                  field("shot", "Shot type", "enum", choices=SHOT_TYPES, labels=SHOT_LABELS)]
        if g.shot == "multi":
            fields.append(field("pellets", "Bullets / shot", "num", int, step=1.0, low=1, high=100))
        fields += [field("damage", "Damage", "num", step=1.0, low=0.0, high=10000.0),
                   field("fire_rate", "Shots / second", "num", step=0.5, low=0.1, high=100.0, unit="/s")]
        if g.mode != "single":
            fields.append(field("mag_size", "Rounds / mag", "num", int, step=1.0, low=1, high=1000))
        fields += [field("start_ammo", "Spare rounds", "num", int, step=6.0, low=0, high=100000),
                   field("reload_time", "Reload time", "num", step=0.1, low=0.0, high=60.0, unit="s"),
                   field("spread", "Spread", "num", step=0.5, low=0.0, high=45.0, unit=" deg"),
                   field("bullet_offset_x", "Bullets ahead", "num", step=0.05, low=-5.0, high=5.0),
                   field("bullet_offset_y", "Bullets right", "num", step=0.05, low=-5.0, high=5.0),
                   field("bullet_offset_z", "Bullets up", "num", step=0.05, low=-5.0, high=5.0)]
        names = ("",) + tuple(a.name for a in self.level.ammo_types)
        fields.append(field("ammo", "Ammo type", "enum", choices=names,
                            labels={"": "(default bullet)", **{n: n for n in names}}))
        fields.append(field("muzzle", "Muzzle effect", "enum", choices=self.effect_choices(),
                            labels=self.effect_labels()))
        fields += self.offset_fields(field, "muzzle", ("Offset ahead", "Offset right", "Offset up")) if g.muzzle else []
        fields.append(field("flash", "Muzzle light", "enum", choices=self.light_choices(), labels=self.light_labels()))
        return fields

    def ammo_fields(self, a):
        """The settings of one ammo type, for the Details pane in the Guns section."""
        def field(name, label, kind, cast=None, **options):
            return Field(name, label, kind, (lambda n=name: getattr(a, n)),
                         (lambda v, n=name, c=cast: self.set_ammo(n, c(v) if c else v)), **options)

        return [field("name", "Name", "text"),
                field("tile", "Bullet sprite", "tile", int, low=0, high=len(self.tiles) - 1),
                field("size", "Bullet size", "num", step=0.02, low=0.01, high=2.0),
                field("speed", "Bullet speed", "num", step=1.0, low=0.5, high=200.0, unit="/s"),
                field("range", "Bullet range", "num", step=1.0, low=0.5, high=200.0),
                field("damage_mult", "Damage x", "num", step=0.1, low=0.0, high=100.0),
                field("trail", "Trail effect", "enum", choices=self.effect_choices(), labels=self.effect_labels()),
                *(self.offset_fields(field, "trail", ("Offset behind", "Offset right", "Offset up")) if a.trail else []),
                field("light", "Bullet light", "enum", choices=self.light_choices(), labels=self.light_labels()),
                *self.name_list_fields(a, "player_hit_effects", "Player effect", self.effect_choices(), self.effect_labels()),
                *self.name_list_fields(a, "player_hit_lights", "Player light", self.light_choices(), self.light_labels()),
                *self.name_list_fields(a, "world_hit_effects", "World effect", self.effect_choices(), self.effect_labels()),
                *self.name_list_fields(a, "world_hit_lights", "World light", self.light_choices(), self.light_labels()),
                field("explodes", "Explosion", "enum", choices=(False, True), labels={False: "None", True: "Explodes"}),
                *(self.explosion_fields(field, a) if a.explodes else [])]

    def explosion_fields(self, field, a):
        """The rows of an ammo type that explodes: how far, how hard, and how it treats the shooter."""
        return [field("blast_radius", "Blast radius", "num", step=0.25, low=0.1, high=20.0),
                field("blast_damage", "Blast damage", "num", step=5.0, low=0.0, high=1000.0),
                field("knockback", "Knockback", "num", step=0.5, low=0.0, high=50.0, unit="/s"),
                field("air_knockback_mult", "Air knockback x", "num", step=0.1, low=0.0, high=10.0),
                field("self_damage_mult", "Self damage x", "num", step=0.05, low=0.0, high=10.0),
                field("self_knockback_mult", "Self knockback x", "num", step=0.1, low=0.0, high=10.0),
                *self.name_list_fields(a, "explosion_effects", "Explosion effect", self.effect_choices(), self.effect_labels()),
                *self.name_list_fields(a, "explosion_lights", "Explosion light", self.light_choices(), self.light_labels())]

    def name_list_fields(self, a, key, label, choices, labels):
        """One dropdown for each name in an ammo type's list `key` (hit effects or lights), then one more,
        empty, to add another. Choosing (none) on a row takes that name out of the list."""
        names = getattr(a, key)

        def setter(i):
            return lambda v: self.set_ammo_name(key, i, v)
        return [Field(f"{key}.{i}", f"{label} {i + 1}", "enum", (lambda i=i: names[i] if i < len(names) else ""),
                      setter(i), choices=choices, labels=labels)
                for i in range(len(names) + 1)]

    def set_ammo_name(self, key, index, value):
        """Set entry `index` of one of the selected ammo type's name lists (one past the end adds one; "" removes)."""
        a = self.selected_ammo()
        if a is None:
            return
        names = list(getattr(a, key))
        if not value:
            if index < len(names):
                del names[index]
        elif index < len(names):
            names[index] = value
        elif len(names) < MAX_HIT_NAMES:
            names.append(value)
        self.set_ammo(key, tuple(names))

    def details_rows(self):
        rect = self.details_rect()
        if rect is None:
            return []
        showing = (self.details_text()[0], self.selected, self.gun_selected, self.ammo_selected, self.prefab_selected,
                   self.effect_selected, self.light_selected, self.settings_selected, self.section_name())
        if showing != self.details_for:                 # something else is shown: back to the top of it
            self.details_for, self.details_scroll = showing, 0
        return details.rows_for(rect, self.details_fields(), (self.font, self.small), self.details_scroll)

    def set_entity(self, name, value):
        """Change one setting of the selected item (one undo step); new items start with it too."""
        e = self.editing_entity()
        if e is None:
            return
        is_prefab = e is self.selected_prefab()
        if name == "name" and is_prefab:
            value = self.new_prefab_name(str(value).strip()[:MAX_NAME], skip=self.prefab_selected) \
                if str(value).strip() else e.name
        if getattr(e, name) == value:
            return
        self.begin_edit()
        old, old_name = e.effect, e.name
        targets = [e] if is_prefab else [e, self.entity_brush]      # new items start with what you last set
        for t in targets:
            setattr(t, name, value)
            if name == "effect" and not (old in ("score", "health") and value in ("score", "health")):
                t.amount = {"score": 10.0, "health": 25.0, "item": 1.0, "gun": 1.0, "ammo": 24.0}.get(value, t.amount)
            if name == "item":
                t.item = str(value).strip()[:MAX_NAME]
        if is_prefab:
            if name == "name":
                for inst in self.level.entities:
                    if inst.prefab == old_name:
                        inst.prefab = value
            self.level.apply_prefabs()                                   # every item made from it follows

    def gun_names(self):
        return [g.name for g in self.level.guns]

    def new_gun_name(self, base="Gun", skip=None):
        taken = {g.name for i, g in enumerate(self.level.guns) if i != skip}
        if base not in taken:
            return base
        n = 2
        while f"{base} {n}"[:MAX_NAME] in taken:
            n += 1
        return f"{base} {n}"[:MAX_NAME]

    def add_gun(self):
        """Add a gun with the default settings (a plain pistol) and select it."""
        self.begin_edit()
        self.level.guns.append(Gun(name=self.new_gun_name("Gun")))
        self.gun_selected = len(self.level.guns) - 1
        self.tile_target = "tile"
        self.say("Added a gun: change it in the Details pane, then hand it out with a Give a gun item")

    def set_gun(self, name, value):
        """Change one setting of the selected gun (one undo step). Renaming keeps the items that give
        the gun pointing at it."""
        g = self.selected_gun()
        if g is None or getattr(g, name) == value:
            return
        if name == "name":
            value = self.new_gun_name(str(value).strip()[:MAX_NAME], skip=self.gun_selected) if str(value).strip() else g.name
            if value == g.name:
                return
        self.begin_edit()
        if name == "name":
            for e in self.level.entities + self.level.prefabs + self.level.settings.buy_items:
                if e.gun == g.name:
                    e.gun = value
            if self.level.settings.start_gun == g.name:
                self.level.settings.start_gun = value
        setattr(g, name, value)

    def new_ammo_name(self, base="Ammo", skip=None):
        taken = {a.name for i, a in enumerate(self.level.ammo_types) if i != skip}
        if base not in taken:
            return base
        n = 2
        while f"{base} {n}"[:MAX_NAME] in taken:
            n += 1
        return f"{base} {n}"[:MAX_NAME]

    def add_ammo_type(self):
        """Add a kind of ammunition (a plain bullet) and select it."""
        self.begin_edit()
        self.level.ammo_types.append(AmmoType(name=self.new_ammo_name("Ammo")))
        self.ammo_selected, self.gun_selected = len(self.level.ammo_types) - 1, None
        self.tile_target = "tile"
        self.say("Added an ammo type: give it to guns with their Ammo type setting")

    def set_ammo(self, name, value):
        """Change one setting of the selected ammo type (one undo step). Renaming keeps the guns and
        ammo pickups that use it pointing at it."""
        a = self.selected_ammo()
        if a is None or getattr(a, name) == value:
            return
        if name == "name":
            value = self.new_ammo_name(str(value).strip()[:MAX_NAME], skip=self.ammo_selected) \
                if str(value).strip() else a.name
            if value == a.name:
                return
        self.begin_edit()
        if name == "name":
            for g in self.level.guns:
                if g.ammo == a.name:
                    g.ammo = value
            for e in self.level.entities + self.level.prefabs:
                if e.ammo == a.name:
                    e.ammo = value
        setattr(a, name, value)

    def delete_ammo_type(self):
        a = self.selected_ammo()
        if a is not None:
            self.begin_edit()
            for g in self.level.guns:                    # guns that used it fall back to the default bullet
                if g.ammo == a.name:
                    g.ammo = ""
            for e in self.level.entities + self.level.prefabs:
                if e.ammo == a.name:
                    e.ammo = ""
            self.level.ammo_types.remove(a)
            self.ammo_selected = None

    def delete_gun(self):
        g = self.selected_gun()
        if g is not None:
            self.begin_edit()
            self.level.guns.remove(g)
            settings = self.level.settings              # it is no longer handed out at the start or sold
            if settings.start_gun == g.name:
                settings.start_gun = ""
            settings.buy_items = [b for b in settings.buy_items if not (b.kind == "gun" and b.gun == g.name)]
            self.gun_selected = None

    def add_animation(self, kind):
        e = self.editing_entity()
        if e is not None and kind in ANIMATION_KINDS and all(a.kind != kind for a in e.animations):
            self.begin_edit()
            e.animations.append(Animation(kind))
            self.level.apply_prefabs()

    def remove_animation(self, index):
        e = self.editing_entity()
        if e is not None and 0 <= index < len(e.animations):
            self.begin_edit()
            del e.animations[index]
            self.level.apply_prefabs()

    def set_animation(self, index, name, value):
        e = self.editing_entity()
        if e is not None and 0 <= index < len(e.animations) and getattr(e.animations[index], name) != value:
            self.begin_edit()
            setattr(e.animations[index], name, value)
            self.level.apply_prefabs()

    # ---------------------------------------------------------------- prefabs

    def new_prefab_name(self, base="Prefab", skip=None):
        taken = {p.name for i, p in enumerate(self.level.prefabs) if i != skip}
        if base not in taken:
            return base
        n = 2
        while f"{base} {n}"[:MAX_NAME] in taken:
            n += 1
        return f"{base} {n}"[:MAX_NAME]

    def add_prefab(self):
        """Add a prefab with the settings of the last item you edited and select it."""
        self.begin_edit()
        base = self.entity_brush.clone(x=0.0, y=0.0, span=0, name="", prefab="", animations=[])
        base.name = self.new_prefab_name("Prefab")
        self.level.prefabs.append(base)
        self.prefab_selected = len(self.level.prefabs) - 1
        self.tile_target = "tile"
        self.say("Added a prefab: set its icon and settings in the Details pane, then place it with the Entity tool")

    def make_prefab(self):
        """Turn the selected plain item into a new prefab (the item becomes an instance of it)."""
        e = self.selected_entity()
        if e is None or e.prefab:
            return
        self.begin_edit()
        base = e.item or e.ammo or e.gun or {"score": "Score", "health": "Health"}.get(e.effect, "Pickup")
        prefab = e.clone(x=0.0, y=0.0, span=0, name="", prefab="")
        prefab.name = self.new_prefab_name(f"{base} pickup"[:MAX_NAME])
        self.level.prefabs.append(prefab)
        e.prefab = prefab.name
        self.place_prefab = prefab.name
        self.say(f"Saved '{prefab.name}'. Edit it in the Prefabs section; place more with the Entity tool")

    def set_instance_prefab(self, name):
        """Point the selected item at a prefab, or at none ('') to detach it (it keeps its settings)."""
        e = self.selected_entity()
        if e is None or e.prefab == name:
            return
        self.begin_edit()
        e.prefab = name if self.level.prefab_named(name) else ""
        self.level.apply_prefabs()

    def delete_prefab(self):
        p = self.selected_prefab()
        if p is not None:
            self.begin_edit()
            for e in self.level.entities:                    # items made from it keep their settings
                if e.prefab == p.name:
                    e.prefab = ""
            self.level.prefabs.remove(p)
            if self.place_prefab == p.name:
                self.place_prefab = ""
            self.prefab_selected = None

    # ---------------------------------------------------------------- particle effects

    def offset_fields(self, field, prefix, labels):
        """The rows that let whatever uses an effect (a gun, an ammo type, an item) say where the effect starts
        instead of using the effect's own start offset: an on/off row, and the three offsets while it is on."""
        fields = [field(f"{prefix}_override", "Start offset", "enum", choices=(False, True),
                        labels={False: "Effect's own", True: "Override"})]
        on = field(f"{prefix}_override", "", "enum").get()
        if on:
            fields += [field(f"{prefix}_offset_{axis}", label, "num", step=0.05, low=-10.0, high=10.0)
                       for axis, label in zip("xyz", labels)]
        return fields

    def effect_choices(self):
        return ("",) + tuple(f.name for f in self.level.effects)

    def effect_labels(self):
        return {"": "(none)", **{f.name: f.name for f in self.level.effects}}

    def effect_fields(self, f):
        """The settings of one particle effect, for the Details pane in the Effects section."""
        def field(name, label, kind, cast=None, **options):
            return Field(name, label, kind, (lambda n=name: getattr(f, n)),
                         (lambda v, n=name, c=cast: self.set_effect(n, c(v) if c else v)), **options)

        fields = [field("name", "Name", "text"),
                  field("tile", "Particle", "tile", int, low=0, high=len(self.tiles) - 1),
                  field("kind", "Kind", "enum", choices=EFFECT_KINDS, labels=EFFECT_KIND_LABELS)]
        if f.kind == "burst":
            fields += [field("count", "Particles", "num", int, step=1.0, low=1, high=200),
                       field("interval", "Repeat every", "num", step=0.25, low=0.0, high=600.0, unit="s")]
        else:
            fields += [field("rate", "Per second", "num", step=5.0, low=0.5, high=500.0, unit="/s"),
                       field("duration", "Plays for", "num", step=0.05, low=0.0, high=60.0, unit="s")]
        fields += [field("life", "Life", "num", step=0.1, low=0.05, high=30.0, unit="s"),
                   field("life_var", "Life varies", "num", step=0.1, low=0.0, high=1.0),
                   field("speed", "Speed", "num", step=0.25, low=0.0, high=50.0, unit="/s"),
                   field("speed_var", "Speed varies", "num", step=0.1, low=0.0, high=1.0),
                   field("spread", "Spread", "num", step=5.0, low=0.0, high=180.0, unit=" deg"),
                   field("radius", "Start radius", "num", step=0.05, low=0.0, high=5.0),
                   field("offset_x", "Start offset X", "num", step=0.05, low=-10.0, high=10.0),
                   field("offset_y", "Start offset Y", "num", step=0.05, low=-10.0, high=10.0),
                   field("offset_z", "Start height +", "num", step=0.05, low=-10.0, high=10.0),
                   field("aim", "Direction", "enum", choices=EFFECT_AIMS, labels=EFFECT_AIM_LABELS),
                   field("relative", "Offset / dir. axes", "enum", choices=(False, True),
                         labels={False: "Map (x east, y south)", True: "Heading (x ahead, y right)"}),
                   field("gravity", "Gravity", "num", step=0.5, low=-50.0, high=50.0),
                   field("drag", "Drag", "num", step=0.25, low=0.0, high=20.0),
                   field("size_start", "Size at start", "num", step=0.02, low=0.0, high=3.0),
                   field("size_end", "Size at end", "num", step=0.02, low=0.0, high=3.0),
                   field("alpha_start", "Solid at start", "num", step=0.1, low=0.0, high=1.0),
                   field("alpha_end", "Solid at end", "num", step=0.1, low=0.0, high=1.0),
                   field("color", "Color", "enum", choices=EFFECT_COLORS, labels=EFFECT_COLOR_LABELS),
                   field("collide", "Hits walls", "enum", choices=(True, False), labels={True: "Stops", False: "Passes through"}),
                   field("light", "Particle light", "enum", choices=self.light_choices(), labels=self.light_labels())]
        at = next(i for i, x in enumerate(fields) if x.key == "color") + 1
        if f.color == "hue":                               # what the color choice needs, right below it
            fields.insert(at, field("hue", "Hue shift", "num", step=15.0, low=-180.0, high=180.0, unit=" deg"))
        elif f.color == "rgb":
            fields[at:at] = [field("tint_r", "Tint red", "num", int, step=15.0, low=0, high=255),
                             field("tint_g", "Tint green", "num", int, step=15.0, low=0, high=255),
                             field("tint_b", "Tint blue", "num", int, step=15.0, low=0, high=255)]
        if f.aim == "custom":                               # the direction to send them in, right below the Direction row
            at = next(i for i, x in enumerate(fields) if x.key == "aim") + 1
            fields[at:at] = [field("dir_x", "Direction X", "num", step=0.25, low=-100.0, high=100.0),
                             field("dir_y", "Direction Y", "num", step=0.25, low=-100.0, high=100.0),
                             field("dir_z", "Direction Z (up)", "num", step=0.25, low=-100.0, high=100.0)]
        return fields

    def new_effect_name(self, base="Effect", skip=None):
        taken = {f.name for i, f in enumerate(self.level.effects) if i != skip}
        if base not in taken:
            return base
        n = 2
        while f"{base} {n}"[:MAX_NAME] in taken:
            n += 1
        return f"{base} {n}"[:MAX_NAME]

    def add_effect(self):
        """Add a particle effect (a small puff) and select it."""
        self.begin_edit()
        self.level.effects.append(Effect(name=self.new_effect_name("Effect")))
        self.effect_selected = len(self.level.effects) - 1
        self.tile_target = "tile"
        self.say("Added an effect: shape it in the Details pane, then give it to a gun, an ammo type or an item")

    def set_effect(self, name, value):
        """Change one setting of the selected effect (one undo step). Renaming keeps the guns, ammo types
        and items that use it pointing at it."""
        f = self.selected_effect()
        if f is None or getattr(f, name) == value:
            return
        if name == "name":
            value = self.new_effect_name(str(value).strip()[:MAX_NAME], skip=self.effect_selected) \
                if str(value).strip() else f.name
            if value == f.name:
                return
        self.begin_edit()
        if name == "name":
            for g in self.level.guns:
                if g.muzzle == f.name:
                    g.muzzle = value
            for a in self.level.ammo_types:
                if a.trail == f.name:
                    a.trail = value
                a.player_hit_effects, a.world_hit_effects, a.explosion_effects = (
                    tuple(value if n == f.name else n for n in names)
                    for names in (a.player_hit_effects, a.world_hit_effects, a.explosion_effects))
            for e in self.level.entities + self.level.prefabs:
                if e.emits == f.name:
                    e.emits = value
        setattr(f, name, value)

    def delete_effect(self):
        f = self.selected_effect()
        if f is None:
            return
        self.begin_edit()
        for g in self.level.guns:                       # whatever used it simply has no effect now
            if g.muzzle == f.name:
                g.muzzle = ""
        for a in self.level.ammo_types:
            if a.trail == f.name:
                a.trail = ""
            a.player_hit_effects, a.world_hit_effects, a.explosion_effects = (
                tuple(n for n in names if n != f.name)
                for names in (a.player_hit_effects, a.world_hit_effects, a.explosion_effects))
        for e in self.level.entities + self.level.prefabs:
            if e.emits == f.name:
                e.emits = ""
        self.level.effects.remove(f)
        self.effect_selected = None

    # ---------------------------------------------------------------- lights

    def light_choices(self):
        return ("",) + tuple(light.name for light in self.level.lights)

    def light_labels(self):
        return {"": "(none)", **{light.name: light.name for light in self.level.lights}}

    def ambient_fields(self):
        """The map's ambient light, for the Details pane in the Lights section."""
        return [Field("ambient", "Ambient light", "num", (lambda: self.level.ambient), self.set_ambient,
                      step=0.05, low=MIN_AMBIENT, high=1.0)]

    def set_ambient(self, value):
        value = max(MIN_AMBIENT, min(1.0, float(value)))
        if value != self.level.ambient:
            self.begin_edit()
            self.level.ambient = round(value, 4)

    def light_fields(self, light):
        """The settings of one light, for the Details pane in the Lights section."""
        def field(name, label, kind, cast=None, **options):
            return Field(name, label, kind, (lambda n=name: getattr(light, n)),
                         (lambda v, n=name, c=cast: self.set_light(n, c(v) if c else v)), **options)

        return [field("name", "Name", "text"),
                field("r", "Red", "num", int, step=15.0, low=0, high=255),
                field("g", "Green", "num", int, step=15.0, low=0, high=255),
                field("b", "Blue", "num", int, step=15.0, low=0, high=255),
                field("intensity", "Brightness", "num", step=0.25, low=0.0, high=20.0),
                field("radius", "Reach", "num", step=0.5, low=0.5, high=20.0, unit=" cells"),
                field("flicker", "Flicker", "num", step=0.1, low=0.0, high=1.0),
                field("flicker_speed", "Flicker speed", "num", step=1.0, low=0.1, high=60.0, unit="/s"),
                field("duration", "Flash length", "num", step=0.02, low=0.02, high=5.0, unit="s"),
                field("wall_tile", "Glowing wall tile", "tile", int, low=-1, high=len(self.tiles) - 1)]

    def new_light_name(self, base="Light", skip=None):
        taken = {light.name for i, light in enumerate(self.level.lights) if i != skip}
        if base not in taken:
            return base
        n = 2
        while f"{base} {n}"[:MAX_NAME] in taken:
            n += 1
        return f"{base} {n}"[:MAX_NAME]

    def add_light(self):
        """Add a light (a warm one) and select it."""
        self.begin_edit()
        self.level.lights.append(Light(name=self.new_light_name("Light")))
        self.light_selected = len(self.level.lights) - 1
        self.tile_target = "wall_tile"
        self.say("Added a light: set its color and reach in the Details pane, then give it to a gun, item, ammo or effect")

    def set_light(self, name, value):
        """Change one setting of the selected light (one undo step). Renaming keeps what carries it pointing at it."""
        light = self.selected_light()
        if light is None or getattr(light, name) == value:
            return
        if name == "name":
            value = self.new_light_name(str(value).strip()[:MAX_NAME], skip=self.light_selected) \
                if str(value).strip() else light.name
            if value == light.name:
                return
        self.begin_edit()
        if name == "name":
            for g in self.level.guns:
                if g.flash == light.name:
                    g.flash = value
            for a in self.level.ammo_types:
                if a.light == light.name:
                    a.light = value
                a.player_hit_lights, a.world_hit_lights, a.explosion_lights = (
                    tuple(value if n == light.name else n for n in names)
                    for names in (a.player_hit_lights, a.world_hit_lights, a.explosion_lights))
            for f in self.level.effects:
                if f.light == light.name:
                    f.light = value
            for e in self.level.entities + self.level.prefabs:
                if e.light == light.name:
                    e.light = value
        setattr(light, name, value)

    def delete_light(self):
        light = self.selected_light()
        if light is None:
            return
        self.begin_edit()
        for g in self.level.guns:
            if g.flash == light.name:
                g.flash = ""
        for a in self.level.ammo_types:
            if a.light == light.name:
                a.light = ""
            a.player_hit_lights, a.world_hit_lights, a.explosion_lights = (
                tuple(n for n in names if n != light.name)
                for names in (a.player_hit_lights, a.world_hit_lights, a.explosion_lights))
        for f in self.level.effects:
            if f.light == light.name:
                f.light = ""
        for e in self.level.entities + self.level.prefabs:
            if e.light == light.name:
                e.light = ""
        self.level.lights.remove(light)
        self.light_selected = None

    # ---------------------------------------------------------------- map settings and the buy menu

    def settings_row(self):
        """RULES_ROW or BUY_ROW while one of those is chosen in the Map settings section, else None."""
        if self.settings_mode and self.settings_selected in (RULES_ROW, BUY_ROW):
            return self.settings_selected
        return None

    def selected_barricade(self):
        """The barricade being edited with the Barricade tool, or None."""
        i = self.barricade_selected
        if self.tool == "barricade" and not self.section_open() and i is not None and 0 <= i < len(self.level.barricades):
            return self.level.barricades[i]
        return None

    def selected_enemy(self):
        """The kind of enemy being edited in the Map settings section (zombies), or None."""
        chosen = self.settings_selected
        if self.settings_mode and isinstance(chosen, int) and chosen <= ENEMY_ROW:
            i = ENEMY_ROW - chosen
            if i < len(self.level.enemies):
                return self.level.enemies[i]
        return None

    def selected_buy_item(self):
        """The buy menu entry being edited in the Map settings section, or None."""
        items = self.level.settings.buy_items
        if self.settings_mode and self.settings_selected is not None and 0 <= self.settings_selected < len(items):
            return items[self.settings_selected]
        return None

    def rules_fields(self):
        """How the map is played, for the Details pane in the Map settings section."""
        rules = self.level.settings

        def field(name, label, kind, **options):
            return Field(name, label, kind, (lambda n=name: getattr(rules, n)),
                         (lambda v, n=name: self.set_rule(n, v)), **options)

        guns = ("",) + tuple(g.name for g in self.level.guns)
        fields = [field("mode", "Game mode", "enum", choices=GAME_MODES, labels=GAME_MODE_LABELS)]
        if rules.mode != "ffa":
            fields.append(field("friendly_fire", "Friendly fire", "enum", choices=(False, True),
                                labels={False: "Off", True: "On"}))
        if rules.mode == "bomb":
            fields.append(Field("bomb_note", "Teams", "info", (lambda: "1 = T (plants), 2 = CT; sites: Sites layer"),
                                None))
        if rules.mode == "koth":
            fields.append(Field("koth_note", "Teams", "info", (lambda: "1 = RED, 2 = BLU; the hill: Sites layer (R)"),
                                None))
        if rules.mode == "zombies":
            fields.append(Field("zombies_note", "Enemies", "info",
                                (lambda: "come in at Enemies spawn points (Spawn tool, Team)"), None))
        if rules.mode in ("ffa", "teams", "coop"):
            fields.append(field("respawn_delay", "Respawn time (s)", "num", step=1.0, low=0.0, high=60.0))
        if rules.has_waiting():                             # (a knocked-out player is out for a while)
            fields.append(field("death_cam", "Death camera", "enum", choices=(False, True),
                                labels={False: "Off", True: "On (watch others when out)"}))
            if rules.death_cam and rules.mode != "ffa":     # (free for all: no teammates, everyone can be watched)
                fields.append(field("death_cam_who", "Who can be watched", "enum", choices=DEATH_CAM_WHO,
                                    labels=DEATH_CAM_WHO_LABELS))
        fields += [field("max_health", "Max health", "num", step=10.0, low=1.0, high=10000.0),
                   field("start_money", "Start money", "num", step=50.0, low=0.0, high=MAX_MONEY),
                   field("kill_score", "Score / kill", "num", step=1.0, low=0.0, high=MAX_MONEY),
                   field("kill_money", "Money / kill", "num", step=50.0, low=0.0, high=MAX_MONEY),
                   field("start_gun", "Starting gun", "enum", choices=guns,
                         labels={"": "(none)", **{n: n for n in guns if n}})]
        if rules.mode == "bomb":
            for name, label, step in BOMB_FIELDS:
                low, high = BOMB_NUMBERS[name]
                fields.append(field(name, label, "num", step=step, low=low, high=high))
            effects = ("",) + tuple(e.name for e in self.level.effects)
            lights = ("",) + tuple(light.name for light in self.level.lights)
            fields += [field("bomb_effect", "Explosion effect", "enum", choices=effects,
                             labels={"": "(none)", **{n: n for n in effects if n}}),
                       field("bomb_light", "Explosion light", "enum", choices=lights,
                             labels={"": "(none)", **{n: n for n in lights if n}})]
        if rules.mode == "koth":
            for name, label, step in KOTH_FIELDS:
                low, high = KOTH_NUMBERS[name]
                fields.append(field(name, label, "num", step=step, low=low, high=high))
            low, high = BOMB_NUMBERS["round_end_time"]
            fields.append(field("round_end_time", "Round end pause (s)", "num", step=1.0, low=low, high=high))
        if rules.mode == "zombies":
            for name, label, step in ZOMBIE_FIELDS:
                low, high = ZOMBIE_NUMBERS[name]
                fields.append(field(name, label, "num", step=step, low=low, high=high))
            fields += [field("downed_can_shoot", "Downed can shoot", "enum", choices=(False, True),
                             labels={False: "No", True: "Yes"}),
                       field("keep_guns", "Back next round with", "enum", choices=(False, True),
                             labels={False: "Only the start gun", True: "Their guns"})]
            if self.curve_shown != "weight":                # (the Waves card's curve, typed exactly)
                fields += self.curve_point_fields(self.curve_shown)
        return fields

    def buy_menu_fields(self):
        """Whether the map has a buy menu and what it costs, for the Details pane in the Map settings section, and a
        list to add one of the map's guns, health or an item to it."""
        rules = self.level.settings

        def field(name, label, kind, **options):
            return Field(name, label, kind, (lambda n=name: getattr(rules, n)),
                         (lambda v, n=name: self.set_rule(n, v)), **options)

        choices = tuple(f"gun:{g.name}" for g in self.level.guns) + ("health:", "item:")
        labels = {c: {"gun": "Gun: ", "health": "Health", "item": "Inventory item"}[c.split(":")[0]]
                  + c.split(":", 1)[1] for c in choices}
        fields = [field("buy_menu", "Buy menu", "enum", choices=(False, True),
                        labels={False: "Off", True: "On (B in the game)"}),
                  field("buy_cost", "Costs", "enum", choices=BUY_COSTS, labels=BUY_COST_LABELS)]
        if len(rules.buy_items) < MAX_BUY_ITEMS:
            fields.append(Field("add_buy", "Add", "menu", None, self.add_buy_choice, choices=choices, labels=labels,
                                text_override="+ Add to the buy menu"))
        return fields

    def buy_item_fields(self, entry):
        """One entry of the buy menu, for the Details pane in the Map settings section."""
        def field(name, label, kind, **options):
            return Field(name, label, kind, (lambda n=name: getattr(entry, n)),
                         (lambda v, n=name: self.set_buy_item(n, v)), **options)

        fields = [field("name", "Button text", "text"),
                  field("kind", "Gives", "enum", choices=BUY_KINDS, labels=BUY_KIND_LABELS)]
        if entry.kind == "gun":
            names = tuple(g.name for g in self.level.guns) or ("",)
            fields.append(field("gun", "Gun", "enum", choices=names, labels={"": "(no guns yet)", **{n: n for n in names}}))
        elif entry.kind == "item":
            fields += [field("item", "Item name", "text"), field("amount", "How many", "num", step=1.0, low=0.0, high=1000.0)]
        else:
            fields.append(field("amount", "Health", "num", step=5.0, low=0.0, high=10000.0))
        fields += [field("price", "Price", "num", step=50.0 if self.level.settings.buy_cost == "money" else 5.0,
                         low=0.0, high=MAX_MONEY),
                   field("team", "For team", "enum", choices=SPAWN_TEAMS, labels=self.buy_team_labels()),
                   field("tile", "Icon", "tile", low=-1, high=len(self.tiles) - 1),
                   Field("move_up", "Move up", "button", None, None, action=lambda: self.move_buy_item(-1),
                         text_override="Move up the menu"),
                   Field("move_down", "Move down", "button", None, None, action=lambda: self.move_buy_item(1),
                         text_override="Move down the menu")]
        return fields

    def spawn_team_label(self, team):
        """What a spawn point's team is called in this map's game mode."""
        if team == ENEMY_SPAWN:
            return "Enemies"
        if self.level.settings.mode == "koth" and team in KOTH_NAMES:
            return KOTH_NAMES[team]
        return SPAWN_TEAM_LABELS[team]

    # ---------------------------------------------------------------- enemy kinds (zombies)

    def enemy_fields(self, enemy):
        """One kind of enemy, for the Details pane in the Map settings section: what it is called, who it chases,
        its numbers and color, and its attacks."""
        def field(name, label, kind, **options):
            return Field(name, label, kind, (lambda n=name: getattr(enemy, n)),
                         (lambda v, n=name: self.set_enemy(n, v)), **options)

        sheets = ("",) + sheet_names()
        if enemy.sheet not in sheets:                   # (a sheet this computer does not have: kept, and shown)
            sheets += (enemy.sheet,)
        fields = [field("name", "Name", "text"),
                  field("sheet", "Sprite sheet", "enum", choices=sheets,
                        labels={name: name or "Player (green shirt)" for name in sheets}),
                  field("pathing", "Chases", "enum", choices=ENEMY_PATHING, labels=ENEMY_PATHING_LABELS)]
        if enemy.pathing == "sticky":
            low, high = ENEMY_NUMBERS["switch_margin"]
            fields.append(field("switch_margin", "Switch if nearer by", "num", step=0.5, low=low, high=high,
                                unit=" cells"))
            low, high = ENEMY_NUMBERS["switch_delay"]
            fields.append(field("switch_delay", "... for (s)", "num", step=0.25, low=low, high=high))
        for name, label, step in ENEMY_FIELDS:
            low, high = ENEMY_NUMBERS[name]
            fields.append(field(name, label, "num", step=step, low=low, high=high))
        for c, label in enumerate(ENEMY_COLOR_NAMES):
            fields.append(Field(f"color{c}", label, "num", (lambda c=c: enemy.color[c]),
                                (lambda v, c=c: self.set_enemy_color(c, v)), step=15, low=0, high=255))
        for j, attack in enumerate(enemy.attacks):
            def afield(name, label, kind, j=j, attack=attack, **options):
                return Field(f"a{j}_{name}", label, kind, (lambda n=name: getattr(attack, n)),
                             (lambda v, n=name: self.set_attack(j, n, v)), **options)

            remove = (lambda j=j: self.remove_attack(j)) if len(enemy.attacks) > 1 else None
            fields.append(Field(f"attack{j}", f"Attack {j + 1}", "header", None, None, action=remove))
            fields.append(afield("kind", "Kind", "enum", choices=ATTACK_KINDS, labels=ATTACK_KIND_LABELS))
            for name, label, step in ATTACK_FIELDS:
                low, high = ATTACK_NUMBERS[name]
                fields.append(afield(name, label, "num", step=step, low=low, high=high))
        if len(enemy.attacks) < MAX_ATTACKS:
            fields.append(Field("add_attack", "Add attack", "button", None, None, action=self.add_attack,
                                text_override="+ Add an attack"))
        low, high = ENEMY_NUMBERS["max_per_round"]
        fields.append(field("max_per_round", "Most a round (0: any)", "num", step=1, low=low, high=high))
        return fields + self.curve_point_fields("weight")

    def new_enemy_name(self, base="Zombie", skip=None):
        taken = {e.name for i, e in enumerate(self.level.enemies) if i != skip}
        if base not in taken:
            return base
        n = 2
        while f"{base} {n}"[:MAX_NAME] in taken:
            n += 1
        return f"{base} {n}"[:MAX_NAME]

    def add_enemy(self):
        """Add a kind of enemy (a plain zombie to start with) and select it."""
        if len(self.level.enemies) >= MAX_ENEMIES:
            self.say(f"A map has at most {MAX_ENEMIES} kinds of enemy")
            return
        self.begin_edit()
        self.level.enemies.append(Enemy(name=self.new_enemy_name()))
        self.settings_selected = ENEMY_ROW - (len(self.level.enemies) - 1)
        self.field_edit = self.menu_open = None
        self.say("Added an enemy: set its health, speed and attacks in the Details pane")

    def delete_enemy(self):
        enemy = self.selected_enemy()
        if enemy is None:
            return
        self.begin_edit()
        self.level.enemies.remove(enemy)
        self.settings_selected = None

    def set_enemy(self, name, value):
        """Change one setting of the selected kind of enemy (one undo step). A name is kept unique."""
        enemy = self.selected_enemy()
        if enemy is None or getattr(enemy, name) == value:
            return
        if name == "name":
            value = self.new_enemy_name(str(value).strip()[:MAX_NAME] or "Zombie",
                                        skip=self.level.enemies.index(enemy))
            if value == enemy.name:
                return
        self.begin_edit()
        setattr(enemy, name, value)

    def set_enemy_color(self, channel, value):
        enemy = self.selected_enemy()
        value = max(0, min(255, int(round(value))))
        if enemy is None or enemy.color[channel] == value:
            return
        self.begin_edit()
        enemy.color[channel] = value

    def set_attack(self, j, name, value):
        enemy = self.selected_enemy()
        if enemy is None or not 0 <= j < len(enemy.attacks) or getattr(enemy.attacks[j], name) == value:
            return
        self.begin_edit()
        setattr(enemy.attacks[j], name, value)

    def add_attack(self):
        enemy = self.selected_enemy()
        if enemy is None or len(enemy.attacks) >= MAX_ATTACKS:
            return
        self.begin_edit()
        enemy.attacks.append(Attack())

    def remove_attack(self, j):
        enemy = self.selected_enemy()
        if enemy is None or len(enemy.attacks) <= 1 or not 0 <= j < len(enemy.attacks):
            return
        self.begin_edit()
        del enemy.attacks[j]

    def enemy_summary(self, enemy):
        attacks = ", ".join(f"{a.damage:g} dmg / {a.windup + a.cooldown:g}s" for a in enemy.attacks)
        return (f"health {enemy.health:g}   speed {enemy.speed:g}   {ENEMY_PATHING_LABELS[enemy.pathing].lower()}"
                f"   attacks: {attacks}   ${enemy.kill_reward:g} a kill")

    def buy_team_labels(self):
        """Names of the teams a buy menu entry can be for, in this map's game mode."""
        if self.level.settings.mode == "bomb":
            return {0: "Everyone", T_TEAM: "T only", CT_TEAM: "CT only"}
        if self.level.settings.mode == "koth":
            return {0: "Everyone", T_TEAM: "RED only", CT_TEAM: "BLU only"}
        suffix = "" if self.level.settings.has_teams() else " (no teams in this mode)"
        return {0: "Everyone", T_TEAM: "Team 1 only" + suffix, CT_TEAM: "Team 2 only" + suffix}

    def set_rule(self, name, value):
        """Change one of the map's settings (one undo step)."""
        rules = self.level.settings
        if getattr(rules, name) == value:
            return
        self.begin_edit()
        setattr(rules, name, value)
        if name == "mode" and value == "zombies" and not self.level.enemies:
            self.level.enemies.append(Enemy())
            self.say("Zombies: a plain Zombie was added under Enemies; place spawn points with the Spawn tool "
                     "(Team: Enemies)")
        if name == "buy_menu" and value and not rules.buy_items:
            self.say("Buy menu on: add entries with + Add to buy menu (players open it with B)")

    def set_buy_item(self, name, value):
        """Change one setting of the selected buy menu entry (one undo step). Choosing what it gives fills in a
        sensible amount and the first gun."""
        entry = self.selected_buy_item()
        if entry is None or getattr(entry, name) == value:
            return
        self.begin_edit()
        if name in ("name", "item"):
            value = str(value).strip()[:MAX_NAME]
        setattr(entry, name, value)
        if name == "kind":
            entry.amount = BUY_AMOUNTS[value]
            if value == "gun" and not entry.gun and self.level.guns:
                entry.gun = self.level.guns[0].name

    def add_buy_item(self, entry=None):
        """Add an entry to the buy menu (by default the first of the map's guns not in it yet, or health) and select
        it. Adding the first entry turns the buy menu on."""
        rules = self.level.settings
        if len(rules.buy_items) >= MAX_BUY_ITEMS:
            self.say(f"A buy menu holds at most {MAX_BUY_ITEMS} entries")
            return
        if entry is None:
            sold = {b.gun for b in rules.buy_items if b.kind == "gun"}
            gun = next((g.name for g in self.level.guns if g.name not in sold), None)
            entry = BuyItem(kind="gun", gun=gun) if gun else BuyItem(kind="health", amount=BUY_AMOUNTS["health"])
        self.begin_edit()
        rules.buy_items.append(entry)
        if len(rules.buy_items) == 1:
            rules.buy_menu = True
        self.settings_selected = len(rules.buy_items) - 1
        self.tile_target = "tile"
        self.field_edit = self.menu_open = None
        self.say(f"Added {entry.label()} to the buy menu: set its price in the Details pane")

    def add_buy_choice(self, choice):
        """An entry picked from the pane's "+ Add" list: "gun:<name>", "health:" or "item:"."""
        kind, name = choice.split(":", 1)
        entry = BuyItem(kind=kind, amount=BUY_AMOUNTS[kind])
        if kind == "gun":
            entry.gun = name
        self.add_buy_item(entry)

    def move_buy_item(self, step):
        """Move the selected entry up (-1) or down (1) the buy menu."""
        items, i = self.level.settings.buy_items, self.settings_selected
        if self.selected_buy_item() is None or not 0 <= i + step < len(items):
            return
        self.begin_edit()
        items[i], items[i + step] = items[i + step], items[i]
        self.settings_selected = i + step

    def delete_buy_item(self):
        entry = self.selected_buy_item()
        if entry is None:
            return
        self.begin_edit()
        self.level.settings.buy_items.remove(entry)
        self.settings_selected = None

    def select_entity(self, entity):
        self.field_edit = None
        self.selected = None
        for i, candidate in enumerate(self.level.entities):
            if candidate is entity:
                self.selected = i

    def deselect(self):
        self.selected, self.field_edit, self.menu_open = None, None, None
        self.barricade_selected = None
        self.gun_selected = self.ammo_selected = self.prefab_selected = self.effect_selected = None
        self.light_selected = self.settings_selected = None

    def delete_selected(self):
        if self.selected_buy_item() is not None:
            self.delete_buy_item()
            return
        if self.selected_barricade() is not None:
            self.begin_edit()
            del self.level.barricades[self.barricade_selected]
            self.barricade_selected = None
            return
        if self.selected_enemy() is not None:
            self.delete_enemy()
            return
        if self.selected_light() is not None:
            self.delete_light()
            return
        if self.selected_effect() is not None:
            self.delete_effect()
            return
        if self.selected_gun() is not None:
            self.delete_gun()
            return
        if self.selected_ammo() is not None:
            self.delete_ammo_type()
            return
        if self.selected_prefab() is not None:
            self.delete_prefab()
            return
        e = self.selected_entity()
        if e is not None:
            self.begin_edit()
            self.level.entities.remove(e)
            self.deselect()

    def show_details_row(self, key):
        """Scroll the Details pane so the row of field `key` is in view (and not under the Delete button)."""
        rect, rows = self.details_rect(), self.details_rows()
        row = next((r for r in rows if r.field.key == key), None)
        if row is None:
            return
        view = details.view_rect(rect)
        bottom = rect.bottom - 52 if self.details_delete_label() else view.bottom
        if row.rect.top < view.top:
            self.set_scroll("details", self.details_scroll - (view.top - row.rect.top))
        elif row.rect.bottom > bottom:
            self.set_scroll("details", self.details_scroll + row.rect.bottom - bottom)

    def details_click(self, pos):
        """A click inside the Details pane: step a value, start typing one, or delete the item."""
        rect = self.details_rect()
        rows = self.details_rows()
        if not details.view_rect(rect).collidepoint(pos):  # (rows scrolled up under the title are not there)
            return
        if self.details_delete_label() and details.button_rect(rect, rows).collidepoint(pos):
            self.delete_selected()
            return
        if self.details_delete_label() and details.button_kept(rect, rows) \
                and pos[1] >= details.button_rect(rect, rows).y - 8:
            return                                      # (rows scrolled under the Delete button are not there)
        for row in rows:
            f = row.field
            if f.kind == "info":
                continue
            if f.kind == "button":
                if details.button_box(row).collidepoint(pos) and f.action is not None:
                    f.action()
                    return                                          # (an action may change the rows under the mouse)
            elif f.kind == "header":
                if f.action is not None and row.plus.collidepoint(pos):
                    f.action()
            elif f.kind == "menu":
                if details.menu_anchor(row).collidepoint(pos):
                    self.menu_open = f.key
            elif row.minus.collidepoint(pos):
                f.set(f.stepped(-1))
            elif row.plus.collidepoint(pos):
                f.set(f.stepped(1))
            elif row.value.collidepoint(pos):
                if f.kind == "num":
                    self.field_edit = [f.key, f"{f.get():g}"]
                elif f.kind == "text":
                    self.field_edit = [f.key, str(f.get())]
                elif f.kind == "enum":
                    self.menu_open = f.key              # a drop-down list of the choices
                elif f.kind == "tile":
                    self.tile_target = f.key            # the next atlas click sets this picture

    def details_delete_label(self):
        """Text of the Details pane's delete button for what is selected ('' for none: the palette)."""
        if self.selected_buy_item() is not None:
            return "Remove from the buy menu"
        if self.selected_enemy() is not None:
            return "Delete enemy"
        if self.selected_barricade() is not None:
            return "Delete barricade"
        if self.settings_row() is not None:
            return ""
        if self.selected_light() is not None:
            return "Delete light"
        if self.selected_effect() is not None:
            return "Delete effect"
        if self.selected_gun() is not None:
            return "Delete gun"
        if self.selected_ammo() is not None:
            return "Delete ammo"
        if self.selected_prefab() is not None:
            return "Delete prefab"
        return "Delete" if self.selected_entity() is not None else ""

    def menu_click(self, pos):
        """A click while a drop-down list is open: pick the choice under it; any click closes the list."""
        key, self.menu_open = self.menu_open, None
        for row in self.details_rows():
            if row.field.key == key:
                for rect, choice in details.menu_rects(row):
                    if rect.collidepoint(pos):
                        row.field.set(choice)
                        return

    def details_wheel(self, pos, notches):
        """The wheel over the Details pane steps the value under it. While the pane has more rows than fit, only
        over a value's - / box / + (elsewhere the wheel scrolls the pane). True if a value was stepped."""
        view = self.scroll_view("details")
        scrolling = view is not None and view[1] > view[0].h
        for row in self.details_rows():
            if row.rect.collidepoint(pos) and row.field.kind in ("num", "enum", "tile") and row.field.wheel:
                if scrolling and not row.minus.union(row.plus).collidepoint(pos):
                    return False
                row.field.set(row.field.stepped(1 if notches > 0 else -1, abs(notches)))
                return True
        return False

    def editing_text(self):
        """True while the Details pane is taking a name (any characters) rather than a number."""
        if self.field_edit is None:
            return False
        return any(f.key == self.field_edit[0] and f.kind == "text" for f in self.details_fields())

    def finish_field_edit(self, commit):
        """Apply (or drop) the number typed into the Details pane."""
        typed, self.field_edit = self.field_edit, None
        if typed and commit:
            for f in self.details_fields():
                if f.key == typed[0]:
                    value = typed[1].strip() if f.kind == "text" else f.parsed(typed[1])
                    if value is not None:
                        f.set(value)

    def preview_column(self):
        """The whole right-hand column (title, picture, hints) of the 3D view, or None if hidden."""
        width = self.preview_width()
        if not width:
            return None
        w, h = self._size()
        return pygame.Rect(w - width, TOOLBAR_H, width, max(1, h - TOOLBAR_H - STATUS_H))

    def preview_rect(self):
        """Where the 3D picture is drawn (the picture's own aspect ratio), or None if hidden."""
        column = self.preview_column()
        if column is None:
            return None
        picture_w = column.w - 16
        return pygame.Rect(column.x + 8, column.y + PREVIEW_TITLE_H, picture_w, picture_w * HEIGHT // WIDTH)

    def over_preview(self):
        column = self.preview_column()
        return column is not None and column.collidepoint(self.mouse)

    def map_point(self, pos):
        """Position in map units (cells, fractions included) under a screen position."""
        origin = self.cell_rect(0, 0)
        return (pos[0] - origin.x) / self.zoom, (pos[1] - origin.y) / self.zoom

    def atlas_rect(self):
        return pygame.Rect(ATLAS_X, ATLAS_Y, self.atlas_img.get_width(), self.atlas_img.get_height())

    def gname(self, layer=None):
        """Stored grid for a layer on the floor being edited."""
        return grid_name(layer or self.layer, self.floor)

    def brush(self, grid):
        """Current height brush for a stored grid such as floor_h or ceil_h3."""
        return self.value.setdefault(grid, default_brush(grid))

    def layout(self):
        """Compute toolbar buttons and text readouts for the current state."""
        self.buttons, self.readouts = [], []
        count = self.level.floor_count
        row1 = [("drop", self.level.names[self.floor], "dropdown"), None,
                ("btn", "Rename(F2)", "rename"), ("btn", "+Floor", "addfloor")]
        if self.floor > 0:
            row1.append(("btn", "Del", "delfloor"))
        row1.append(("txt", f"floor {self.floor + 1} of {count}", DIM))
        row1 += [None, ("btn", "Guns(G)", "guns"), ("btn", "Prefabs(P)", "prefabs"), ("btn", "Effects(X)", "effects"), ("btn", "Lights(L)", "lights"),
                 ("btn", "Map settings(J)", "mapsettings"),
                 ("btn", "Key(K)", "legend"), ("btn", "3D(V)", "preview"),
                 ("btn", "Reload tex(F6)", "textures")]
        if self.show_preview:
            row1.append(("btn", "Cam->Start", "camstart"))
        row2 = [("txt", "Layer:", DIM)]
        row2 += [("btn", f"{LAYER_LABELS[name]}({i + 1})", f"layer:{name}") for i, name in enumerate(EDITOR_LAYERS)]
        row2.append(None)
        if self.layer in VALUE_LAYERS:
            typed = self.value_edit
            row2 += [("btn", "Val-", "val-"), ("btn", "Val+", "val+"),
                     ("val", f"value {fmt(self.brush(self.gname()))}" if typed is None else typed, "val_type")]
        elif self.layer == "ramp":
            row2 += [("btn", "Rotate(R)", "dir"), ("txt", f"rises {RAMP_NAMES[self.ramp_dir]}", ACCENT)]
        elif self.layer == "site":
            row2 += [("btn", "A / B / Hill / Barrier (R)", "dir"),
                     ("txt", f"paints {SITE_BRUSHES[self.site_brush]}", ACCENT), ("txt", "erase (E) clears", DIM)]
        elif self.layer == "sides":
            row2 += [("btn", "From-", "side_from-"), ("btn", "From+", "side_from+"),
                     ("txt", f"from {fmt(self.side_from)}", ACCENT),
                     ("btn", "To-", "side_to-"), ("btn", "To+", "side_to+"),
                     ("txt", f"to {fmt(self.side_to) if self.side_to else 'top'}", ACCENT),
                     ("btn", "Full height", "side_full")]
        if self.tool == "stairs":
            row2 += [None, ("btn", "Step-", "step-"), ("btn", "Step+", "step+"),
                     ("txt", f"step {fmt(self.stair_step)}", ACCENT)]
        if self.tool == "shape":
            row2 += [None] + [("btn", label, f"shape:{kind}") for kind, label in SHAPES.items()]
        if self.tool == "select":
            row2 += [None, ("btn", "Copy", "copy"), ("btn", "Cut", "cut"), ("btn", "Paste", "paste"),
                     ("btn", "Clear", "clear"), ("btn", "All", "select_all")]
            if self.area:
                x0, y0, x1, y1 = self.area
                row2.append(("txt", f"{x1 - x0 + 1}x{y1 - y0 + 1} selected", ACCENT))
            if self.clip:
                row2.append(("txt", f"copy: {self.clip.width}x{self.clip.height}"
                                    + (" (click to put it down, Esc stops)" if self.pasting else ""), DIM))
        if self.tool == "spawn":
            row2 += [None, ("btn", "Order-", "order-"), ("btn", "Order+", "order+"),
                     ("txt", f"order {self.spawn_order}", ACCENT),
                     ("btn", f"Team: {self.spawn_team_label(self.spawn_team)}", "spawn_team"),
                     ("txt", f"{len(self.level.spawners)} spawn point{'s' if len(self.level.spawners) != 1 else ''}"
                             " (0 is used first)", DIM)]
        if self.tool == "barricade":
            row2 += [None, ("txt", "Click an open ground floor cell (a gap in a wall) to board it up, or a barricade "
                                   "to edit it; right-click removes one", DIM)]
        if self.tool == "entity":
            row2 += [None, ("txt", "Pick what to place in the list on the right, click a cell to place it, or click an item to edit it", DIM)]
        row3 = [("btn", f"{name.capitalize()}({key})", f"tool:{name}") for name, key in TOOLS.items()]
        row3 += [None, ("btn", "Undo", "undo"), ("btn", "Redo", "redo"), None,
                 ("btn", "Border", "border"), ("txt", "Edge", DIM),
                 *[("btn", f"{side}{sign}", f"edge:{side}{sign}") for side in "LRTB" for sign in "+-"],
                 ("txt", f"{self.level.width}x{self.level.height}".ljust(7), ACCENT), None,
                 ("btn", "New", "new"), ("btn", "Open", "open"), ("btn", "Import", "import"), ("btn", "Reload", "reload"), ("btn", "Save", "save"),
                 ("btn", "Play(F5)", "play")]
        for y, items in zip(ROW_Y, (row1, row2, row3)):
            x = 8
            for item in items:
                if item is None:
                    x += 10
                elif item[0] == "txt":
                    self.readouts.append((item[1], (x, y + 8), item[2]))
                    x += self.font.size(item[1])[0] + 8
                elif item[0] == "drop":
                    rect = pygame.Rect(x, y, DROPDOWN_W, 34)
                    self.buttons.append((rect, item[1], item[2]))
                    x = rect.right + 4
                elif item[0] == "val":                  # the brush value: click it to type one
                    rect = pygame.Rect(x, y, max(90, self.font.size(item[1] + "|")[0] + 16), 34)
                    self.buttons.append((rect, item[1], item[2]))
                    x = rect.right + 4
                else:
                    rect = pygame.Rect(x, y, self.font.size(item[1])[0] + 16, 34)
                    self.buttons.append((rect, item[1], item[2]))
                    x = rect.right + 4
        return self.buttons

    def dropdown_items(self):
        """[(rect, label, action)] for the open floor list, one row per floor plus a final
        entry that adds a floor."""
        top = ROW_Y[0] + 34 + 2
        items = [(pygame.Rect(8, top + i * ITEM_H, DROPDOWN_W, ITEM_H), f"{i + 1}. {name}", f"floor:{i}")
                 for i, name in enumerate(self.level.names)]
        items.append((pygame.Rect(8, top + len(items) * ITEM_H, DROPDOWN_W, ITEM_H),
                      "+ New floor", "addfloor"))
        return items

    @staticmethod
    def _make_backdrop(size, square=8):
        """A gray checkerboard to put under tiles, so transparent pixels are visible as such."""
        backdrop = pygame.Surface(size)
        backdrop.fill((46, 48, 56))
        for y in range(0, size[1], square):
            for x in range(0, size[0], square):
                if (x // square + y // square) % 2:
                    pygame.draw.rect(backdrop, (70, 72, 82), (x, y, square, square))
        return backdrop

    def is_transparent_tile(self, tile_id):
        """True if the atlas tile for a map id has see-through pixels."""
        index = max(0, min(tile_id - 1, len(self.tiles) - 1))
        return bool(self.transparent[index])

    def _make_atlas_grid(self, cell=TILE):
        grid = pygame.Surface((self.atlas_cols * cell, self.atlas_rows * cell), pygame.SRCALPHA)
        for x in range(0, grid.get_width() + 1, cell):
            pygame.draw.line(grid, (255, 255, 255, 40), (x, 0), (x, grid.get_height()))
        for y in range(0, grid.get_height() + 1, cell):
            pygame.draw.line(grid, (255, 255, 255, 40), (0, y), (grid.get_width(), y))
        return grid

    def atlas_cell(self):
        """Size on screen of one atlas tile at the atlas panel's zoom."""
        return round(TILE * self.atlas_zoom)

    def atlas_origin(self):
        """Screen position of the zoomed atlas picture's top-left (it may be above / left of the view)."""
        rect = self.atlas_rect()
        return rect.x - self.atlas_scroll[0], rect.y - self.atlas_scroll[1]

    def atlas_pictures(self):
        """(backdrop, picture, grid) of the atlas at the panel's zoom."""
        if self.atlas_zoom == 1.0:
            return self.atlas_backdrop, self.atlas_img, self.atlas_grid
        if self.atlas_zoom not in self._atlas_zoomed:
            cell = self.atlas_cell()
            size = (self.atlas_cols * cell, self.atlas_rows * cell)
            self._atlas_zoomed[self.atlas_zoom] = (pygame.transform.scale(self.atlas_backdrop, size),
                                                   pygame.transform.scale(self.atlas_img, size),  # (nearest: crisp pixels)
                                                   self._make_atlas_grid(cell))
        return self._atlas_zoomed[self.atlas_zoom]

    def clamp_atlas_scroll(self):
        rect, cell = self.atlas_rect(), self.atlas_cell()
        self.atlas_scroll = [max(0, min(self.atlas_scroll[0], self.atlas_cols * cell - rect.w)),
                             max(0, min(self.atlas_scroll[1], self.atlas_rows * cell - rect.h))]

    def zoom_atlas(self, pos, step):
        """Zoom the atlas panel one step in (step > 0) or out, keeping the point under `pos` where it is."""
        i = ATLAS_ZOOMS.index(self.atlas_zoom) if self.atlas_zoom in ATLAS_ZOOMS else 0
        zoom = ATLAS_ZOOMS[max(0, min(len(ATLAS_ZOOMS) - 1, i + (1 if step > 0 else -1)))]
        if zoom == self.atlas_zoom:
            return
        rect, old = self.atlas_rect(), self.atlas_cell()
        mx, my = pos[0] - rect.x, pos[1] - rect.y
        self.atlas_zoom = zoom
        new = self.atlas_cell()
        self.atlas_scroll = [round((mx + self.atlas_scroll[0]) * new / old - mx),
                             round((my + self.atlas_scroll[1]) * new / old - my)]
        self.clamp_atlas_scroll()
        self.say(f"Atlas zoom {zoom:g}x" + (" (middle-drag or Space+drag to move around)" if zoom > 1 else ""))

    def atlas_cell_at(self, pos):
        """(column, row) of the atlas tile at a screen position, clamped to the tiles in view."""
        rect, cell = self.atlas_rect(), self.atlas_cell()
        x = min(max(pos[0], rect.left), rect.right - 1)
        y = min(max(pos[1], rect.top), rect.bottom - 1)
        ox, oy = self.atlas_origin()
        return (min(self.atlas_cols - 1, (x - ox) // cell), min(self.atlas_rows - 1, (y - oy) // cell))

    # ---------------------------------------------------------------- view

    def fit_view(self):
        """Zoom and center the map in the map area, clear of the rulers."""
        area = self.map_area()
        room_w, room_h = area.w - RULER, area.h - RULER
        self.zoom = max(8, min(64, room_w // (self.level.width + 1), room_h // (self.level.height + 1)))
        self.pan = [RULER + (room_w - self.level.width * self.zoom) // 2,
                    RULER + (room_h - self.level.height * self.zoom) // 2]

    def cell_at(self, pos):
        area = self.map_area()
        return (math.floor((pos[0] - area.x - self.pan[0]) / self.zoom),
                math.floor((pos[1] - area.y - self.pan[1]) / self.zoom))

    def cell_rect(self, cx, cy):
        area = self.map_area()
        return pygame.Rect(area.x + self.pan[0] + cx * self.zoom, area.y + self.pan[1] + cy * self.zoom,
                           self.zoom, self.zoom)

    def tile_surface(self, index, dim=False):
        index = max(0, min(index, len(self.tiles) - 1))
        key = (self.zoom, index, dim)
        if key not in self._scaled:
            surface = (self.tiles[index] if self.zoom == TILE else
                       pygame.transform.scale(self.tiles[index], (self.zoom, self.zoom)))
            if dim:
                surface = surface.copy()
                surface.fill((90, 90, 96), special_flags=pygame.BLEND_MULT)
            self._scaled[key] = surface
        return self._scaled[key]

    # ---------------------------------------------------------------- selection / brush

    def tile_index_at(self, pos):
        """Atlas tile index under a screen position, or None."""
        if not self.atlas_rect().collidepoint(pos):
            return None
        col, row = self.atlas_cell_at(pos)
        return row * self.atlas_cols + col

    def stamp(self):
        """[(dx, dy, map_id)] for the selection, relative to its bounding box's top-left."""
        points = [(i % self.atlas_cols, i // self.atlas_cols, i + 1) for i in sorted(self.selection)]
        if not points:
            return []
        min_x, min_y = min(p[0] for p in points), min(p[1] for p in points)
        return [(x - min_x, y - min_y, tile_id) for x, y, tile_id in points]

    def primary_id(self):
        """Map id used by single-tile tools (fill, border): the first selected tile."""
        return min(self.selection) + 1 if self.selection else 1

    def brush_value(self):
        """Single value the active layer paints with (fill, stairs, pick target)."""
        if self.layer in VALUE_LAYERS:
            return self.brush(self.gname())
        if self.layer == "ramp":
            return self.ramp_dir
        if self.layer == "site":
            return self.site_brush
        return self.primary_id()

    def drag_indices(self):
        (c0, r0), (c1, r1) = self.atlas_drag
        return {r * self.atlas_cols + c
                for r in range(min(r0, r1), max(r0, r1) + 1)
                for c in range(min(c0, c1), max(c0, c1) + 1)}

    # ---------------------------------------------------------------- editing

    def mods(self):
        return pygame.key.get_mods()

    def say(self, text, seconds=4.0):
        self.message, self.message_until = text, time.time() + seconds

    def touch(self):
        self.dirty = True
        self.quit_armed = False
        self.revision += 1

    def begin_edit(self):
        self.undo.append(self.level.copy())
        del self.undo[:-MAX_UNDO]
        self.redo.clear()
        self.touch()

    def apply_undo(self, source, target, name):
        if not source:
            self.say(f"Nothing to {name}")
            return
        target.append(self.level.copy())
        self.level = source.pop()
        self.clamp_floor()
        self.touch()

    def set_height(self, x, y, layer, value):
        """Set a cell's floor_h or ceil_h on the floor being edited. On a higher floor a cell
        without a room gets one: the other height comes from its brush (or a default room
        height), and the ceiling of the floor below is lowered to leave a slab."""
        level, floor_grid, ceil_grid = self.level, self.gname("floor_h"), self.gname("ceil_h")
        if not level.in_bounds(x, y):
            return
        if self.floor == 0:
            level.set(layer, x, y, value)
            return
        had_room = level.span_present(self.floor, x, y)
        level.set(self.gname(layer), x, y, value)
        if not had_room:
            if layer == "floor_h":
                want = self.brush(ceil_grid)
                level.set(ceil_grid, x, y, want if want - value >= MIN_SPAN else value + 1.5)
            else:
                want = self.brush(floor_grid)
                level.set(floor_grid, x, y, want if value - want >= MIN_SPAN else value - 1.5)
        self.make_slab(x, y)

    def make_slab(self, x, y):
        """Keep the ceiling of the room below this floor under this floor, leaving a slab
        SLAB thick (only where the lowered ceiling still leaves headroom)."""
        level, floor = self.level, self.floor
        if floor == 0 or level.is_solid(x, y, floor) or not level.span_present(floor, x, y):
            return
        below = max((s for s in range(floor) if level.span_present(s, x, y)), default=None)
        if below is None:
            return
        top = level.get(self.gname("floor_h"), x, y) - SLAB
        ceil_below, floor_below = grid_name("ceil_h", below), grid_name("floor_h", below)
        if level.get(ceil_below, x, y) > top and top - level.get(floor_below, x, y) >= PLAYER_HEIGHT:
            level.set(ceil_below, x, y, top)

    def remove_room(self, x, y):
        for layer in ROOM_HEIGHT_LAYERS:
            self.level.set(self.gname(layer), x, y, DEFAULTS[self.gname(layer)])

    def side_at(self, pos):
        """The side ("n", "e", "s" or "w") of the cell under screen point `pos` that the point is nearest to."""
        cell = self.cell_at(pos)
        rect = self.cell_rect(*cell)
        fx = (pos[0] - rect.x) / max(1, rect.w) - 0.5
        fy = (pos[1] - rect.y) / max(1, rect.h) - 0.5
        if abs(fx) >= abs(fy):
            return "e" if fx > 0 else "w"
        return "s" if fy > 0 else "n"

    def painted_side(self):
        """The side of a wall that painting on the WallSide layer changes: the one a Shape drag started on,
        or the one nearest the mouse."""
        return self.side_lock or self.side_at(self.mouse)

    def step_side_band(self, end, direction):
        """From- / From+ / To- / To+: move one end of the band a wall side's own tile is painted over. To "top"
        (0) steps down to just under a standard wall's height; the band never ends where it starts."""
        if end == "from":
            self.side_from = round(max(0.0, min(MAX_SIDE_BAND - SIDE_STEP, self.side_from + direction * SIDE_STEP)), 4)
            if self.side_to and self.side_to <= self.side_from:
                self.side_to = round(self.side_from + SIDE_STEP, 4)
        else:
            to = self.side_to or (1.0 if direction < 0 else 0.0)
            to = round(to + direction * SIDE_STEP, 4) if to else 0.0
            if to and to <= self.side_from:
                to = round(self.side_from + SIDE_STEP, 4)
            self.side_to = min(MAX_SIDE_BAND, to)
        self.say(f"Wall side band: from {fmt(self.side_from)} to {fmt(self.side_to) if self.side_to else 'the top'}")

    def set_side(self, cx, cy, side, tile_id):
        """Give the wall in (cx, cy) tile `tile_id` on one side (0: the wall's own tile), over the band set with
        From / To. Open cells are left alone."""
        if self.level.in_bounds(cx, cy) and self.level.walls[cy][cx]:
            self.level.set(f"side_{side}", cx, cy, tile_id)
            self.level.set(f"side_{side}_from", cx, cy, self.side_from if tile_id else 0.0)
            self.level.set(f"side_{side}_to", cx, cy, self.side_to if tile_id else 0.0)

    def side_tile(self, cx, cy, side):
        """The map id a wall shows on one side: its own for that side, else the wall's."""
        return self.level.get(f"side_{side}", cx, cy) or self.level.walls[cy][cx]

    def paint_at(self, cx, cy):
        layer, level = self.layer, self.level
        if layer == "sides":
            self.set_side(cx, cy, self.painted_side(), self.primary_id())
        elif layer in STAMP_LAYERS:
            for dx, dy, tile_id in self.stamp():
                self.put_tile(cx + dx, cy + dy, tile_id)
        elif layer == "wall_h":
            if level.in_bounds(cx, cy) and level.is_solid(cx, cy, self.floor):   # heights only mean something on walls
                level.set("wall_h", cx, cy, self.brush_value())
        elif self.edits_wall_ceiling(cx, cy):
            level.set("wall_ceil", cx, cy, self.brush_value())          # the ceiling over this wall
            if not self.wall_ceiling_matters(cx, cy, explicit_counts=False):
                self.say("A full-height wall reaches the ceiling anyway: this shows once the wall is "
                         "shortened on the WallH layer")
        elif self.edits_upper_wall(cx, cy):
            level.set(self.gname(), cx, cy, self.brush_value())        # base (FloorH) or top (CeilH) of the wall
        elif layer in ROOM_HEIGHT_LAYERS:
            self.set_height(cx, cy, layer, self.brush_value())
        elif layer == "site" and self.brush_value() in BARRIER_SITES and self.floor > 0:
            self.say("Barriers only work on the ground floor (floor 1)")
        else:
            level.set(self.gname(), cx, cy, self.brush_value())

    def put_tile(self, x, y, tile_id, layer=None):
        """Set one cell of a tile layer (walls, floor or ceiling texture; the active one unless given)
        to `tile_id`."""
        level, layer = self.level, layer or self.layer
        if layer == "walls" and level.in_bounds(x, y) and not level.walls[y][x]:
            for side in SIDES:                                  # a new wall shows its own tile on every side
                for name in (f"side_{side}", f"side_{side}_from", f"side_{side}_to"):
                    level.set(name, x, y, DEFAULTS[name])
        if layer == "walls" and level.in_bounds(x, y) and not level.is_solid(x, y, self.floor):
            level.set("wall_h", x, y, DEFAULTS["wall_h"])      # a new wall starts full height
            level.set("wall_floor", x, y, self.floor)          # ... and on this floor, not the ones below
            if self.floor > 0:                                  # its base: this floor's brush height
                level.set(self.gname("floor_h"), x, y, self.brush(self.gname("floor_h")))
        level.set(self.gname(layer), x, y, tile_id)

    def edits_upper_wall(self, cx, cy):
        """True when the FloorH / CeilH layers here set the base / top of a wall that starts on the
        floor being edited (a higher floor): there is no room in that cell to give heights to."""
        return (self.floor >= 1 and self.layer in ROOM_HEIGHT_LAYERS and self.level.in_bounds(cx, cy)
                and self.level.is_solid(cx, cy, self.floor) and self.level.wall_floor(cx, cy) == self.floor)

    def edits_wall_ceiling(self, cx, cy):
        """True when painting the CeilH layer here sets the ceiling over a wall (on the ground
        floor, where short walls live) instead of the ceiling of a room."""
        return (self.layer == "ceil_h" and self.floor == 0 and self.level.in_bounds(cx, cy)
                and self.level.is_solid(cx, cy))

    def wall_ceiling_matters(self, x, y, explicit_counts=True):
        """True if the ceiling over this wall can be seen: it is a short or see-through wall (or,
        with explicit_counts, one that already has a ceiling set)."""
        level = self.level
        if not level.in_bounds(x, y) or not level.walls[y][x]:
            return False
        return (level.short_wall_top(x, y) is not None or self.is_transparent_tile(level.walls[y][x])
                or (explicit_counts and level.has_explicit_wall_ceiling(x, y)))

    def erase_at(self, cx, cy):
        if self.layer == "sides":
            self.set_side(cx, cy, self.painted_side(), 0)
        elif self.layer == "walls":
            self.open_like_neighbors(cx, cy)
            for side in SIDES:                                          # ... and its sides' own tiles
                for name in (f"side_{side}", f"side_{side}_from", f"side_{side}_to"):
                    self.level.set(name, cx, cy, DEFAULTS[name])
            self.level.set("wall_h", cx, cy, DEFAULTS["wall_h"])       # an erased wall forgets its height
            self.level.set("wall_ceil", cx, cy, DEFAULTS["wall_ceil"])  # ... and its ceiling
            self.level.set("wall_floor", cx, cy, DEFAULTS["wall_floor"])
            self.level.set("walls", cx, cy, DEFAULTS["walls"])
        elif self.edits_wall_ceiling(cx, cy):
            self.level.set("wall_ceil", cx, cy, DEFAULTS["wall_ceil"])  # back to the automatic ceiling
        elif self.edits_upper_wall(cx, cy):
            self.level.set(self.gname(), cx, cy, DEFAULTS[self.gname()])   # (top: back to full height)
        elif self.floor >= 1 and self.layer in ROOM_HEIGHT_LAYERS:
            self.remove_room(cx, cy)                    # erasing a higher floor's height removes the room
        else:
            self.level.set(self.gname(), cx, cy, DEFAULTS[self.gname()])   # (wall height: back to full)

    def open_like_neighbors(self, x, y):
        """Before a ground wall is erased, give its cell the room around it: the floor and ceiling
        stored under a wall are never seen, so left as they are they could leave a sunken pocket
        (say floor 0, ceiling 1 beside a floor at 2) that still looks and blocks like a wall. A wall
        with its own ceiling (a short wall's, say a step's) leaves that ceiling, which is the one
        you could see over it, not the lower one of a room beside it."""
        level = self.level
        if not level.in_bounds(x, y) or not level.walls[y][x] or level.wall_floor(x, y):
            return
        if not level._beside(x, y, "floor_h"):          # boxed in by walls: nothing to match
            return
        level.set("floor_h", x, y, level.wall_base(x, y))
        level.set("ceil_h", x, y, level.wall_ceiling(x, y))
        for name in ("floor_tex", "ceil_tex"):          # the most common texture beside it
            values = level._beside(x, y, name)
            level.set(name, x, y, max(set(values), key=values.count))

    def stroke_cell(self, cell):
        (self.erase_at if self.stroke == "erase" else self.paint_at)(*cell)

    def fill(self, cell):
        if self.layer == "sides":                       # that side of the whole wall, where it faces open space
            side = self.side_at(self.mouse)
            dx, dy = SIDE_VECTORS[side]
            group = [(x, y) for x, y in self.level.wall_region(*cell)
                     if not (self.level.in_bounds(x + dx, y + dy) and self.level.walls[y + dy][x + dx])]
            if not group:
                self.say("Click a wall to give one side of the whole wall the selected tile")
                return
            self.begin_edit()
            for x, y in group:
                self.set_side(x, y, side, self.primary_id())
            return
        level, grid, value = self.level, self.gname(), self.brush_value()
        if self.layer == "wall_h":                      # sets the height of the whole wall you click
            group = level.wall_region(*cell)
            if not group:
                self.say("Click a wall to set the height of the whole wall")
                return
            self.begin_edit()
            for x, y in group:
                level.set("wall_h", x, y, value)
            return
        if not level.in_bounds(*cell) or level.get(grid, *cell) == value:
            return
        if self.layer == "site" and value in BARRIER_SITES and self.floor > 0:
            self.say("Barriers only work on the ground floor (floor 1)")
            return
        self.begin_edit()
        if self.layer in ROOM_HEIGHT_LAYERS and self.floor >= 1:
            for x, y in level.region(grid, *cell):      # per cell, so rooms get created properly
                if not level.is_solid(x, y, self.floor):
                    self.set_height(x, y, self.layer, value)
        else:
            level.flood_fill_cells(grid, cell[0], cell[1], value)

    def map_click(self, cell, button):
        """Start of a click on the map: left uses the active tool, right always erases."""
        if button == 1 and self.start_move(cell):
            return
        if button == 3 and self.tool == "entity":
            self.remove_entities(cell)
            return
        if self.tool == "spawn":
            (self.remove_spawners if button == 3 else self.place_spawner)(cell)
            return
        if self.tool == "barricade":
            (self.remove_barricade if button == 3 else self.place_barricade)(cell)
            return
        if self.tool == "select":
            if button == 3:                             # right-click: stop pasting, or let go of the selection
                if self.pasting:
                    self.pasting = False
                else:
                    self.area = None
                return
            if self.pasting:
                x, y = self.paste_corner(cell)
                self.begin_edit()
                paste_area(self.level, self.clip, x, y, self.floor)
                self.area = area_rect(self.level, (x, y), (x + self.clip.width - 1, y + self.clip.height - 1))
                self.say(f"Pasted on {self.level.names[self.floor]}: click again for another, Esc stops")
            else:
                self.area_drag = (cell, cell)
            return
        if self.tool == "shape":
            self.shape_drag = (cell, cell, button == 3)
            self.shape_side = self.side_at(self.mouse)  # (the WallSide layer paints the side picked here)
            return
        if button == 3:
            self.begin_edit()
            self.stroke, self.last_cell = "erase", cell
            self.stroke_cell(cell)
            return
        tool = self.tool
        if tool in ("paint", "erase"):
            self.begin_edit()
            self.stroke, self.last_cell = tool, cell
            self.stroke_cell(cell)
        elif tool == "fill":
            self.fill(cell)
        elif tool == "pick":
            self.pick(cell)
        elif tool == "start":
            self.place_start(cell)
        elif tool == "camera":
            self.place_camera(cell, self.map_point(self.mouse))
        elif tool == "entity":
            self.place_entity(cell)
        elif tool == "stairs":
            if self.layer not in ("floor_h", "wall_h"):
                self.layer = "floor_h"
                self.say("Stairs paint floor heights (or wall steps on WallH): switched to the FloorH layer")
            self.stairs_drag = (cell, cell)

    def entities_in(self, cell):
        """The entities standing in this cell on the floor being edited."""
        return [e for e in self.level.entities
                if (math.floor(e.x), math.floor(e.y)) == tuple(cell) and e.span == self.floor]

    def mount_side(self, cell):
        """The side of open cell `cell` that the mouse is near and that has a wall on the floor being edited
        (an item added there hangs on that wall), or None."""
        level = self.level
        if not level.in_bounds(*cell) or not level.span_present(self.floor, *cell) or level.is_solid(*cell, self.floor):
            return None
        rect = self.cell_rect(*cell)
        fx = (self.mouse[0] - rect.x) / max(1, rect.w)
        fy = (self.mouse[1] - rect.y) / max(1, rect.h)
        near = {"w": fx, "e": 1.0 - fx, "n": fy, "s": 1.0 - fy}
        side = min(near, key=near.get)
        dx, dy = SIDE_VECTORS[side]
        if near[side] > MOUNT_ZONE or not level.is_solid(cell[0] + dx, cell[1] + dy, self.floor):
            return None
        return side

    def mount_entity(self, e, wall):
        """Hang an item on the wall on side `wall` of its cell, or ("") stand it in the middle of the cell."""
        if e.wall == wall:
            return
        self.begin_edit()
        e.wall = wall
        e.x, e.y = mounted_position(math.floor(e.x), math.floor(e.y), wall)

    def place_entity(self, cell):
        """Entity tool: clicking an item selects it (its settings appear in the Details pane);
        clicking an empty cell adds an item there, in the middle of the cell on the floor being
        edited, with the settings of the last item you edited, and selects it."""
        level = self.level
        if not level.in_bounds(*cell):
            return
        found = self.entities_in(cell)
        if found:
            self.select_entity(found[0])
            return
        if not level.span_present(self.floor, *cell) and not level.is_solid(*cell, self.floor):
            self.deselect()
            self.say("An item needs an open floor or the top of a wall to stand on: no room in this cell on this floor")
            return
        self.begin_edit()
        wall = self.mount_side(cell) or ""             # (near a walled side: hung on that wall)
        x, y = mounted_position(*cell, wall)
        prefab = level.prefab_named(self.place_prefab) if self.place_prefab else None
        if prefab is not None:                      # an instance of the chosen prefab: it follows the prefab
            level.entities.append(prefab.clone(x=x, y=y, span=self.floor, name="", prefab=prefab.name, wall=wall))
        else:
            level.entities.append(self.entity_brush.clone(x=x, y=y, span=self.floor, animations=[], wall=wall))
        self.select_entity(level.entities[-1])
        self.say("Added an item: change its settings in the Details pane" if prefab is None
                 else f"Placed {prefab.name}: edit it in the Prefabs section")

    def remove_entities(self, cell):
        found = self.entities_in(cell)
        if found:
            self.begin_edit()
            for e in found:
                self.level.entities.remove(e)
            self.deselect()

    def start_move(self, cell):
        """Pressing on an item (Entity tool), a spawn point (Spawn tool) or the start (Start tool) picks it
        up: dragging it to another cell moves it there; letting go where it was is a plain click."""
        level, kind, thing = self.level, None, None
        if not level.in_bounds(*cell):
            return False
        if self.tool == "entity" and self.entities_in(cell):
            kind, thing = "entity", self.entities_in(cell)[0]
            self.select_entity(thing)
        elif self.tool == "spawn" and self.spawners_in(cell):
            kind, thing = "spawn", self.spawners_in(cell)[0]
        elif self.tool == "start" and cell == (int(level.start_x), int(level.start_y)) and level.start_span == self.floor:
            kind = "start"
        if kind is None:
            return False
        self.move_drag = (kind, thing, tuple(cell), tuple(cell))
        return True

    def move_target_ok(self, kind, cell):
        """Whether the thing being dragged can be put down in `cell` on the floor being edited."""
        level = self.level
        if not level.in_bounds(*cell):
            return False
        if kind == "entity":                        # (an item may also stand on top of a wall)
            return level.span_present(self.floor, *cell) or level.is_solid(*cell, self.floor)
        return level.span_present(self.floor, *cell)

    def finish_move(self):
        """Let go of the dragged item, spawn point or start: move it to the cell under the mouse."""
        kind, thing, start, cell = self.move_drag
        self.move_drag = None
        level = self.level
        if cell == start:                           # not moved: a plain click
            if kind == "spawn":
                self.place_spawner(start)
            elif kind == "start":
                self.place_start(start)
            return
        if not self.move_target_ok(kind, cell):
            self.say("Can't move it there: no room in that cell on this floor")
            return
        if kind == "entity" and thing in level.entities:
            self.begin_edit()
            dx, dy = SIDE_VECTORS.get(thing.wall, (0, 0))
            if thing.wall and (level.is_solid(*cell, self.floor) or not level.is_solid(cell[0] + dx, cell[1] + dy, self.floor)):
                thing.wall = ""                         # no wall on that side there: stand in the middle
            if thing.wall:
                thing.x, thing.y = mounted_position(*cell, thing.wall)
            else:                                       # keep where in its cell it stood
                thing.x, thing.y = cell[0] + thing.x - math.floor(thing.x), cell[1] + thing.y - math.floor(thing.y)
            self.say(f"Moved the item to {cell[0]}, {cell[1]}")
        elif kind == "spawn" and thing in level.spawners:
            self.begin_edit()
            thing.x, thing.y = cell[0] + 0.5, cell[1] + 0.5
            self.say(f"Moved the spawn point to {cell[0]}, {cell[1]}")
        elif kind == "start":
            self.begin_edit()
            level.start_x, level.start_y = cell[0] + 0.5, cell[1] + 0.5
            self.say(f"Moved the start to {cell[0]}, {cell[1]}")

    def place_camera(self, cell, point):
        """Camera tool: stand the 3D view's camera in this cell, on the floor being edited (or the
        nearest floor that has a room there). Dragging afterwards turns it toward the cursor."""
        preview = self.ensure_preview()
        preview.sync(self.level, self.revision, force=True)
        if preview.place(cell[0] + 0.5, cell[1] + 0.5, self.floor):
            self.camera_drag = True
        else:
            self.say("The camera can't stand there (wall, no room, or too low)")

    def area_action(self, action):
        """Copy, Cut, Clear, Paste and All for the Select tool (see the module's notes on copy and paste)."""
        floor = self.level.names[self.floor]
        if action == "select_all":
            self.tool, self.pasting = "select", False
            self.area = (0, 0, self.level.width - 1, self.level.height - 1)
            self.say(f"Selected the whole map on {floor}")
        elif action == "paste":
            if self.clip is None:
                self.say("Nothing copied yet: select an area and Copy (Ctrl+C) first")
                return
            self.tool, self.pasting = "select", True
            self.say(f"Click to put the {self.clip.width}x{self.clip.height} copy down on {floor}; Esc stops")
        elif self.area is None:
            self.say("Select an area first: drag on the map with the Select tool (M)")
        else:
            corners = self.area[:2], self.area[2:]
            if action in ("copy", "cut"):
                self.clip = copy_area(self.level, *corners, self.floor)
            if action in ("cut", "clear"):
                self.begin_edit()
                clear_area(self.level, *corners, self.floor)
            done = {"copy": "Copied", "cut": "Cut", "clear": "Cleared"}[action]
            self.say(f"{done} {self.area[2] - self.area[0] + 1}x{self.area[3] - self.area[1] + 1} of {floor}"
                     + ("; Ctrl+V pastes it" if action != "clear" else ""))

    def paste_corner(self, cell):
        """The top-left cell the copy goes at when the mouse is over `cell` (the copy is centered on it)."""
        return cell[0] - self.clip.width // 2, cell[1] - self.clip.height // 2

    def spawners_in(self, cell):
        """The spawn points in this cell on the floor being edited."""
        return [s for s in self.level.spawners
                if (math.floor(s.x), math.floor(s.y)) == tuple(cell) and s.span == self.floor]

    def place_spawner(self, cell):
        """Spawn tool: add a spawn point in the middle of an open cell, with the chosen order. Clicking one gives
        it the chosen order, or turns it a quarter if it has that order already."""
        level = self.level
        if not level.in_bounds(*cell):
            return
        found = self.spawners_in(cell)
        if not found and not level.span_present(self.floor, *cell):
            self.say("A spawn point needs open floor: no room in this cell on this floor")
            return
        self.begin_edit()
        team = self.spawn_team_label(self.spawn_team)
        if not found:
            level.spawners.append(Spawner(cell[0] + 0.5, cell[1] + 0.5, self.floor, 0.0, self.spawn_order, self.spawn_team))
            self.say(f"Spawn point {len(level.spawners)}, order {self.spawn_order}, {team} (click it again to turn it)")
        elif found[0].order != self.spawn_order or found[0].team != self.spawn_team:
            found[0].order, found[0].team = self.spawn_order, self.spawn_team
            self.say(f"Spawn point now has order {self.spawn_order}, {team}")
        else:
            found[0].angle = (found[0].angle + math.pi / 2) % math.tau
            self.say(f"Spawn point faces {math.degrees(found[0].angle):.0f} deg")

    def place_barricade(self, cell):
        """Barricade tool: board up an open ground floor cell with what is picked to place (a plain barricade, or one
        of the saved types) and select it, or select the one there."""
        level = self.level
        if not level.in_bounds(*cell):
            return
        found = level.barricade_at(*cell)
        if found is not None:
            self.barricade_selected = found
            self.field_edit = self.menu_open = None
            return
        if self.floor != 0:
            self.say("Barricades go on the ground floor")
            return
        if level.is_solid(*cell) or not level.span_present(0, *cell):
            self.say("A barricade goes in an open cell: the gap in a wall that enemies come through")
            return
        self.begin_edit()
        kind = self.place_barricade_kind if level.barricade_kind_named(self.place_barricade_kind) else ""
        level.barricades.append(Barricade(*cell, kind=kind))
        level.apply_barricade_kinds()
        self.barricade_selected = len(level.barricades) - 1
        self.field_edit = self.menu_open = None
        self.tile_target = "tile"
        note = "" if level.settings.mode == "zombies" else " (barricades are only used in Zombies)"
        what = f"A {kind}" if kind else f"Barricade {len(level.barricades)}"
        self.say(f"{what}: set it up in the Details pane, or save it as a type to place more{note}")

    def remove_barricade(self, cell):
        found = self.level.barricade_at(*cell)
        if found is not None and self.floor == 0:
            self.begin_edit()
            del self.level.barricades[found]
            self.barricade_selected = None
            self.say(f"Removed a barricade ({len(self.level.barricades)} left)")

    def barricade_palette_active(self):
        """The Barricade tool with no barricade selected shows the list of what to place."""
        return self.tool == "barricade" and not self.section_open() and self.selected_barricade() is None

    def barricade_palette_fields(self):
        """The Barricade tool's list of what to place: a plain barricade, or one of the map's saved types."""
        def pick(name):
            return lambda: setattr(self, "place_barricade_kind", name)

        fields = [Field("palette", "Place", "header", None, None),
                  Field("pick_plain", "Plain barricade", "button", (lambda: self.place_barricade_kind == ""), None,
                        action=pick(""), icon=BARRICADE_TILE)]
        for i, kind in enumerate(self.level.barricade_kinds):
            fields.append(Field(f"pick_{i}", kind.name, "button", (lambda n=kind.name: self.place_barricade_kind == n),
                                None, action=pick(kind.name), icon=barricade_icon(kind)))
        if not self.level.barricade_kinds:
            fields.append(Field("no_types", "Types", "info",
                                (lambda: "none yet: select a barricade, Save as a type"), None))
        return fields

    def barricade_target(self):
        """What the Details pane's barricade settings change: the selected barricade's saved type (and so every
        barricade of it) when it has one, else the barricade itself."""
        barricade = self.selected_barricade()
        if barricade is None:
            return None
        return self.level.barricade_kind_named(barricade.kind) if barricade.kind else barricade

    def barricade_fields(self, barricade):
        """One barricade, for the Details pane (Barricade tool): its type, then its settings (those of its type, when
        it has one, which change every barricade of that type)."""
        target = self.barricade_target() or barricade

        def field(name, label, kind, **options):
            return Field(name, label, kind, (lambda n=name: getattr(target, n)),
                         (lambda v, n=name: self.set_barricade(n, v)), **options)

        names = ("",) + tuple(k.name for k in self.level.barricade_kinds)
        fields = [Field("where", "Cell", "info", (lambda: f"{barricade.x}, {barricade.y} (ground floor)"), None)]
        group = next(g for g in self.level.barricade_groups() if self.barricade_selected in g)
        if len(group) > 1:
            first = self.level.barricades[group[0]]
            note = ("its boards, rebuild and reward count for all" if group[0] == self.barricade_selected
                    else f"the one at {first.x}, {first.y} sets boards, rebuild, reward")
            fields.append(Field("group", f"Acts as one with {len(group) - 1} touching", "info", (lambda: note), None))
        fields.append(Field("kind", "Type", "enum", (lambda: barricade.kind), self.set_barricade_kind, choices=names,
                            labels={"": "(its own settings)", **{n: n for n in names if n}}))
        if barricade.kind:
            fields += [Field("type_header", f"Type {barricade.kind}: changes all of them", "header", None, None),
                       Field("type_name", "Type name", "text", (lambda: barricade.kind), self.rename_barricade_kind)]
        low, high = BARRICADE_NUMBERS["repair_time"]
        fields += [field("boards", "Boards", "num", step=1, low=1, high=MAX_BARRICADE_BOARDS),
                   field("repair_time", "Rebuild a board (s)", "num", step=0.1, low=low, high=high),
                   field("reward_kind", "Rebuilding earns", "enum", choices=REWARD_KINDS, labels=REWARD_KIND_LABELS)]
        low, high = BARRICADE_NUMBERS["reward"]
        fields.append(field("reward", "Per board", "num", step=5.0, low=low, high=high))
        low, high = BARRICADE_NUMBERS["reward_cap"]
        fields.append(field("reward_cap", "Most per round", "num", step=10.0, low=low, high=high))
        last = len(self.tiles) - 1
        if not target.stages:
            fields.append(field("tile", "Boards look like", "tile", low=0, high=last))
        fields.append(Field("stages_header", "Damage stages", "header", None, None))
        for i in range(len(target.stages)):
            label = "Whole" if i == 0 else ("Last board" if i == len(target.stages) - 1 else f"Stage {i + 1}")
            fields.append(Field(f"stage{i}", label, "tile", (lambda i=i: target.stages[i]),
                                (lambda v, i=i: self.set_barricade_stage(i, v)), low=0, high=last))
        if len(target.stages) < MAX_BARRICADE_STAGES:
            fields.append(Field("add_stage", "Add stage", "button", None, None, action=self.add_barricade_stage,
                                text_override="+ Add a stage (more torn down)"))
        if target.stages:
            fields.append(Field("remove_stage", "Remove stage", "button", None, None,
                                action=self.remove_barricade_stage, text_override="Remove the last stage"))
        if barricade.kind:
            fields += [Field("detach", "Detach", "button", None, None, action=lambda: self.set_barricade_kind(""),
                             text_override="Detach (its own settings from now on)"),
                       Field("delete_type", "Delete type", "button", None, None, action=self.delete_barricade_kind,
                             text_override=f"Delete the type {barricade.kind}")]
        else:
            fields.append(Field("save_type", "Save as a type", "button", None, None, action=self.save_barricade_kind,
                                text_override="Save as a type (to place more of it)"))
        return fields

    def new_barricade_kind_name(self, base="Barricade", skip=None):
        taken = {k.name for k in self.level.barricade_kinds if k is not skip}
        return base if base not in taken else unique_thing_name(base, taken)

    def save_barricade_kind(self):
        """Save the selected barricade's settings as a new type, link it to it, and pick that type to place."""
        barricade = self.selected_barricade()
        if barricade is None or barricade.kind:
            return
        self.begin_edit()
        kind = BarricadeKind.from_barricade(self.new_barricade_kind_name(), barricade)
        self.level.barricade_kinds.append(kind)
        barricade.kind = self.place_barricade_kind = kind.name
        self.say(f"Saved as the type {kind.name}: it is picked to place (and can be imported into other maps)")

    def set_barricade_kind(self, name):
        """Link the selected barricade to a saved type (taking its settings), or detach it ("": it keeps them)."""
        barricade = self.selected_barricade()
        if barricade is None or barricade.kind == name:
            return
        self.begin_edit()
        barricade.kind = name
        self.level.apply_barricade_kinds()

    def rename_barricade_kind(self, name):
        barricade = self.selected_barricade()
        kind = self.barricade_target()
        if barricade is None or not barricade.kind or kind is None:
            return
        name = self.new_barricade_kind_name(str(name).strip()[:MAX_NAME] or "Barricade", skip=kind)
        if name == kind.name:
            return
        self.begin_edit()
        for b in self.level.barricades:
            if b.kind == kind.name:
                b.kind = name
        if self.place_barricade_kind == kind.name:
            self.place_barricade_kind = name
        kind.name = name

    def delete_barricade_kind(self):
        """Delete the selected barricade's type: the barricades of it keep its settings as their own."""
        kind = self.barricade_target()
        barricade = self.selected_barricade()
        if barricade is None or not barricade.kind or kind is None:
            return
        self.begin_edit()
        self.level.barricade_kinds.remove(kind)
        self.level.apply_barricade_kinds()              # (its barricades are detached)
        if self.place_barricade_kind == kind.name:
            self.place_barricade_kind = ""
        self.say(f"Deleted the type {kind.name}: its barricades keep its settings")

    def set_barricade(self, name, value):
        target = self.barricade_target()
        if name == "boards":
            value = int(round(value))
        if target is None or getattr(target, name) == value:
            return
        self.begin_edit()
        setattr(self.barricade_target(), name, value)
        self.level.apply_barricade_kinds()

    def set_barricade_stage(self, i, tile):
        target = self.barricade_target()
        if target is None or not 0 <= i < len(target.stages) or target.stages[i] == tile:
            return
        self.begin_edit()
        self.barricade_target().stages[i] = tile
        self.level.apply_barricade_kinds()

    def add_barricade_stage(self):
        """Add a stage after the others (starting from the last one's tile, or the plain tile) and make the next atlas
        click set it."""
        target = self.barricade_target()
        if target is None or len(target.stages) >= MAX_BARRICADE_STAGES:
            return
        self.begin_edit()
        target = self.barricade_target()
        target.stages.append(target.stages[-1] if target.stages else target.tile)
        self.level.apply_barricade_kinds()
        self.tile_target = f"stage{len(target.stages) - 1}"
        self.say(f"Stage {len(target.stages)}: click an atlas tile for it (transparent pixels show as gaps)")

    def remove_barricade_stage(self):
        target = self.barricade_target()
        if target is None or not target.stages:
            return
        self.begin_edit()
        self.barricade_target().stages.pop()
        self.level.apply_barricade_kinds()
        self.tile_target = "tile"

    def remove_spawners(self, cell):
        found = self.spawners_in(cell)
        if found:
            self.begin_edit()
            self.level.spawners = [s for s in self.level.spawners if s not in found]
            self.say(f"Removed a spawn point ({len(self.level.spawners)} left)")

    def place_start(self, cell):
        level = self.level
        if not level.in_bounds(*cell):
            return
        if not level.span_present(self.floor, *cell):
            self.say("The player can't start there: no open floor in this cell on this floor")
            return
        self.begin_edit()
        if cell == (int(level.start_x), int(level.start_y)) and level.start_span == self.floor:
            level.start_angle = (level.start_angle + math.pi / 2) % math.tau
        else:
            level.start_x, level.start_y, level.start_span = cell[0] + 0.5, cell[1] + 0.5, self.floor
        self.say(f"Start on {level.names[self.floor]} facing {math.degrees(level.start_angle):.0f} deg "
                 "(click the start cell again to rotate)")

    def pick(self, cell):
        if not self.level.in_bounds(*cell):
            return
        if self.layer == "sides":
            if self.level.walls[cell[1]][cell[0]]:
                side = self.side_at(self.mouse)
                self.selection = {self.side_tile(*cell, side) - 1}
                if self.level.get(f"side_{side}", *cell):           # ... and the band it covers
                    self.side_from = self.level.get(f"side_{side}_from", *cell)
                    self.side_to = self.level.get(f"side_{side}_to", *cell)
                self.tool = "paint"
                self.say(f"Picked tile #{min(self.selection) + 1}")
            return
        value = self.level.get(self.gname(), *cell)
        if self.edits_wall_ceiling(*cell):
            value = self.level.wall_ceiling(*cell)                      # the ceiling over the wall, as it is now
        if self.layer in STAMP_LAYERS:
            if value > 0:
                self.selection = {min(value, len(self.tiles)) - 1}
        elif self.layer in VALUE_LAYERS:
            low = VALUE_LIMITS[self.layer][0]
            if value >= low:                             # (a wall of height 0 is a full-height wall: no brush)
                self.value[self.gname()] = value
        elif value > 0 and self.layer == "site":         # a bomb site
            self.site_brush = value
        elif value > 0:                                  # a ramp direction
            self.ramp_dir = value
        self.tool = "paint"
        self.say(f"Picked {fmt(value)}")

    def stairs_heights(self):
        """[(cell, height)] along the current stairs drag: floor heights, or on the WallH layer the
        heights of the walls that make the steps (never 0, which would be a full-height wall)."""
        start, end = self.stairs_drag
        layer = "wall_h" if self.layer == "wall_h" else "floor_h"
        base = self.brush(self.gname(layer))
        low = VALUE_LIMITS["wall_h"][0] if layer == "wall_h" else -math.inf
        return [(cell, max(low, round(base + i * self.stair_step, 4)))
                for i, cell in enumerate(line_cells(start, end))]

    def finish_stairs(self):
        steps = [((x, y), height) for (x, y), height in self.stairs_heights() if self.level.in_bounds(x, y)]
        self.stairs_drag = None
        if not steps:
            return
        self.begin_edit()
        for (x, y), height in steps:
            if self.layer == "wall_h":
                self.put_wall_step(x, y, height)
            else:
                self.set_height(x, y, "floor_h", height)
        self.say(f"Stairs: {len(steps)} cells, {fmt(steps[0][1])} to {fmt(steps[-1][1])}")

    def put_wall_step(self, x, y, height):
        """One step of wall stairs: a short wall (a new one with the selected tile where there is
        none) `height` tall. A ground-floor step keeps the ceiling over it fixed at the room's ceiling
        there, so building next to the stairs later (a higher floor beside them, with a lower ceiling
        under it) does not bring the automatic ceiling down onto the steps."""
        level = self.level
        ceiling = level.grids["ceil_h"][y][x]              # the room this step goes (or went) in
        if not level.is_solid(x, y, self.floor):
            self.put_tile(x, y, self.primary_id(), "walls")
        level.set("wall_h", x, y, height)
        if not level.wall_floor(x, y) and not level.has_explicit_wall_ceiling(x, y):
            level.set("wall_ceil", x, y, max(ceiling, level.auto_wall_ceiling(x, y)))

    def shape_drag_cells(self):
        """The cells the shape being dragged covers now (Shift: a square box or a circle)."""
        start, end, _erasing = self.shape_drag
        if self.shape != "line" and self.mods() & pygame.KMOD_SHIFT:
            end = square_end(start, end)
        return [cell for cell in shape_cells(self.shape, start, end) if self.level.in_bounds(*cell)]

    def shape_tile(self, cell):
        """The tile a shape puts in `cell` on a tile layer: one per cell, the selected tiles repeating as a
        pattern from where the drag started (a single tile just fills the shape)."""
        stamp = self.stamp()
        width, height = max(t[0] for t in stamp) + 1, max(t[1] for t in stamp) + 1
        pattern = {(dx, dy): tile_id for dx, dy, tile_id in stamp}
        start = self.shape_drag[0]
        return pattern.get(((cell[0] - start[0]) % width, (cell[1] - start[1]) % height), stamp[0][2])

    def finish_shape(self):
        """Paint (or erase) every cell of the dragged shape, as the brush would, as one undo step."""
        cells, erasing = self.shape_drag_cells(), self.shape_drag[2]
        tiles = {cell: self.shape_tile(cell) for cell in cells} \
            if not erasing and self.layer in STAMP_LAYERS and self.stamp() else None
        self.shape_drag = None
        if not cells:
            return
        self.begin_edit()
        self.side_lock = self.shape_side
        for cell in cells:
            if erasing:
                self.erase_at(*cell)
            elif tiles is not None:
                self.put_tile(*cell, tiles[cell])
            else:
                self.paint_at(*cell)
        self.side_lock = None
        self.say(f"{'Erased' if erasing else 'Drew'} {SHAPES[self.shape].lower()}: {len(cells)} cells")

    def finish_atlas_drag(self):
        picked, ctrl = self.drag_indices(), bool(self.mods() & pygame.KMOD_CTRL)
        single = self.atlas_drag[0] == self.atlas_drag[1]
        if not ctrl:
            self.selection = picked
        elif single and picked <= self.selection:
            self.selection -= picked                    # Ctrl+click a selected tile removes it
        else:
            self.selection |= picked
        self.atlas_drag = None
        if self.prefabs_mode:                           # the Prefabs section: the prefab's icon
            if self.selected_prefab() is not None:
                self.set_entity("tile", min(picked))
                self.say(f"Prefab icon: tile {min(picked) + 1}")
            else:
                self.say("Select a prefab first (or add one), then click a tile")
            return
        if self.settings_mode:                          # the Map settings section: a buy menu entry's icon
            if self.selected_buy_item() is not None:
                self.set_buy_item("tile", min(picked))
                self.say(f"Buy menu icon: tile {min(picked) + 1}")
            else:
                self.say("Select an entry of the buy menu first (or add one), then click a tile for its icon")
            return
        if self.lights_mode:                            # the Lights section: the wall tile that glows with the light
            if self.selected_light() is not None:
                self.set_light("wall_tile", min(picked))
                self.say(f"Walls made from tile {min(picked) + 1} now glow with this light")
            else:
                self.say("Select a light first (or add one), then click a wall tile to make it glow")
            return
        if self.effects_mode:                           # the Effects section: what each particle looks like
            if self.selected_effect() is not None:
                self.set_effect("tile", min(picked))
                self.say(f"Particle picture: tile {min(picked) + 1}")
            else:
                self.say("Select an effect first (or add one), then click a tile")
            return
        if self.guns_mode:                              # the Guns section: the picture of the gun or its bullet
            if self.selected_gun() is not None:
                self.set_gun("tile", min(picked))
                self.say(f"Gun sprite: tile {min(picked) + 1}")
            elif self.selected_ammo() is not None:
                self.set_ammo("tile", min(picked))
                self.say(f"Bullet sprite: tile {min(picked) + 1}")
            else:
                self.say("Select a gun or an ammo type first (or add one), then click a tile")
            return
        barricade = self.barricade_target()
        if barricade is not None:                       # what the selected barricade (or one of its stages) looks like
            target = self.tile_target
            if target.startswith("stage") and target[5:].isdigit() and int(target[5:]) < len(barricade.stages):
                self.set_barricade_stage(int(target[5:]), min(picked))
                self.say(f"Barricade stage {int(target[5:]) + 1}: tile {min(picked) + 1}")
            elif barricade.stages:
                self.say("Click a stage's picture in the Details pane first, then a tile")
            else:
                self.set_barricade("tile", min(picked))
                self.say(f"Barricade boards: tile {min(picked) + 1}")
            return
        if self.tool == "entity":                       # the tile chosen here is the item's sprite
            chosen = self.selected_entity()
            if chosen is not None and chosen.prefab:
                self.say(f"This item follows {chosen.prefab}: change its icon in the Prefabs section")
                return
            if chosen is not None:
                self.set_entity("tile", min(picked))
            else:
                self.entity_brush.tile = min(picked)
            self.say(f"Item sprite: tile {min(picked) + 1}")
            return
        if self.tool in ("erase", "pick", "start", "stairs"):
            self.tool = "paint"
        if self.layer not in TILE_LAYERS:
            self.layer = "walls"                        # choosing a tile means you want to paint tiles
            self.say("Switched to the Walls layer (tile selection applies to the texture layers)")

    # ---------------------------------------------------------------- actions

    def select_floor(self, floor):
        self.floor = max(0, min(floor, self.level.floor_count - 1))
        self.stairs_drag = self.shape_drag = self.move_drag = None
        e = self.selected_entity()
        if e is not None and e.span != self.floor:
            self.deselect()                             # the item is on another floor

    def add_floor(self):
        self.begin_edit()
        self.floor = self.level.add_floor()
        self.say(f"Added '{self.level.names[self.floor]}' on top. Press F2 to rename it")

    def delete_floor(self):
        name = self.level.names[self.floor]
        if self.floor == 0:
            self.say("The ground floor can't be deleted")
        elif self.confirm != "delfloor":
            self.confirm = "delfloor"
            self.say(f"Click Del again to delete '{name}' and everything on it", 6)
        else:
            self.confirm = None
            self.begin_edit()
            self.level.remove_floor(self.floor)
            self.value = {k: v for k, v in self.value.items() if split_grid_name(k)[1] < self.floor}
            self.floor -= 1
            self.say(f"Deleted '{name}'")

    def start_rename(self):
        self.rename = self.level.names[self.floor]
        self.say("Type the new name, Enter to confirm, Esc to cancel", 60)

    def finish_rename(self, commit=True):
        text = (self.rename or "").strip()
        self.rename = None
        if commit and text and text != self.level.names[self.floor]:
            self.begin_edit()
            self.say(f"Renamed to '{self.level.rename_floor(self.floor, text)}'")
        else:
            self.say("Name unchanged")

    def clamp_floor(self):
        """Keep the edited floor valid after the level changed (undo, reload, new map)."""
        self.floor = max(0, min(self.floor, self.level.floor_count - 1))
        self.rename = self.value_edit = self.move_drag = None
        self.field_edit = self.menu_open = None
        if self.selected_entity() is None:
            self.selected = None
        if self.gun_selected is not None and not 0 <= self.gun_selected < len(self.level.guns):
            self.gun_selected = None
        if self.ammo_selected is not None and not 0 <= self.ammo_selected < len(self.level.ammo_types):
            self.ammo_selected = None
        if self.prefab_selected is not None and not 0 <= self.prefab_selected < len(self.level.prefabs):
            self.prefab_selected = None
        if self.effect_selected is not None and not 0 <= self.effect_selected < len(self.level.effects):
            self.effect_selected = None
        if self.light_selected not in (None, AMBIENT_ROW) and not 0 <= self.light_selected < len(self.level.lights):
            self.light_selected = None
        if self.place_prefab and self.level.prefab_named(self.place_prefab) is None:
            self.place_prefab = ""
        self.dropdown_open = False

    def do(self, action):
        if action != self.confirm:
            self.confirm = None
        if action != "dropdown":
            self.dropdown_open = False
        if action in ("lights", "effects", "guns", "prefabs"):
            self.settings_mode = False
        if action == "mapsettings":
            self.settings_mode = not self.settings_mode
            self.guns_mode = self.prefabs_mode = self.effects_mode = self.lights_mode = False
            self.deselect()
            self.settings_scroll = 0
            if self.settings_mode:
                self.settings_selected = RULES_ROW
            self.say("Map settings: the game mode and rules, and the buy menu" if self.settings_mode else "Back to the map")
        elif action == "lights":
            self.lights_mode, self.effects_mode, self.guns_mode, self.prefabs_mode = not self.lights_mode, False, False, False
            self.deselect()
            self.say("Lights: add one, set its color and reach, then give it to a gun, item, ammo or effect"
                     if self.lights_mode else "Back to the map")
        elif action == "effects":
            self.effects_mode, self.guns_mode, self.prefabs_mode = not self.effects_mode, False, False
            self.lights_mode = False
            self.deselect()
            self.say("Effects: add one, shape it in the Details pane, then give it to a gun, ammo or item"
                     if self.effects_mode else "Back to the map")
        elif action == "guns":
            self.guns_mode, self.prefabs_mode, self.effects_mode = not self.guns_mode, False, False
            self.lights_mode = False
            self.deselect()
            self.say("Guns: add a gun, then edit it in the Details pane" if self.guns_mode else "Back to the map")
        elif action == "prefabs":
            self.prefabs_mode, self.guns_mode, self.effects_mode = not self.prefabs_mode, False, False
            self.lights_mode = False
            self.deselect()
            self.say("Prefabs: add one, set its icon and settings, then place it with the Entity tool"
                     if self.prefabs_mode else "Back to the map")
        elif action.startswith("shape:"):
            self.shape = action[6:]
            self.say(f"Shape: {SHAPES[self.shape]} (drag on the map; right-drag erases, Shift: square / circle)")
        elif action in ("copy", "cut", "clear", "paste", "select_all"):
            self.area_action(action)
        elif action.startswith("tool:"):
            self.tool = action[5:]
            self.shape_drag = self.area_drag = None
            self.pasting = False
            self.guns_mode = self.prefabs_mode = self.effects_mode = self.lights_mode = self.settings_mode = False
            if self.tool != "entity":
                self.deselect()
            if self.tool == "camera" and not self.show_preview:
                self.set_preview(True)
        elif action.startswith("layer:"):
            self.layer = action[6:]
        elif action.startswith("floor:"):
            self.select_floor(int(action[6:]))
        elif action == "dropdown":
            self.dropdown_open = not self.dropdown_open
        elif action == "legend":
            self.show_legend = not self.show_legend
        elif action == "textures":
            self.reload_textures()
        elif action == "preview":
            self.set_preview(not self.show_preview)
        elif action == "camstart":
            if not self.show_preview:
                self.set_preview(True)
            self.preview.request_reset()
            self.preview.sync(self.level, self.revision, force=True)
        elif action == "addfloor":
            self.add_floor()
        elif action == "delfloor":
            self.delete_floor()
        elif action == "rename":
            self.start_rename()
        elif action in ("order-", "order+"):
            self.spawn_order = max(0, min(MAX_SPAWN_ORDER, self.spawn_order + (1 if action == "order+" else -1)))
            self.say(f"New spawn points get order {self.spawn_order} (click one to give it this order)")
        elif action in ("val-", "val+") and self.tool == "spawn":
            self.do("order-" if action == "val-" else "order+")        # [ and ] step the order too
        elif action in ("val-", "val+"):
            self.adjust_value(-VALUE_STEP if action == "val-" else VALUE_STEP)
        elif action == "val_type" and self.layer in VALUE_LAYERS:
            self.value_edit = ""
            self.say("Type the brush value, Enter to use it, Esc to cancel", 60)
        elif action == "dir" and self.layer == "site":
            self.site_brush = self.site_brush % len(SITE_NAMES) + 1
            self.say(f"Painting {SITE_BRUSHES[self.site_brush]}")
        elif action == "dir":
            self.ramp_dir = self.ramp_dir % 4 + 1
        elif action == "spawn_team":
            self.spawn_team = SPAWNER_TEAMS[(SPAWNER_TEAMS.index(self.spawn_team) + 1) % len(SPAWNER_TEAMS)]
            self.say(f"New spawn points are for {self.spawn_team_label(self.spawn_team)} (click one to give it this team)")
        elif action == "side_full":
            self.side_from = self.side_to = 0.0
            self.say("Wall side band: the whole height of the side")
        elif action.startswith("side_"):
            self.step_side_band(action[5:-1], 1 if action.endswith("+") else -1)
        elif action in ("step-", "step+"):
            delta = -VALUE_STEP if action == "step-" else VALUE_STEP
            self.stair_step = max(-1.0, min(1.0, round(self.stair_step + delta, 4)))
        elif action == "undo":
            self.apply_undo(self.undo, self.redo, "undo")
        elif action == "redo":
            self.apply_undo(self.redo, self.undo, "redo")
        elif action == "border":
            self.begin_edit()
            self.level.fill_border(self.primary_id())
        elif action.startswith("edge:"):
            self.resize_side(action[5], 1 if action[6] == "+" else -1)
        elif action in ("new", "open", "reload"):
            if self.dirty and self.confirm != action:
                self.confirm = action
                self.say(f"Unsaved changes: click {action.capitalize()} again to discard them", 6)
                return
            self.confirm = None
            {"new": self.start_new_map, "open": self.start_open, "reload": self.reload}[action]()
        elif action == "import":
            self.start_import()
        elif action == "save":
            self.save()
        elif action == "play":
            self.play()

    # ---------------------------------------------------------------- the 3D view

    def set_preview(self, show):
        """Show or hide the 3D view. The map is re-fitted to the room that is left for it."""
        self.show_preview = show
        self.look_drag = self.camera_drag = False
        if show:
            self.ensure_preview().sync(self.level, self.revision)       # ready on the very next draw
        self.fit_view()

    def ensure_preview(self):
        if self.preview is None:
            self.preview = Preview(atlas_array(self.tiles))
        return self.preview

    def update(self, dt, pressed=None):
        """Per-frame work: keep the 3D world in step with the level, and walk the camera with the
        keys held while the mouse is over the 3D view (or is dragging in it)."""
        self.watch_textures()
        self.step_fx_preview(dt)
        self.step_gun_preview(dt)
        self.light_clock += dt
        if not self.show_preview:
            return
        preview = self.ensure_preview()
        try:
            preview.sync(self.level, self.revision)
        except Exception as error:              # a half-finished edit must never take the editor down
            self.say(f"3D view could not be rebuilt: {error}")
        if not preview.ready:
            return
        pressed = pygame.key.get_pressed() if pressed is None else pressed
        active = self.over_preview() or self.look_drag
        down = (lambda key: int(bool(pressed[key]))) if active else (lambda key: 0)
        forward = (down(pygame.K_w) or down(pygame.K_UP)) - (down(pygame.K_s) or down(pygame.K_DOWN))
        strafe = down(pygame.K_d) - down(pygame.K_a)
        turn = (down(pygame.K_RIGHT) - down(pygame.K_LEFT)) * 2.0 * dt
        sprint = bool(down(pygame.K_LSHIFT) or down(pygame.K_RSHIFT))
        preview.update(dt, forward, strafe, turn, sprint)

    def resize_side(self, side, delta):
        """Add (+1) or remove (-1) a column / row along one side of the map: L R T B. Everything
        else stays where it is, on screen too, and the 3D camera keeps its place on the map."""
        level = self.level
        grows = {"L": (delta, 0, 0, 0), "R": (0, delta, 0, 0), "T": (0, 0, delta, 0), "B": (0, 0, 0, delta)}[side]
        if delta > 0 and (level.width if side in "LR" else level.height) >= MAX_SIZE:
            self.say(f"The map can't be more than {MAX_SIZE} cells wide or tall")
            return
        if delta < 0 and (level.width if side in "LR" else level.height) <= 3:
            self.say("The map can't be smaller than 3 cells each way")
            return
        self.begin_edit()
        dx, dy = level.resize_edges(*grows)
        self.pan[0] -= dx * self.zoom
        self.pan[1] -= dy * self.zoom
        if self.preview is not None and self.preview.player is not None:
            self.preview.player.x += dx
            self.preview.player.y += dy

    def nudge_cell(self, cell, delta):
        """Ctrl + wheel: change what the selected layer holds in this cell by `delta`, where that is
        a number (floor / ceiling heights, wall heights, the ceiling over a wall)."""
        x, y = cell
        level, layer, floor = self.level, self.layer, self.floor
        if not level.in_bounds(x, y) or layer not in VALUE_LAYERS:
            return
        low, high = VALUE_LIMITS[layer]

        def clamp(v):
            return max(low, min(high, round(v, 4)))

        if layer == "wall_h":
            if not level.is_solid(x, y, floor):
                return
            value = level.grids["wall_h"][y][x]
            if value <= 0:                                  # full height: step down from the real height
                if floor == 0 or level.wall_floor(x, y) == 0:
                    ceiling, base = level.wall_ceiling(x, y), level.wall_base(x, y)
                else:
                    ceiling, base = level.upper_wall_full_top(x, y), level.get(self.gname("floor_h"), x, y)
                if delta > 0:
                    return
                value = ceiling - base
            self.begin_edit()
            new = clamp(value + delta)
            full = (level.wall_ceiling(x, y) - level.wall_base(x, y) if level.wall_floor(x, y) == 0
                    else level.upper_wall_full_top(x, y) - level.get(grid_name("floor_h", level.wall_floor(x, y)), x, y))
            level.set("wall_h", x, y, 0.0 if new >= full - MIN_WALL_GAP else new)
        elif self.edits_wall_ceiling(x, y):
            self.begin_edit()
            level.set("wall_ceil", x, y, clamp(level.wall_ceiling(x, y) + delta))
        elif self.edits_upper_wall(x, y):
            name = self.gname()
            value = level.get(name, x, y)
            if layer == "ceil_h" and value <= level.get(self.gname("floor_h"), x, y):
                value = level.get(self.gname("floor_h"), x, y)      # no top yet: start at the base
            self.begin_edit()
            level.set(name, x, y, clamp(value + delta))
        elif level.span_present(floor, x, y):
            self.begin_edit()
            self.set_height(x, y, layer, clamp(level.get(self.gname(), x, y) + delta))
        else:
            return
        self.touch()

    def finish_value_edit(self, commit):
        """Use (or drop) the brush value typed into the toolbar, clamped to the layer's limits."""
        typed, self.value_edit = self.value_edit, None
        if not commit or not typed or self.layer not in VALUE_LAYERS:
            return
        try:
            value = float(typed.replace(",", "."))
        except ValueError:
            self.say(f"'{typed}' is not a number: value unchanged")
            return
        low, high = VALUE_LIMITS[self.layer]
        self.value[self.gname()] = max(low, min(high, round(value, 2)))
        self.say(f"Brush value {fmt(self.value[self.gname()])}")

    def adjust_value(self, delta):
        if self.layer in VALUE_LAYERS:
            low, high = VALUE_LIMITS[self.layer]
            name = self.gname()
            self.value[name] = max(low, min(high, round(self.brush(name) + delta, 4)))

    def start_new_map(self):
        """Open the New map dialog, offering a name no map in the folder has yet."""
        name, number = "new_map", 1
        while os.path.exists(self.map_file(name)):
            number += 1
            name = f"new_map_{number}"
        self.new_name, self.new_error = name, ""

    def map_file(self, name):
        """Where the map called `name` is saved: <name>.json next to the map being edited."""
        return os.path.join(self.map_folder(), name + ".json")

    def finish_new_map(self, commit=True):
        """Make the blank map under the typed name and save it, so the editor works on that file from now
        on. A name that is empty or already a file keeps the dialog open with the reason."""
        if not commit:
            self.new_name, self.new_error = None, ""
            self.say("No new map made")
            return
        name = (self.new_name or "").strip()
        path = self.map_file(name)
        if not name:
            self.new_error = "Type a name for the map"
            return
        if os.path.exists(path):
            self.new_error = f"{name}.json already exists: pick another name"
            return
        level = self.blank_map()
        try:
            save_level(path, level)
        except OSError as e:
            self.new_error = f"Can't save {name}.json: {e.strerror or e}"
            return
        self.new_name, self.new_error = None, ""
        self.switch_to(path)
        self.start_over(level)
        self.say(f"New blank map (16x16), saved as {name}.json")

    @staticmethod
    def blank_map():
        level = Level.blank(16, 16)
        level.start_x = level.start_y = 1.5
        return level

    def start_over(self, level):
        """Edit `level` from here on (a new, opened or reloaded map), with no undo history."""
        self.undo.clear()
        self.redo.clear()
        self.level = level
        self.clamp_floor()
        self.dirty = False
        self.revision += 1
        self.fit_view()

    def switch_to(self, path):
        """Work on the map file at `path` from now on (and remember it, if remembering)."""
        self.path = path
        if self.settings:
            remember_map(path, self.settings)

    def map_folder(self):
        return os.path.dirname(os.path.abspath(self.path))

    def start_import(self):
        """Open the Import dialog on the maps in this map's folder (not this one)."""
        names = [n for n in map_files(self.map_folder()) if n != os.path.basename(self.path)]
        if not names:
            self.say("There are no other maps in this folder to import from")
            return
        self.importing = ImportDialog(self.map_folder(), names, self.level, self.font, self.small, self.tiles)

    def after_import(self, outcome):
        """What the Import dialog asked for: None (carry on), "close", or ("import", source level, picks, taken)."""
        if outcome == "close":
            self.importing = None
            self.say("Nothing imported")
        elif isinstance(outcome, tuple):
            _, source, picks, taken = outcome
            self.importing = None
            self.begin_edit()                                   # (one undo step takes it all back)
            self.say(import_things(self.level, source, picks, taken).summary(), 8)

    def start_open(self):
        """Open the Open dialog: the maps in the folder of the map being edited, that one picked."""
        try:
            names = sorted((n for n in os.listdir(self.map_folder()) if n.lower().endswith(".json")), key=str.lower)
        except OSError as e:
            self.say(f"Can't list the maps: {e.strerror or e}")
            return
        if not names:
            self.say("No maps in this folder yet")
            return
        current = os.path.basename(self.path)
        self.open_maps, self.open_error = names, ""
        self.open_pick = names.index(current) if current in names else 0
        self.open_scroll = 0
        self.open_click = (None, 0.0)
        self.pick_map(self.open_pick)

    def pick_map(self, index):
        """Pick the map at `index` in the Open dialog, scrolling the list to show it."""
        self.open_pick = max(0, min(len(self.open_maps) - 1, index))
        self.open_error = ""
        if self.open_pick < self.open_scroll:
            self.open_scroll = self.open_pick
        elif self.open_pick >= self.open_scroll + OPEN_ROWS:
            self.open_scroll = self.open_pick - OPEN_ROWS + 1

    def finish_open(self, commit=True):
        """Edit the picked map from now on. One that can't be read keeps the dialog open with the reason."""
        if not commit:
            self.open_maps, self.open_error = None, ""
            self.say("Kept the map that was open")
            return
        name = self.open_maps[self.open_pick]
        path = os.path.join(self.map_folder(), name)
        try:
            level = load_level(path)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            self.open_error = f"Can't open {name}: {e}"[:90]
            return
        self.open_maps, self.open_error = None, ""
        self.switch_to(path)
        self.start_over(level)
        self.say(f"Opened {name}")

    def reload(self):
        if not os.path.exists(self.path):
            self.say("Nothing saved yet to reload")
            return
        self.start_over(load_level(self.path))
        self.say(f"Reloaded {os.path.basename(self.path)}")

    def save(self):
        save_level(self.path, self.level)
        self.dirty = False
        problems = self.problems()
        self.say(f"Saved {os.path.basename(self.path)}" + (f"  (warning: {problems[0]})" if problems else ""))

    def play(self):
        if self.dirty or not os.path.exists(self.path):
            self.save()
        command, folder = self.game_command()
        subprocess.Popen(command + ["--map", self.path], cwd=folder)
        self.say("Launched the game with this map")

    @staticmethod
    def game_command():
        """(the command that starts the game, the folder to start it in): main.py with this Python, or when running
        from the built programs, RaycastGame (RaycastGame.exe on Windows) in the same folder as this one."""
        if getattr(sys, "frozen", False):
            folder = os.path.dirname(sys.executable)
            return [os.path.join(folder, "RaycastGame" + (".exe" if os.name == "nt" else ""))], folder
        game = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
        return [sys.executable, game], os.path.dirname(game)

    def issues(self):
        """The level's (message, cell) problems, recomputed only after an edit."""
        if self._problems_cache[0] != self.revision:
            self._problems_cache = (self.revision, self.level.issues())
        return self._problems_cache[1]

    def problems(self):
        return [message for message, _cell in self.issues()]

    def problem_cells(self):
        return {cell for _message, cell in self.issues() if cell is not None}

    def request_quit(self):
        if self.dirty and not self.quit_armed:
            self.quit_armed = True
            self.say("Unsaved changes: close the window again to discard them, or Ctrl+S to save", 6)
        else:
            self.running = False

    # ---------------------------------------------------------------- events

    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.request_quit()
        elif e.type in RESIZE_EVENTS:
            if time.time() < self.refit_until:
                self.fit_view()
        elif e.type == pygame.KEYDOWN:
            self.on_key(e)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            self.on_mouse_down(e)
        elif e.type == pygame.MOUSEBUTTONUP:
            self.on_mouse_up(e)
        elif e.type == pygame.MOUSEMOTION:
            self.on_mouse_move(e)
        elif e.type == pygame.MOUSEWHEEL:
            self.on_wheel(e)

    def on_key(self, e):
        if self.importing is not None:                  # the Import dialog takes every key
            self.after_import(self.importing.key(e))
            return
        if self.open_maps is not None:                  # the Open dialog takes every key
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.finish_open(True)
            elif e.key == pygame.K_ESCAPE:
                self.finish_open(False)
            elif e.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                step = {pygame.K_UP: -1, pygame.K_DOWN: 1, pygame.K_PAGEUP: -OPEN_ROWS, pygame.K_PAGEDOWN: OPEN_ROWS}
                self.pick_map(self.open_pick + step[e.key])
            elif e.key in (pygame.K_HOME, pygame.K_END):
                self.pick_map(0 if e.key == pygame.K_HOME else len(self.open_maps) - 1)
            return
        if self.new_name is not None:                   # the New map dialog takes every key
            char = getattr(e, "unicode", "")
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.finish_new_map(True)
            elif e.key == pygame.K_ESCAPE:
                self.finish_new_map(False)
            elif e.key == pygame.K_BACKSPACE:
                self.new_name, self.new_error = self.new_name[:-1], ""
            elif char and char in MAP_NAME_CHARS and len(self.new_name) < MAX_MAP_NAME:
                self.new_name, self.new_error = self.new_name + char, ""
            return
        if self.rename is not None:                     # typing a floor name takes every key
            char = getattr(e, "unicode", "")
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.finish_rename(True)
            elif e.key == pygame.K_ESCAPE:
                self.finish_rename(False)
            elif e.key == pygame.K_BACKSPACE:
                self.rename = self.rename[:-1]
            elif char and char.isprintable() and len(self.rename) < MAX_NAME_LENGTH:
                self.rename += char
            return
        if self.value_edit is not None:                 # typing the brush value into the toolbar
            char = getattr(e, "unicode", "")
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.finish_value_edit(True)
            elif e.key == pygame.K_ESCAPE:
                self.finish_value_edit(False)
            elif e.key == pygame.K_BACKSPACE:
                self.value_edit = self.value_edit[:-1]
            elif char and char in "0123456789.,-" and len(self.value_edit) < 8:
                _whole, dot, decimals = self.value_edit.replace(",", ".").partition(".")
                if not (dot and (char in ".," or len(decimals) >= 2)):    # one point, 2 decimal places
                    self.value_edit += char
            return
        if self.field_edit is not None:                 # typing a number into the Details pane
            char = getattr(e, "unicode", "")
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.finish_field_edit(True)
            elif e.key == pygame.K_ESCAPE:
                self.finish_field_edit(False)
            elif e.key == pygame.K_BACKSPACE:
                self.field_edit[1] = self.field_edit[1][:-1]
            elif char and self.editing_text() and char.isprintable() and len(self.field_edit[1]) < MAX_NAME:
                self.field_edit[1] += char
            elif char and not self.editing_text() and char in "0123456789.,-" and len(self.field_edit[1]) < 8:
                self.field_edit[1] += char
            return
        ctrl = bool(e.mod & pygame.KMOD_CTRL)
        if e.key == pygame.K_ESCAPE:
            if self.move_drag:
                self.move_drag = None
                self.say("Move cancelled")
            elif self.shape_drag:
                self.shape_drag = None
                self.say("Shape cancelled")
            elif self.pasting:
                self.pasting = False
                self.say("Stopped pasting (Ctrl+V pastes again)")
            elif self.area is not None and self.tool == "select":
                self.area = None
            elif self.dropdown_open:
                self.dropdown_open = False
            elif self.menu_open is not None:
                self.menu_open = None
            elif self.details_width():
                self.deselect()                         # (Esc no longer quits: close the window for that)
        elif e.key == pygame.K_DELETE and self.details_width():
            self.delete_selected()
        elif e.key == pygame.K_DELETE and self.tool == "select" and self.area is not None:
            self.do("clear")
        elif ctrl and e.key in (pygame.K_c, pygame.K_x, pygame.K_v, pygame.K_a):
            self.do({pygame.K_c: "copy", pygame.K_x: "cut", pygame.K_v: "paste", pygame.K_a: "select_all"}[e.key])
        elif ctrl and e.key == pygame.K_s:
            self.do("save")
        elif ctrl and e.key == pygame.K_o:
            self.do("open")
        elif ctrl and e.key == pygame.K_z:
            self.do("redo" if e.mod & pygame.KMOD_SHIFT else "undo")
        elif ctrl and e.key == pygame.K_y:
            self.do("redo")
        elif e.key == pygame.K_F6:
            self.do("textures")
        elif e.key == pygame.K_F5:
            self.do("play")
        elif e.key == pygame.K_HOME:
            self.fit_view()
        elif ctrl:
            return
        elif e.key in PREVIEW_KEYS and self.over_preview():     # walking the camera, not a hotkey
            if e.key == pygame.K_SPACE and self.preview is not None:
                self.preview.jump_pending = True
        elif e.key == pygame.K_TAB:                     # step through the floors (Shift: backwards)
            step = -1 if e.mod & pygame.KMOD_SHIFT else 1
            self.do(f"floor:{(self.floor + step) % self.level.floor_count}")
        elif e.key == pygame.K_F2:
            self.do("rename")
        elif e.key == pygame.K_k:
            self.do("legend")
        elif e.key == pygame.K_g:
            self.do("guns")
        elif e.key == pygame.K_p:
            self.do("prefabs")
        elif e.key == pygame.K_x:
            self.do("effects")
        elif e.key == pygame.K_l:
            self.do("lights")
        elif e.key == pygame.K_j:
            self.do("mapsettings")
        elif e.key == pygame.K_v:
            self.do("preview")
        elif e.key in LAYER_KEYS:
            self.do("layer:" + LAYER_KEYS[e.key])
        elif e.key in TOOL_KEYS:
            self.do("tool:" + TOOL_KEYS[e.key])
        elif e.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET) and self.selected_entity() is not None:
            item = self.selected_entity()                   # raise / lower the selected item
            step = ELEVATION_STEP * (5 if e.mod & pygame.KMOD_SHIFT else 1)
            self.set_elevation(item, item.elevation + (step if e.key == pygame.K_RIGHTBRACKET else -step))
        elif e.key == pygame.K_LEFTBRACKET:
            self.do("val-")
        elif e.key == pygame.K_RIGHTBRACKET:
            self.do("val+")
        elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.layer in VALUE_LAYERS:
            self.do("val_type")
        elif e.key == pygame.K_r:
            self.do("dir")

    def on_mouse_down(self, e):
        self.mouse = e.pos
        if self.importing is not None:                  # the Import dialog takes every click
            if e.button == 1:
                self.after_import(self.importing.click(e.pos, self._size()))
            return
        if self.open_maps is not None:                  # the Open dialog takes every click
            if e.button == 1 and not self.scrollbar_press(e.pos, ("open",)):
                self.open_dialog_click(e.pos)
            return
        if self.new_name is not None:                   # the New map dialog takes every click
            _box, _field, create, cancel = self.new_map_rects()
            if e.button == 1 and create.collidepoint(e.pos):
                self.finish_new_map(True)
            elif e.button == 1 and cancel.collidepoint(e.pos):
                self.finish_new_map(False)
            return
        if self.rename is not None:                     # clicking away keeps the typed name
            self.finish_rename(True)
            return
        if self.value_edit is not None:                 # ... and the typed brush value
            self.finish_value_edit(True)
            return
        if self.field_edit is not None:                 # ... and the typed number
            self.finish_field_edit(True)
        if self.menu_open is not None:                  # an open drop-down list takes the next click
            if e.button == 1:
                self.menu_click(e.pos)
            else:
                self.menu_open = None
            return
        if e.button == 1 and self.scrollbar_press(e.pos, ("details", self.section_name())):
            return
        pane = self.details_rect()
        if pane is not None and pane.collidepoint(e.pos) and e.pos[1] >= TOOLBAR_H:
            if e.button == 1:
                self.details_click(e.pos)
            return
        if self.dropdown_open:                          # the open list swallows the next click
            self.dropdown_open = False
            if e.button == 1:
                for rect, _label, action in self.dropdown_items():
                    if rect.collidepoint(e.pos):
                        self.do(action)
                        break
            return
        if self.show_legend and self.legend_rect().collidepoint(e.pos):
            return                                      # a floating key sits on the map: don't paint through it
        area, atlas = self.map_area(), self.atlas_rect()
        if self.over_preview() and e.pos[1] >= TOOLBAR_H:
            if e.button == 1 and self.preview_rect().collidepoint(e.pos):
                self.look_drag = True
            return
        if e.button == 1 and e.pos[1] < TOOLBAR_H:
            for rect, _label, action in self.layout():
                if rect.collidepoint(e.pos):
                    self.do(action)
                    return
        elif atlas.collidepoint(e.pos) and (e.button == 2 or (e.button == 1 and pygame.key.get_pressed()[pygame.K_SPACE])):
            self.atlas_pan = True                       # move the zoomed atlas around
        elif e.button == 1 and atlas.collidepoint(e.pos):
            index = self.tile_index_at(e.pos)
            cell = (index % self.atlas_cols, index // self.atlas_cols)
            self.atlas_drag = (cell, cell)
        elif area.collidepoint(e.pos):
            if e.button == 2 or (e.button == 1 and pygame.key.get_pressed()[pygame.K_SPACE]):
                self.pan_drag = True
            elif self.guns_mode:
                if e.button == 1:
                    self.guns_click(e.pos)
            elif self.prefabs_mode:
                if e.button == 1:
                    self.prefabs_click(e.pos)
            elif self.effects_mode:
                if e.button == 1:
                    self.effects_click(e.pos)
            elif self.lights_mode:
                if e.button == 1:
                    self.lights_click(e.pos)
            elif self.settings_mode:
                if e.button in (1, 3) and self.curve_press(e.pos, e.button):
                    pass
                elif e.button == 1:
                    self.settings_click(e.pos)
            elif e.button in (1, 3) and not self.over_ruler(e.pos):
                self.confirm = None
                self.map_click(self.cell_at(e.pos), e.button)

    def on_mouse_up(self, e):
        self.mouse = e.pos
        if e.button == 1:
            self.scroll_drag = None
            if self.importing is not None:
                self.importing.grab = None
        if e.button == 1 and self.atlas_drag:
            self.finish_atlas_drag()
        if e.button == 1 and self.stairs_drag:
            self.finish_stairs()
        if e.button == 1 and self.move_drag:
            self.finish_move()
        if self.shape_drag and e.button == (3 if self.shape_drag[2] else 1):
            self.finish_shape()
        if self.area_drag and e.button == 1:
            self.area = area_rect(self.level, *self.area_drag)
            self.area_drag = None
            x0, y0, x1, y1 = self.area
            self.say(f"Selected {x1 - x0 + 1}x{y1 - y0 + 1}: Ctrl+C copies, Ctrl+X cuts, Delete clears")
        if e.button in (1, 3):
            self.stroke = self.last_cell = None
        if e.button == 1:
            self.look_drag = self.camera_drag = False
            if self.gizmo_drag:
                self.gizmo_release()
            self.curve_drag = None
        if e.button in (1, 2):
            self.pan_drag = self.atlas_pan = False

    def on_mouse_move(self, e):
        self.mouse = e.pos
        if self.importing is not None and self.importing.grab is not None:
            self.importing.drag(e.pos[1], self._size())
        elif self.scroll_drag is not None:
            self.scroll_drag_to(e.pos[1])
        elif self.gizmo_drag:
            self.gizmo_move(e.pos)
        elif self.curve_drag is not None:
            self.curve_move(e.pos)
        elif self.look_drag and self.preview is not None:
            self.preview.look(e.rel[0] * MOUSE_SENSITIVITY, -e.rel[1] * MOUSE_SENSITIVITY)
        elif self.camera_drag and self.preview is not None:
            self.preview.aim(*self.map_point(e.pos))
        elif self.atlas_pan:
            self.atlas_scroll = [self.atlas_scroll[0] - e.rel[0], self.atlas_scroll[1] - e.rel[1]]
            self.clamp_atlas_scroll()
        elif self.atlas_drag:                   # (clamped: dragging outside keeps the nearest tile)
            self.atlas_drag = (self.atlas_drag[0], self.atlas_cell_at(e.pos))
        elif self.stairs_drag:
            self.stairs_drag = (self.stairs_drag[0], self.cell_at(e.pos))
        elif self.move_drag:
            self.move_drag = self.move_drag[:3] + (self.cell_at(e.pos),)
        elif self.shape_drag:
            self.shape_drag = (self.shape_drag[0], self.cell_at(e.pos), self.shape_drag[2])
        elif self.area_drag:
            self.area_drag = (self.area_drag[0], self.cell_at(e.pos))
        elif self.pan_drag:
            self.pan[0] += e.rel[0]
            self.pan[1] += e.rel[1]
        elif self.stroke:
            cell = self.cell_at(e.pos)
            for step in line_cells(self.last_cell, cell)[1:]:
                self.stroke_cell(step)
            self.last_cell = cell
            self.revision += 1

    def on_wheel(self, e):
        if self.importing is not None:                  # the wheel scrolls the Import dialog's list
            self.importing.wheel(e.y)
            return
        if self.open_maps is not None:                  # the wheel scrolls the Open dialog's list
            most = max(0, len(self.open_maps) - OPEN_ROWS)
            self.open_scroll = max(0, min(most, self.open_scroll - e.y))
            return
        if self.menu_open is not None:                  # (an open drop-down list stays where its row is)
            return
        if self.new_name is not None:
            return
        if self.atlas_rect().collidepoint(self.mouse):  # the wheel zooms the atlas
            self.zoom_atlas(self.mouse, e.y)
            return
        pane = self.details_rect()
        if pane is not None and pane.collidepoint(self.mouse):      # the wheel steps the value under it
            if not self.details_wheel(self.mouse, e.y):             # ... or scrolls the pane
                self.set_scroll("details", self.details_scroll - e.y * 48)
            return
        if self.over_preview():                 # the wheel walks the camera forward / back
            if self.preview is not None:
                self.preview.nudge(1 if e.y > 0 else -1, abs(e.y))
            return
        area = self.map_area()
        section = self.section_name()
        if section is not None and area.collidepoint(self.mouse):  # the wheel scrolls a section shown instead of the map
            self.set_scroll(section, getattr(self, f"{section}_scroll") - e.y * 48)
            return
        if not area.collidepoint(self.mouse) or self.section_open():
            return
        if self.mods() & pygame.KMOD_CTRL:      # Ctrl + wheel changes the value under the cursor, no zoom
            self.nudge_cell(self.cell_at(self.mouse), VALUE_STEP * (1 if e.y > 0 else -1) * abs(e.y))
            return
        old = self.zoom
        self.zoom = max(8, min(96, old + (4 if e.y > 0 else -4) * abs(e.y)))
        if self.zoom != old:                    # keep the point under the cursor fixed
            mx, my = self.mouse[0] - area.x, self.mouse[1] - area.y
            self.pan[0] = round(mx - (mx - self.pan[0]) * self.zoom / old)
            self.pan[1] = round(my - (my - self.pan[1]) * self.zoom / old)

    # ---------------------------------------------------------------- drawing

    def draw(self, screen):
        screen.fill(BG)
        self.tips = []
        if self.guns_mode:
            self.draw_guns(screen)
        elif self.prefabs_mode:
            self.draw_prefabs(screen)
        elif self.effects_mode:
            self.draw_effects(screen)
        elif self.lights_mode:
            self.draw_lights(screen)
        elif self.settings_mode:
            self.draw_settings(screen)
        else:
            self.draw_map(screen)
        self.draw_panel(screen)
        self.draw_preview(screen)
        self.draw_details(screen)
        self.draw_legend(screen)
        self.draw_status(screen)
        self.draw_toolbar(screen)
        self.draw_dropdown(screen)
        if self.dropdown_open or self.menu_open is not None or self.new_name is not None or self.open_maps is not None \
                or self.importing is not None:
            self.tips = []                              # (what is under a list or dialog has no tooltips)
        self.draw_new_map_dialog(screen)
        self.draw_open_dialog(screen)
        if self.importing is not None:
            self.draw_shade(screen)
            self.tips += self.importing.draw(screen, self._size(), self.mouse) or []
        self.draw_tip(screen)
        title = f"Map editor {version_label()} - {os.path.basename(self.path)}{' *' if self.dirty else ''}"
        if pygame.display.get_caption()[0] != title:
            pygame.display.set_caption(title)

    def draw_cell(self, screen, x, y, rect):
        level, layer, floor = self.level, self.layer, self.floor
        wall = level.walls[y][x] if level.is_solid(x, y, floor) else 0   # a wall from a higher floor is open here
        if wall:
            if layer == "wall_h":
                self.draw_wall_height(screen, x, y, rect)
                return
            if self.edits_upper_wall(x, y):
                value = level.get(self.gname(layer), x, y)
                pygame.draw.rect(screen, heat(value, *HEIGHT_RANGE[layer]), rect)
                if self.zoom >= 24:
                    label = self.small.render(fmt(value), True, (10, 10, 20))
                    screen.blit(label, label.get_rect(center=rect.center))
                return
            if layer == "ceil_h" and floor == 0 and self.wall_ceiling_matters(x, y):
                self.draw_wall_ceiling(screen, x, y, rect)
                return
            if self.is_transparent_tile(wall):               # see-through: show the cell behind it
                pygame.draw.rect(screen, EMPTY_CELL, rect)
            screen.blit(self.tile_surface(wall - 1, dim=layer != "walls"), rect)
            if level.short_wall_top(x, y) is not None:
                draw_short_wall_mark(screen, rect)
            if layer == "sides":
                for side in SIDES:
                    if level.get(f"side_{side}", x, y):
                        partial = level.get(f"side_{side}_from", x, y) or level.get(f"side_{side}_to", x, y)
                        self.draw_side(screen, rect, side, level.get(f"side_{side}", x, y),
                                       outline=PARTIAL_SIDE if partial else ACCENT)
            return
        if layer == "wall_h":                           # heights live on walls: open cells are just context
            pygame.draw.rect(screen, EMPTY_CELL, rect)
            return
        grids = level.grids
        if floor >= 1 and not level.span_present(floor, x, y):
            # No room on this floor here: show the floor below, faded, as context.
            below = max(s for s in range(floor) if level.span_present(s, x, y))
            screen.blit(self.tile_surface(grids[grid_name("floor_tex", below)][y][x] - 1, dim=True), rect)
            return
        g = self.gname
        if layer in ("walls", "sides"):
            pygame.draw.rect(screen, EMPTY_CELL, rect)
        elif layer in ("floor_tex", "ceil_tex"):
            screen.blit(self.tile_surface(grids[g()][y][x] - 1), rect)
        else:
            source = "ceil_h" if layer == "ceil_h" else "floor_h"
            value = grids[g(source)][y][x]
            color = heat(value, *HEIGHT_RANGE[source])
            if layer in ("ramp", "site"):
                color = tuple(c // 2 for c in color)
            pygame.draw.rect(screen, color, rect)
            if layer in VALUE_LAYERS and self.zoom >= 24:
                label = self.small.render(fmt(value), True, (10, 10, 20))
                screen.blit(label, label.get_rect(center=rect.center))
        if layer == "ramp" and grids[g("ramp")][y][x]:
            self.draw_arrow(screen, rect, grids[g("ramp")][y][x], ACCENT)
        if layer == "site" and grids[g("site")][y][x] in SITE_COLORS:
            site = grids[g("site")][y][x]
            veil = pygame.Surface(rect.size, pygame.SRCALPHA)
            veil.fill((*SITE_COLORS[site], 150))
            screen.blit(veil, rect)
            if self.zoom >= 14:
                label = self.small.render(SITE_MARKS[site], True, (10, 10, 20))
                screen.blit(label, label.get_rect(center=rect.center))
        if self.zoom >= 16 and any(level.span_present(s, x, y) for s in range(floor + 1, level.floor_count)):
            draw_upper_mark(screen, rect)

    @staticmethod
    def side_rect(rect, side):
        """The strip along one side of a cell's rectangle on the map, a quarter of the cell deep."""
        depth = max(3, rect.w // 4)
        return {"n": pygame.Rect(rect.x, rect.y, rect.w, depth), "s": pygame.Rect(rect.x, rect.bottom - depth, rect.w, depth),
                "w": pygame.Rect(rect.x, rect.y, depth, rect.h), "e": pygame.Rect(rect.right - depth, rect.y, depth, rect.h)}[side]

    def draw_side(self, screen, rect, side, tile_id, alpha=255, outline=ACCENT):
        """A wall side's own tile, as a strip along that side of the wall's cell (outlined in PARTIAL_SIDE when
        it covers only a band of the side)."""
        strip = self.side_rect(rect, side)
        picture = pygame.transform.scale(self.tile_surface(tile_id - 1), strip.size)
        picture.set_alpha(alpha)
        screen.blit(picture, strip)
        pygame.draw.rect(screen, outline, strip, 1)

    def draw_wall_ceiling(self, screen, x, y, rect):
        """A wall on the CeilH layer where the ceiling over it matters: colored like a ceiling, with
        the number if it was set, or the number in (brackets), duller, while it is automatic."""
        level = self.level
        value = level.wall_ceiling(x, y)
        explicit = level.has_explicit_wall_ceiling(x, y)
        color = heat(value, *HEIGHT_RANGE["ceil_h"])
        pygame.draw.rect(screen, color if explicit else tuple(c * 2 // 3 for c in color), rect)
        if level.short_wall_top(x, y) is not None:
            draw_short_wall_mark(screen, rect)
        if self.zoom >= 24:
            text = self.small.render(fmt(value) if explicit else f"({fmt(value)})", True, (10, 10, 20))
            screen.blit(text, text.get_rect(center=rect.center))

    def draw_wall_height(self, screen, x, y, rect):
        """A wall on the WallH layer: colored by its height, with the number, or 'full'."""
        level = self.level
        value = level.grids["wall_h"][y][x]
        if level.short_wall_top(x, y) is None:          # 0, or tall enough to reach the ceiling
            color, label = WALL_FULL, ("full" if value <= 0 else fmt(value))
            text_color = (255, 255, 255)
        else:
            color, label = heat(value, *HEIGHT_RANGE["wall_h"]), fmt(value)
            text_color = (10, 10, 20)
        pygame.draw.rect(screen, color, rect)
        if self.zoom >= 24:
            text = self.small.render(label, True, text_color)
            screen.blit(text, text.get_rect(center=rect.center))

    def draw_arrow(self, screen, rect, kind, color):
        dx, dy = RAMP_VECTORS[kind]
        cx, cy, r = rect.centerx, rect.centery, rect.w * 0.32
        tip = (cx + dx * r, cy + dy * r)
        tail = (cx - dx * r, cy - dy * r)
        side = (-dy * r * 0.7, dx * r * 0.7)
        pygame.draw.line(screen, color, tail, tip, max(2, rect.w // 10))
        pygame.draw.polygon(screen, color, [tip, (cx + side[0], cy + side[1]), (cx - side[0], cy - side[1])])

    def draw_map(self, screen):
        area, level, z = self.map_area(), self.level, self.zoom
        screen.set_clip(area)
        origin = self.cell_rect(0, 0)
        x0, y0 = max(0, self.cell_at(area.topleft)[0]), max(0, self.cell_at(area.topleft)[1])
        x1 = min(level.width, self.cell_at(area.bottomright)[0] + 1)
        y1 = min(level.height, self.cell_at(area.bottomright)[1] + 1)
        for y in range(y0, y1):
            for x in range(x0, x1):
                self.draw_cell(screen, x, y, self.cell_rect(x, y))
        if z >= 12:
            for x in range(x0, x1 + 1):
                pygame.draw.line(screen, GRID, self.cell_rect(x, 0).topleft, self.cell_rect(x, level.height).topleft)
            for y in range(y0, y1 + 1):
                pygame.draw.line(screen, GRID, self.cell_rect(0, y).topleft, self.cell_rect(level.width, y).topleft)
        pygame.draw.rect(screen, ACCENT, (origin.x - 1, origin.y - 1, level.width * z + 2, level.height * z + 2), 1)
        for cx, cy in self.problem_cells():             # cells the status bar warns about, in red
            if x0 <= cx < x1 and y0 <= cy < y1:
                draw_problem_outline(screen, self.cell_rect(cx, cy))
        self.draw_entities(screen)
        self.draw_spawners(screen)
        self.draw_barricades(screen)
        self.draw_start(screen)
        self.draw_camera(screen)
        self.draw_cursor(screen, area)
        self.draw_center_marks(screen)
        self.draw_rulers(screen, area)
        screen.set_clip(None)

    def ruler_label_step(self):
        """Cells between the numbers on the rulers: the smallest step that leaves room for the widest number."""
        room = self.small.size(str(max(self.level.width, self.level.height)))[0] + 10
        return next((step for step in RULER_LABEL_STEPS if step * self.zoom >= room), RULER_LABEL_STEPS[-1])

    def map_center(self):
        """The middle of the map on the screen (x, y), in pixels."""
        origin = self.cell_rect(0, 0)
        return origin.x + self.level.width * self.zoom / 2, origin.y + self.level.height * self.zoom / 2

    def draw_center_marks(self, screen):
        """Small triangles on the map's border at the middle of each axis, pointing in (the rulers mark it too)."""
        origin, z = self.cell_rect(0, 0), self.zoom
        mx, my = self.map_center()
        right, bottom = origin.x + self.level.width * z, origin.y + self.level.height * z
        size = max(4, min(8, z // 3))
        for edge, inward in ((origin.y - 1, 1), (bottom + 1, -1)):            # top and bottom: the middle column
            pygame.draw.polygon(screen, ACCENT, [(mx - size, edge - inward * size), (mx + size, edge - inward * size),
                                                 (mx, edge)])
        for edge, inward in ((origin.x - 1, 1), (right + 1, -1)):             # left and right: the middle row
            pygame.draw.polygon(screen, ACCENT, [(edge - inward * size, my - size), (edge - inward * size, my + size),
                                                 (edge, my)])

    def draw_rulers(self, screen, area):
        """The rulers along the top and left of the map area: a tick on every grid line, a number every
        ruler_label_step() cells, the cell under the mouse lit up, and a triangle at the middle of each axis."""
        z, level = self.zoom, self.level
        origin = self.cell_rect(0, 0)
        top = pygame.Rect(area.x, area.y, area.w, RULER)
        left = pygame.Rect(area.x, area.y, RULER, area.h)
        pygame.draw.rect(screen, PANEL_BG, top)
        pygame.draw.rect(screen, PANEL_BG, left)
        hover = self.cell_at(self.mouse) if area.collidepoint(self.mouse) else None
        if hover is not None and level.in_bounds(*hover):           # where the mouse is, on both rulers
            pygame.draw.rect(screen, BUTTON_HOT, (origin.x + hover[0] * z, top.y, z, RULER))
            pygame.draw.rect(screen, BUTTON_HOT, (left.x, origin.y + hover[1] * z, RULER, z))
        step = self.ruler_label_step()
        for x in range(level.width + 1):
            px = origin.x + x * z
            if area.x + RULER <= px <= area.right:
                long = x % step == 0
                pygame.draw.line(screen, TEXT if long else DIM, (px, top.bottom - (10 if long else 4)), (px, top.bottom - 1))
                if long:
                    screen.blit(self.small.render(str(x), True, TEXT), (px + 2, top.y + 1))
        for y in range(level.height + 1):
            py = origin.y + y * z
            if area.y + RULER <= py <= area.bottom:
                long = y % step == 0
                pygame.draw.line(screen, TEXT if long else DIM, (left.right - (10 if long else 4), py), (left.right - 1, py))
                if long:
                    screen.blit(self.small.render(str(y), True, TEXT), (left.x + 2, py + 1))
        mx, my = self.map_center()
        if area.x + RULER <= mx <= area.right:                      # the middle of each axis
            pygame.draw.polygon(screen, ACCENT, [(mx - 5, top.bottom - 9), (mx + 5, top.bottom - 9), (mx, top.bottom - 1)])
        if area.y + RULER <= my <= area.bottom:
            pygame.draw.polygon(screen, ACCENT, [(left.right - 9, my - 5), (left.right - 9, my + 5), (left.right - 1, my)])
        pygame.draw.line(screen, GRID, (top.x, top.bottom - 1), (top.right, top.bottom - 1))
        pygame.draw.line(screen, GRID, (left.right - 1, left.y), (left.right - 1, left.bottom))
        pygame.draw.rect(screen, PANEL_BG, (area.x, area.y, RULER - 1, RULER - 1))   # the corner where they meet

    def over_ruler(self, pos):
        """True if `pos` is on one of the rulers (clicks there do not paint the map under them)."""
        area = self.map_area()
        return area.collidepoint(pos) and (pos[0] < area.x + RULER or pos[1] < area.y + RULER)

    # ---------------------------------------------------------------- the Guns section

    GUN_ROW_H = 46
    SECTION_GAP = 34

    def _list_width(self):
        return min(self.map_area().w - 40, 400)

    def gun_rows(self):
        """[(rect, gun index)] for the list of guns, and the rect of the Add button after it."""
        area = self.map_area()
        width = self._list_width()
        base = area.y + 74 - self.guns_scroll
        rows = [(pygame.Rect(area.x + 20, base + i * self.GUN_ROW_H, width, self.GUN_ROW_H - 4), i)
                for i in range(len(self.level.guns))]
        top = base + len(rows) * self.GUN_ROW_H
        return rows, pygame.Rect(area.x + 20, top, 160, 34)

    def ammo_rows(self):
        """[(rect, ammo index)] for the list of ammo types, below the guns, and the rect of its Add button."""
        area = self.map_area()
        _rows, add_gun = self.gun_rows()
        start = add_gun.bottom + self.SECTION_GAP + 30
        rows = [(pygame.Rect(area.x + 20, start + i * self.GUN_ROW_H, self._list_width(), self.GUN_ROW_H - 4), i)
                for i in range(len(self.level.ammo_types))]
        return rows, pygame.Rect(area.x + 20, start + len(rows) * self.GUN_ROW_H, 190, 34)

    def guns_click(self, pos):
        if self.gun_controls_click(pos) or self.gizmo_press(pos):
            return
        rows, add = self.gun_rows()
        ammo_rows, add_ammo = self.ammo_rows()
        if add.collidepoint(pos):
            self.add_gun()
            return
        if add_ammo.collidepoint(pos):
            self.add_ammo_type()
            return
        for rect, i in rows:
            if rect.collidepoint(pos):
                self.gun_selected, self.ammo_selected = i, None
                self.tile_target = "tile"
                self.field_edit = self.menu_open = None
                return
        for rect, i in ammo_rows:
            if rect.collidepoint(pos):
                self.ammo_selected, self.gun_selected = i, None
                self.tile_target = "tile"
                self.field_edit = self.menu_open = None
                return

    def guns_card_rect(self):
        """The rect of the preview card (gun or ammo) in the Guns section, where draw_guns puts it."""
        area = self.map_area()
        _rows, add_ammo = self.ammo_rows()
        right = area.x + 20 + self._list_width() + 24
        widest = GUN_CARD_WIDTH if self.selected_gun() is not None else 400     # (a gun's views want the room)
        card_w = min(widest, area.right - right - 20)
        if card_w < 200:                                   # no room beside the lists: below them
            right, card_w, top = area.x + 20, max(160, min(widest, area.w - 40)), add_ammo.bottom + 20
        else:
            top = area.y + 74 - self.guns_scroll
        if self.selected_ammo() is not None:
            return pygame.Rect(right, top, card_w, 190)
        return pygame.Rect(right, top, card_w, card_w * 9 // 16)

    def gun_controls(self, card):
        """{name: rect} of the controls under the gun picture (two check boxes and a button), flowing onto a
        second row when the card is narrow, and the y below them."""
        x, y = card.x, card.bottom + 10
        boxes = {}
        for name, label in (("continuous", "Fire continuously"), ("dark", "Dark room")):
            width = 22 + self.small.size(label)[0] + 8
            if x + width > card.right and x > card.x:
                x, y = card.x, y + 28
            boxes[name] = (pygame.Rect(x, y, 20, 20), label)
            x += width + 18
        if x + 92 > card.right and x > card.x:
            x, y = card.x, y + 28
        boxes["once"] = (pygame.Rect(x, y - 2, 92, 24), "Fire once")
        return boxes, y + 28

    def gizmo_points(self, gun):
        """{handle: (ahead, right, up)}: where the bullets start and where the muzzle effect starts, as offsets in cells
        from the gun's usual muzzle point (so the bullets' are exactly the Bullets ahead / right / up rows, and the
        effect's is the bullets' point plus the effect's start offset: the gun's own override, or the effect's).
        There is no "effect" while the gun has no muzzle effect."""
        bullet = (gun.bullet_offset_x, gun.bullet_offset_y, gun.bullet_offset_z)
        points = {"bullet": bullet}
        effect = self.level.effect_named(gun.muzzle) if gun.muzzle else None
        if effect is not None:
            ox, oy, oz = ((gun.muzzle_offset_x, gun.muzzle_offset_y, gun.muzzle_offset_z) if gun.muzzle_override
                          else (effect.offset_x, effect.offset_y, effect.offset_z))
            points["effect"] = (bullet[0] + ox, bullet[1] + oy, bullet[2] + oz)
        return points

    def gizmo_layout(self, card):
        """Where the placement controls go under the gun picture: a button for each handle, the depth slider (its
        track, and the strip of text before it), a line of numbers, and the y below it all. The handles themselves
        are drawn on the picture."""
        _controls, below = self.gun_controls(card)
        y = below + 22
        half = (card.w - 8) // 2
        buttons = {"bullet": pygame.Rect(card.x, y, half, 26), "effect": pygame.Rect(card.x + half + 8, y, half, 26)}
        slider_y = y + 42
        track = pygame.Rect(card.x + 178, slider_y, card.w - 178 - 84, 8)
        return {"buttons": buttons, "track": track, "slider_row": pygame.Rect(card.x, slider_y - 11, card.w, 30),
                "status": slider_y + 26, "bottom": slider_y + 26 + 17 + 34 + 8}

    @staticmethod
    def gizmo_eye(point):
        """(ahead, right, up) of an offset point as seen from the player's eye (the muzzle is MUZZLE ahead of it and
        EYE_DROP below it), with ahead kept in front of the eye."""
        return (max(GIZMO_NEAR, MUZZLE + point[0]), point[1], point[2] - EYE_DROP)

    @staticmethod
    def gizmo_focal():
        return (WIDTH / 2) / math.tan(math.radians(FOV_DEG) / 2)

    def gizmo_pixel(self, card, point):
        """The pixel on the gun picture where an offset point appears, kept inside the picture (a point off the edge
        sits on the edge, where it can still be grabbed)."""
        ahead, right, up = self.gizmo_eye(point)
        focal = self.gizmo_focal()
        x = card.x + (WIDTH / 2 + right / ahead * focal) * card.w / WIDTH
        y = card.y + (HEIGHT / 2 - up / ahead * focal) * card.h / HEIGHT
        return (round(min(max(x, card.left), card.right - 1)), round(min(max(y, card.top), card.bottom - 1)))

    def gizmo_from_pixel(self, card, pos, ahead):
        """(right, up) offsets, in cells, of the point at depth `ahead` (from the eye) that shows at pixel `pos`."""
        focal = self.gizmo_focal()
        x = (min(max(pos[0], card.left), card.right - 1) - card.x) * WIDTH / card.w - WIDTH / 2
        y = (min(max(pos[1], card.top), card.bottom - 1) - card.y) * HEIGHT / card.h - HEIGHT / 2
        return (round(x / focal * ahead, 3), round(-y / focal * ahead, 3))     # (fine enough to follow the mouse close to the eye)

    def gizmo_hit(self, card, gun, pos):
        """The handle under `pos` on the picture, or None. Where two handles lie on top of each other the selected one
        wins, so a click never switches handle by surprise (the buttons do that)."""
        if not card.collidepoint(pos):
            return None
        points = self.gizmo_points(gun)
        for handle in [self.gizmo_selected] + [h for h in points if h != self.gizmo_selected]:
            if handle in points:
                px, py = self.gizmo_pixel(card, points[handle])
                if math.hypot(pos[0] - px, pos[1] - py) <= GIZMO_HIT:
                    return handle
        return None

    def gizmo_depth(self, gun):
        """The picked handle's depth for the slider: cells ahead of the gun's usual muzzle point."""
        points = self.gizmo_points(gun)
        return points[self.gizmo_selected if self.gizmo_selected in points else "bullet"][0]

    def gizmo_slider_value(self, layout, pos):
        """The depth the slider shows at pixel `pos`, kept within the slider's range."""
        track = layout["track"]
        f = min(max((pos[0] - track.x) / track.w, 0.0), 1.0)
        return round(GIZMO_DEPTH[0] + f * (GIZMO_DEPTH[1] - GIZMO_DEPTH[0]), 2)

    def gizmo_press(self, pos):
        """A click in the placement controls. A handle button picks which handle moves. On the picture a click on a
        handle grabs it and a click anywhere else puts the picked handle there (at the depth it has), and dragging goes
        on moving it. On the slider a click sets the picked handle's depth, and dragging goes on."""
        gun = self.selected_gun()
        if gun is None:
            return False
        card = self.guns_card_rect()
        layout = self.gizmo_layout(card)
        points = self.gizmo_points(gun)
        for handle, rect in layout["buttons"].items():
            if rect.collidepoint(pos):
                if handle in points:
                    self.gizmo_selected = handle
                else:
                    self.say("Choose a Muzzle effect for this gun first, then you can place where it starts")
                return True
        target = None
        if layout["slider_row"].collidepoint(pos):
            target = "slider"
        elif card.collidepoint(pos):
            hit = self.gizmo_hit(card, gun, pos)
            if hit is not None:
                self.gizmo_selected = hit
            elif self.gizmo_selected not in points:
                self.gizmo_selected = "bullet"
            target = "picture"
        if target is None:
            return False
        self.undo.append(self.level.copy())                        # the whole drag is one undo step; the preview is left
        del self.undo[:-MAX_UNDO]                                  # running until the mouse is let go (see gizmo_release)
        self.redo.clear()
        self.dirty = True
        self.gizmo_drag = target
        self.gizmo_move(pos)
        return True

    def gizmo_move(self, pos):
        """Move the picked handle to where the mouse is: on the picture, sideways and up at the depth it has; on the
        slider, in and out."""
        gun = self.selected_gun()
        if gun is None or self.gizmo_drag is None:
            return
        card = self.guns_card_rect()
        handle = self.gizmo_selected if self.gizmo_selected in self.gizmo_points(gun) else "bullet"
        if self.gizmo_drag == "slider":
            self.gizmo_set(gun, handle, ahead=self.gizmo_slider_value(self.gizmo_layout(card), pos))
        else:
            ahead = self.gizmo_eye(self.gizmo_points(gun)[handle])[0]
            right, up = self.gizmo_from_pixel(card, pos, ahead)
            self.gizmo_set(gun, handle, right=right, up=up + EYE_DROP)

    def gizmo_set(self, gun, handle, ahead=None, right=None, up=None):
        """Put `handle` at the given offsets from the gun's usual muzzle point (any left out stay as they are), by
        setting the gun's offsets: the bullets' directly, the effect's relative to the bullets'."""
        def keep(value):
            return round(max(-5.0, min(5.0, value)), 3)
        points = self.gizmo_points(gun)
        if handle == "bullet":
            if ahead is not None:
                gun.bullet_offset_x = keep(ahead)
            if right is not None:
                gun.bullet_offset_y = keep(right)
            if up is not None:
                gun.bullet_offset_z = keep(up)
        elif handle == "effect" and "effect" in points:
            if not gun.muzzle_override:                            # start overriding, from where it is now
                effect = self.level.effect_named(gun.muzzle)
                gun.muzzle_override = True
                gun.muzzle_offset_x, gun.muzzle_offset_y, gun.muzzle_offset_z = effect.offset_x, effect.offset_y, effect.offset_z
            bullet = points["bullet"]
            if ahead is not None:
                gun.muzzle_offset_x = keep(ahead - bullet[0])
            if right is not None:
                gun.muzzle_offset_y = keep(right - bullet[1])
            if up is not None:
                gun.muzzle_offset_z = keep(up - bullet[2])
        self.dirty = True
        if self.gun_preview is not None:
            self.gun_preview.sync_gun(gun)

    def gizmo_release(self):
        self.gizmo_drag = None
        self.touch()                                               # the preview starts over with the new place

    def draw_gizmo_handle(self, screen, handle, center, selected, hot):
        """A handle: an orange disc for the bullets, a cyan diamond for the effect, ringed white when it is the
        picked one and larger while the mouse is on it."""
        color = GIZMO_COLORS[handle]
        r = 8 + (3 if hot else 0)
        if handle == "bullet":
            pygame.draw.circle(screen, color, center, r)
            pygame.draw.circle(screen, (20, 20, 28), center, r, 1)
        else:
            diamond = [(center[0], center[1] - r - 2), (center[0] + r + 2, center[1]), (center[0], center[1] + r + 2),
                       (center[0] - r - 2, center[1])]
            pygame.draw.polygon(screen, color, diamond)
            pygame.draw.polygon(screen, (20, 20, 28), diamond, 1)
        if selected:
            pygame.draw.circle(screen, (255, 255, 255), center, r + 6, 2)

    def draw_gizmo(self, screen, card, gun):
        """The placement controls: the handles on the gun picture (where the bullets and the muzzle effect start, drawn
        where they really are), which handle is picked, the depth slider that moves it in and out of the screen, and
        the numbers it comes to."""
        layout = self.gizmo_layout(card)
        points = self.gizmo_points(gun)
        picked = self.gizmo_selected if self.gizmo_selected in points else "bullet"
        for handle, rect in layout["buttons"].items():
            enabled = handle in points
            pygame.draw.rect(screen, BUTTON_ON if handle == picked and enabled else
                             (BUTTON_HOT if rect.collidepoint(self.mouse) and enabled else BUTTON), rect, border_radius=4)
            if enabled:
                self.draw_gizmo_handle(screen, handle, (rect.x + 16, rect.centery), False, False)
            label = {"bullet": "Bullets come from", "effect": "Effect starts at"}[handle] if enabled else "Effect (pick a muzzle effect)"
            screen.blit(self.small.render(label, True, TEXT if enabled else DIM), (rect.x + 34, rect.y + 6))
        hover = self.gizmo_hit(card, gun, self.mouse) if not self.gizmo_drag else None
        screen.set_clip(card)
        if "effect" in points:                                     # a dashed line from the bullets' point to the effect's
            a, b = (self.gizmo_pixel(card, points[h]) for h in ("bullet", "effect"))
            length = math.hypot(a[0] - b[0], a[1] - b[1])
            if length > 14:
                steps = max(2, round(length / 6))
                for i in range(0, steps, 2):
                    p1 = (a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)
                    p2 = (a[0] + (b[0] - a[0]) * (i + 1) / steps, a[1] + (b[1] - a[1]) * (i + 1) / steps)
                    pygame.draw.line(screen, (230, 234, 245), p1, p2)
        for handle in [h for h in ("effect", "bullet") if h in points and h != picked] + [picked]:   # the picked one on top
            center = self.gizmo_pixel(card, points[handle])
            self.draw_gizmo_handle(screen, handle, center, handle == picked, hover == handle)
            if handle == picked:
                tag = self.small.render(GIZMO_NAMES[handle], True, GIZMO_COLORS[handle])
                back = pygame.Rect(0, 0, tag.get_width() + 6, tag.get_height() + 2)
                back.midleft = (min(center[0] + 16, card.right - back.w - 2), max(card.y + 10, center[1] - 20))
                pygame.draw.rect(screen, (16, 17, 22), back, border_radius=3)
                screen.blit(tag, (back.x + 3, back.y + 1))
        screen.set_clip(None)
        track = layout["track"]                                    # the depth slider
        color = GIZMO_COLORS[picked]
        screen.blit(self.small.render("Depth (in / out)", True, TEXT), (card.x, track.centery - 8))
        pygame.draw.rect(screen, (40, 43, 54), track, border_radius=4)
        zero = track.x + round((0 - GIZMO_DEPTH[0]) / (GIZMO_DEPTH[1] - GIZMO_DEPTH[0]) * track.w)
        pygame.draw.line(screen, (150, 156, 170), (zero, track.y - 5), (zero, track.bottom + 5))     # the usual muzzle point
        screen.blit(self.small.render("muzzle", True, DIM), (zero - 18, track.bottom + 6))
        depth = self.gizmo_depth(gun)
        knob = track.x + round(min(max((depth - GIZMO_DEPTH[0]) / (GIZMO_DEPTH[1] - GIZMO_DEPTH[0]), 0.0), 1.0) * track.w)
        pygame.draw.rect(screen, color, (track.x, track.y, max(0, knob - track.x), track.h), border_radius=4)
        self.draw_gizmo_handle(screen, picked, (knob, track.centery), self.gizmo_drag == "slider", False)
        screen.blit(self.small.render(f"{depth:+.2f}", True, color), (track.right + 22, track.centery - 8))
        if picked == "bullet":                                     # the numbers of the pane's rows
            a, r, u = gun.bullet_offset_x, gun.bullet_offset_y, gun.bullet_offset_z
            where = "from the gun's usual muzzle point"
        else:
            a, r, u = (points["effect"][i] - points["bullet"][i] for i in range(3))
            where = "from where the bullets start"
        screen.blit(self.small.render(f"Moving: {GIZMO_NAMES[picked]}   ahead {a:+.2f}  right {r:+.2f}  up {u:+.2f}",
                                      True, color), (card.x, layout["status"]))
        self._draw_wrapped(screen, (f"Offsets {where}. Drag a handle on the picture (sideways and up), or click to put it "
                                    "there; the slider moves it in and out of the screen; the buttons switch handle.",),
                           card.x, layout["status"] + 17, card.w)
        return layout

    def step_gun_preview(self, dt):
        """Keep the live gun in the Guns section running: built again whenever the level, the gun or the dark
        room setting changes, then run on by dt (firing all the time if Fire continuously is ticked)."""
        gun = self.selected_gun()
        if not self.guns_mode or gun is None:
            return
        if self.gun_preview is None:
            self.gun_preview = GunPreview(atlas_array(self.tiles))
        key = (self.revision, self.gun_selected, self.gun_dark)
        if self.gun_preview_key != key:
            self.gun_preview.build(self.level, gun.name, self.gun_dark)
            self.gun_preview_key = key
        self.gun_preview.update(dt, self.gun_continuous)

    def gun_controls_click(self, pos):
        """A click on the gun picture's controls; True if it hit one."""
        if self.selected_gun() is None:
            return False
        controls, _bottom = self.gun_controls(self.guns_card_rect())
        for name, (rect, _label) in controls.items():
            if rect.collidepoint(pos):
                if name == "continuous":
                    self.gun_continuous = not self.gun_continuous
                elif name == "dark":
                    self.gun_dark = not self.gun_dark
                elif self.gun_preview is not None:
                    self.gun_preview.fire_once()
                return True
        return False

    def draw_guns(self, screen):
        """The Guns section: the map's guns and ammo types as lists, and a preview of the selected one."""
        area = self.map_area()
        screen.set_clip(area)
        pygame.draw.rect(screen, BG, area)
        self.clamp_guns_scroll()
        screen.blit(self.font.render("Guns in this map", True, ACCENT), (area.x + 20, area.y + 14 - self.guns_scroll))
        self.blit_fitted(screen, self.small, "Click a gun or an ammo type to edit it in the Details pane. Pick pictures "
                         "from the atlas.", DIM, (area.x + 20, area.y + 40 - self.guns_scroll), area.right - 14)
        rows, add = self.gun_rows()
        for rect, i in rows:
            g = self.level.guns[i]
            on = i == self.gun_selected
            pygame.draw.rect(screen, BUTTON_ON if on else (BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON),
                             rect, border_radius=4)
            screen.set_clip(rect.clip(area))                   # long summaries stop at the row's edge
            screen.blit(self.tiles[max(0, min(g.tile, len(self.tiles) - 1))], (rect.x + 6, rect.y + (rect.h - TILE) // 2))
            self.blit_fitted(screen, self.font, g.name, TEXT, (rect.x + 48, rect.y + 5), rect.right - 8)
            summary = (f"{GUN_MODE_LABELS[g.mode]}   {g.damage:g} dmg   {g.fire_rate:g}/s   {g.capacity} rounds   "
                       f"ammo: {g.ammo or 'default'}")
            if g.shot != "single":
                summary += f"   {SHOT_LABELS[g.shot].lower()}" + (f" x{g.pellets}" if g.shot == "multi" else "")
            self.blit_fitted(screen, self.small, summary, TEXT if on else DIM, (rect.x + 48, rect.y + 24), rect.right - 8)
            screen.set_clip(area)
        self._draw_add_button(screen, add, "+ Add gun")
        ammo_rows, add_ammo = self.ammo_rows()
        screen.blit(self.font.render("Ammunition", True, ACCENT), (add.x, add.bottom + self.SECTION_GAP - 4))
        for rect, i in ammo_rows:
            a = self.level.ammo_types[i]
            on = i == self.ammo_selected
            pygame.draw.rect(screen, BUTTON_ON if on else (BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON),
                             rect, border_radius=4)
            screen.set_clip(rect.clip(area))
            screen.blit(self.tiles[max(0, min(a.tile, len(self.tiles) - 1))], (rect.x + 6, rect.y + (rect.h - TILE) // 2))
            self.blit_fitted(screen, self.font, a.name, TEXT, (rect.x + 48, rect.y + 5), rect.right - 8)
            users = [g.name for g in self.level.guns if g.ammo == a.name]
            summary = (f"speed {a.speed:g}   range {a.range:g}   damage x{a.damage_mult:g}   used by "
                       + (", ".join(users) if users else "no gun"))
            self.blit_fitted(screen, self.small, summary, TEXT if on else DIM, (rect.x + 48, rect.y + 24), rect.right - 8)
            screen.set_clip(area)
        self._draw_add_button(screen, add_ammo, "+ Add ammo type")
        card = self.guns_card_rect()
        gun, ammo = self.selected_gun(), self.selected_ammo()
        if gun is not None:
            self.draw_gun_preview(screen, card, gun)
        elif ammo is not None:
            self.draw_ammo_preview(screen, card, ammo)
        else:
            note = "No guns yet: add one." if not self.level.guns else "Select a gun or an ammo type to edit it."
            screen.blit(self.small.render(note, True, DIM), (card.x, card.y))
        self.draw_scrollbar(screen, "guns")
        screen.set_clip(None)

    def guns_content_bottom(self):
        """The y of the bottom of everything in the Guns section if it were not scrolled at all."""
        area = self.map_area()
        scrolled, self.guns_scroll = self.guns_scroll, 0
        try:
            _rows, add_ammo = self.ammo_rows()
            bottom = add_ammo.bottom + 40
            card = self.guns_card_rect()
            if self.selected_gun() is not None:
                bottom = max(bottom, self.gizmo_layout(card)["bottom"] + 8 + 56 + 14 + 4 * 17 + 20)
            elif self.selected_ammo() is not None:
                bottom = max(bottom, card.bottom + 120)
        finally:
            self.guns_scroll = scrolled
        return bottom

    def clamp_guns_scroll(self):
        """Keep the scroll within the content (it shrinks when the selection or the window does)."""
        self.set_scroll("guns", self.guns_scroll)

    # ---------------------------------------------------------------- scrolling, and text cut short to fit

    SCROLLED_SECTIONS = ("guns", "prefabs", "effects", "lights", "settings")

    def section_name(self):
        """Which scrolling section is showing in place of the map, or None."""
        return next((name for name in self.SCROLLED_SECTIONS if getattr(self, f"{name}_mode")), None)

    def section_bottom(self, name):
        """The y of the bottom of everything in section `name` if it were not scrolled at all."""
        if name == "guns":
            return self.guns_content_bottom()
        if name == "settings":
            return self.settings_content_bottom()
        add = {"prefabs": self.prefab_rows, "effects": self.effect_rows, "lights": self.light_rows}[name]()[-1]
        bottom = add.bottom + 40
        card = self.section_card(name)
        if card is not None:
            card, lines, width = card
            wrapped = sum(len(details.note_lines([text], self.small, width)) for text in lines)
            bottom = max(bottom, card.bottom + 12 + 17 * wrapped + 20)
        return bottom + getattr(self, f"{name}_scroll")

    def scroll_view(self, name):
        """(view, content height, scroll) of something that scrolls: "details" (the Details pane's rows), "open"
        (the Open dialog's list) or a section showing in place of the map; None while it is not showing."""
        if name == "details":
            rect = self.details_rect()
            if rect is None:
                return None
            rows = details.rows_for(rect, self.details_fields(), (self.font, self.small), self.details_scroll)
            height = details.content_height(rect, rows, self.details_text()[1], self.small, self.details_delete_label())
            return details.view_rect(rect), height, self.details_scroll
        if name == "open":
            if self.open_maps is None:
                return None
            listing = self.open_rects()[1]
            return listing, len(self.open_maps) * OPEN_ROW_H, self.open_scroll * OPEN_ROW_H
        if name in self.SCROLLED_SECTIONS and getattr(self, f"{name}_mode"):
            area = self.map_area()
            return area, self.section_bottom(name) - area.y, getattr(self, f"{name}_scroll")
        return None

    def set_scroll(self, name, scroll):
        """Scroll `name` (see scroll_view) to `scroll` pixels, kept between the top and the end of what is in it."""
        view = self.scroll_view(name)
        most = 0 if view is None else max(0, view[1] - view[0].h)
        scroll = max(0, min(round(scroll), most))
        if name == "open":
            self.open_scroll = max(0, min(len(self.open_maps or ()) - OPEN_ROWS, round(scroll / OPEN_ROW_H)))
        else:
            setattr(self, f"{name}_scroll", scroll)

    def scrollbar(self, name):
        """(track, thumb) of the bar showing where `name` is scrolled to, or None when all of it fits."""
        view = self.scroll_view(name)
        return None if view is None else details.scrollbar(*view)

    def scrollbar_press(self, pos, names):
        """A press on the bar of one of `names`: drag its thumb from there (or, on the track, jump the thumb
        there first). True if it was on a bar."""
        for name in names:
            bar = self.scrollbar(name) if name else None
            if bar is not None and bar[0].inflate(10, 0).collidepoint(pos):
                _track, thumb = bar
                self.scroll_drag = (name, pos[1] - thumb.y if thumb.top <= pos[1] < thumb.bottom else thumb.h // 2)
                self.scroll_drag_to(pos[1])
                return True
        return False

    def scroll_drag_to(self, y):
        """While a bar is dragged: scroll so the point grabbed on its thumb is at screen row `y`."""
        name, grab = self.scroll_drag
        view = self.scroll_view(name)
        if view is not None:
            self.set_scroll(name, details.scroll_for(view[0], view[1], y - grab))

    def draw_scrollbar(self, screen, name):
        """The thin bar at the right edge of `name` (see scroll_view) when there is more in it than shows."""
        bar = self.scrollbar(name)
        if bar is not None:
            dragged = self.scroll_drag is not None and self.scroll_drag[0] == name
            hot = dragged or bar[0].inflate(10, 0).collidepoint(self.mouse)
            details.draw_scrollbar(screen, bar, hot)

    def blit_fitted(self, screen, font, text, color, pos, right):
        """Draw `text` at `pos`, cut short with "..." to end by screen column `right`; text cut short shows whole
        in a tooltip while the mouse is over it."""
        shown = details.fit_text(font, text, right - pos[0])
        if shown != text:
            area = pygame.Rect(pos[0], pos[1], right - pos[0], font.get_linesize())
            clip = screen.get_clip()
            self.tips.append((area.clip(clip) if clip else area, text))
        screen.blit(font.render(shown, True, color), pos)

    def draw_tip(self, screen):
        """The whole of the text cut short under the mouse, in a box beside it (the last drawn is on top)."""
        for area, text in reversed(self.tips):
            if area.w > 0 and area.h > 0 and area.collidepoint(self.mouse):
                lines = details.note_lines([text], self.small, 460)
                width = max(self.small.size(line)[0] for line in lines)
                box = pygame.Rect(self.mouse[0] + 14, self.mouse[1] + 18, width + 14, 17 * len(lines) + 8)
                box.clamp_ip(screen.get_rect())
                pygame.draw.rect(screen, (20, 21, 27), box, border_radius=4)
                pygame.draw.rect(screen, GRID, box, 1, border_radius=4)
                for i, line in enumerate(lines):
                    screen.blit(self.small.render(line, True, TEXT), (box.x + 7, box.y + 4 + 17 * i))
                return


    def _draw_wrapped(self, screen, lines, x, y, width):
        """Small gray lines of text wrapped to `width` pixels, starting at (x, y); returns the y below them."""
        for text in lines:
            line = ""
            for word in text.split():
                trial = f"{line} {word}".strip()
                if line and self.small.size(trial)[0] > width:
                    screen.blit(self.small.render(line, True, DIM), (x, y))
                    y, line = y + 17, word
                else:
                    line = trial
            screen.blit(self.small.render(line, True, DIM), (x, y))
            y += 17
        return y

    def _draw_add_button(self, screen, rect, text):
        pygame.draw.rect(screen, BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON, rect, border_radius=4)
        label = self.font.render(text, True, TEXT)
        screen.blit(label, label.get_rect(center=rect.center))

    def _draw_bullet(self, screen, box, ammo, cell=56):
        """The bullet at its real size next to a one cell square."""
        pygame.draw.rect(screen, GRID, box, 1)
        size = max(2, round(ammo.size * cell))
        bullet = pygame.transform.scale(self.tiles[max(0, min(ammo.tile, len(self.tiles) - 1))], (size, size))
        screen.blit(bullet, bullet.get_rect(center=box.center))
        screen.blit(self.small.render("bullet vs a 1 cell square", True, DIM), (box.right + 10, box.centery - 8))

    def draw_gun_preview(self, screen, card, gun):
        """The gun as the player sees it: the game's own picture of a corridor with the gun in hand, firing with
        its real fire rate, magazine, reload, muzzle effect and light, bullets and trails (while Fire
        continuously is ticked, or after Fire once). Under it, the bullet at its real size next to a cell-sized
        square, and the numbers that matter."""
        ammo = self.level.ammo_for(gun)
        live = self.gun_preview
        picture = None
        if live is not None and live.ready and live.gun_name == gun.name and self.gun_preview_key is not None:
            try:
                picture = live.render(self.tiles, self.hud_font)
            except Exception:                              # a half-finished edit must not take the editor down
                picture = None
        if picture is None:
            picture = pygame.Surface((640, 360))
            picture.fill((44, 48, 60))
            pygame.draw.rect(picture, (64, 60, 52), (0, 300, 640, 60))
            hud.draw_weapon(picture, self.tiles, GunState(gun, mag=gun.capacity), 0.0)
        screen.blit(pygame.transform.smoothscale(picture, card.size), card)
        pygame.draw.rect(screen, GRID, card.inflate(2, 2), 1)
        controls, below = self.gun_controls(card)
        for name, (rect, label) in controls.items():
            if name == "once":
                pygame.draw.rect(screen, BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON, rect, border_radius=4)
                text = self.small.render(label, True, TEXT)
                screen.blit(text, text.get_rect(center=rect.center))
                continue
            on = self.gun_continuous if name == "continuous" else self.gun_dark
            pygame.draw.rect(screen, BUTTON_ON if on else BUTTON, rect, border_radius=3)
            pygame.draw.rect(screen, GRID, rect, 1, border_radius=3)
            if on:
                pygame.draw.lines(screen, TEXT, False, [(rect.x + 4, rect.centery), (rect.x + 8, rect.bottom - 6),
                                                        (rect.right - 4, rect.y + 5)], 2)
            screen.blit(self.small.render(label, True, TEXT), (rect.right + 8, rect.y + 3))
        if live is not None and live.ready and live.gun_name == gun.name:
            count = live.shots_last_second()
            screen.blit(self.small.render(f"{count} shot{'s' if count != 1 else ''} in the last second "
                                          f"(set to {gun.fire_rate:g} a second)", True, DIM), (card.x, below - 4))
        below = self.draw_gizmo(screen, card, gun)["bottom"]
        box = pygame.Rect(card.x, below + 8, 56, 56)
        self._draw_bullet(screen, box, ammo)
        damage = gun.damage * ammo.damage_mult
        lines = (f"{damage:g} damage a bullet, {damage * gun.fire_rate:g} a second at full fire rate",
                 f"{gun.capacity} round{'s' if gun.capacity != 1 else ''} a magazine, {gun.start_ammo} spare "
                 f"({ammo.name}), {gun.reload_time:g}s to reload",
                 f"a shot every {1 / gun.fire_rate:.2g} s; bullets fly {ammo.speed:g} cells a second for up to "
                 f"{ammo.range:g} cells")
        self._draw_wrapped(screen, lines, card.x, box.bottom + 14, card.w)

    def draw_ammo_preview(self, screen, card, ammo):
        pygame.draw.rect(screen, (44, 48, 60), card)
        pygame.draw.rect(screen, GRID, card.inflate(2, 2), 1)
        self._draw_bullet(screen, pygame.Rect(card.x + 20, card.y + 20, 56, 56), ammo)
        users = [g.name for g in self.level.guns if g.ammo == ammo.name]
        lines = (f"flies {ammo.speed:g} cells a second for up to {ammo.range:g} cells",
                 f"multiplies a gun's damage by {ammo.damage_mult:g}",
                 "used by: " + (", ".join(users) if users else "no gun yet"),
                 "guns that use it share one pool of spare rounds")
        self._draw_wrapped(screen, lines, card.x + 20, card.y + 90, card.w - 40)

    # ---------------------------------------------------------------- the Prefabs section

    PREFAB_ROW_H = 46

    def prefab_rows(self):
        """[(rect, prefab index)] for the list of prefabs, and the rect of the Add button after it."""
        area = self.map_area()
        width = min(area.w - 40, 440)
        base = area.y + 74 - self.prefabs_scroll
        rows = [(pygame.Rect(area.x + 20, base + i * self.PREFAB_ROW_H, width, self.PREFAB_ROW_H - 4), i)
                for i in range(len(self.level.prefabs))]
        top = base + len(rows) * self.PREFAB_ROW_H
        return rows, pygame.Rect(area.x + 20, top, 170, 34)

    def prefabs_click(self, pos):
        rows, add = self.prefab_rows()
        if add.collidepoint(pos):
            self.add_prefab()
            return
        for rect, i in rows:
            if rect.collidepoint(pos):
                self.prefab_selected = i
                self.tile_target = "tile"
                self.field_edit = self.menu_open = None
                return

    def draw_prefabs(self, screen):
        """The Prefabs section: the map's prefabs as a list, and a big look at the selected one's icon."""
        area = self.map_area()
        screen.set_clip(area)
        pygame.draw.rect(screen, BG, area)
        self.set_scroll("prefabs", self.prefabs_scroll)
        top = area.y - self.prefabs_scroll
        screen.blit(self.font.render("Prefabs in this map", True, ACCENT), (area.x + 20, top + 14))
        self.blit_fitted(screen, self.small, "A prefab is a saved item (icon, pickup effect, animation) you can place as "
                         "often as you like.", DIM, (area.x + 20, top + 40), area.right - 14)
        rows, add = self.prefab_rows()
        for rect, i in rows:
            p = self.level.prefabs[i]
            on = i == self.prefab_selected
            pygame.draw.rect(screen, BUTTON_ON if on else (BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON),
                             rect, border_radius=4)
            screen.set_clip(rect.clip(area))
            screen.blit(self.tiles[max(0, min(p.tile, len(self.tiles) - 1))], (rect.x + 6, rect.y + (rect.h - TILE) // 2))
            self.blit_fitted(screen, self.font, p.name, TEXT, (rect.x + 48, rect.y + 5), rect.right - 8)
            used = sum(1 for e in self.level.entities if e.prefab == p.name)
            summary = f"{MODE_LABELS[p.mode]}   {describe(p)}   placed {used}x"
            self.blit_fitted(screen, self.small, summary, TEXT if on else DIM, (rect.x + 48, rect.y + 24), rect.right - 8)
            screen.set_clip(area)
        self._draw_add_button(screen, add, "+ Add prefab")
        right = area.x + 20 + min(area.w - 40, 440) + 24
        p = self.selected_prefab()
        if p is None:
            note = "No prefabs yet: add one." if not self.level.prefabs else "Select a prefab to edit it."
            screen.blit(self.small.render(note, True, DIM), (right if area.right - right > 200 else add.x, add.bottom + 14
                                                           if area.right - right <= 200 else top + 74))
        else:
            card, lines, width = self.section_card("prefabs")
            pygame.draw.rect(screen, (44, 48, 60), card)
            pygame.draw.rect(screen, GRID, card.inflate(2, 2), 1)
            icon = pygame.transform.scale(self.tiles[max(0, min(p.tile, len(self.tiles) - 1))], (128, 128))
            screen.blit(icon, icon.get_rect(center=(card.centerx, card.y + 76)))
            screen.blit(self.small.render("how it looks in the world", True, DIM), (card.x + 12, card.bottom - 24))
            self._draw_wrapped(screen, lines, card.x, card.bottom + 12, width)
        self.draw_scrollbar(screen, "prefabs")
        screen.set_clip(None)

    def section_card(self, name):
        """(card rect, lines of text under it, how wide they wrap) of the selected thing's preview in the
        Prefabs, Effects or Lights section (beside the list, or below it when there is no room), or None while
        nothing is selected there."""
        area = self.map_area()
        right = area.x + 20 + min(area.w - 40, 440) + 24
        top = area.y + 74 - getattr(self, f"{name}_scroll")
        if name == "prefabs":
            p = self.selected_prefab()
            if p is None:
                return None
            card = pygame.Rect(right, top, 200, 200)
            if area.right - right < 220:
                card = pygame.Rect(area.x + 20, self.prefab_rows()[1].bottom + 20, 200, 200)
            lines = (f"{MODE_LABELS[p.mode]}: {describe(p)}",
                     ", ".join(ANIMATION_LABELS[a.kind].lower() for a in p.animations) or "no animation",
                     f"size {p.size:g}, lift {p.lift:g}")
            return card, lines, max(200, area.right - card.x - 20)
        if name == "effects":
            thing, add = self.selected_effect(), self.effect_rows()[1]
            if thing is None:
                return None
            users = self.effect_users(thing)
            lines = (self.effect_summary(thing), "used by: " + (", ".join(users) if users else "nothing yet"))
        else:
            thing, add = self.selected_light(), self.light_rows()[2]
            if thing is None:
                return None
            users = self.light_users(thing)
            lines = (self.light_summary(thing), "used by: " + (", ".join(users) if users else "nothing yet"))
        width = min(420, area.right - right - 20)
        card = pygame.Rect(right, top, width, 330)
        if width < 220:
            card = pygame.Rect(add.x, add.bottom + 20, min(420, max(160, area.w - 40)), 330)
        return card, lines, card.w

    # ---------------------------------------------------------------- the Effects section

    EFFECT_ROW_H = 46

    def effect_rows(self):
        """[(rect, effect index)] for the list of effects, and the rect of the Add button after it."""
        area = self.map_area()
        width = min(area.w - 40, 440)
        base = area.y + 74 - self.effects_scroll
        rows = [(pygame.Rect(area.x + 20, base + i * self.EFFECT_ROW_H, width, self.EFFECT_ROW_H - 4), i)
                for i in range(len(self.level.effects))]
        top = base + len(rows) * self.EFFECT_ROW_H
        return rows, pygame.Rect(area.x + 20, top, 170, 34)

    def effects_click(self, pos):
        rows, add = self.effect_rows()
        if add.collidepoint(pos):
            self.add_effect()
            return
        for rect, i in rows:
            if rect.collidepoint(pos):
                self.effect_selected = i
                self.tile_target = "tile"
                self.field_edit = self.menu_open = None
                return

    def effect_users(self, effect):
        """Short names of what uses an effect: guns (muzzle), ammo types (trail) and how many items emit it."""
        users = [f"{g.name} muzzle" for g in self.level.guns if g.muzzle == effect.name]
        users += [f"{a.name} trail" for a in self.level.ammo_types if a.trail == effect.name]
        users += [f"{a.name} hit" for a in self.level.ammo_types
                  if effect.name in a.player_hit_effects + a.world_hit_effects]
        emitting = sum(1 for e in self.level.entities if e.emits == effect.name)
        if emitting:
            users.append(f"{emitting} item{'s' if emitting != 1 else ''}")
        return users

    def effect_summary(self, f):
        how = f"burst of {f.count}" if f.kind == "burst" else f"{f.rate:g} a second"
        return f"{how}   life {f.life:g}s   speed {f.speed:g}   spread {f.spread:g} deg"

    def step_fx_preview(self, dt):
        """Keep the Effects section's live preview playing: restarted whenever the effect is changed,
        a burst repeating after it dies away and a stream running all the time."""
        f = self.selected_effect()
        if f is None:
            self.fx_sim = None
            return
        key = (self.effect_selected, astuple(f))
        if self.fx_sim is None or self.fx_sim[1] != key:
            self.fx_sim = [ParticleSystem([f], PreviewFloor()), key, 0.0]
        sim, _, wait = self.fx_sim
        if f.kind == "stream":
            sim.attach("preview", f.name, 0.0, 0.0, FX_BASE, UP, dt)
        else:
            wait -= dt
            if wait <= 0:
                sim.play(f.name, 0.0, 0.0, FX_BASE, UP)
                wait = max(f.interval, f.life * (1 + f.life_var) + 0.3)
            self.fx_sim[2] = wait
        sim.update(dt)

    def draw_fx_preview(self, screen, card):
        """The selected effect playing side on, over a floor: x across, height up. A cell is FX_CELL pixels."""
        pygame.draw.rect(screen, (30, 33, 44), card)
        floor_y = card.bottom - 26
        pygame.draw.rect(screen, (58, 54, 50), (card.x, floor_y, card.w, card.bottom - floor_y))
        center = card.centerx
        start_y = floor_y - FX_BASE * FX_CELL
        pygame.draw.circle(screen, ACCENT, (center, round(start_y)), 3)
        if self.fx_sim is not None:                                 # where the particles really start, and which way they head
            (ox, _oy, oz), (dx, dy, dz) = placement(self.fx_sim[0].effects[self.selected_effect().name], UP)
            origin = (round(center + ox * FX_CELL), round(start_y - oz * FX_CELL))
            norm = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
            tip = (origin[0] + round(dx / norm * FX_CELL * 0.7), origin[1] - round(dz / norm * FX_CELL * 0.7))
            pygame.draw.line(screen, ACCENT, origin, tip, 2)
            pygame.draw.circle(screen, (255, 255, 255), origin, 4, 1)
        for x in range(center % FX_CELL, card.w, FX_CELL):          # a one cell grid so sizes can be judged
            pygame.draw.line(screen, (44, 48, 60), (card.x + x, card.y), (card.x + x, floor_y))
        if self.fx_sim is not None:
            screen.set_clip(card)
            for (x, y, z, size, tile, _spin, alpha, _glow, *color) in self.fx_sim[0].sprites()[:FX_CAP]:
                pixels = max(2, round(size * FX_CELL))
                picture = self.fx_scaled.get((tile, pixels, *color))
                if picture is None:
                    picture = pygame.transform.scale(self.tiles[max(0, min(tile, len(self.tiles) - 1))], (pixels, pixels))
                    if color:
                        picture = recolored(picture, color[0])
                    if len(self.fx_scaled) > 600:
                        self.fx_scaled.clear()
                    self.fx_scaled[(tile, pixels, *color)] = picture
                picture.set_alpha(round(255 * alpha))
                screen.blit(picture, picture.get_rect(center=(round(center + x * FX_CELL),
                                                              round(floor_y - (z + size / 2) * FX_CELL))))
            screen.set_clip(None)
        pygame.draw.rect(screen, GRID, card.inflate(2, 2), 1)
        self.blit_fitted(screen, self.small, "side view (x across, up is up), one square = 1 cell; the line shows the "
                         "direction", DIM, (card.x + 8, card.bottom - 20), card.right - 8)

    def draw_effects(self, screen):
        """The Effects section: the map's particle effects as a list, and a live preview of the selected one."""
        area = self.map_area()
        screen.set_clip(area)
        pygame.draw.rect(screen, BG, area)
        self.set_scroll("effects", self.effects_scroll)
        top = area.y - self.effects_scroll
        screen.blit(self.font.render("Particle effects in this map", True, ACCENT), (area.x + 20, top + 14))
        self.blit_fitted(screen, self.small, "Design an effect here, then give it to a gun (muzzle), an ammo type (trail) "
                         "or an item.", DIM, (area.x + 20, top + 40), area.right - 14)
        rows, add = self.effect_rows()
        for rect, i in rows:
            f = self.level.effects[i]
            on = i == self.effect_selected
            pygame.draw.rect(screen, BUTTON_ON if on else (BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON),
                             rect, border_radius=4)
            screen.set_clip(rect.clip(area))
            screen.blit(self.tiles[max(0, min(f.tile, len(self.tiles) - 1))], (rect.x + 6, rect.y + (rect.h - TILE) // 2))
            self.blit_fitted(screen, self.font, f.name, TEXT, (rect.x + 48, rect.y + 5), rect.right - 8)
            self.blit_fitted(screen, self.small, self.effect_summary(f), TEXT if on else DIM, (rect.x + 48, rect.y + 24),
                             rect.right - 8)
            screen.set_clip(area)
        self._draw_add_button(screen, add, "+ Add effect")
        right = area.x + 20 + min(area.w - 40, 440) + 24
        f = self.selected_effect()
        if f is None:
            note = "No effects yet: add one." if not self.level.effects else "Select an effect to edit it."
            narrow = area.right - right <= 200
            screen.blit(self.small.render(note, True, DIM), (add.x if narrow else right,
                                                           add.bottom + 14 if narrow else top + 74))
        else:
            card, lines, width = self.section_card("effects")
            self.draw_fx_preview(screen, card)
            self._draw_wrapped(screen, lines, card.x, card.bottom + 12, width)
        self.draw_scrollbar(screen, "effects")
        screen.set_clip(None)

    # ---------------------------------------------------------------- the Lights section

    LIGHT_ROW_H = 46

    def light_rows(self):
        """(ambient row rect, [(rect, light index)], Add button rect) for the Lights section's list."""
        area = self.map_area()
        width = min(area.w - 40, 440)
        base = area.y + 74 - self.lights_scroll
        ambient = pygame.Rect(area.x + 20, base, width, self.LIGHT_ROW_H - 4)
        rows = [(pygame.Rect(area.x + 20, base + (i + 1) * self.LIGHT_ROW_H, width, self.LIGHT_ROW_H - 4), i)
                for i in range(len(self.level.lights))]
        top = base + (len(rows) + 1) * self.LIGHT_ROW_H
        return ambient, rows, pygame.Rect(area.x + 20, top, 170, 34)

    def lights_click(self, pos):
        ambient, rows, add = self.light_rows()
        if add.collidepoint(pos):
            self.add_light()
            return
        if ambient.collidepoint(pos):
            self.light_selected = AMBIENT_ROW
            self.field_edit = self.menu_open = None
            return
        for rect, i in rows:
            if rect.collidepoint(pos):
                self.light_selected = i
                self.tile_target = "wall_tile"
                self.field_edit = self.menu_open = None
                return

    def light_users(self, light):
        """Short names of what carries a light: guns (muzzle), ammo (bullet), effects (particles), items and wall tiles."""
        users = [f"{g.name} muzzle" for g in self.level.guns if g.flash == light.name]
        users += [f"{a.name} bullet" for a in self.level.ammo_types if a.light == light.name]
        users += [f"{a.name} hit" for a in self.level.ammo_types
                  if light.name in a.player_hit_lights + a.world_hit_lights + a.explosion_lights]
        users += [f"{f.name} particles" for f in self.level.effects if f.light == light.name]
        carried = sum(1 for e in self.level.entities if e.light == light.name)
        if carried:
            users.append(f"{carried} item{'s' if carried != 1 else ''}")
        if light.wall_tile >= 0:
            users.append(f"wall tile {light.wall_tile + 1}")
        return users

    def light_summary(self, light):
        shape = f"reach {light.radius:g}   brightness {light.intensity:g}"
        return shape + (f"   flicker {light.flicker:g}" if light.flicker > 0 else "")

    def draw_light_preview(self, screen, card, light):
        """The light seen from above on a floor of one cell squares, with a wall along its right side that the
        light cannot pass: how far it reaches, its color and how it flickers (the same falloff the game uses)."""
        pygame.draw.rect(screen, (22, 24, 30), card)
        w, h = card.size
        cx, cy = w // 2, h // 2
        xs = (np.arange(w) - cx) / LIGHT_CELL
        ys = (np.arange(h) - cy) / LIGHT_CELL
        d2 = xs[None, :] ** 2 + ys[:, None] ** 2
        r2 = light.radius ** 2
        falloff = np.clip(1.0 - d2 / r2, 0.0, 1.0) ** 2
        falloff[:, xs > 1.5] = 0.0                                  # the wall at 1.5 cells to the right stops it
        wobble = 1.0
        if light.flicker > 0:
            t = self.light_clock * light.flicker_speed * math.tau
            wobble = 1.0 - light.flicker * (1.0 - (0.5 + 0.25 * math.sin(t) + 0.25 * math.sin(t * 2.31)))
        gain = light.intensity * wobble * falloff
        color = np.array((light.r, light.g, light.b), np.float64) / 255.0
        floor = np.array((70, 66, 60), np.float64)
        lit = np.clip(floor[None, None, :] * (0.25 + gain[:, :, None] * color[None, None, :] * 1.6), 0, 255)
        picture = pygame.surfarray.make_surface(lit.astype(np.uint8).swapaxes(0, 1))
        screen.blit(picture, card)
        for gx in range(cx % LIGHT_CELL, w, LIGHT_CELL):            # a one cell grid so the reach can be judged
            pygame.draw.line(screen, (36, 38, 46), (card.x + gx, card.y), (card.x + gx, card.bottom))
        for gy in range(cy % LIGHT_CELL, h, LIGHT_CELL):
            pygame.draw.line(screen, (36, 38, 46), (card.x, card.y + gy), (card.right, card.y + gy))
        wall = pygame.Rect(card.x + cx + round(1.5 * LIGHT_CELL), card.y, card.w, card.h)
        pygame.draw.rect(screen, (120, 70, 60), wall.clip(card))
        pygame.draw.circle(screen, (255, 255, 255), (card.x + cx, card.y + cy), 4)
        pygame.draw.rect(screen, GRID, card.inflate(2, 2), 1)
        self.blit_fitted(screen, self.small, "from above, one grid square = 1 cell, wall on the right", DIM,
                         (card.x + 8, card.bottom - 20), card.right - 8)

    def draw_lights(self, screen):
        """The Lights section: the map's ambient light and lights as a list, and a preview of the selected light."""
        area = self.map_area()
        screen.set_clip(area)
        pygame.draw.rect(screen, BG, area)
        self.set_scroll("lights", self.lights_scroll)
        top = area.y - self.lights_scroll
        screen.blit(self.font.render("Lights in this map", True, ACCENT), (area.x + 20, top + 14))
        self.blit_fitted(screen, self.small, "Design a light here, then give it to a gun (muzzle), ammo (bullet), effect "
                         "(particles) or item;", DIM, (area.x + 20, top + 36), area.right - 14)
        self.blit_fitted(screen, self.small, "or make a wall tile glow. Lower the ambient light to make a map dark.", DIM,
                         (area.x + 20, top + 52), area.right - 14)
        ambient, rows, add = self.light_rows()
        on = self.light_selected == AMBIENT_ROW
        pygame.draw.rect(screen, BUTTON_ON if on else (BUTTON_HOT if ambient.collidepoint(self.mouse) else BUTTON),
                         ambient, border_radius=4)
        shade = round(255 * self.level.ambient)
        pygame.draw.rect(screen, (shade, shade, shade), (ambient.x + 6, ambient.y + 7, 32, 28), border_radius=3)
        screen.blit(self.font.render("Map ambient light", True, TEXT), (ambient.x + 48, ambient.y + 5))
        screen.blit(self.small.render(f"{self.level.ambient:g}   (1 is fully lit, as maps always were)", True,
                                      TEXT if on else DIM), (ambient.x + 48, ambient.y + 24))
        for rect, i in rows:
            light = self.level.lights[i]
            on = i == self.light_selected
            pygame.draw.rect(screen, BUTTON_ON if on else (BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON),
                             rect, border_radius=4)
            pygame.draw.rect(screen, (light.r, light.g, light.b), (rect.x + 6, rect.y + 7, 32, 28), border_radius=3)
            screen.set_clip(rect.clip(area))
            self.blit_fitted(screen, self.font, light.name, TEXT, (rect.x + 48, rect.y + 5), rect.right - 8)
            self.blit_fitted(screen, self.small, self.light_summary(light), TEXT if on else DIM,
                             (rect.x + 48, rect.y + 24), rect.right - 8)
            screen.set_clip(area)
        self._draw_add_button(screen, add, "+ Add light")
        right = area.x + 20 + min(area.w - 40, 440) + 24
        light = self.selected_light()
        if light is None:
            note = ("Select the ambient light or a light to edit it."
                    if self.level.lights or self.light_selected != AMBIENT_ROW else "")
            narrow = area.right - right <= 200
            screen.blit(self.small.render(note, True, DIM), (add.x if narrow else right,
                                                           add.bottom + 14 if narrow else top + 74))
        else:
            card, lines, width = self.section_card("lights")
            self.draw_light_preview(screen, card, light)
            self._draw_wrapped(screen, lines, card.x, card.bottom + 12, width)
        self.draw_scrollbar(screen, "lights")
        screen.set_clip(None)

    SETTINGS_ROW_H = 46                         # a row with a one-line summary (and the gap under it)
    SETTINGS_LIST_W = 500                       # the widest the rows get; a longer summary goes on more lines

    def settings_list_width(self):
        return min(self.map_area().w - 40, self.SETTINGS_LIST_W)

    def summary_lines(self, text, width):
        """A row's summary (parts split by three spaces) on as many lines `width` pixels wide as it takes,
        breaking between the parts where it can."""
        lines = []
        for part in text.split("   "):
            if lines and self.small.size(lines[-1] + "   " + part)[0] <= width:
                lines[-1] += "   " + part
            else:
                lines.extend(details.note_lines([part], self.small, width))
        return lines or [""]

    def settings_row_height(self, summary, width, icon=False):
        """How tall a Map settings row is for its summary to fit (the row's title above it)."""
        return self.SETTINGS_ROW_H - 4 + 17 * (len(self.summary_lines(summary, width - (58 if icon else 20))) - 1)

    def buy_entry_summary(self, i):
        """What a buy menu entry gives (and for which team), under its name in the list."""
        entry = self.level.settings.buy_items[i]
        what = BUY_KIND_LABELS[entry.kind] + ("" if entry.kind != "gun" or entry.gun in self.gun_names()
                                               else "  (no such gun: not sold)")
        if entry.team:
            what += "   " + self.buy_team_labels()[entry.team]
        return what

    def settings_rows(self):
        """(rules row rect, buy menu row rect, [(rect, entry index)], Add button rect) for the Map settings section.
        A row is as tall as its summary needs."""
        area = self.map_area()
        width = self.settings_list_width()
        x, top = area.x + 20, area.y + 74 - self.settings_scroll
        rules = pygame.Rect(x, top, width, self.settings_row_height(self.rules_summary(), width))
        _enemies, enemy_add = self.enemy_rows(rules)
        below = enemy_add.bottom + 16 if enemy_add is not None else rules.bottom + 4
        buy = pygame.Rect(x, below, width, self.settings_row_height(self.buy_summary(), width))
        y = buy.bottom + 4 + 30
        rows = []
        for i, entry in enumerate(self.level.settings.buy_items):
            icon = 0 <= entry_tile(entry, self.level.guns) < len(self.tiles)
            rows.append((pygame.Rect(x, y, width, self.settings_row_height(self.buy_entry_summary(i), width, icon)), i))
            y = rows[-1][0].bottom + 4
        add = pygame.Rect(x, y, 220, 34)
        return rules, buy, rows, add

    def enemy_rows(self, rules=None):
        """([(rect, enemy index)], Add button rect) of the enemy kinds listed under the game rules in the Map settings
        section, in zombies mode (([], None) in the others)."""
        if self.level.settings.mode != "zombies":
            return [], None
        if rules is None:
            rules = self.settings_rows()[0]
        width = self.settings_list_width()
        y = rules.bottom + 4 + 30
        rows = []
        for i, enemy in enumerate(self.level.enemies):
            rows.append((pygame.Rect(rules.x, y, width,
                                     self.settings_row_height(self.enemy_summary(enemy), width)), i))
            y = rows[-1][0].bottom + 4
        return rows, pygame.Rect(rules.x, y, 220, 34)

    # ---------------------------------------------------------------- the waves card (zombies' curves)

    def waves_card_rect(self):
        """The Waves card in the Map settings section (zombies mode): beside the list, above the buy menu preview, or
        under the list when there is no room. None in the other modes."""
        if self.level.settings.mode != "zombies":
            return None
        area = self.map_area()
        right = area.x + 20 + self.settings_list_width() + 24
        width = min(WAVES_CARD_W, area.right - right - 20)
        if width >= 300:
            return pygame.Rect(right, area.y + 74 - self.settings_scroll, width, WAVES_CARD_H)
        _rules, _buy, _rows, add = self.settings_rows()
        return pygame.Rect(add.x, add.bottom + 24, min(WAVES_CARD_W, max(260, area.w - 40)), WAVES_CARD_H)

    def curve_enemy(self):
        """The index of the kind of enemy whose weight the Enemy mix tab edits: the one selected, else the first
        (None when the map has none)."""
        enemy = self.selected_enemy()
        if enemy is not None:
            return self.level.enemies.index(enemy)
        return 0 if self.level.enemies else None

    def curve_points(self, name=None):
        """The points of a curve: one of the map's zombies curves, or ("weight") the edited enemy's weight; None if
        there is no such curve (no enemies)."""
        name = name or self.curve_shown
        if name == "weight":
            i = self.curve_enemy()
            return None if i is None else self.level.enemies[i].weight
        return getattr(self.level.settings, name)

    def curve_layout(self, card):
        """(tab rects {name: rect}, graph rect, legend rects [(rect, enemy index)]) of the Waves card."""
        tabs, x = {}, card.x + 12
        for name, label in CURVE_TABS:
            width = self.small.size(label)[0] + 14
            tabs[name] = pygame.Rect(x, card.y + 32, width, 22)
            x += width + 4
        graph = pygame.Rect(card.x + 46, card.y + 66, card.w - 60, card.h - 66 - 72)   # (rounds, legend, hint)
        legend, x = [], graph.x
        if self.curve_shown == "weight":
            for i, enemy in enumerate(self.level.enemies):
                width = self.small.size(enemy.name)[0] + 18
                if x + width > card.right - 8:
                    break
                legend.append((pygame.Rect(x, graph.bottom + 26, width, 18), i))
                x += width + 6
        return tabs, graph, legend

    def curve_scale(self, graph):
        """(last round, top value) the graph shows: past the last point of every curve drawn by a few rounds, and
        above the highest value they reach there. It holds still while a point is dragged (the point follows the
        mouse, even above the top), and fits again when it is let go."""
        if self.curve_drag is not None and self.curve_drag_scale is not None:
            return self.curve_drag_scale
        curves = ([e.weight for e in self.level.enemies] if self.curve_shown == "weight"
                  else [self.curve_points()])
        curves = [c for c in curves if c]
        last = max([CURVE_MIN_ROUNDS] + [c[-1][0] + 5 for c in curves])
        top = max([1.0] + [curve_at(c, x) for c in curves for x in [p[0] for p in c] + [last]])
        step = 10 ** math.floor(math.log10(top * 1.15))
        return last, math.ceil(top * 1.15 / step) * step

    def curve_to_screen(self, graph, scale, x, value):
        last, top = scale
        return (graph.x + (x - 1) / max(1, last - 1) * graph.w, graph.bottom - value / top * graph.h)

    def curve_from_screen(self, graph, scale, pos):
        """(round, value) under a point of the graph, the round a whole number, the value rounded to the curve's step
        and held in its limits."""
        last, top = scale
        x = round(1 + (pos[0] - graph.x) / max(1, graph.w) * (last - 1))
        value = (graph.bottom - pos[1]) / max(1, graph.h) * top
        return max(1, min(MAX_CURVE_X, x)), self.curve_value(value)

    def curve_value(self, value, name=None):
        name = name or self.curve_shown
        low, high = CURVE_LIMITS[name]
        step = CURVE_STEPS[name]
        return max(low, min(high, round(round(value / step) * step, 4)))

    def curve_press(self, pos, button):
        """A click in the Waves card: a tab, an enemy in the legend, or the graph (grab a point, add one, or remove
        one with the right button). True if the card took it."""
        card = self.waves_card_rect()
        if card is None or not card.collidepoint(pos):
            return False
        tabs, graph, legend = self.curve_layout(card)
        for name, rect in tabs.items():
            if rect.collidepoint(pos) and button == 1:
                self.curve_shown = name
                if name == "weight" and not self.level.enemies:
                    self.say("Add an enemy first: Enemy mix is how likely each kind is, round by round")
                return True
        for rect, i in legend:
            if rect.collidepoint(pos) and button == 1:
                self.settings_selected = ENEMY_ROW - i
                self.field_edit = self.menu_open = None
                return True
        points = self.curve_points()
        if points is None or not graph.inflate(12, 12).collidepoint(pos):
            return True
        scale = self.curve_scale(graph)
        near = [(math.dist(pos, self.curve_to_screen(graph, scale, *p)), i) for i, p in enumerate(points)]
        hit = min(near)[1] if near and min(near)[0] <= CURVE_HIT else None
        if button == 3:
            if hit is not None and len(points) > 1:
                self.begin_edit()
                del self.curve_points()[hit]
            return True
        if button != 1:
            return True
        self.begin_edit()
        points = self.curve_points()
        if hit is None:
            x, value = self.curve_from_screen(graph, scale, pos)
            same = next((i for i, p in enumerate(points) if p[0] == x), None)
            if same is not None:
                points[same][1] = value
                hit = same
            elif len(points) < MAX_CURVE_POINTS:
                points.append([x, value])
                points.sort(key=lambda p: p[0])
                hit = next(i for i, p in enumerate(points) if p[0] == x)
            else:
                self.say(f"A curve has at most {MAX_CURVE_POINTS} points")
                return True
        self.curve_drag_scale = scale
        self.curve_drag = hit
        return True

    def curve_move(self, pos):
        """Drag the grabbed point: its round stays between its neighbors'."""
        card = self.waves_card_rect()
        points = self.curve_points()
        if card is None or points is None or not 0 <= self.curve_drag < len(points):
            self.curve_drag = None
            return
        _tabs, graph, _legend = self.curve_layout(card)
        x, value = self.curve_from_screen(graph, self.curve_scale(graph), pos)
        i = self.curve_drag
        low = points[i - 1][0] + 1 if i > 0 else 1
        high = points[i + 1][0] - 1 if i + 1 < len(points) else MAX_CURVE_X
        points[i] = [max(low, min(high, x)), value]

    def set_curve_point(self, name, i, x=None, value=None):
        """Type a point's round or value in the Details pane (one undo step); the round stays between its
        neighbors'."""
        points = self.curve_points(name)
        if points is None or not 0 <= i < len(points):
            return
        new = list(points[i])
        if x is not None:
            low = points[i - 1][0] + 1 if i > 0 else 1
            high = points[i + 1][0] - 1 if i + 1 < len(points) else MAX_CURVE_X
            new[0] = max(low, min(high, int(round(x))))
        if value is not None:
            new[1] = self.curve_value(value, name)
        if new == points[i]:
            return
        self.begin_edit()
        self.curve_points(name)[i] = new

    def curve_point_fields(self, name):
        """The Details pane's rows for each point of a curve: its round and its value, typed exactly."""
        points = self.curve_points(name)
        if points is None:
            return []
        label = dict(CURVE_TABS)[name]
        low, high = CURVE_LIMITS[name]
        fields = [Field(f"curve_{name}", f"{label}: round -> value", "header", None, None)]
        for i in range(len(points)):
            fields += [Field(f"{name}{i}x", f"Point {i + 1}: round", "num",
                             (lambda i=i: self.curve_points(name)[i][0]),
                             (lambda v, i=i: self.set_curve_point(name, i, x=v)), step=1, low=1, high=MAX_CURVE_X),
                       Field(f"{name}{i}y", "   value", "num", (lambda i=i: self.curve_points(name)[i][1]),
                             (lambda v, i=i: self.set_curve_point(name, i, value=v)), step=CURVE_STEPS[name],
                             low=low, high=high)]
        return fields

    def draw_waves_card(self, screen, card):
        """The Waves card: tabs for each curve, the chosen one as a graph of round -> value (Enemy mix: every kind's
        weight in its color, the selected one's points to drag), and the value under the mouse."""
        pygame.draw.rect(screen, PANEL_BG, card, border_radius=6)
        pygame.draw.rect(screen, GRID, card, 1, border_radius=6)
        screen.blit(self.font.render("Waves", True, ACCENT), (card.x + 12, card.y + 8))
        tabs, graph, legend = self.curve_layout(card)
        for name, rect in tabs.items():
            on = name == self.curve_shown
            pygame.draw.rect(screen, BUTTON_ON if on else (BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON),
                             rect, border_radius=4)
            label = self.small.render(dict(CURVE_TABS)[name], True, TEXT)
            screen.blit(label, label.get_rect(center=rect.center))
        pygame.draw.rect(screen, BG, graph)
        points = self.curve_points()
        if points is None:
            self.blit_fitted(screen, self.small, "No enemies yet: add one under Enemies", DIM,
                             (graph.x + 8, graph.y + 8), graph.right - 8)
            return
        scale = self.curve_scale(graph)
        last, top = scale
        for k in range(5):                                  # value lines
            value = top * k / 4
            y = round(graph.bottom - graph.h * k / 4)
            pygame.draw.line(screen, GRID, (graph.x, y), (graph.right, y))
            text = self.small.render(f"{value:g}", True, DIM)
            screen.blit(text, (graph.x - 6 - text.get_width(), y - 7))
        step = max(1, round((last - 1) / 6))
        for x in range(1, last + 1, step):                  # round marks
            sx = round(self.curve_to_screen(graph, scale, x, 0)[0])
            pygame.draw.line(screen, GRID, (sx, graph.bottom), (sx, graph.bottom + 4))
            text = self.small.render(str(x), True, DIM)
            screen.blit(text, (sx - text.get_width() // 2, graph.bottom + 5))
        if self.curve_shown == "weight":
            edited = self.curve_enemy()
            drawn = [(i, e.weight, tuple(e.color)) for i, e in enumerate(self.level.enemies) if i != edited]
            drawn.append((edited, points, tuple(self.level.enemies[edited].color)))
        else:
            drawn = [(None, points, ACCENT)]
        clip = screen.get_clip()
        screen.set_clip(graph.inflate(2, 2).clip(clip) if clip else graph.inflate(2, 2))
        for owner, curve, color in drawn:
            mine = curve is points
            line = [self.curve_to_screen(graph, scale, x, curve_at(curve, x)) for x in range(1, last + 1)]
            pygame.draw.lines(screen, color, False, line, 3 if mine else 1)
        for i, (x, value) in enumerate(points):
            spot = self.curve_to_screen(graph, scale, x, value)
            pygame.draw.circle(screen, TEXT if i == self.curve_drag else ACCENT, spot, 6)
            pygame.draw.circle(screen, BG, spot, 6, 2)
        screen.set_clip(clip)
        for rect, i in legend:
            enemy = self.level.enemies[i]
            pygame.draw.rect(screen, tuple(enemy.color), (rect.x, rect.y + 4, 10, 10))
            screen.blit(self.small.render(enemy.name, True, TEXT if i == self.curve_enemy() else DIM),
                        (rect.x + 14, rect.y))
        hint = "Drag a point, click to add one, right-click removes; type exact values in the Details pane"
        if self.curve_shown == "weight":
            hint = "How likely each kind is (0: none); click a name to edit its curve"
        self.blit_fitted(screen, self.small, hint, DIM, (card.x + 12, card.bottom - 20), card.right - 10)
        if graph.collidepoint(self.mouse):
            x, _value = self.curve_from_screen(graph, scale, self.mouse)
            here = pygame.Rect(self.mouse[0] - 1, self.mouse[1] - 1, 3, 3)
            self.tips.append((here, f"Round {x}: {curve_at(points, x):g}"))

    def settings_card_rect(self):
        """The buy menu preview's card: beside the list, or below it when there is no room."""
        area = self.map_area()
        _rules, _buy, _rows, add = self.settings_rows()
        right = area.x + 20 + self.settings_list_width() + 24
        width = min(380, area.right - right - 20)
        card = pygame.Rect(right, area.y + 74 - self.settings_scroll, width, self.buy_preview_height())
        if width < 240:
            card = pygame.Rect(add.x, add.bottom + 24, min(380, max(200, area.w - 40)), self.buy_preview_height())
        waves = self.waves_card_rect()
        if waves is not None and (waves.x == card.x or waves.colliderect(card)):
            card.y = waves.bottom + 20                      # (under the Waves card)
        return card

    def settings_content_bottom(self):
        """The y of the bottom of everything in the Map settings section if it were not scrolled at all."""
        _rules, _buy, _rows, add = self.settings_rows()
        return max(add.bottom, self.settings_card_rect().bottom) + self.settings_scroll + 20

    def clamp_settings_scroll(self):
        self.set_scroll("settings", self.settings_scroll)

    def settings_click(self, pos):
        rules, buy, rows, add = self.settings_rows()
        if add.collidepoint(pos):
            self.add_buy_item()
            return
        enemies, enemy_add = self.enemy_rows(rules)
        if enemy_add is not None and enemy_add.collidepoint(pos):
            self.add_enemy()
            return
        for rect, choice in [(rules, RULES_ROW), (buy, BUY_ROW)] + rows + [(r, ENEMY_ROW - i) for r, i in enemies]:
            if rect.collidepoint(pos):
                self.settings_selected = choice
                self.tile_target = "tile"
                self.field_edit = self.menu_open = None
                return

    def rules_summary(self):
        rules = self.level.settings
        text = GAME_MODE_LABELS[rules.mode] + (", friendly fire" if rules.mode != "ffa" and rules.friendly_fire else "")
        text += f"   health {rules.max_health:g}"
        if rules.start_money or rules.kill_money:
            text += f"   start ${rules.start_money:g}"
        if rules.kill_score or rules.kill_money:
            text += f"   kill +{rules.kill_score:g} score +${rules.kill_money:g}"
        text += f"   starts with {rules.start_gun}" if rules.start_gun else ""
        if rules.mode == "bomb":
            text += (f"   round {rules.round_time:g}s, bomb {rules.bomb_time:g}s, {rules.max_rounds:g} rounds")
        if rules.mode == "koth":
            text += (f"   hold {rules.hill_time:g}s, capture {rules.capture_time:g}s (+{rules.capture_bonus:g}s),"
                     f" {rules.win_limit:g} rounds to win")
        if rules.mode == "zombies":
            text += (f"   enemies: {curve_text(rules.zombie_count)}, {rules.intermission:g}s between rounds")
        if rules.mode in ("ffa", "teams", "coop") and rules.respawn_delay > 0:
            text += f"   respawn {rules.respawn_delay:g}s"
        if rules.has_waiting():
            who = "everyone" if rules.mode == "ffa" else DEATH_CAM_WHO_LABELS[rules.death_cam_who].lower()
            text += f"   death cam: {who}" if rules.death_cam else "   no death cam"
        return text

    def buy_summary(self):
        rules = self.level.settings
        if not rules.buy_menu:
            return "Off" + (f" ({len(rules.buy_items)} entries kept)" if rules.buy_items else "")
        count = len(rules.buy_items)
        return f"On   costs {BUY_COST_LABELS[rules.buy_cost].lower()}   {count} entr{'y' if count == 1 else 'ies'}"

    def draw_settings_row(self, screen, rect, title, summary, on, icon=-1):
        """A Map settings row: its title, and its summary on as many lines as the row was made tall for."""
        pygame.draw.rect(screen, BUTTON_ON if on else (BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON),
                         rect, border_radius=4)
        x = rect.x + 10
        if 0 <= icon < len(self.tiles):
            screen.blit(pygame.transform.scale(self.tiles[icon], (32, 32)), (rect.x + 6, rect.y + 5))
            x = rect.x + 48
        clip = screen.get_clip()
        screen.set_clip(rect.clip(clip))
        self.blit_fitted(screen, self.font, title, TEXT, (x, rect.y + 5), rect.right - 8)
        for i, line in enumerate(self.summary_lines(summary, rect.right - 10 - x)):
            self.blit_fitted(screen, self.small, line, TEXT if on else DIM, (x, rect.y + 24 + 17 * i), rect.right - 8)
        screen.set_clip(clip)

    def draw_settings(self, screen):
        """The Map settings section: the game rules, the buy menu and its entries as a list, and the buy menu as a
        player who just joined sees it."""
        area = self.map_area()
        screen.set_clip(area)
        pygame.draw.rect(screen, BG, area)
        self.clamp_settings_scroll()
        rules = self.level.settings
        top = area.y - self.settings_scroll
        screen.blit(self.font.render("Map settings", True, ACCENT), (area.x + 20, top + 14))
        self.blit_fitted(screen, self.small, "How this map is played: its game mode and rules, and the buy menu players "
                         "open", DIM, (area.x + 20, top + 36), area.right - 14)
        self.blit_fitted(screen, self.small, "with B. Select a row to change it in the Details pane.", DIM,
                         (area.x + 20, top + 52), area.right - 14)
        rules_rect, buy_rect, rows, add = self.settings_rows()
        self.draw_settings_row(screen, rules_rect, "Game rules", self.rules_summary(), self.settings_selected == RULES_ROW)
        enemies, enemy_add = self.enemy_rows(rules_rect)
        if enemy_add is not None:
            screen.blit(self.font.render("Enemies", True, ACCENT), (rules_rect.x, rules_rect.bottom + 12))
            for rect, i in enemies:
                enemy = self.level.enemies[i]
                self.draw_settings_row(screen, rect, enemy.name, self.enemy_summary(enemy),
                                       self.settings_selected == ENEMY_ROW - i)
            self._draw_add_button(screen, enemy_add, "+ Add enemy")
        self.draw_settings_row(screen, buy_rect, "Buy menu", self.buy_summary(), self.settings_selected == BUY_ROW)
        screen.blit(self.font.render("In the buy menu", True, ACCENT if rules.buy_menu else DIM),
                    (buy_rect.x, buy_rect.bottom + 12))
        for rect, i in rows:
            entry = rules.buy_items[i]
            self.draw_settings_row(screen, rect, f"{entry.label()}   {price_text(rules.buy_cost, entry.price)}",
                                   self.buy_entry_summary(i), i == self.settings_selected,
                                   entry_tile(entry, self.level.guns))
        self._draw_add_button(screen, add, "+ Add to buy menu")
        waves = self.waves_card_rect()
        if waves is not None:
            self.draw_waves_card(screen, waves)
        self.draw_buy_preview(screen, self.settings_card_rect())
        self.draw_scrollbar(screen, "settings")
        screen.set_clip(None)

    def buy_preview_height(self):
        rules = self.level.settings
        shown = min(10, len(rules.buy_items))
        return 72 + max(1, shown) * 36 + (18 if len(rules.buy_items) > shown else 0)

    def draw_buy_preview(self, screen, card):
        """The buy menu as a player who has just joined sees it in the game: entries they cannot afford with the
        start money (or no score) are greyed out."""
        rules = self.level.settings
        entries = rules.buy_items[:10]

        pygame.draw.rect(screen, (32, 34, 42), card, border_radius=8)
        pygame.draw.rect(screen, (90, 94, 110), card, 1, border_radius=8)
        title = self.font.render("Buy menu" + ("" if rules.buy_menu else "  (off)"), True, ACCENT)
        screen.blit(title, title.get_rect(midtop=(card.centerx, card.y + 10)))
        have = {"free": None, "money": rules.start_money, "score": 0.0}[rules.buy_cost]
        wallet = ("Everything here is free" if have is None else
                  f"A new player has ${have:g}" if rules.buy_cost == "money" else "A new player has 0 score")
        line = self.small.render(wallet, True, DIM)
        screen.blit(line, line.get_rect(midtop=(card.centerx, card.y + 34)))
        y = card.y + 58
        if not entries:
            line = self.small.render("Nothing for sale yet", True, DIM)
            screen.blit(line, line.get_rect(midtop=(card.centerx, y + 8)))
        for entry in entries:
            button = pygame.Rect(card.x + 14, y, card.w - 28, 30)
            can = have is None or entry.price <= 0 or have >= entry.price
            pygame.draw.rect(screen, BUTTON if can else (46, 48, 56), button, border_radius=5)
            tile = entry_tile(entry, self.level.guns)
            if 0 <= tile < len(self.tiles):
                picture = pygame.transform.scale(self.tiles[tile], (24, 24))
                if not can:
                    picture.set_alpha(110)
                screen.blit(picture, (button.x + 4, button.y + 3))
            text = self.font.render(f"{entry.label()}   {price_text(rules.buy_cost, entry.price)}", True,
                                    TEXT if can else DIM)
            screen.blit(text, text.get_rect(center=button.center))
            y += 36
        if len(rules.buy_items) > len(entries):
            more = self.small.render(f"... and {len(rules.buy_items) - len(entries)} more (the wheel scrolls in the game)",
                                     True, DIM)
            screen.blit(more, more.get_rect(midtop=(card.centerx, y)))

    def details_text(self):
        """(title, notes under the rows) of the Details pane for what is selected."""
        e, gun, ammo = self.selected_entity(), self.selected_gun(), self.selected_ammo()
        prefab, effect = self.selected_prefab(), self.selected_effect()
        light, ambient = self.selected_light(), self.ambient_chosen()
        entry, rules_row = self.selected_buy_item(), self.settings_row()
        if rules_row == RULES_ROW:
            notes = ("Two teams: players are split as they", "join; a teammate's name shows white.",
                     "Co-op: everyone is on one team.", "Friendly fire off: teammates' bullets",
                     "and blasts do not hurt (your own do).", "Knocking out an opponent earns the",
                     "Score / Money per kill. Score and money", "stay when a player is knocked out.")
        elif self.selected_barricade() is not None:
            notes = ("Zombies: players can never walk", "through a barricade; enemies tear its",
                     "boards off, then climb through.", "Players hold E beside it to put boards",
                     "back, earning the reward up to the", "most per round. Damage stages: one",
                     "tile each, whole first; transparent", "pixels show as gaps. Click a stage,",
                     "then an atlas tile. Enemies only get", "through once every board is gone.")
        elif self.selected_enemy() is not None:
            notes = ("Enemies come in at spawn points of the", "Enemies team (Spawn tool: Team).",
                     "Sticky: keeps chasing one player until", "another is nearer by the margin for",
                     "that long. Reach is from its body's edge.", "A player who gets out of reach during",
                     "the wind-up is missed. Health grows", "with the rounds (Game rules).")
        elif rules_row == BUY_ROW:
            notes = ("Players open the buy menu with B.", "Free: every entry is free. Money or",
                     "Score: an entry is only given to a", "player who has its price, which is",
                     "taken off. Money comes from Start", "money and Money / kill (Game rules).")
        elif entry is not None:
            cost = self.level.settings.buy_cost
            notes = (("The menu is free: the price is not used." if cost == "free"
                      else f"Costs {price_text(cost, entry.price)} ({BUY_COST_LABELS[cost].lower()})."),
                     "Button text blank: named after", "what it gives.", "Icon none: a gun shows its own picture.",
                     "Click an atlas tile to set the icon.")
        elif ambient:
            notes = ("How bright the map is without any", "light: 1 is fully lit, as maps were",
                     "before lights; lower is darker, so", "lights show. Walls, items and the",
                     "player are all dimmed by it.")
        elif light is not None:
            notes = ("Lights stop at walls. Flash length is how", "long a muzzle flash takes to fade.",
                     "Click a wall tile in the atlas to make", "every wall of it glow with this light.",
                     "Give it to a gun (Muzzle light), ammo", "(Bullet light), an effect (Particle", "light) or an item (Light).")
        elif effect is not None:
            notes = ("Plays on every player's own screen:", "it never changes the game.",
                     "Click an atlas tile to set the particle.", "Give it to a gun (Muzzle effect), an ammo",
                     "type (Trail effect) or an item (Emits).")
        elif prefab is not None:
            used = sum(1 for i in self.level.entities if i.prefab == prefab.name)
            notes = (f"Placed {used} time{'s' if used != 1 else ''} in this map.",
                     "Changes here update every one of them.", "Click an atlas tile to set the icon.",
                     "Place it with the Entity tool (N).")
        elif e is None and gun is None and ammo is None:
            notes = ("Click a cell to place the chosen one.", "Click a placed item to edit it.",
                     "Make prefabs in the Prefabs section (P),", "or save an item as one from its pane.")
        elif e is not None and e.prefab:
            notes = (f"A {e.prefab}: its settings come from", "the prefab, so they are shown, not editable.",
                     "Edit the prefab to change every copy,", "or detach this one to change only it.")
        elif gun is not None:
            how = {"single": "one round, reloads after every shot", "semi": "one round per trigger pull",
                   "auto": "keeps firing while the trigger is held"}[gun.mode]
            gap = 1.0 / gun.fire_rate
            notes = (f"{GUN_MODE_LABELS[gun.mode]}: {how}.",
                     f"At {gun.fire_rate:g} shots a second, one shot every {gap:.2g} s.",
                     {"single": "One bullet a shot.", "multi": f"{gun.pellets} bullets a shot, each with its own spread.",
                      "projectile": "Projectile: fires as one bullet for now."}[gun.shot],
                     "Click a Sprite row, then an atlas tile,",
                     "to set that picture.", "Hand the gun out with an item whose", "effect is Give a gun.")
        elif ammo is not None:
            users = [g.name for g in self.level.guns if g.ammo == ammo.name]
            notes = ("Guns that use this share one pool", "of spare rounds.",
                     "Used by: " + (", ".join(users) if users else "no gun yet"),
                     "Click the Bullet sprite row, then an", "atlas tile, to set the picture.",
                     "Give rounds with an item whose effect", "is Give ammo.")
        else:
            notes = (f"Cell ({math.floor(e.x)}, {math.floor(e.y)}) on {self.level.names[e.span]}",
                     "Wheel over a value steps it.", "Click a number to type one.",
                     "Click an atlas tile: sets the sprite.", "Esc closes this; Del removes the item.")
        if self.selected_enemy() is not None:
            return "Enemy", notes
        if self.selected_barricade() is not None:
            return "Barricade", notes
        if self.barricade_palette_active():
            return "Barricade to place", ("Click an open ground floor cell (a gap", "in a wall) to board it up with what is",
                                          "picked here. Select a barricade and", "Save as a type to place more like it;",
                                          "Import brings types in from other", "maps. Right-click removes one.")
        title = ("Game rules" if rules_row == RULES_ROW else "Buy menu" if rules_row == BUY_ROW
                 else "Buy menu entry" if entry is not None else "Ambient light" if ambient else "Light" if light is not None else "Effect" if effect is not None else "Gun" if gun is not None else "Ammo type" if ammo is not None
                 else "Prefab" if prefab is not None else "Prefab to place" if e is None else "Item")
        return title, notes

    def draw_details(self, screen):
        """The docked Details pane (only while something is selected)."""
        rect = self.details_rect()
        if rect is None:
            return
        theme = {"panel": PANEL_BG, "grid": GRID, "text": TEXT, "dim": DIM, "accent": ACCENT, "button": BUTTON,
                 "button_hot": BUTTON_HOT, "field": (28, 29, 34), "field_edit": (50, 52, 64),
                 "danger": (120, 50, 55), "danger_hot": (160, 64, 70), "button_on": BUTTON_ON}
        rows = self.details_rows()                      # (another thing selected starts at the top)
        self.set_scroll("details", self.details_scroll)
        if rows and rows[0].rect.y != details.view_rect(rect).y - self.details_scroll:
            rows = self.details_rows()                  # (the scroll was pulled back within the rows)
        title, notes = self.details_text()
        self.tips += details.draw(screen, rect, title, rows, theme, (self.font, self.small),
                                  focus=self.tile_target, button_label=self.details_delete_label(),
                                  editing=self.field_edit, hover=self.mouse, open_menu=self.menu_open,
                                  tile_surface=lambda i: self.tiles[max(0, min(i, len(self.tiles) - 1))],
                                  notes=notes, scroll=self.details_scroll,
                                  scroll_hot=self.scroll_drag is not None and self.scroll_drag[0] == "details")

    def draw_entities(self, screen):
        """Items on the floor being edited: their sprite on the map, ringed in the color of their mode
        (white once, cyan respawning, green staying)."""
        z = self.zoom
        origin = self.cell_rect(0, 0)
        size = max(8, int(z * 0.7))
        chosen = self.selected_entity()
        for e in self.level.entities:
            if e.span != self.floor:
                continue
            cx, cy = round(origin.x + e.x * z), round(origin.y + e.y * z)
            if e.wall:                                   # hung on a wall: a bar on the wall, the icon in front of it
                dx, dy = SIDE_VECTORS[e.wall]
                half = int(z * 0.3)
                pygame.draw.line(screen, ENTITY_MODE_COLORS[e.mode], (cx - abs(dy) * half, cy - abs(dx) * half),
                                 (cx + abs(dy) * half, cy + abs(dx) * half), max(2, z // 10))
                cx, cy = cx - round(dx * size * 0.6), cy - round(dy * size * 0.6)
            sprite = pygame.transform.scale(self.tiles[max(0, min(e.tile, len(self.tiles) - 1))], (size, size))
            pygame.draw.circle(screen, (20, 20, 30), (cx, cy), size // 2 + 2)
            screen.blit(sprite, sprite.get_rect(center=(cx, cy)))
            pygame.draw.circle(screen, ENTITY_MODE_COLORS[e.mode], (cx, cy), size // 2 + 2, 2)
            if e is chosen:                              # the selected item gets a bright outer ring
                pygame.draw.circle(screen, ACCENT, (cx, cy), size // 2 + 6, 3)
            if e.elevation and z >= 24:                  # raised or lowered: by how much
                label = self.small.render(f"{e.elevation:+g}", True, ACCENT)
                screen.blit(label, (cx + size // 2 + 2, cy - size // 2 - label.get_height() // 2))

    def draw_barricades(self, screen):
        """Barricades (ground floor only): a brown cell crossed by planks, with its number of boards."""
        if self.floor != 0:
            return
        z = self.zoom
        leaders = {g[0] for g in self.level.barricade_groups()}       # (one count of boards per group)
        for i, b in enumerate(self.level.barricades):
            rect = self.cell_rect(b.x, b.y)
            inset = rect.inflate(-max(2, z // 8), -max(2, z // 8))
            pygame.draw.rect(screen, BARRICADE_FILL, inset)
            for k in (1, 2, 3):
                y = inset.y + inset.h * k // 4
                pygame.draw.line(screen, BARRICADE_PLANK, (inset.x, y), (inset.right - 1, y), max(1, z // 10))
            if i == self.barricade_selected and self.tool == "barricade":
                pygame.draw.rect(screen, ACCENT, rect, 2)
            if z >= 16 and i in leaders:
                label = self.small.render(str(b.boards), True, (255, 255, 255))
                screen.blit(label, label.get_rect(center=rect.center))

    def draw_spawners(self, screen):
        """Spawn points: a blue disc with a facing line and its order, or a hollow ring on another floor."""
        z = self.zoom
        origin = self.cell_rect(0, 0)
        radius = max(4, z * 0.3)
        for s in self.level.spawners:
            cx, cy = origin.x + s.x * z, origin.y + s.y * z
            if s.span != self.floor:
                pygame.draw.circle(screen, SPAWN_TEAM_FILLS.get(s.team, SPAWN_FILL), (cx, cy), radius, 2)
                continue
            tip = (cx + math.cos(s.angle) * z * 0.45, cy + math.sin(s.angle) * z * 0.45)
            pygame.draw.circle(screen, SPAWN_TEAM_FILLS.get(s.team, SPAWN_FILL), (cx, cy), radius)
            pygame.draw.circle(screen, SPAWN_EDGE, (cx, cy), radius, 2)
            pygame.draw.line(screen, (255, 255, 255), (cx, cy), tip, max(2, z // 12))
            if z >= 16:
                label = self.small.render(str(s.order), True, SPAWN_EDGE)
                screen.blit(label, label.get_rect(center=(cx, cy)))

    def draw_start(self, screen):
        z, level = self.zoom, self.level
        origin = self.cell_rect(0, 0)
        cx, cy = origin.x + level.start_x * z, origin.y + level.start_y * z
        draw_start_icon(screen, cx, cy, max(3, z * 0.25), level.start_angle, z * 0.45, max(2, z // 10),
                        filled=level.start_span == self.floor)

    def camera_visible(self):
        return self.show_preview and self.preview is not None and self.preview.ready

    def draw_camera(self, screen):
        """The 3D view's camera on the map: a dot with a wedge showing the field of view. Solid on
        the floor being edited, an outline when the camera is on another floor."""
        if not self.camera_visible():
            return
        p = self.preview.player
        origin = self.cell_rect(0, 0)
        draw_camera_icon(screen, origin.x + p.x * self.zoom, origin.y + p.y * self.zoom, p.angle,
                         max(10, self.zoom * 0.9), filled=p.span == self.floor)

    def draw_preview(self, screen):
        """The live 3D view in the column at the right, drawn by the game's own renderer."""
        column = self.preview_column()
        if column is None or self.preview is None:
            return
        pygame.draw.rect(screen, PANEL_BG, column)
        screen.blit(self.font.render("3D view (live)", True, ACCENT), (column.x + 8, column.y + 4))
        rect = self.preview_rect()
        if self.preview.ready:
            picture = pygame.transform.scale(self.preview.render(), rect.size)
            screen.blit(picture, rect)
        hot = self.look_drag or (self.over_preview() and rect.collidepoint(self.mouse))
        pygame.draw.rect(screen, ACCENT if hot else GRID, rect.inflate(2, 2), 1)
        hints = ("Drag: look around", "Wheel / W S: forward, back", "A D: strafe   arrows: turn",
                 "Shift: sprint   Space: jump", "Camera tool (C): click map to place,", "  drag to aim",
                 "V hides this view")
        for i, line in enumerate(hints):
            if rect.bottom + 10 + (i + 1) * 17 > column.bottom:
                break
            screen.blit(self.small.render(line, True, DIM), (column.x + 10, rect.bottom + 10 + i * 17))

    # ---------------------------------------------------------------- the key (legend)

    def legend_entries(self):
        """[(icon, text)] explaining the marks that can be on the map in the current view, so the
        key never lists something that cannot be seen: the dot only where a floor exists above,
        the start as a solid or a hollow marker as drawn, the red outline only while there are
        problem cells, and the arrow and height colors only on the layers that draw them."""
        entries = []
        if self.camera_visible():
            entries.append(("camera", "3D view camera (wedge = view)"))
        if self.floor < self.level.floor_count - 1:                 # there is a floor above this one
            entries.append(("upper", "Room on a floor above"))
        if self.level.start_span == self.floor:
            entries.append(("start", "Player start (line = facing)"))
        else:
            entries.append(("start_other", "Start is on another floor"))
        if self.floor >= 1:
            entries.append(("below", "No room: floor below, faded"))
        if self.problem_cells():
            entries.append(("problem", "Problem cell (see status bar)"))
        if self.layer not in ("walls", "wall_h"):
            entries.append(("wall_dim", "Wall, dimmed (edit on Walls)"))
        if self.layer != "wall_h" and self.has_short_walls():
            entries.append(("short_wall", "Short wall (heights: WallH)"))
        if self.layer != "wall_h" and self.see_through_wall_tile() is not None:
            entries.append(("see_through", "See-through wall (alpha tile)"))
        if self.layer == "ceil_h" and self.floor == 0 and self.has_wall_ceiling_marks():
            entries.append(("wall_ceiling", "Over a wall: n set, (n) auto"))
        if self.layer == "wall_h":
            entries.append(("wall_full", "Full-height wall"))
        if self.layer == "ramp":
            entries.append(("ramp", "Ramp: rises toward arrow"))
        if self.layer == "site":
            entries.append(("site_a", "Bomb site A (plant here)"))
            entries.append(("site_b", "Bomb site B (plant here)"))
            entries.append(("site_hill", "Hill: King of the Hill point"))
            entries.append(("site_bar1", "Barrier: only team 1 passes"))
            entries.append(("site_bar2", "Barrier: only team 2 passes"))
        if self.layer in VALUE_LAYERS or self.layer in ("ramp", "site"):
            entries.append(("heat", "Height: blue low, yellow high"))
        return entries

    def has_wall_ceiling_marks(self):
        """True if any wall shows a ceiling number on the CeilH layer (cached until the next edit)."""
        if self._ceiling_cache[0] != self.revision:
            level = self.level
            found = any(self.wall_ceiling_matters(x, y)
                        for y in range(level.height) for x in range(level.width) if level.walls[y][x])
            self._ceiling_cache = (self.revision, found)
        return self._ceiling_cache[1]

    def see_through_wall_tile(self):
        """Map id of a see-through (alpha) tile that some wall uses, or None (cached until an edit)."""
        if self._trans_cache[0] != self.revision:
            found = next((v for row in self.level.walls for v in row if v and self.is_transparent_tile(v)), None)
            self._trans_cache = (self.revision, found)
        return self._trans_cache[1]

    def has_short_walls(self):
        """True if any wall is shorter than its room (cached until the next edit)."""
        if self._short_cache[0] != self.revision:
            level = self.level
            found = any(level.short_wall_top(x, y) is not None
                        for y in range(level.height) for x in range(level.width) if level.walls[y][x])
            self._short_cache = (self.revision, found)
        return self._short_cache[1]

    def legend_layout(self):
        """(rect, columns, docked) for the key. It goes in the free band of the left panel (two
        columns) whenever it fits there, so it never covers the map; in a window too short for
        that it floats over the map's bottom-right corner (one column) instead."""
        entries = self.legend_entries()
        _y, _cell, after, hints_y = self.panel_metrics()
        dock_rows = (len(entries) + 1) // 2
        dock_h = LEGEND_TITLE + dock_rows * LEGEND_ROW + 6
        if hints_y - after - 12 >= dock_h:
            return pygame.Rect(ATLAS_X, after + 6, PANEL_W - 2 * ATLAS_X, dock_h), 2, True
        text_w = max(self.font.size(text)[0] for _icon, text in entries)
        width = 12 + LEGEND_ICON + 10 + text_w + 14
        height = LEGEND_TITLE + len(entries) * LEGEND_ROW + 6
        area = self.map_area()
        return pygame.Rect(area.right - width - 10, area.bottom - height - 10, width, height), 1, False

    def legend_rect(self):
        return self.legend_layout()[0]

    def legend_tile(self, index, dim):
        """A small copy of an atlas tile for the key."""
        key = ("legend", index, dim)
        if key not in self._scaled:
            tile = pygame.transform.scale(self.tiles[max(0, min(index, len(self.tiles) - 1))],
                                          (LEGEND_ICON, LEGEND_ICON))
            if dim:
                tile.fill((90, 90, 96), special_flags=pygame.BLEND_MULT)
            self._scaled[key] = tile
        return self._scaled[key]

    def draw_legend_icon(self, screen, kind, box):
        """Draw one key icon inside box, using the same drawing code as the map."""
        if kind == "below":
            screen.blit(self.legend_tile(DEFAULTS["floor_tex"] - 1, True), box)
            return
        if kind in ("wall_dim", "short_wall"):
            wall = next((v for row in self.level.walls for v in row if v), 1)
            screen.blit(self.legend_tile(wall - 1, True), box)
            if kind == "short_wall":
                draw_short_wall_mark(screen, box)
            return
        if kind == "wall_full":
            pygame.draw.rect(screen, WALL_FULL, box)
            return
        if kind == "heat":
            lo, hi = HEIGHT_RANGE["wall_h" if self.layer == "wall_h" else "floor_h"]
            for i in range(box.w):
                pygame.draw.line(screen, heat(lo + (hi - lo) * i / (box.w - 1), lo, hi),
                                 (box.x + i, box.y), (box.x + i, box.bottom - 1))
            return
        pygame.draw.rect(screen, EMPTY_CELL, box)
        if kind == "upper":
            draw_upper_mark(screen, box)
        elif kind == "start":
            draw_start_icon(screen, box.centerx, box.centery, 7, 0.0, 12, 2, filled=True)
        elif kind == "camera":
            draw_camera_icon(screen, box.centerx - 3, box.centery, 0.0, 22, filled=True)
        elif kind == "start_other":
            draw_start_icon(screen, box.centerx, box.centery, 7, 0.0, 12, 2, filled=False)
        elif kind == "problem":
            draw_problem_outline(screen, box)
        elif kind == "see_through":
            screen.blit(self.legend_tile(self.see_through_wall_tile() - 1, False), box)
        elif kind == "wall_ceiling":
            color = heat(3.0, *HEIGHT_RANGE["ceil_h"])
            pygame.draw.rect(screen, tuple(c * 2 // 3 for c in color), box)
            text = self.small.render("(n)", True, (10, 10, 20))
            screen.blit(text, text.get_rect(center=box.center))
        elif kind == "ramp":
            pygame.draw.rect(screen, tuple(c // 2 for c in heat(1.0, *HEIGHT_RANGE["floor_h"])), box)
            self.draw_arrow(screen, box, 1, ACCENT)
        elif kind in ("site_a", "site_b", "site_hill", "site_bar1", "site_bar2"):
            site = {"site_a": 1, "site_b": 2, "site_hill": HILL_SITE, "site_bar1": 4, "site_bar2": 5}[kind]
            pygame.draw.rect(screen, SITE_COLORS[site], box)
            text = self.small.render(SITE_MARKS[site], True, (10, 10, 20))
            screen.blit(text, text.get_rect(center=box.center))

    def draw_legend(self, screen):
        """The key to the marks on the map (K or the Key button shows and hides it). Docked in
        the left panel when there is room, otherwise floating over the map's corner."""
        if not self.show_legend:
            return
        rect, columns, docked = self.legend_layout()
        font = self.small if docked else self.font
        if not docked:
            screen.set_clip(self.map_area())
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((24, 25, 30, 255 if docked else 235))
        screen.blit(panel, rect)
        pygame.draw.rect(screen, GRID, rect, 1)
        screen.blit(self.font.render("Key", True, ACCENT), (rect.x + 10, rect.y + 5))
        hide = self.small.render("K hides", True, DIM)
        screen.blit(hide, (rect.right - hide.get_width() - 10, rect.y + 8))
        entries = self.legend_entries()
        per_column = (len(entries) + columns - 1) // columns
        column_w = rect.w // columns
        for i, (kind, text) in enumerate(entries):
            column, row = divmod(i, per_column)
            x = rect.x + 10 + column * column_w
            y = rect.y + LEGEND_TITLE + row * LEGEND_ROW
            box = pygame.Rect(x, y + (LEGEND_ROW - LEGEND_ICON) // 2, LEGEND_ICON, LEGEND_ICON)
            self.draw_legend_icon(screen, kind, box)
            label = font.render(text, True, TEXT)
            screen.blit(label, (box.right + 8, y + (LEGEND_ROW - label.get_height()) // 2))
        if not docked:
            screen.set_clip(None)

    def area_screen_rect(self, x0, y0, x1, y1):
        return self.cell_rect(x0, y0).union(self.cell_rect(x1, y1))

    def draw_selection(self, screen, area):
        """Select tool: the rectangle being dragged or selected, and while pasting the copy under the mouse."""
        if self.area_drag:
            pygame.draw.rect(screen, ACCENT, self.area_screen_rect(*area_rect(self.level, *self.area_drag)), 2)
        elif self.area is not None:
            box = self.area_screen_rect(*self.area)
            pygame.draw.rect(screen, (20, 20, 26), box.inflate(2, 2), 1)
            pygame.draw.rect(screen, ACCENT, box, 2)
        if self.pasting and self.clip is not None and area.collidepoint(self.mouse):
            x, y = self.paste_corner(self.cell_at(self.mouse))
            clip = self.clip
            for dy in range(clip.height):
                for dx in range(clip.width):
                    wall = clip.walls.get((dx, dy))
                    tile = wall["walls"] if wall else clip.span["floor_tex"][dy][dx]
                    ghost = self.tile_surface(tile - 1).copy()
                    ghost.set_alpha(150 if wall else 90)
                    screen.blit(ghost, self.cell_rect(x + dx, y + dy))
            origin, z = self.cell_rect(0, 0), self.zoom
            size = max(8, int(z * 0.6))
            for e in clip.entities:                             # the items and spawn points that come with it
                icon = pygame.transform.scale(self.tiles[max(0, min(e.tile, len(self.tiles) - 1))], (size, size))
                icon.set_alpha(170)
                screen.blit(icon, icon.get_rect(center=(origin.x + (e.x + x) * z, origin.y + (e.y + y) * z)))
            for sp in clip.spawners:
                pygame.draw.circle(screen, SPAWN_FILL, (origin.x + (sp.x + x) * z, origin.y + (sp.y + y) * z),
                                   max(4, z * 0.3), 2)
            pygame.draw.rect(screen, ACCENT, self.area_screen_rect(x, y, x + clip.width - 1, y + clip.height - 1), 2)

    def draw_cursor(self, screen, area):
        if self.tool == "select":
            self.draw_selection(screen, area)
            if self.area_drag or self.pasting:
                return
        if self.shape_drag:
            erasing = self.shape_drag[2]
            tiles = not erasing and self.layer in STAMP_LAYERS and self.stamp()
            for cell in self.shape_drag_cells():
                rect = self.cell_rect(*cell)
                if tiles:
                    ghost = self.tile_surface(self.shape_tile(cell) - 1).copy()
                    ghost.set_alpha(150)
                    screen.blit(ghost, rect)
                pygame.draw.rect(screen, WARN if erasing else ACCENT, rect, 1 if tiles else 2)
            return
        if self.move_drag:
            kind, _thing, start, cell = self.move_drag
            if cell != start:
                color = ACCENT if self.move_target_ok(kind, cell) else WARN
                pygame.draw.line(screen, color, self.cell_rect(*start).center, self.cell_rect(*cell).center, 2)
                pygame.draw.rect(screen, color, self.cell_rect(*cell), 2)
            return
        if self.stairs_drag:
            for cell, height in self.stairs_heights():
                rect = self.cell_rect(*cell)
                pygame.draw.rect(screen, (120, 200, 255), rect, 2)
                if self.zoom >= 24:
                    label = self.small.render(fmt(height), True, (255, 255, 255))
                    screen.blit(label, label.get_rect(center=rect.center))
            return
        if not area.collidepoint(self.mouse) or self.pan_drag:
            return
        cell = self.cell_at(self.mouse)
        if self.layer == "sides" and self.tool in ("paint", "erase", "fill", "pick", "shape") \
                and self.level.in_bounds(*cell) and self.level.walls[cell[1]][cell[0]]:
            side, rect = self.side_at(self.mouse), self.cell_rect(*cell)
            if self.tool in ("paint", "shape", "fill") and self.stroke != "erase" and self.selection:
                self.draw_side(screen, rect, side, self.primary_id(), alpha=170)
            pygame.draw.rect(screen, WARN if self.tool == "erase" or self.stroke == "erase" else ACCENT,
                             self.side_rect(rect, side), 2)
            return
        if self.tool == "entity" and self.mount_side(cell) and self.selected_entity() is None:
            pygame.draw.rect(screen, ACCENT, self.side_rect(self.cell_rect(*cell), self.mount_side(cell)), 2)
            return
        if self.tool == "paint" and self.stroke != "erase" and self.layer in STAMP_LAYERS:
            for dx, dy, tile_id in self.stamp():
                ghost = self.tile_surface(tile_id - 1).copy()
                ghost.set_alpha(150)
                rect = self.cell_rect(cell[0] + dx, cell[1] + dy)
                screen.blit(ghost, rect)
                pygame.draw.rect(screen, ACCENT, rect, 1)
        elif self.tool == "paint" and self.layer == "ramp":
            rect = self.cell_rect(*cell)
            pygame.draw.rect(screen, ACCENT, rect, 1)
            self.draw_arrow(screen, rect, self.ramp_dir, TEXT)
        else:
            color = {"erase": WARN, "fill": (120, 200, 255), "pick": (200, 120, 255),
                      "start": (60, 220, 110), "spawn": SPAWN_FILL, "stairs": (120, 200, 255),
                      "shape": ACCENT}.get(self.tool, ACCENT)
            pygame.draw.rect(screen, color, self.cell_rect(*cell), 2)

    def draw_panel(self, screen):
        h = self._size()[1]
        pygame.draw.rect(screen, PANEL_BG, (0, TOOLBAR_H, PANEL_W, h - TOOLBAR_H - STATUS_H))
        view = self.atlas_rect()
        screen.set_clip(view)                           # (zoomed in, only part of the atlas is in view)
        backdrop, picture, grid = self.atlas_pictures()
        origin = self.atlas_origin()
        screen.blit(backdrop, origin)                   # shows through transparent pixels
        screen.blit(picture, origin)
        screen.blit(grid, origin)
        shown = self.drag_indices() if self.atlas_drag and not (self.mods() & pygame.KMOD_CTRL) \
            else (self.selection | (self.drag_indices() if self.atlas_drag else set()))
        veil = pygame.Surface((self.atlas_cell(), self.atlas_cell()), pygame.SRCALPHA)
        veil.fill((255, 205, 60, 70))
        for index in shown:
            rect = self.tile_rect(index)
            screen.blit(veil, rect)
            pygame.draw.rect(screen, ACCENT, rect, 2)
        hover = self.tile_index_at(self.mouse)
        if hover is not None:
            pygame.draw.rect(screen, TEXT, self.tile_rect(hover), 1)
        if self.layer not in TILE_LAYERS:               # the atlas is not what this layer paints with
            shade = pygame.Surface(view.size, pygame.SRCALPHA)
            shade.fill((20, 20, 26, 150))
            screen.blit(shade, view)
        screen.set_clip(None)
        self.draw_atlas_scrollbars(screen, view)
        if self.atlas_zoom > 1:
            label = self.small.render(f"{self.atlas_zoom:g}x", True, TEXT)
            back = label.get_rect(topright=(view.right - 12, view.y + 4)).inflate(8, 4)
            pygame.draw.rect(screen, (20, 20, 26), back, border_radius=3)
            screen.blit(label, label.get_rect(center=back.center))

        y, cell, _after, hints_y = self.panel_metrics()
        count = len(self.selection)
        screen.blit(self.font.render(f"Selected: {count} tile{'s' if count != 1 else ''}", True, TEXT), (ATLAS_X, y))
        for dx, dy, tile_id in self.stamp():
            small = pygame.transform.scale(self.tiles[tile_id - 1], (cell, cell))
            screen.blit(small, (ATLAS_X + dx * cell, y + 22 + dy * cell))
        hints = ("Atlas: click / drag = select, Ctrl = add/remove, wheel zoom, middle-drag pan",
                 "Map: L-drag paint, R-drag erase, wheel zoom, Space+drag pan",
                 "Tab floor, layers 1-8, tools B E F I S O T H M C N, [ ] value, R ramp, K key")
        for i, text in enumerate(hints):
            screen.blit(self.small.render(text, True, DIM), (ATLAS_X, hints_y + i * 16))

    def draw_atlas_scrollbars(self, screen, view):
        """Thin bars at the right and bottom of the atlas when, zoomed in, it is taller or wider than its view."""
        cell = self.atlas_cell()
        wide, tall = self.atlas_cols * cell, self.atlas_rows * cell
        hot = self.atlas_pan and view.collidepoint(self.mouse)
        if tall > view.h:
            short = view.inflate(0, -8) if wide > view.w else view    # (room for the other bar in the corner)
            short.top = view.top
            details.draw_scrollbar(screen, details.scrollbar(short, tall - (view.h - short.h), self.atlas_scroll[1]), hot)
        if wide > view.w:
            track = pygame.Rect(view.x + 2, view.bottom - details.SCROLLBAR_W - 2,
                                view.w - 4 - (8 if tall > view.h else 0), details.SCROLLBAR_W)
            width = max(24, track.w * view.w // wide)
            x = track.x + round((track.w - width) * self.atlas_scroll[0] / (wide - view.w))
            details.draw_scrollbar(screen, (track, pygame.Rect(x, track.y, width, track.h)), hot)

    def panel_metrics(self):
        """Vertical layout of the left panel below the atlas: (y of the "Selected" line, size of
        a tile in the stamp preview, y just below the preview, y of the first hint line)."""
        h = self._size()[1]
        y = self.atlas_rect().bottom + 8
        stamp = self.stamp()
        cell, after = 0, y + 22
        if stamp:
            cols, rows = max(s[0] for s in stamp) + 1, max(s[1] for s in stamp) + 1
            room_h = max(16, h - STATUS_H - y - 24 - 70)
            cell = max(4, min(TILE, (PANEL_W - 2 * ATLAS_X) // cols, room_h // rows))
            after = y + 22 + rows * cell + 6
        return y, cell, after, max(after, h - STATUS_H - 56)

    def tile_rect(self, index):
        (x, y), cell = self.atlas_origin(), self.atlas_cell()
        return pygame.Rect(x + (index % self.atlas_cols) * cell, y + (index // self.atlas_cols) * cell, cell, cell)

    def draw_toolbar(self, screen):
        pygame.draw.rect(screen, PANEL_BG, (0, 0, self._size()[0], TOOLBAR_H))
        self.layout()
        for rect, label, action in self.buttons:
            if action == "dropdown":
                self.draw_dropdown_button(screen, rect, label)
                continue
            if action == "val_type":
                self.draw_value_box(screen, rect, label)
                continue
            active = action in (f"tool:{self.tool}", f"layer:{self.layer}", f"shape:{self.shape}") \
                or (action == "legend" and self.show_legend) or (action == "guns" and self.guns_mode) \
                or (action == "prefabs" and self.prefabs_mode) or (action == "effects" and self.effects_mode) or (action == "lights" and self.lights_mode) \
                or (action == "mapsettings" and self.settings_mode)
            color = BUTTON_ON if active else (BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON)
            pygame.draw.rect(screen, color, rect, border_radius=4)
            text = self.font.render(label, True, TEXT)
            screen.blit(text, text.get_rect(center=rect.center))
        for text, pos, color in self.readouts:
            screen.blit(self.font.render(text, True, color), pos)

    def draw_value_box(self, screen, rect, label):
        """The brush value in the toolbar: its number, or a text box while one is being typed."""
        typing = self.value_edit is not None
        hot = rect.collidepoint(self.mouse)
        pygame.draw.rect(screen, (24, 26, 32), rect, border_radius=4)
        pygame.draw.rect(screen, ACCENT if typing else (BUTTON_HOT if hot else BUTTON), rect, 2, border_radius=4)
        caret = ("|" if int(time.time() * 2) % 2 == 0 else " ") if typing else ""
        screen.blit(self.font.render(label + caret, True, TEXT if typing else ACCENT), (rect.x + 8, rect.y + 8))

    def draw_dropdown_button(self, screen, rect, label):
        """The closed dropdown: the current floor's name and an arrow, or a text box while renaming."""
        if self.rename is not None:
            pygame.draw.rect(screen, (24, 26, 32), rect, border_radius=4)
            pygame.draw.rect(screen, ACCENT, rect, 2, border_radius=4)
            caret = "|" if int(time.time() * 2) % 2 == 0 else " "
            screen.blit(self.font.render(self.rename + caret, True, TEXT), (rect.x + 8, rect.y + 8))
            return
        color = BUTTON_ON if self.dropdown_open else (BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON)
        pygame.draw.rect(screen, color, rect, border_radius=4)
        screen.blit(self.font.render(label, True, TEXT), (rect.x + 10, rect.y + 8))
        cx, cy = rect.right - 16, rect.centery
        arrow = [(cx - 6, cy - 3), (cx + 6, cy - 3), (cx, cy + 4)]
        pygame.draw.polygon(screen, TEXT, arrow)

    def new_map_rects(self):
        """(box, name field, Create button, Cancel button) of the New map dialog, in the middle of the window."""
        w, h = self._size()
        box = pygame.Rect(0, 0, min(520, w - 20), 178)
        box.center = (w // 2, h // 2)
        field = pygame.Rect(box.x + 20, box.y + 62, box.w - 40, 32)
        cancel = pygame.Rect(box.right - 20 - 100, box.bottom - 16 - 32, 100, 32)
        create = pygame.Rect(cancel.x - 12 - 100, cancel.y, 100, 32)
        return box, field, create, cancel

    @staticmethod
    def draw_shade(screen):
        """Dim everything drawn so far, under a dialog."""
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill(SHADE)
        screen.blit(shade, (0, 0))

    def open_rects(self):
        """(box, list, Open button, Cancel button, [(row rect, map index)] of the rows shown) of the Open dialog."""
        w, h = self._size()
        rows = min(OPEN_ROWS, max(1, len(self.open_maps)))
        box = pygame.Rect(0, 0, min(520, w - 20), 62 + rows * OPEN_ROW_H + 34 + 16 + 32 + 16)
        box.center = (w // 2, h // 2)
        listing = pygame.Rect(box.x + 20, box.y + 62, box.w - 40, rows * OPEN_ROW_H)
        cancel = pygame.Rect(box.right - 20 - 100, box.bottom - 16 - 32, 100, 32)
        opener = pygame.Rect(cancel.x - 12 - 100, cancel.y, 100, 32)
        shown = [(pygame.Rect(listing.x, listing.y + i * OPEN_ROW_H, listing.w, OPEN_ROW_H), self.open_scroll + i)
                 for i in range(rows) if self.open_scroll + i < len(self.open_maps)]
        return box, listing, opener, cancel, shown

    def open_dialog_click(self, pos):
        _box, _listing, opener, cancel, shown = self.open_rects()
        if opener.collidepoint(pos) or cancel.collidepoint(pos):
            self.finish_open(opener.collidepoint(pos))
            return
        for rect, index in shown:
            if rect.collidepoint(pos):
                again = self.open_click[0] == index and time.time() - self.open_click[1] < DOUBLE_CLICK
                self.pick_map(index)
                self.open_click = (index, time.time())
                if again:
                    self.finish_open(True)
                return

    def draw_open_dialog(self, screen):
        """The Open dialog over a dimmed editor: the maps in the folder, the picked one highlighted."""
        if self.open_maps is None:
            return
        self.draw_shade(screen)
        box, listing, opener, cancel, shown = self.open_rects()
        pygame.draw.rect(screen, PANEL_BG, box, border_radius=6)
        pygame.draw.rect(screen, GRID, box, 1, border_radius=6)
        folder = os.path.basename(self.map_folder())
        screen.blit(self.font.render(f"Open map ({folder}/)", True, ACCENT), (box.x + 20, box.y + 14))
        screen.blit(self.small.render("Double-click or Enter opens it, Esc cancels", True, DIM), (box.x + 20, box.y + 40))
        pygame.draw.rect(screen, (24, 26, 32), listing)
        current = os.path.basename(self.path)
        for rect, index in shown:
            name = self.open_maps[index]
            if index == self.open_pick:
                pygame.draw.rect(screen, BUTTON_ON, rect)
            elif rect.collidepoint(self.mouse):
                pygame.draw.rect(screen, BUTTON_HOT, rect)
            note = self.small.render("open now", True, DIM)
            right = rect.right - 14 - (note.get_width() + 8 if name == current else 0)
            self.blit_fitted(screen, self.font, name[:-5], TEXT, (rect.x + 8, rect.y + 4), right)
            if name == current:
                screen.blit(note, (rect.right - note.get_width() - 14, rect.y + 6))
        pygame.draw.rect(screen, GRID, listing, 1)
        self.draw_scrollbar(screen, "open")                 # where the rows shown are in the whole list

        if self.open_error:
            screen.blit(self.small.render(self.open_error, True, WARN), (box.x + 20, listing.bottom + 8))
        for rect, label in ((opener, "Open"), (cancel, "Cancel")):
            pygame.draw.rect(screen, BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON, rect, border_radius=4)
            text = self.font.render(label, True, TEXT)
            screen.blit(text, text.get_rect(center=rect.center))

    def draw_new_map_dialog(self, screen):
        """The New map dialog over a dimmed editor: the name being typed and where it will be saved."""
        if self.new_name is None:
            return
        self.draw_shade(screen)
        box, field, create, cancel = self.new_map_rects()
        pygame.draw.rect(screen, PANEL_BG, box, border_radius=6)
        pygame.draw.rect(screen, GRID, box, 1, border_radius=6)
        screen.blit(self.font.render("New map", True, ACCENT), (box.x + 20, box.y + 14))
        screen.blit(self.small.render("Name (Enter to create, Esc to cancel):", True, DIM), (box.x + 20, box.y + 40))
        pygame.draw.rect(screen, (24, 26, 32), field, border_radius=4)
        pygame.draw.rect(screen, ACCENT, field, 2, border_radius=4)
        caret = "|" if int(time.time() * 2) % 2 == 0 else " "
        screen.blit(self.font.render(self.new_name + caret, True, TEXT), (field.x + 8, field.y + 8))
        folder = os.path.basename(self.map_folder())
        note, color = (self.new_error, WARN) if self.new_error else \
            (f"Saved as {folder}/{self.new_name.strip() or '...'}.json", DIM)
        screen.blit(self.small.render(note, True, color), (box.x + 20, field.bottom + 8))
        for rect, label in ((create, "Create"), (cancel, "Cancel")):
            pygame.draw.rect(screen, BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON, rect, border_radius=4)
            text = self.font.render(label, True, TEXT)
            screen.blit(text, text.get_rect(center=rect.center))

    def draw_dropdown(self, screen):
        """The open floor list, drawn last so it sits on top of everything."""
        if not self.dropdown_open:
            return
        for index, (rect, label, action) in enumerate(self.dropdown_items()):
            current = action == f"floor:{self.floor}"
            color = BUTTON_ON if current else (BUTTON_HOT if rect.collidepoint(self.mouse) else PANEL_BG)
            pygame.draw.rect(screen, color, rect)
            pygame.draw.rect(screen, GRID, rect, 1)
            text = self.font.render(label, True, ACCENT if action == "addfloor" else TEXT)
            screen.blit(text, (rect.x + 10, rect.y + 6))

    def draw_status(self, screen):
        w, h = self._size()
        pygame.draw.rect(screen, PANEL_BG, (0, h - STATUS_H, w, STATUS_H))
        info = self.message if time.time() < self.message_until else self.hover_info()
        screen.blit(self.font.render(info, True, TEXT), (8, h - STATUS_H + 4))
        problems = self.problems()
        if problems:
            count = f" ({len(problems)}, outlined in red)" if len(problems) > 1 else " (outlined in red)"
            warn = self.font.render(f"WARNING{count}: {problems[0]}", True, WARN)
            screen.blit(warn, (w - warn.get_width() - 8, h - STATUS_H + 4))

    def hover_info(self):
        index = self.tile_index_at(self.mouse)
        if index is not None:
            return (f"Atlas tile row {index // self.atlas_cols}, col {index % self.atlas_cols}"
                    f"  ->  map id {index + 1}")
        if self.map_area().collidepoint(self.mouse):
            x, y = self.cell_at(self.mouse)
            if self.level.in_bounds(x, y):
                g = self.level.grids
                if self.level.is_solid(x, y, self.floor):
                    height = g["wall_h"][y][x]
                    if self.level.short_wall_top(x, y) is not None:
                        how = f", short: {fmt(height)} high"
                    elif height > 0:
                        how = f", {fmt(height)} high (reaches the ceiling: full height)"
                    else:
                        how = ", full height"
                    if self.is_transparent_tile(g["walls"][y][x]):
                        how += ", see-through (blocks movement)"
                    if self.wall_ceiling_matters(x, y):
                        kind = "set" if self.level.has_explicit_wall_ceiling(x, y) else "automatic"
                        how += f", ceiling over it {fmt(self.level.wall_ceiling(x, y))} ({kind})"
                    if self.layer == "sides":
                        side = self.side_at(self.mouse)
                        own = g[f"side_{side}"][y][x]
                        how += f"   {WALL_LABELS[side].split()[0]} side: " + (f"tile #{own}" if own else "the wall's own")
                        low, high = g[f"side_{side}_from"][y][x], g[f"side_{side}_to"][y][x]
                        if own and (low or high):
                            how += f" from {fmt(low)} to {fmt(high) if high else 'the top'}"
                    return f"Cell ({x}, {y}): wall id {g['walls'][y][x]}{how}"
                parts = [f"Cell ({x}, {y})"]
                for s in self.level.rooms_at(x, y):
                    lo, hi = g[grid_name("floor_h", s)][y][x], g[grid_name("ceil_h", s)][y][x]
                    ramp = g[grid_name("ramp", s)][y][x]
                    parts.append(f"{self.level.names[s]}: {fmt(lo)}-{fmt(hi)}"
                                 + (f" ramp {RAMP_NAMES[ramp]}" if ramp else ""))
                return "   ".join(parts)
        return (f"Floor: {self.level.names[self.floor]}   Layer: {LAYER_LABELS[self.layer]}"
                f"   Tool: {self.tool}")


def starting_map(args, settings=SETTINGS_PATH):
    """The map to open: the one named on the command line, else the one edited last, else maps/map.json."""
    return os.path.abspath(args[0]) if args else (last_map(settings) or MAP_PATH)


def map_files(folder):
    """The map files in `folder`, by name (none if it cannot be read)."""
    try:
        return sorted((n for n in os.listdir(folder) if n.lower().endswith(".json")), key=str.lower)
    except OSError:
        return []


TAKEN_LABELS = {"keep": "Keep mine", "replace": "Replace", "copy": "Add a copy"}
COMING = (90, 170, 255)                         # Import dialog: the box of a thing coming in with a ticked one
IMPORT_ICON = 20                                # Import dialog: the picture beside each thing, in pixels
IMPORT_ROWS, IMPORT_ROW_H = 12, 26              # Import dialog: list rows shown at once, and their height


class ImportDialog:
    """The editor's Import dialog: first the other maps in the folder, then what one of them has (prefabs, lights,
    effects, guns, ammo types) to tick, and what to do with names this map already uses. It changes nothing
    itself: click() and key() say what to do - None (carry on), "close", or ("import", source, picks, taken)."""

    def __init__(self, folder, names, level, font, small, tiles=()):
        """`tiles` are the atlas's pictures (the maps in a folder share one atlas), to show what each thing looks
        like."""
        self.folder, self.names, self.level = folder, names, level
        self.font, self.small = font, small
        self.tiles = list(tiles)
        self._icons = {}                        # (kind, name) -> the small picture drawn beside it
        self.source = self.source_name = None   # the map picked to import from, once picked
        self.chosen = set()                     # (kind, name) ticked
        self.taken = "copy"                     # what to do with a name already used here (TAKEN_CHOICES)
        self.scroll = 0
        self.grab = None                        # while the list's bar is dragged: how far down its thumb it was grabbed
        self.error = ""

    # ------------------------------------------------------------------ what is listed

    def rows(self):
        """The list's rows: ("map", name) to pick from, or ("kind", kind) headings and ("thing", (kind, name))."""
        if self.source is None:
            return [("map", n) for n in self.names]
        out = []
        for kind, _label in IMPORT_KINDS.items():
            names = sorted(things_named(self.source, kind), key=str.lower)
            if names:
                out.append(("kind", kind))
                out += [("thing", (kind, n)) for n in names]
        return out

    def icon(self, kind, name):
        """The small picture of a thing in the map imported from: its tile (a prefab's icon, a gun's picture, an
        ammo type's bullet, an effect's particle) cropped to what is drawn in it and made to fit, or for a light a
        swatch of its color at full strength. None when there is nothing to show."""
        key = (kind, name)
        if key not in self._icons:
            thing = things_named(self.source, kind)[name]
            picture = None
            if kind == "lights":
                bright = max(thing.r, thing.g, thing.b, 1)
                picture = pygame.Surface((IMPORT_ICON, IMPORT_ICON))
                picture.fill(tuple(round(c * 255 / bright) for c in (thing.r, thing.g, thing.b)))
                pygame.draw.rect(picture, GRID, picture.get_rect(), 1)
            elif self.tiles:
                icon = barricade_icon(thing) if kind == "barricade_kinds" else thing.tile
                tile = self.tiles[max(0, min(icon, len(self.tiles) - 1))]
                box = tile.get_bounding_rect()                  # just what is drawn in the tile, made to fit
                if box.w and box.h:
                    scale = IMPORT_ICON / max(box.w, box.h)
                    part = pygame.transform.scale(tile.subsurface(box), (max(1, round(box.w * scale)),
                                                                         max(1, round(box.h * scale))))
                    picture = pygame.Surface((IMPORT_ICON, IMPORT_ICON), pygame.SRCALPHA)
                    picture.blit(part, part.get_rect(center=picture.get_rect().center))
            self._icons[key] = picture
        return self._icons[key]

    def coming(self):
        """{(kind, name): name of a ticked thing that uses it} for what is not ticked but will come in with what is
        (a prefab's light, a gun's ammo type and that ammo's effects...)."""
        out = {}
        for picked in sorted(self.chosen):
            for needed in sorted(with_needs(self.source, {picked}) - self.chosen):
                out.setdefault(needed, picked[1])
        return out

    def state(self, kind, name):
        """How a thing of the source stands here: "new", "same" (this map has it just the same) or "taken"."""
        mine = things_named(self.level, kind).get(name)
        theirs = things_named(self.source, kind)[name]
        return "new" if mine is None else ("same" if mine == theirs else "taken")

    def rects(self, size):
        """(box, list, [(row rect, row)], {button: rect}) laid out in the middle of a window of `size`."""
        w, h = size
        shown_rows = min(IMPORT_ROWS, max(1, len(self.rows())))
        extra = 0 if self.source is None else 30 + 26          # (the "name taken" choice and the count)
        box = pygame.Rect(0, 0, min(600, w - 20), 66 + shown_rows * IMPORT_ROW_H + 16 + extra + 30 + 48)
        box.center = (w // 2, h // 2)
        listing = pygame.Rect(box.x + 20, box.y + 66, box.w - 40, shown_rows * IMPORT_ROW_H)
        rows = self.rows()
        self.scroll = max(0, min(self.scroll, len(rows) - IMPORT_ROWS))
        shown = [(pygame.Rect(listing.x, listing.y + i * IMPORT_ROW_H, listing.w, IMPORT_ROW_H), rows[self.scroll + i])
                 for i in range(shown_rows) if self.scroll + i < len(rows)]
        buttons = {"cancel": pygame.Rect(box.right - 20 - 100, box.bottom - 16 - 32, 100, 32)}
        if self.source is not None:
            buttons["back"] = buttons["cancel"].move(-112, 0)
            buttons["import"] = buttons["back"].move(-112, 0)
            y = listing.bottom + 14
            for i, choice in enumerate(TAKEN_CHOICES):
                buttons[f"taken:{choice}"] = pygame.Rect(listing.x + 170 + i * 122, y, 114, 28)
        return box, listing, shown, buttons

    # ------------------------------------------------------------------ input

    def scrollbar(self, size):
        """(list rect, (track, thumb) of the bar beside it, or None when every row shows)."""
        listing = self.rects(size)[1]
        return listing, details.scrollbar(listing, len(self.rows()) * IMPORT_ROW_H, self.scroll * IMPORT_ROW_H)

    def drag(self, y, size):
        """While the bar is dragged: scroll so the point grabbed on its thumb is at screen row `y`."""
        listing, _bar = self.scrollbar(size)
        pixels = details.scroll_for(listing, len(self.rows()) * IMPORT_ROW_H, y - self.grab)
        self.scroll = max(0, min(len(self.rows()) - IMPORT_ROWS, round(pixels / IMPORT_ROW_H)))

    def click(self, pos, size):
        _listing, bar = self.scrollbar(size)
        if bar is not None and bar[0].inflate(10, 0).collidepoint(pos):
            _track, thumb = bar                 # on the thumb: drag it from there; on the track: jump there first
            self.grab = pos[1] - thumb.y if thumb.top <= pos[1] < thumb.bottom else thumb.h // 2
            self.drag(pos[1], size)
            return None
        _box, _listing, shown, buttons = self.rects(size)
        for name, rect in buttons.items():
            if rect.collidepoint(pos):
                return self.press(name)
        for rect, (kind, value) in shown:
            if not rect.collidepoint(pos):
                continue
            if kind == "map":
                self.pick(value)
            elif kind == "kind":
                group = {(value, n) for n in things_named(self.source, value)}
                self.chosen = self.chosen - group if group <= self.chosen else self.chosen | group
            else:
                self.chosen ^= {value}
            return None
        return None

    def press(self, button):
        if button == "cancel":
            return "close"
        if button == "back":
            self.source = self.source_name = None
            self.chosen, self.scroll, self.error = set(), 0, ""
            return None
        if button.startswith("taken:"):
            self.taken = button[6:]
            return None
        if button == "import":
            if not self.chosen:
                self.error = "Tick something to import first"
                return None
            return ("import", self.source, set(self.chosen), self.taken)
        return None

    def pick(self, name):
        """Read the map to import from; one that cannot be read says why and stays on the list of maps."""
        try:
            self.source = load_level(os.path.join(self.folder, name))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            self.error = f"Can't read {name}: {e}"[:80]
            return
        self.source_name, self.chosen, self.scroll, self.error = name, set(), 0, ""
        if not self.rows():
            self.error = f"{name[:-5]} has no prefabs, lights, effects, guns or ammo types"

    def key(self, e):
        if e.key == pygame.K_ESCAPE:
            return "close" if self.source is None else self.press("back")
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.source is not None:
            return self.press("import")
        return None

    def wheel(self, y):
        self.scroll = max(0, self.scroll - y)

    # ------------------------------------------------------------------ drawing

    def draw(self, screen, size, mouse):
        """Draw the dialog. Returns [(rect, whole text)] of the names cut short to fit, to show whole on hover."""
        box, listing, shown, buttons = self.rects(size)
        coming = self.coming() if self.source is not None else {}
        cut = []

        def fitted(text, pos, right):
            shown_text = details.fit_text(self.font, text, right - pos[0])
            if shown_text != text:
                cut.append((pygame.Rect(pos[0], pos[1], right - pos[0], IMPORT_ROW_H - 4), text))
            screen.blit(self.font.render(shown_text, True, TEXT), pos)
        pygame.draw.rect(screen, PANEL_BG, box, border_radius=6)
        pygame.draw.rect(screen, GRID, box, 1, border_radius=6)
        if self.source is None:
            title, hint = "Import from a map", "Pick the map to bring prefabs, lights, effects, guns or ammo from"
        else:
            title, hint = (f"Import from {self.source_name[:-5]}",
                           "Tick what to bring in (a heading ticks its group); what they use comes too")
        screen.blit(self.font.render(title, True, ACCENT), (box.x + 20, box.y + 14))
        screen.blit(self.small.render(hint, True, DIM), (box.x + 20, box.y + 42))
        pygame.draw.rect(screen, (24, 26, 32), listing)
        for rect, (kind, value) in shown:
            if rect.collidepoint(mouse):
                pygame.draw.rect(screen, BUTTON_HOT, rect)
            if kind == "map":
                fitted(value[:-5], (rect.x + 8, rect.y + 4), rect.right - 14)
            elif kind == "kind":
                group = {(value, n) for n in things_named(self.source, value)}
                ticked, along = len(group & self.chosen), len(group & set(coming))
                count = f"{ticked} of {len(group)}" + (f", {along} coming with them" if along else "")
                screen.blit(self.font.render(f"{IMPORT_KINDS[value]}  ({count})", True, ACCENT), (rect.x + 8, rect.y + 4))
            else:
                ticked, along = value in self.chosen, value in coming
                tick = pygame.Rect(rect.x + 18, rect.y + 6, 14, 14)
                if ticked or along:                         # yellow: ticked; blue: comes in with a ticked thing
                    pygame.draw.rect(screen, ACCENT if ticked else COMING, tick, border_radius=2)
                else:
                    pygame.draw.rect(screen, DIM, tick, 1, border_radius=2)
                picture = self.icon(*value)
                if picture is not None:
                    screen.blit(picture, (tick.right + 10, rect.y + (IMPORT_ROW_H - IMPORT_ICON) // 2))
                notes = [(f"comes with {coming[value]}", COMING)] if along else []
                notes += {"same": [("already here", DIM)], "taken": [("name used here", WARN)]}.get(self.state(*value), [])
                right = rect.right - 14
                for text, color in reversed(notes):
                    label = self.small.render(text, True, color)
                    right -= label.get_width()
                    screen.blit(label, (right, rect.y + 6))
                    right -= 14
                fitted(value[1], (tick.right + 18 + IMPORT_ICON, rect.y + 4), right)
        pygame.draw.rect(screen, GRID, listing, 1)
        _listing, bar = self.scrollbar(size)                # where the rows shown are in the whole list
        if bar is not None:
            details.draw_scrollbar(screen, bar, self.grab is not None or bar[0].inflate(10, 0).collidepoint(mouse))

        if self.source is not None:
            screen.blit(self.small.render("If a name is used here:", True, TEXT), (listing.x, listing.bottom + 20))
            needs = len(with_needs(self.source, self.chosen)) - len(self.chosen)
            count = f"{len(self.chosen)} ticked" + (f", and {needs} more they use (blue)" if needs else "")
            screen.blit(self.small.render(count, True, DIM), (listing.x, listing.bottom + 52))
        for name, rect in buttons.items():
            on = name == f"taken:{self.taken}"
            hot = rect.collidepoint(mouse)
            pygame.draw.rect(screen, BUTTON_ON if on else (BUTTON_HOT if hot else BUTTON), rect, border_radius=4)
            label = TAKEN_LABELS[name[6:]] if name.startswith("taken:") else name.capitalize()
            text = (self.small if name.startswith("taken:") else self.font).render(label, True, TEXT)
            screen.blit(text, text.get_rect(center=rect.center))
        if self.error:
            screen.blit(self.small.render(self.error, True, WARN), (box.x + 20, box.bottom - 40))
        return cut


def main():
    path = starting_map(sys.argv[1:])
    pygame.init()
    pygame.display.set_mode((1280, 860), pygame.RESIZABLE)
    if not os.path.exists(ATLAS_PATH):
        sys.exit("textures.png not found - run `python make_atlas.py` first")
    editor = Editor(path, SETTINGS_PATH)
    editor.start_maximized()                    # the editor opens maximized
    clock = pygame.time.Clock()
    while editor.running:
        dt = clock.tick(60) / 1000
        for event in pygame.event.get():
            editor.handle_event(event)
        editor.update(dt)
        editor.draw(pygame.display.get_surface())
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
