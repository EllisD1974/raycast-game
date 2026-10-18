"""Generates assets/character.png: the pictures of a player seen by someone else (see character.py).

Run once:  python make_character.py            (refuses to overwrite an existing character.png;
           python make_character.py --force    regenerates it, replacing any hand-made changes)

The sheet is one row of 5 tiles of 32x32 pixels, the character seen from the front, turned a bit,
in profile, turned away and from the back (the other three views are these mirrored). Edit it in any
image editor, keeping a transparent background. Paint the shirt (and anything else that should take
the player's color) in pure magenta (255, 0, 255): character.py swaps that for each player's shirt.
"""
import os
import sys

import pygame

TILE = 32
VIEWS = 5
SHIRT = (255, 0, 255)                               # the color character.py replaces with a player's own
SKIN = (235, 190, 150)
HAIR = (90, 60, 40)
TROUSERS = (50, 55, 90)
OUTLINE = (20, 20, 28)
PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "character.png")


def draw_view(view):
    """One picture: view 0 the front, 1 turned a bit to the viewer's left, 2 in profile, 3 turned away, 4 the back."""
    tile = pygame.Surface((TILE, TILE), pygame.SRCALPHA)

    def block(x, y, w, h, color):
        pygame.draw.rect(tile, OUTLINE, (x - 1, y - 1, w + 2, h + 2))
        pygame.draw.rect(tile, color, (x, y, w, h))

    # body x and width, arm x positions, head x and width, eye x positions, hair height (0 for none)
    body_x, body_w, arms, head_x, head_w, eyes, hair = {
        0: (10, 12, (6, 22), 12, 8, (14, 18), 0),
        1: (11, 10, (8, 21), 11, 9, (12, 16), 0),
        2: (12, 8, (14,), 12, 8, (13,), 0),
        3: (11, 10, (8, 21), 12, 9, (), 5),
        4: (10, 12, (6, 22), 12, 8, (), 9),
    }[view]
    profile = view == 2
    for x in (13, 17) if profile else (11, 17):                     # legs
        block(x, 23, 3 if profile else 4, 8, TROUSERS)
    block(body_x, 12, body_w, 12, SHIRT)                            # body, then arms (in front of it in profile)
    for x in arms:
        block(x, 12, 4, 9, SHIRT)
    block(head_x, 2, head_w, 9, SKIN)                               # head
    if hair:
        block(head_x, 2, head_w, hair, HAIR)
    if profile:
        block(10, 6, 2, 3, SKIN)                                    # nose, pointing the way the character faces
    for x in eyes:
        pygame.draw.rect(tile, OUTLINE, (x, 5, 1, 2))
    return tile


def main():
    if os.path.exists(PATH) and "--force" not in sys.argv:
        sys.exit(f"{PATH} already exists - pass --force to replace it")
    sheet = pygame.Surface((TILE * VIEWS, TILE), pygame.SRCALPHA)
    for view in range(VIEWS):
        sheet.blit(draw_view(view), (view * TILE, 0))
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    pygame.image.save(sheet, PATH)
    print("wrote", PATH)


if __name__ == "__main__":
    main()
