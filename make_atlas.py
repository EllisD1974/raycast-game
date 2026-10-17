"""Generates textures.png: a texture map (atlas) of 32x32 tiles with room for 256.

Run once:  python make_atlas.py            (refuses to overwrite an existing textures.png;
           python make_atlas.py --force    regenerates it, replacing any hand-made changes)
main.py then loads the atlas and unpacks it into one surface per tile.

You can edit textures.png in any image editor. Give a tile transparent or semi-transparent pixels
(a PNG alpha channel) and walls made from it become see-through: fully transparent pixels show what
is behind (a fence, a window frame), partly transparent ones blend (glass).

The atlas is COLUMNS x ROWS tiles (16x16 = 256 slots, 512x512 px). Only the tiles in
TEXTURES below are drawn; every other slot shows a magenta/black "missing texture"
checker so an unpopulated map id is obvious. To add a texture, write a function
like brick() and append it to TEXTURES. Its index (row-major) is its map id - 1.
Tile order: 0 brick, 1 mossy stone, 2 wood, 3 blue tiles, 4 floor, 5 ceiling, 6-9 left free for
hand-drawn textures, 10 gem, 11 heart, 12 coin, 13 key, 14 bullet, 16 pistol. Tiles 10-14 are sprites for map entities: they have transparent corners, so
only the shape is drawn.
Map ids are index + 1; mapfile.DEFAULTS uses ids 5 and 6 as the default floor and ceiling.
"""
import os
import random

import pygame

TILE = 32
COLUMNS = ROWS = 16


def clamp(v):
    return max(0, min(255, int(v)))


def noisy(color, amount, rng):
    n = rng.randint(-amount, amount)
    return tuple(clamp(c + n) for c in color)


def brick(rng):
    s = pygame.Surface((TILE, TILE))
    s.fill((170, 165, 155))                                  # mortar
    for row in range(4):
        offset = 8 if row % 2 else 0
        for col in range(-1, 3):
            x = col * 16 + offset
            tint = noisy((150, 62, 45), 18, rng)
            pygame.draw.rect(s, tint, (x + 1, row * 8 + 1, 14, 6))
    return s


def mossy_stone(rng):
    s = pygame.Surface((TILE, TILE))
    for y in range(TILE):
        for x in range(TILE):
            base = (110, 112, 116)
            if rng.random() < 0.18:
                base = (70, 120, 70)                         # moss speckle
            s.set_at((x, y), noisy(base, 14, rng))
    pygame.draw.rect(s, (60, 60, 64), (0, 0, TILE, TILE), 1)
    pygame.draw.line(s, (60, 60, 64), (0, 16), (TILE, 16))
    return s


def wood(rng):
    s = pygame.Surface((TILE, TILE))
    for plank in range(4):
        base = noisy((150, 100, 55), 14, rng)
        pygame.draw.rect(s, base, (plank * 8, 0, 8, TILE))
        for _ in range(4):                                   # grain lines
            gx = plank * 8 + rng.randint(1, 6)
            pygame.draw.line(s, noisy((115, 75, 40), 8, rng), (gx, 0), (gx, TILE))
        pygame.draw.line(s, (70, 45, 25), (plank * 8, 0), (plank * 8, TILE))
    return s


def blue_tiles(rng):
    s = pygame.Surface((TILE, TILE))
    for ty in range(2):
        for tx in range(2):
            color = (50, 80, 190) if (tx + ty) % 2 == 0 else (90, 130, 220)
            pygame.draw.rect(s, noisy(color, 8, rng), (tx * 16, ty * 16, 16, 16))
    pygame.draw.rect(s, (25, 35, 90), (0, 0, TILE, TILE), 1)
    return s


def missing(_rng=None):
    """Placeholder for unpopulated slots: magenta/black checker."""
    s = pygame.Surface((TILE, TILE))
    half = TILE // 2
    for ty in range(2):
        for tx in range(2):
            color = (255, 0, 255) if (tx + ty) % 2 == 0 else (0, 0, 0)
            pygame.draw.rect(s, color, (tx * half, ty * half, half, half))
    return s


def floor_tile(rng):
    """Default floor (map id 5): worn stone slabs."""
    s = pygame.Surface((TILE, TILE))
    for ty in range(2):
        for tx in range(2):
            pygame.draw.rect(s, noisy((122, 118, 110), 10, rng), (tx * 16, ty * 16, 16, 16))
    for y in range(TILE):
        for x in range(TILE):
            if rng.random() < 0.25:
                s.set_at((x, y), noisy(s.get_at((x, y))[:3], 8, rng))
    pygame.draw.line(s, (70, 68, 64), (0, 0), (TILE, 0))
    pygame.draw.line(s, (70, 68, 64), (0, 0), (0, TILE))
    pygame.draw.line(s, (70, 68, 64), (0, 16), (TILE, 16))
    pygame.draw.line(s, (70, 68, 64), (16, 0), (16, TILE))
    return s


