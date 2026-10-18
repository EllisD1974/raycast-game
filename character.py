"""A very basic character picture for other players: a little person facing the camera.

Sprites are tiles in the texture array, so these are drawn here and appended after the atlas's own
tiles (see main.py). One variant per shirt colour so players can be told apart.
"""
import pygame

from constants import TILE

SHIRTS = [(200, 60, 60), (60, 120, 210), (70, 170, 80), (225, 190, 60),
          (160, 90, 200), (230, 130, 50), (70, 190, 190), (210, 210, 210)]
SKIN = (235, 190, 150)
TROUSERS = (50, 55, 90)
OUTLINE = (20, 20, 28)


def character_tiles():
    """One TILE x TILE picture per shirt colour, transparent around the figure."""
    return [draw_character(shirt) for shirt in SHIRTS]


def draw_character(shirt):
    u = TILE / 32                                   # drawn on a 32 pixel grid, scaled to the tile size
    tile = pygame.Surface((TILE, TILE), pygame.SRCALPHA)

    def block(x, y, w, h, colour):
        pygame.draw.rect(tile, OUTLINE, (round((x - 1) * u), round((y - 1) * u), round((w + 2) * u), round((h + 2) * u)))
        pygame.draw.rect(tile, colour, (round(x * u), round(y * u), round(w * u), round(h * u)))

    block(11, 23, 4, 8, TROUSERS)                   # legs
    block(17, 23, 4, 8, TROUSERS)
    block(6, 12, 4, 9, shirt)                       # arms
    block(22, 12, 4, 9, shirt)
    block(10, 12, 12, 12, shirt)                    # body
    block(12, 2, 8, 9, SKIN)                        # head
    for x in (14, 18):                              # eyes
        pygame.draw.rect(tile, OUTLINE, (round(x * u), round(5 * u), max(1, round(u)), max(1, round(2 * u))))
    return tile
