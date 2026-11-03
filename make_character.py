"""Generates assets/character.png: the pictures of a player seen by someone else (see character.py).

Run once:  python make_character.py            (refuses to overwrite an existing character.png; one made before
                                               there were crouching pictures gets the crouching row added, its
                                               standing row kept as it is)
           python make_character.py --force    regenerates it, replacing any hand-made changes

The sheet is two rows of 5 tiles of 32x32 pixels: the character standing (top row) and crouching (bottom row),
seen from the front, turned a bit, in profile, turned away and from the back (the other three views are these
mirrored). A crouching player is drawn on the same size of tile as a standing one, so the crouching figure stands
on the tile's bottom edge and only reaches about two thirds of the way up (its head where a crouching body's top is).
Edit it in any image editor, keeping a transparent background. Paint the shirt (and anything else that should take
the player's color) in pure magenta (255, 0, 255): character.py swaps that for each player's shirt.
"""
import os
import sys

import pygame

TILE = 32
VIEWS = 5
ROWS = 2                                            # standing, crouching
SHIRT = (255, 0, 255)                               # the color character.py replaces with a player's own
SKIN = (235, 190, 150)
HAIR = (90, 60, 40)
TROUSERS = (50, 55, 90)
OUTLINE = (20, 20, 28)
PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "character.png")

# body x and width, arm x positions, head x and width, eye x positions, hair height (0 for none), per view
SHAPES = {
    0: (10, 12, (6, 22), 12, 8, (14, 18), 0),
    1: (11, 10, (8, 21), 11, 9, (12, 16), 0),
    2: (12, 8, (14,), 12, 8, (13,), 0),
    3: (11, 10, (8, 21), 12, 9, (), 5),
    4: (10, 12, (6, 22), 12, 8, (), 9),
}


def painter(tile):
    def block(x, y, w, h, color):
        pygame.draw.rect(tile, OUTLINE, (x - 1, y - 1, w + 2, h + 2))
        pygame.draw.rect(tile, color, (x, y, w, h))
    return block


def draw_head(tile, block, view, top):
    """The head with its top at row `top`: face, hair, the nose in profile, the eyes."""
    _body_x, _body_w, _arms, head_x, head_w, eyes, hair = SHAPES[view]
    block(head_x, top, head_w, 9, SKIN)
    if hair:
        block(head_x, top, head_w, hair, HAIR)
    if view == 2:
        block(10, top + 4, 2, 3, SKIN)                              # nose, pointing the way the character faces
    for x in eyes:
        pygame.draw.rect(tile, OUTLINE, (x, top + 3, 1, 2))


def draw_view(view):
    """One standing picture: view 0 the front, 1 turned a bit to the viewer's left, 2 in profile, 3 turned away,
    4 the back."""
    tile = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    block = painter(tile)
    body_x, body_w, arms, *_head = SHAPES[view]
    profile = view == 2
    for x in (13, 17) if profile else (11, 17):                     # legs
        block(x, 23, 3 if profile else 4, 8, TROUSERS)
    block(body_x, 12, body_w, 12, SHIRT)                            # body, then arms (in front of it in profile)
    for x in arms:
        block(x, 12, 4, 9, SHIRT)
    draw_head(tile, block, view, 2)
    return tile


def draw_crouched_view(view):
    """One crouching picture, the same views as draw_view: knees bent and apart, the body low and a little hunched,
    the arms resting forward on the knees. The figure is about 22 pixels tall, standing on the tile's bottom edge."""
    tile = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    block = painter(tile)
    body_x, body_w, arms, *_head = SHAPES[view]
    if view == 2:                                                   # in profile, facing the viewer's left
        block(16, 27, 5, 4, TROUSERS)                               # the back leg, folded under the hips
        block(13, 19, 7, 7, SHIRT)                                  # the body, hunched forward
        block(7, 24, 12, 3, TROUSERS)                               # the thigh, out level to the knee
        block(7, 26, 3, 5, TROUSERS)                                # the shin, straight down to the foot
        block(7, 21, 9, 3, SHIRT)                                   # the arm, reaching forward over the knee
        draw_head(tile, block, view, 10)
        return tile
    spread = 2 if view in (1, 3) else 0                             # turned a bit: the knees look closer together
    hips = body_x + body_w // 2
    for side in (-1, 1):                                            # each leg: thigh out to a wide knee, shin down
        knee = hips + side * (11 - spread) - (3 if side > 0 else 0)
        block(min(hips, knee), 24, abs(hips - knee) + 3, 3, TROUSERS)
        block(knee, 26, 3, 5, TROUSERS)
    block(body_x, 18, body_w, 7, SHIRT)                             # the body, short and hunched between the knees
    for x in arms:                                                  # the forearms, resting on the knees
        block(x + (2 if x < body_x else -2), 20, 3, 5, SHIRT)
    draw_head(tile, block, view, 10)
    return tile


def standing_row():
    """The top row as it is in an existing character.png (it may have been edited), or None."""
    if not os.path.exists(PATH):
        return None
    sheet = pygame.image.load(PATH)
    if sheet.get_width() != TILE * VIEWS or sheet.get_height() not in (TILE, TILE * ROWS):
        return None
    return sheet.subsurface((0, 0, TILE * VIEWS, TILE)).copy()


def main():
    force = "--force" in sys.argv
    existing = None if force else standing_row()
    if existing is None and os.path.exists(PATH) and not force:
        sys.exit(f"{PATH} is not a sheet this script knows - pass --force to replace it")
    if not force and existing is not None and pygame.image.load(PATH).get_height() == TILE * ROWS:
        sys.exit(f"{PATH} already has its crouching row - pass --force to replace it")
    sheet = pygame.Surface((TILE * VIEWS, TILE * ROWS), pygame.SRCALPHA)
    for view in range(VIEWS):
        if existing is None:
            sheet.blit(draw_view(view), (view * TILE, 0))
        sheet.blit(draw_crouched_view(view), (view * TILE, TILE))
    if existing is not None:
        sheet.blit(existing, (0, 0))                                # (an edited standing row stays as it was)
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    pygame.image.save(sheet, PATH)
    print("wrote", PATH, "(added the crouching row)" if existing is not None else "")


if __name__ == "__main__":
    main()