def ceiling_panel(rng):
    """Default ceiling (map id 6): dark panels with a lighter rim."""
    s = pygame.Surface((TILE, TILE))
    s.fill(noisy((62, 64, 78), 3, rng))
    for y in range(TILE):
        for x in range(TILE):
            if rng.random() < 0.3:
                s.set_at((x, y), noisy((62, 64, 78), 6, rng))
    pygame.draw.rect(s, (88, 90, 108), (0, 0, TILE, TILE), 1)
    pygame.draw.rect(s, (48, 50, 62), (4, 4, TILE - 8, TILE - 8), 1)
    return s


def _sprite():
    return pygame.Surface((TILE, TILE), pygame.SRCALPHA)


def gem(rng):
    """Item sprite: a cyan diamond."""
    s = _sprite()
    points = ((16, 4), (26, 14), (16, 28), (6, 14))
    pygame.draw.polygon(s, (60, 200, 230), points)
    pygame.draw.polygon(s, (200, 250, 255), ((16, 4), (26, 14), (16, 14), (6, 14)))
    pygame.draw.polygon(s, (20, 90, 140), points, 2)
    return s


def heart(rng):
    """Item sprite: a red heart (health)."""
    s = _sprite()
    pygame.draw.circle(s, (220, 50, 70), (11, 12), 7)
    pygame.draw.circle(s, (220, 50, 70), (21, 12), 7)
    pygame.draw.polygon(s, (220, 50, 70), ((5, 15), (27, 15), (16, 28)))
    pygame.draw.circle(s, (255, 170, 180), (9, 9), 2)
    return s


def coin(rng):
    """Item sprite: a gold coin."""
    s = _sprite()
    pygame.draw.circle(s, (230, 180, 40), (16, 16), 11)
    pygame.draw.circle(s, (150, 105, 20), (16, 16), 11, 2)
    pygame.draw.circle(s, (250, 220, 110), (16, 16), 6, 2)
    return s


def key(rng):
    """Item sprite: a golden key."""
    s = _sprite()
    gold, dark = (235, 190, 50), (140, 100, 20)
    pygame.draw.circle(s, gold, (10, 10), 6)
    pygame.draw.circle(s, (0, 0, 0, 0), (10, 10), 2)
    pygame.draw.rect(s, gold, (14, 14, 5, 14))
    pygame.draw.rect(s, gold, (19, 22, 6, 3))
    pygame.draw.rect(s, gold, (19, 17, 4, 3))
    pygame.draw.circle(s, dark, (10, 10), 6, 1)
    return s


def bullet(rng):
    """Projectile sprite: a small glowing yellow dot."""
    s = _sprite()
    pygame.draw.circle(s, (255, 230, 120), (16, 16), 6)
    pygame.draw.circle(s, (255, 255, 230), (16, 16), 3)
    return s


def pistol(rng):
    """Gun sprite: a plain black pistol seen from the side (the editor's Guns section uses it)."""
    s = _sprite()
    pygame.draw.rect(s, (0, 0, 0), (5, 10, 15, 5))
    pygame.draw.polygon(s, (0, 0, 0), ((18, 10), (21, 10), (26, 19), (21, 19)))
    return s


TEXTURES = (brick, mossy_stone, wood, blue_tiles, floor_tile, ceiling_panel,
            missing, missing, missing, missing,     # 6-9: free slots (draw your own)
            gem, heart, coin, key,
            bullet, missing,                        # 14: bullet sprite, 15: free
            pistol)                                 # 16: the pistol; append new textures here


ATLAS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "textures.png")


def main(path=ATLAS_FILE, force=False):
    """Write the generated atlas to `path`. An existing file is left alone unless force is True:
    textures.png is meant to be edited by hand (including transparent pixels), and regenerating
    it would replace that work with the generated tiles."""
    if os.path.exists(path) and not force:
        raise SystemExit(f"{path} already exists, so it was left alone.\n"
                         "Re-run with --force to regenerate it (this overwrites any changes you made).")
    rng = random.Random(1)
    if len(TEXTURES) > COLUMNS * ROWS:
        raise SystemExit(f"{len(TEXTURES)} textures do not fit in a {COLUMNS}x{ROWS} atlas")
    atlas = pygame.Surface((TILE * COLUMNS, TILE * ROWS), pygame.SRCALPHA)
    for i in range(COLUMNS * ROWS):
        make = TEXTURES[i] if i < len(TEXTURES) else missing
        atlas.blit(make(rng), ((i % COLUMNS) * TILE, (i // COLUMNS) * TILE))
    pygame.image.save(atlas, path)
    print(f"wrote {path} ({atlas.get_width()}x{atlas.get_height()})")


if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)
