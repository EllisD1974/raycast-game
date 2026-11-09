"""A very basic character picture for other players: a little person seen from any side.

Sprites are tiles in the texture array, so these are made here and appended after the atlas's own
tiles (see main.py). The pictures are drawn in assets/character.png (see make_character.py); each
shirt color (so players can be told apart) gets its own copy with the shirt recolored: VIEWS
pictures standing, from the front round to the back, then VIEWS crouching (PICTURES per shirt). The one
drawn follows which way the player faces relative to the viewer, and whether they crouch.

Other pictures in assets/ laid out the same way are sprite sheets for enemies (sheet_names): each adds one
copy, PICTURES tiles, after the players' (sheet_tiles; enemies pick theirs with Enemy.sheet).
"""
import functools
import math
import os

import pygame

from constants import TILE
from make_character import draw_crouched_view

SHIRTS = [(200, 60, 60), (60, 120, 210), (70, 170, 80), (225, 190, 60),
          (160, 90, 200), (230, 130, 50), (70, 190, 190), (210, 210, 210)]
VIEWS = 8                                           # pictures per pose: 45 degrees apart
POSES = 2                                           # standing, crouching
PICTURES = VIEWS * POSES                            # pictures per shirt
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
SHEET_PATH = os.path.join(ASSETS, "character.png")
NOT_SHEETS = ("character", "textures")              # pictures in assets/ that are not enemies' sprite sheets
SHEET_TILE = 32                                     # the sheet's tiles; scaled to TILE when that differs
SHEET_VIEWS = VIEWS // 2 + 1                        # front, turned, profile, turned away, back
SHIRT_MARK = (255, 0, 255)                          # the sheet's pixels of this color are the player's shirt
ENEMY_SHIRT = 2                                     # the shirt enemies wear (green)


def character_tiles(path=SHEET_PATH):
    """PICTURES pictures per shirt color (shirt by shirt: VIEWS standing then VIEWS crouching, see character_view),
    transparent around the figure. A sheet from before there were crouching pictures (one row) gets the ones
    make_character.py draws."""
    poses = sheet_poses(path)
    return [picture for shirt in SHIRTS for pose in poses for picture in draw_views(pose, shirt)]


@functools.lru_cache(maxsize=None)
def sheet_names(folder=ASSETS):
    """The enemies' sprite sheets: the names of the pictures in `folder` laid out like character.png (other than
    NOT_SHEETS), in order. Their tiles follow the players' in that order (sheet_tiles)."""
    names = []
    for entry in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        name, ext = os.path.splitext(entry)
        if ext.lower() != ".png" or name in NOT_SHEETS:
            continue
        try:
            size = pygame.image.load(os.path.join(folder, entry)).get_size()
        except pygame.error:
            continue
        if size[0] == SHEET_TILE * SHEET_VIEWS and size[1] in (SHEET_TILE, SHEET_TILE * POSES):
            names.append(name)
    return tuple(names)


def sheet_tiles(folder=ASSETS):
    """PICTURES pictures for each of sheet_names, sheet by sheet (as character_tiles' for one shirt: its
    SHIRT_MARK pixels, if any, in an enemy's green)."""
    return [picture for name in sheet_names(folder) for pose in sheet_poses(os.path.join(folder, name + ".png"))
            for picture in draw_views(pose, SHIRTS[ENEMY_SHIRT])]


def sheet_poses(path):
    """The pictures of a sheet laid out like character.png: [standing views, crouching views], each SHEET_VIEWS
    pictures TILE square."""
    sheet = pygame.image.load(path)
    if sheet.get_width() != SHEET_TILE * SHEET_VIEWS or sheet.get_height() not in (SHEET_TILE, SHEET_TILE * POSES):
        raise ValueError(f"{path} should be {SHEET_VIEWS} tiles of {SHEET_TILE}x{SHEET_TILE} in a row, standing, "
                         "and the same again crouching under them")
    sheet = sheet.convert_alpha() if pygame.display.get_surface() else sheet.convert(32, pygame.SRCALPHA)
    poses = [[sheet.subsurface((view * SHEET_TILE, row * SHEET_TILE, SHEET_TILE, SHEET_TILE)).copy()
              for view in range(SHEET_VIEWS)] for row in range(sheet.get_height() // SHEET_TILE)]
    if len(poses) < POSES:
        poses.append([draw_crouched_view(view) for view in range(SHEET_VIEWS)])
    if SHEET_TILE != TILE:
        poses = [[pygame.transform.scale(view, (TILE, TILE)) for view in pose] for pose in poses]
    return poses


def character_view(viewer_angle, angle):
    """Which of a character's VIEWS the viewer sees when looking along `viewer_angle` at someone facing
    `angle`: 0 is the front (facing the viewer), 2 facing the viewer's left, 4 the back, 6 facing their right."""
    turn = (angle - viewer_angle - math.pi) % math.tau
    return round(turn / (math.tau / VIEWS)) % VIEWS


def draw_views(turned, shirt):
    """The VIEWS pictures of one character in `shirt`, from the front round to the back. The right-hand
    ones (5 to 7) are the left-hand ones (3 to 1) mirrored."""
    left = [tint(view, shirt) for view in turned]
    return left + [pygame.transform.flip(left[VIEWS - view], True, False) for view in range(len(left), VIEWS)]


def tint(picture, shirt):
    """A copy of `picture` with its shirt-colored pixels (SHIRT_MARK) in `shirt`."""
    picture = picture.copy()
    rgb = pygame.surfarray.pixels3d(picture)
    rgb[(rgb == SHIRT_MARK).all(axis=2)] = shirt
    del rgb                                         # let go of the surface's pixels
    return picture
