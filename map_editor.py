"""Map editor for the simple raycaster.

Run:  python map_editor.py [maps/map.json]      (opens maximized)

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
  4 FloorH     floor height of each cell (stairs, platforms, pits); [ ] change the brush value
  5 CeilH      ceiling height of each cell (tall rooms, low tunnels)
  6 Ramps      ramp direction; a run of ramp cells slopes from the floor before it to the floor
               after it. R rotates the direction.

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
it keeps its layout from the atlas, with its top-left at the cursor.
Map: left-drag paints, right-drag erases (back to the layer's default), wheel zooms,
middle-drag or Space+drag pans.

Textures: edit textures.png in any image editor and the editor picks the change up by itself
within a moment (the atlas, the map and the 3D view all update); F6 or the "Reload tex" button
does it on demand. A file that can't be read leaves the old textures in place.

Map size: the Edge buttons add (+) or remove (-) a column or row on one side: L left, R right,
T top, B bottom. Cells, the start and the 3D camera stay where they are on the map.

Tools: B paint, E erase, F fill, I pick from the map, S set the start (on the floor you are
editing; click it again to rotate), T stairs (drag a line on the FloorH layer: heights rise by
the Step each cell, starting at the brush value). Ctrl+Z / Ctrl+Y undo / redo, Ctrl+S save,
F5 save and play, Home reset view, Tab / Shift+Tab switch floor, F2 rename floor.

Items (the Entity tool, N): pick a sprite tile in the atlas, set the Item buttons in the second
row, and click a cell to put an item in the middle of it on the floor you are editing (right click
removes one; clicking an occupied cell replaces it). Mode: "Pick up once" (touching it gives the
effect and it is gone), "Respawns" (gone, then back after the set seconds) or "Stays" (touching
gives the effect each visit but it is never removed). Effect: none, score or health, with an
amount; Size and Lift set how big the sprite is and how far it floats above the floor. Items show
on the map ringed white / cyan / green by mode, and in the 3D view as sprites that face you.

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
ramp arrows and height colours.
"""
import math
from dataclasses import replace
import os
import subprocess
import sys
import time

import pygame

from atlas import ATLAS_PATH, atlas_array, transparent_tiles, unpack_atlas
from constants import HEIGHT, MOUSE_SENSITIVITY, PLAYER_HEIGHT, TILE, WIDTH
from mapfile import (DEFAULTS, EDIT_LAYERS, ENTITY_EFFECTS, ENTITY_MODES, MAP_PATH, MAX_NAME_LENGTH, MIN_WALL_GAP,
                     MODE_LABELS, Entity, Level, default_level,
                     grid_name, load_level, save_level, split_grid_name)
from preview import Preview
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
                "wall_h": (0.0, 3.0)}           # colour scale of the height views
VALUE_LIMITS = {"floor_h": (-4.0, 8.0), "ceil_h": (-4.0, 8.0),
                "wall_h": (VALUE_STEP, 8.0)}    # a wall height of 0 would mean "full": erase for that
WALL_FULL = (150, 70, 60)                       # colour of a full-height wall on the WallH layer
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

STAMP_LAYERS = ("walls", "floor_tex", "ceil_tex")
ROOM_HEIGHT_LAYERS = ("floor_h", "ceil_h")                  # heights that make up a floor's rooms
VALUE_LAYERS = ROOM_HEIGHT_LAYERS + ("wall_h",)             # every layer painted with a number
LAYER_LABELS = {"walls": "Walls", "floor_tex": "FloorTex", "ceil_tex": "CeilTex",
                "floor_h": "FloorH", "ceil_h": "CeilH", "ramp": "Ramps", "wall_h": "WallH"}
LAYER_KEYS = {pygame.K_1 + i: name for i, name in enumerate(EDIT_LAYERS)}
TOOLS = {"paint": "B", "erase": "E", "fill": "F", "pick": "I", "start": "S", "stairs": "T", "camera": "C",
         "entity": "N"}
