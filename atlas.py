"""Loading the texture atlas (assets/textures.png), shared by the game and the editor.

The atlas may have an alpha channel (paint it with transparent pixels in any image editor). Tiles
with any transparent or semi-transparent pixel are see-through when used as walls: fully transparent
pixels show what is behind, partly transparent ones blend (glass).
"""
import io
import os

import numpy as np
import pygame

from constants import TILE

ATLAS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "textures.png")


def unpack_atlas(source=ATLAS_PATH, tile=TILE):
    """Slice the texture map into individual tile x tile surfaces, row by row, keeping alpha.

    `source` is the file's path, or the bytes of the PNG (what a host sends to its joiners).
    Map id N uses tiles[N - 1]. Works with or without a display (the game draws through a GPU renderer and
    sets no display mode, which convert_alpha() needs).
    """
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    atlas = pygame.image.load(source, "textures.png")
    atlas = atlas.convert_alpha() if pygame.display.get_surface() else atlas.convert(32, pygame.SRCALPHA)
    return [
        atlas.subsurface((x, y, tile, tile)).copy()
        for y in range(0, atlas.get_height(), tile)
        for x in range(0, atlas.get_width(), tile)
    ]


def atlas_array(tiles):
    """Stack tile surfaces into one uint8 array indexed [tile, y, x, rgba] for the renderer.

    A tile without an alpha channel is fully opaque (alpha 255)."""
    def rgba(tile):
        rgb = pygame.surfarray.array3d(tile)
        alpha = pygame.surfarray.array_alpha(tile)[..., None]
        return np.concatenate([rgb, alpha], axis=2).swapaxes(0, 1)       # [x, y, c] -> [y, x, c]

    return np.ascontiguousarray(np.stack([rgba(t) for t in tiles]).astype(np.uint8))


def ensure_rgba(textures):
    """The same textures with an alpha channel (opaque) if they only had color."""
    if textures.shape[-1] == 4:
        return textures
    opaque = np.full(textures.shape[:-1] + (1,), 255, np.uint8)
    return np.ascontiguousarray(np.concatenate([textures, opaque], axis=-1))


def transparent_tiles(textures):
    """Boolean array, one per tile: True if the tile has any pixel that is not fully opaque."""
    return (ensure_rgba(textures)[..., 3] < 255).any(axis=(1, 2))
