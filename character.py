"""A very basic character picture for other players: a little person seen from any side.

Sprites are tiles in the texture array, so these are made here and appended after the atlas's own
tiles (see main.py). The pictures are drawn in assets/character.png (see make_character.py); each
shirt color (so players can be told apart) gets its own copy with the shirt recolored, VIEWS
pictures per shirt from the front round to the back, and the one drawn follows which way the player
faces relative to the viewer.
"""
import math
import os

import pygame

from constants import TILE

SHIRTS = [(200, 60, 60), (60, 120, 210), (70, 170, 80), (225, 190, 60),
          (160, 90, 200), (230, 130, 50), (70, 190, 190), (210, 210, 210)]
VIEWS = 8                                           # pictures per shirt: 45 degrees apart
SHEET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "character.png")
SHEET_TILE = 32                                     # the sheet's tiles; scaled to TILE when that differs
SHEET_VIEWS = VIEWS // 2 + 1                        # front, turned, profile, turned away, back
SHIRT_MARK = (255, 0, 255)                          # the sheet's pixels of this color are the player's shirt


def character_tiles(path=SHEET_PATH):
    """VIEWS pictures per shirt color (shirt by shirt, see character_view), transparent around the figure."""
    sheet = pygame.image.load(path)
    if sheet.get_width() != SHEET_TILE * SHEET_VIEWS or sheet.get_height() != SHEET_TILE:
        raise ValueError(f"{path} should be {SHEET_VIEWS} tiles of {SHEET_TILE}x{SHEET_TILE} in one row")
    sheet = sheet.convert_alpha() if pygame.display.get_surface() else sheet.convert(32, pygame.SRCALPHA)
    turned = [sheet.subsurface((view * SHEET_TILE, 0, SHEET_TILE, SHEET_TILE)).copy() for view in range(SHEET_VIEWS)]
    if SHEET_TILE != TILE:
        turned = [pygame.transform.scale(view, (TILE, TILE)) for view in turned]
    return [view for shirt in SHIRTS for view in draw_views(turned, shirt)]


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