TOOL_KEYS = {pygame.K_b: "paint", pygame.K_e: "erase", pygame.K_f: "fill",
             pygame.K_i: "pick", pygame.K_s: "start", pygame.K_t: "stairs", pygame.K_c: "camera",
             pygame.K_n: "entity"}
ENTITY_MODE_COLOURS = {"once": (255, 255, 255), "respawn": (90, 210, 255), "persistent": (110, 230, 120)}
ENTITY_FIRST_TILE = 10                          # the first item sprite in the stock atlas (the gem)
RAMP_NAMES = {1: "East", 2: "West", 3: "South", 4: "North"}
RAMP_VECTORS = {1: (1, 0), 2: (-1, 0), 3: (0, 1), 4: (0, -1)}


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
    """Colour for a height: blue (low) through green to yellow (high)."""
    t = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    stops = ((40, 60, 150), (50, 160, 120), (240, 200, 60))
    a, b, f = (stops[0], stops[1], t * 2) if t < 0.5 else (stops[1], stops[2], t * 2 - 1)
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def fmt(value):
    return f"{value:g}"


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


class Editor:
    def __init__(self, path):
        self.path = path
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

        self.floor = 0                        # index of the floor being edited (0 = ground)
        self.dropdown_open = False
        self.show_legend = True                 # the key to the marks on the map (K toggles)
        self.rename = None                      # text being typed while renaming a floor
        self.layer = "walls"
        self.tool = "paint"
        self.entity_brush = Entity(0.0, 0.0, tile=ENTITY_FIRST_TILE)   # settings the Entity tool places with
        self.selection = {0}                    # selected atlas tile indices (0-based)
        self.value = {}                         # height brush per stored grid; see brush()
        self.ramp_dir = 1
        self.stair_step = 0.25
        self.atlas_drag = None                  # (start_cell, current_cell) while dragging
        self.stairs_drag = None                 # (start_cell, current_cell) while dragging
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
        self._scaled = {}
        self._trans_cache = (None, None)
        self._atlas_stamp = self._atlas_mtime()
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
        """Width of the 3D view's column at the window's right; 0 while the view is hidden."""
        if not self.show_preview:
            return 0
        return int(min(PREVIEW_MAX_W, max(PREVIEW_MIN_W, (self._size()[0] - PANEL_W) * 0.4)))

    def map_area(self):
        w, h = self._size()
        return pygame.Rect(PANEL_W, TOOLBAR_H, max(1, w - PANEL_W - self.preview_width()),
                           max(1, h - TOOLBAR_H - STATUS_H))

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
        row1 += [None, ("btn", "Key(K)", "legend"), ("btn", "3D(V)", "preview"),
                 ("btn", "Reload tex(F6)", "textures")]
        if self.show_preview:
            row1.append(("btn", "Cam->Start", "camstart"))
        row2 = [("txt", "Layer:", DIM)]
        row2 += [("btn", f"{LAYER_LABELS[name]}({i + 1})", f"layer:{name}") for i, name in enumerate(EDIT_LAYERS)]
        row2.append(None)
        if self.layer in VALUE_LAYERS:
            row2 += [("btn", "Val-", "val-"), ("btn", "Val+", "val+"),
                     ("txt", f"value {fmt(self.brush(self.gname()))}", ACCENT)]
        elif self.layer == "ramp":
            row2 += [("btn", "Rotate(R)", "dir"), ("txt", f"rises {RAMP_NAMES[self.ramp_dir]}", ACCENT)]
        if self.tool == "stairs":
            row2 += [None, ("btn", "Step-", "step-"), ("btn", "Step+", "step+"),
                     ("txt", f"step {fmt(self.stair_step)}", ACCENT)]
        if self.tool == "entity":
            e = self.entity_brush
            row2 += [None, ("txt", "Item:", DIM), ("btn", MODE_LABELS[e.mode], "ent:mode"),
                     ("btn", f"Effect: {e.effect}", "ent:effect")]
            if e.effect != "none":
                row2 += [("btn", "-", "ent:amount-"), ("txt", f"amount {e.amount:g}", ACCENT),
                         ("btn", "+", "ent:amount+")]
            if e.mode == "respawn":
                row2 += [("btn", "-", "ent:respawn-"), ("txt", f"back after {e.respawn:g}s", ACCENT),
                         ("btn", "+", "ent:respawn+")]
            row2 += [("btn", "-", "ent:size-"), ("txt", f"size {e.size:g}", ACCENT), ("btn", "+", "ent:size+"),
                     ("btn", "-", "ent:lift-"), ("txt", f"lift {e.lift:g}", ACCENT), ("btn", "+", "ent:lift+")]
        row3 = [("btn", f"{name.capitalize()}({key})", f"tool:{name}") for name, key in TOOLS.items()]
        row3 += [None, ("btn", "Undo", "undo"), ("btn", "Redo", "redo"), None,
                 ("btn", "Border", "border"), ("txt", "Edge", DIM),
                 *[("btn", f"{side}{sign}", f"edge:{side}{sign}") for side in "LRTB" for sign in "+-"],
                 ("txt", f"{self.level.width}x{self.level.height}".ljust(7), ACCENT), None,
                 ("btn", "New", "new"), ("btn", "Reload", "reload"), ("btn", "Save", "save"),
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
        """A grey checkerboard to put under tiles, so transparent pixels are visible as such."""
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

    def _make_atlas_grid(self):
        grid = pygame.Surface(self.atlas_img.get_size(), pygame.SRCALPHA)
        for x in range(0, grid.get_width() + 1, TILE):
            pygame.draw.line(grid, (255, 255, 255, 40), (x, 0), (x, grid.get_height()))
        for y in range(0, grid.get_height() + 1, TILE):
            pygame.draw.line(grid, (255, 255, 255, 40), (0, y), (grid.get_width(), y))
        return grid

    # ---------------------------------------------------------------- view

    def fit_view(self):
        area = self.map_area()
        self.zoom = max(8, min(64, area.w // (self.level.width + 1), area.h // (self.level.height + 1)))
        self.pan = [(area.w - self.level.width * self.zoom) // 2,
                    (area.h - self.level.height * self.zoom) // 2]

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
        rect = self.atlas_rect()
        if not rect.collidepoint(pos):
            return None
        col, row = (pos[0] - rect.x) // TILE, (pos[1] - rect.y) // TILE
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

    def paint_at(self, cx, cy):
        layer, level = self.layer, self.level
        if layer in STAMP_LAYERS:
            for dx, dy, tile_id in self.stamp():
                x, y = cx + dx, cy + dy
                if layer == "walls" and level.in_bounds(x, y) and not level.is_solid(x, y, self.floor):
                    level.set("wall_h", x, y, DEFAULTS["wall_h"])      # a new wall starts full height
                    level.set("wall_floor", x, y, self.floor)          # ... and on this floor, not the ones below
                    if self.floor > 0:                                  # its base: this floor's brush height
                        level.set(self.gname("floor_h"), x, y, self.brush(self.gname("floor_h")))
                level.set(self.gname(), x, y, tile_id)
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
        else:
            level.set(self.gname(), cx, cy, self.brush_value())

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
        if self.layer == "walls":
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

    def stroke_cell(self, cell):
        (self.erase_at if self.stroke == "erase" else self.paint_at)(*cell)

    def fill(self, cell):
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
        self.begin_edit()
        if self.layer in ROOM_HEIGHT_LAYERS and self.floor >= 1:
            for x, y in level.region(grid, *cell):      # per cell, so rooms get created properly
                if not level.is_solid(x, y, self.floor):
                    self.set_height(x, y, self.layer, value)
        else:
            level.flood_fill_cells(grid, cell[0], cell[1], value)

    def map_click(self, cell, button):
        """Start of a click on the map: left uses the active tool, right always erases."""
        if button == 3 and self.tool == "entity":
            self.remove_entities(cell)
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
            if self.layer != "floor_h":
                self.layer = "floor_h"
                self.say("Stairs paint floor heights: switched to the FloorH layer")
            self.stairs_drag = (cell, cell)

    def entities_in(self, cell):
        """The entities standing in this cell on the floor being edited."""
        return [e for e in self.level.entities
                if (math.floor(e.x), math.floor(e.y)) == tuple(cell) and e.span == self.floor]

    def place_entity(self, cell):
        """Entity tool: put an item with the current settings in the middle of the cell, on the floor
        being edited, replacing any item already there."""
        level = self.level
        if not level.in_bounds(*cell):
            return
        if not level.span_present(self.floor, *cell):
            self.say("An item needs an open floor to stand on: no room in this cell on this floor")
            return
        self.begin_edit()
        for old in self.entities_in(cell):
            level.entities.remove(old)
        level.entities.append(replace(self.entity_brush, x=cell[0] + 0.5, y=cell[1] + 0.5, span=self.floor))
        self.say(f"Placed an item ({MODE_LABELS[self.entity_brush.mode].lower()}, effect {self.entity_brush.effect})")

    def remove_entities(self, cell):
        found = self.entities_in(cell)
        if found:
            self.begin_edit()
            for e in found:
                self.level.entities.remove(e)

    def entity_action(self, action):
        """The Item buttons: cycle the mode / effect, or step amount, respawn time, size and lift."""
        e, what = self.entity_brush, action[4:]
        if what == "mode":
            e.mode = ENTITY_MODES[(ENTITY_MODES.index(e.mode) + 1) % len(ENTITY_MODES)]
        elif what == "effect":
            e.effect = ENTITY_EFFECTS[(ENTITY_EFFECTS.index(e.effect) + 1) % len(ENTITY_EFFECTS)]
        else:
            name, sign = what[:-1], 1 if what.endswith("+") else -1
            step, low, high = {"amount": (5.0, 0.0, 1000.0), "respawn": (1.0, 0.0, 600.0),
                               "size": (0.1, 0.1, 3.0), "lift": (0.1, -2.0, 5.0)}[name]
            setattr(e, name, round(max(low, min(high, getattr(e, name) + sign * step)), 3))

    def place_camera(self, cell, point):
        """Camera tool: stand the 3D view's camera in this cell, on the floor being edited (or the
        nearest floor that has a room there). Dragging afterwards turns it toward the cursor."""
        preview = self.ensure_preview()
        preview.sync(self.level, self.revision, force=True)
        if preview.place(cell[0] + 0.5, cell[1] + 0.5, self.floor):
            self.camera_drag = True
        else:
            self.say("The camera can't stand there (wall, no room, or too low)")

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
        elif value > 0:                                  # a ramp direction
            self.ramp_dir = value
        self.tool = "paint"
        self.say(f"Picked {fmt(value)}")

    def stairs_heights(self):
        """[(cell, height)] along the current stairs drag."""
        start, end = self.stairs_drag
        base = self.brush(self.gname("floor_h"))
        return [(cell, round(base + i * self.stair_step, 4))
                for i, cell in enumerate(line_cells(start, end))]

    def finish_stairs(self):
        steps = self.stairs_heights()
        self.stairs_drag = None
        self.begin_edit()
        for (x, y), height in steps:
            self.set_height(x, y, "floor_h", height)
        self.say(f"Stairs: {len(steps)} cells, {fmt(steps[0][1])} to {fmt(steps[-1][1])}")

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
        if self.tool == "entity":                       # the tile chosen here is the item's sprite
            self.entity_brush.tile = min(picked)
            self.say(f"Item sprite: tile {self.entity_brush.tile + 1}")
            return
        if self.tool in ("erase", "pick", "start", "stairs"):
            self.tool = "paint"
        if self.layer not in STAMP_LAYERS:
            self.layer = "walls"                        # choosing a tile means you want to paint tiles
            self.say("Switched to the Walls layer (tile selection applies to the texture layers)")

    # ---------------------------------------------------------------- actions

    def select_floor(self, floor):
        self.floor = max(0, min(floor, self.level.floor_count - 1))
        self.stairs_drag = None

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
        self.rename = None
        self.dropdown_open = False

    def do(self, action):
        if action != self.confirm:
            self.confirm = None
        if action != "dropdown":
            self.dropdown_open = False
        if action.startswith("ent:"):
            self.entity_action(action)
        elif action.startswith("tool:"):
            self.tool = action[5:]
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
        elif action in ("val-", "val+"):
            self.adjust_value(-VALUE_STEP if action == "val-" else VALUE_STEP)
        elif action == "dir":
            self.ramp_dir = self.ramp_dir % 4 + 1
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
        elif action in ("new", "reload"):
            if self.dirty and self.confirm != action:
                self.confirm = action
                self.say(f"Unsaved changes: click {action.capitalize()} again to discard them", 6)
                return
            self.confirm = None
            self.new_map() if action == "new" else self.reload()
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

    def adjust_value(self, delta):
        if self.layer in VALUE_LAYERS:
            low, high = VALUE_LIMITS[self.layer]
            name = self.gname()
            self.value[name] = max(low, min(high, round(self.brush(name) + delta, 4)))

    def new_map(self):
        self.undo.clear()
        self.redo.clear()
        self.level = Level.blank(16, 16)
        self.level.start_x = self.level.start_y = 1.5
        self.clamp_floor()
        self.dirty = False
        self.revision += 1
        self.fit_view()
        self.say("New blank map (16x16)")

    def reload(self):
        if not os.path.exists(self.path):
            self.say("Nothing saved yet to reload")
            return
        self.level = load_level(self.path)
        self.clamp_floor()
        self.undo.clear()
        self.redo.clear()
        self.dirty = False
        self.revision += 1
        self.fit_view()
        self.say(f"Reloaded {os.path.basename(self.path)}")

    def save(self):
        save_level(self.path, self.level)
        self.dirty = False
        problems = self.problems()
        self.say(f"Saved {os.path.basename(self.path)}" + (f"  (warning: {problems[0]})" if problems else ""))

    def play(self):
        if self.dirty or not os.path.exists(self.path):
            self.save()
        game = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
        subprocess.Popen([sys.executable, game, "--map", self.path], cwd=os.path.dirname(game))
        self.say("Launched the game with this map")

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
            self.say("Unsaved changes: press Esc / close again to discard them, or Ctrl+S to save", 6)
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
        ctrl = bool(e.mod & pygame.KMOD_CTRL)
        if e.key == pygame.K_ESCAPE:
            if self.dropdown_open:
                self.dropdown_open = False
            else:
                self.request_quit()
        elif ctrl and e.key == pygame.K_s:
            self.do("save")
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
        elif e.key == pygame.K_v:
            self.do("preview")
        elif e.key in LAYER_KEYS:
            self.do("layer:" + LAYER_KEYS[e.key])
        elif e.key in TOOL_KEYS:
            self.do("tool:" + TOOL_KEYS[e.key])
        elif e.key == pygame.K_LEFTBRACKET:
            self.do("val-")
        elif e.key == pygame.K_RIGHTBRACKET:
            self.do("val+")
        elif e.key == pygame.K_r:
            self.do("dir")

    def on_mouse_down(self, e):
        self.mouse = e.pos
        if self.rename is not None:                     # clicking away keeps the typed name
            self.finish_rename(True)
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
        elif e.button == 1 and atlas.collidepoint(e.pos):
            index = self.tile_index_at(e.pos)
            cell = (index % self.atlas_cols, index // self.atlas_cols)
            self.atlas_drag = (cell, cell)
        elif area.collidepoint(e.pos):
            if e.button == 2 or (e.button == 1 and pygame.key.get_pressed()[pygame.K_SPACE]):
                self.pan_drag = True
            elif e.button in (1, 3):
                self.confirm = None
                self.map_click(self.cell_at(e.pos), e.button)

    def on_mouse_up(self, e):
        self.mouse = e.pos
        if e.button == 1 and self.atlas_drag:
            self.finish_atlas_drag()
        if e.button == 1 and self.stairs_drag:
            self.finish_stairs()
        if e.button in (1, 3):
            self.stroke = self.last_cell = None
        if e.button == 1:
            self.look_drag = self.camera_drag = False
        if e.button in (1, 2):
            self.pan_drag = False

    def on_mouse_move(self, e):
        self.mouse = e.pos
        if self.look_drag and self.preview is not None:
            self.preview.look(e.rel[0] * MOUSE_SENSITIVITY, -e.rel[1] * MOUSE_SENSITIVITY)
        elif self.camera_drag and self.preview is not None:
            self.preview.aim(*self.map_point(e.pos))
        elif self.atlas_drag:
            rect = self.atlas_rect()            # clamp so dragging outside keeps the nearest tile
            x = min(max(e.pos[0], rect.left), rect.right - 1)
            y = min(max(e.pos[1], rect.top), rect.bottom - 1)
            self.atlas_drag = (self.atlas_drag[0], ((x - rect.x) // TILE, (y - rect.y) // TILE))
        elif self.stairs_drag:
            self.stairs_drag = (self.stairs_drag[0], self.cell_at(e.pos))
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
        if self.over_preview():                 # the wheel walks the camera forward / back
            if self.preview is not None:
                self.preview.nudge(1 if e.y > 0 else -1, abs(e.y))
            return
        area = self.map_area()
        if not area.collidepoint(self.mouse):
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
        self.draw_map(screen)
        self.draw_panel(screen)
        self.draw_preview(screen)
        self.draw_legend(screen)
        self.draw_status(screen)
        self.draw_toolbar(screen)
        self.draw_dropdown(screen)
        title = f"Map editor - {os.path.basename(self.path)}{' *' if self.dirty else ''}"
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
        if layer == "walls":
            pygame.draw.rect(screen, EMPTY_CELL, rect)
        elif layer in ("floor_tex", "ceil_tex"):
            screen.blit(self.tile_surface(grids[g()][y][x] - 1), rect)
        else:
            source = "ceil_h" if layer == "ceil_h" else "floor_h"
            value = grids[g(source)][y][x]
            colour = heat(value, *HEIGHT_RANGE[source])
            if layer == "ramp":
                colour = tuple(c // 2 for c in colour)
            pygame.draw.rect(screen, colour, rect)
            if layer in VALUE_LAYERS and self.zoom >= 24:
                label = self.small.render(fmt(value), True, (10, 10, 20))
                screen.blit(label, label.get_rect(center=rect.center))
        if layer == "ramp" and grids[g("ramp")][y][x]:
            self.draw_arrow(screen, rect, grids[g("ramp")][y][x], ACCENT)
        if self.zoom >= 16 and any(level.span_present(s, x, y) for s in range(floor + 1, level.floor_count)):
            draw_upper_mark(screen, rect)

    def draw_wall_ceiling(self, screen, x, y, rect):
        """A wall on the CeilH layer where the ceiling over it matters: coloured like a ceiling, with
        the number if it was set, or the number in (brackets), duller, while it is automatic."""
        level = self.level
        value = level.wall_ceiling(x, y)
        explicit = level.has_explicit_wall_ceiling(x, y)
        colour = heat(value, *HEIGHT_RANGE["ceil_h"])
        pygame.draw.rect(screen, colour if explicit else tuple(c * 2 // 3 for c in colour), rect)
        if level.short_wall_top(x, y) is not None:
            draw_short_wall_mark(screen, rect)
        if self.zoom >= 24:
            text = self.small.render(fmt(value) if explicit else f"({fmt(value)})", True, (10, 10, 20))
            screen.blit(text, text.get_rect(center=rect.center))

    def draw_wall_height(self, screen, x, y, rect):
        """A wall on the WallH layer: coloured by its height, with the number, or 'full'."""
        level = self.level
        value = level.grids["wall_h"][y][x]
        if level.short_wall_top(x, y) is None:          # 0, or tall enough to reach the ceiling
            colour, label = WALL_FULL, ("full" if value <= 0 else fmt(value))
            text_colour = (255, 255, 255)
        else:
            colour, label = heat(value, *HEIGHT_RANGE["wall_h"]), fmt(value)
            text_colour = (10, 10, 20)
        pygame.draw.rect(screen, colour, rect)
        if self.zoom >= 24:
            text = self.small.render(label, True, text_colour)
            screen.blit(text, text.get_rect(center=rect.center))

    def draw_arrow(self, screen, rect, kind, colour):
        dx, dy = RAMP_VECTORS[kind]
        cx, cy, r = rect.centerx, rect.centery, rect.w * 0.32
        tip = (cx + dx * r, cy + dy * r)
        tail = (cx - dx * r, cy - dy * r)
        side = (-dy * r * 0.7, dx * r * 0.7)
        pygame.draw.line(screen, colour, tail, tip, max(2, rect.w // 10))
        pygame.draw.polygon(screen, colour, [tip, (cx + side[0], cy + side[1]), (cx - side[0], cy - side[1])])

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
        self.draw_start(screen)
        self.draw_camera(screen)
        self.draw_cursor(screen, area)
        screen.set_clip(None)

    def draw_entities(self, screen):
        """Items on the floor being edited: their sprite on the map, ringed in the colour of their mode
        (white once, cyan respawning, green staying)."""
        z = self.zoom
        origin = self.cell_rect(0, 0)
        size = max(8, int(z * 0.7))
        for e in self.level.entities:
            if e.span != self.floor:
                continue
            cx, cy = round(origin.x + e.x * z), round(origin.y + e.y * z)
            sprite = pygame.transform.scale(self.tiles[max(0, min(e.tile, len(self.tiles) - 1))], (size, size))
            pygame.draw.circle(screen, (20, 20, 30), (cx, cy), size // 2 + 2)
            screen.blit(sprite, sprite.get_rect(center=(cx, cy)))
            pygame.draw.circle(screen, ENTITY_MODE_COLOURS[e.mode], (cx, cy), size // 2 + 2, 2)

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
        problem cells, and the arrow and height colours only on the layers that draw them."""
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
        if self.layer in VALUE_LAYERS or self.layer == "ramp":
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
            colour = heat(3.0, *HEIGHT_RANGE["ceil_h"])
            pygame.draw.rect(screen, tuple(c * 2 // 3 for c in colour), box)
            text = self.small.render("(n)", True, (10, 10, 20))
            screen.blit(text, text.get_rect(center=box.center))
        elif kind == "ramp":
            pygame.draw.rect(screen, tuple(c // 2 for c in heat(1.0, *HEIGHT_RANGE["floor_h"])), box)
            self.draw_arrow(screen, box, 1, ACCENT)

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

    def draw_cursor(self, screen, area):
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
            colour = {"erase": WARN, "fill": (120, 200, 255), "pick": (200, 120, 255),
                      "start": (60, 220, 110), "stairs": (120, 200, 255)}.get(self.tool, ACCENT)
            pygame.draw.rect(screen, colour, self.cell_rect(*cell), 2)

    def draw_panel(self, screen):
        h = self._size()[1]
        pygame.draw.rect(screen, PANEL_BG, (0, TOOLBAR_H, PANEL_W, h - TOOLBAR_H - STATUS_H))
        screen.blit(self.atlas_backdrop, self.atlas_rect())      # shows through transparent pixels
        screen.blit(self.atlas_img, self.atlas_rect())
        screen.blit(self.atlas_grid, self.atlas_rect())
        shown = self.drag_indices() if self.atlas_drag and not (self.mods() & pygame.KMOD_CTRL) \
            else (self.selection | (self.drag_indices() if self.atlas_drag else set()))
        veil = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        veil.fill((255, 205, 60, 70))
        for index in shown:
            rect = self.tile_rect(index)
            screen.blit(veil, rect)
            pygame.draw.rect(screen, ACCENT, rect, 2)
        hover = self.tile_index_at(self.mouse)
        if hover is not None:
            pygame.draw.rect(screen, TEXT, self.tile_rect(hover), 1)
        if self.layer not in STAMP_LAYERS:              # the atlas is not what this layer paints with
            shade = pygame.Surface(self.atlas_img.get_size(), pygame.SRCALPHA)
            shade.fill((20, 20, 26, 150))
            screen.blit(shade, self.atlas_rect())

        y, cell, _after, hints_y = self.panel_metrics()
        count = len(self.selection)
        screen.blit(self.font.render(f"Selected: {count} tile{'s' if count != 1 else ''}", True, TEXT), (ATLAS_X, y))
        for dx, dy, tile_id in self.stamp():
            small = pygame.transform.scale(self.tiles[tile_id - 1], (cell, cell))
            screen.blit(small, (ATLAS_X + dx * cell, y + 22 + dy * cell))
        hints = ("Atlas: click / drag = select, Ctrl = add/remove",
                 "Map: L-drag paint, R-drag erase, wheel zoom, Space+drag pan",
                 "Tab floor, layers 1-7, tools B E F I S T C, [ ] value, R ramp, K key")
        for i, text in enumerate(hints):
            screen.blit(self.small.render(text, True, DIM), (ATLAS_X, hints_y + i * 16))

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
        base = self.atlas_rect()
        return pygame.Rect(base.x + (index % self.atlas_cols) * TILE,
                           base.y + (index // self.atlas_cols) * TILE, TILE, TILE)

    def draw_toolbar(self, screen):
        pygame.draw.rect(screen, PANEL_BG, (0, 0, self._size()[0], TOOLBAR_H))
        self.layout()
        for rect, label, action in self.buttons:
            if action == "dropdown":
                self.draw_dropdown_button(screen, rect, label)
                continue
            active = action in (f"tool:{self.tool}", f"layer:{self.layer}") \
                or (action == "legend" and self.show_legend)
            colour = BUTTON_ON if active else (BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON)
            pygame.draw.rect(screen, colour, rect, border_radius=4)
            text = self.font.render(label, True, TEXT)
            screen.blit(text, text.get_rect(center=rect.center))
        for text, pos, colour in self.readouts:
            screen.blit(self.font.render(text, True, colour), pos)

    def draw_dropdown_button(self, screen, rect, label):
        """The closed dropdown: the current floor's name and an arrow, or a text box while renaming."""
        if self.rename is not None:
            pygame.draw.rect(screen, (24, 26, 32), rect, border_radius=4)
            pygame.draw.rect(screen, ACCENT, rect, 2, border_radius=4)
            caret = "|" if int(time.time() * 2) % 2 == 0 else " "
            screen.blit(self.font.render(self.rename + caret, True, TEXT), (rect.x + 8, rect.y + 8))
            return
        colour = BUTTON_ON if self.dropdown_open else (BUTTON_HOT if rect.collidepoint(self.mouse) else BUTTON)
        pygame.draw.rect(screen, colour, rect, border_radius=4)
        screen.blit(self.font.render(label, True, TEXT), (rect.x + 10, rect.y + 8))
        cx, cy = rect.right - 16, rect.centery
        arrow = [(cx - 6, cy - 3), (cx + 6, cy - 3), (cx, cy + 4)]
        pygame.draw.polygon(screen, TEXT, arrow)

    def draw_dropdown(self, screen):
        """The open floor list, drawn last so it sits on top of everything."""
        if not self.dropdown_open:
            return
        for index, (rect, label, action) in enumerate(self.dropdown_items()):
            current = action == f"floor:{self.floor}"
            colour = BUTTON_ON if current else (BUTTON_HOT if rect.collidepoint(self.mouse) else PANEL_BG)
            pygame.draw.rect(screen, colour, rect)
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


def main():
    path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else MAP_PATH
    pygame.init()
    pygame.display.set_mode((1280, 860), pygame.RESIZABLE)
    if not os.path.exists(ATLAS_PATH):
        sys.exit("textures.png not found - run `python make_atlas.py` first")
    editor = Editor(path)
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
