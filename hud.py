"""What is drawn over the game picture: health and score, the inventory, and the equipped gun."""
import pygame

from constants import HEIGHT, WIDTH

TEXT = (255, 255, 255)
SHADOW = (0, 0, 0)
HIGHLIGHT = (255, 240, 120)
DIM = (170, 170, 180)
UNIT = HEIGHT / 8                      # a gun's size of 1.0 draws its 32 pixel tile this many pixels tall


def shadowed(picture, font, text, pos, color=TEXT, center=False):
    label, shade = font.render(text, True, color), font.render(text, True, SHADOW)
    if center:
        pos = (pos[0] - label.get_width() // 2, pos[1])
    picture.blit(shade, (pos[0] + 1, pos[1] + 1))
    picture.blit(label, pos)
    return label.get_width()


def weapon_picture(tile, size):
    """The gun's picture: the tile cropped to what is drawn in it and scaled up (crisp pixels) by `size`."""
    box = tile.get_bounding_rect()
    if box.w == 0 or box.h == 0:
        return None
    scale = size * UNIT / tile.get_width()
    return pygame.transform.scale(tile.subsurface(box), (max(1, round(box.w * scale)), max(1, round(box.h * scale))))


def draw_weapon(picture, tiles, state, kick=0.0):
    """The equipped gun at the bottom of the picture, kicked back by `kick` (0..1) after a shot and
    dipped while it reloads."""
    if state is None:
        return
    gun = state.gun
    art = weapon_picture(tiles[max(0, min(gun.tile, len(tiles) - 1))], gun.size)
    if art is None:
        return
    dip = art.get_height() * (0.6 if state.reloading else 0.0)
    x = WIDTH // 2 + int(WIDTH * 0.1) - art.get_width() // 2
    y = HEIGHT - art.get_height() + 4 + int(kick * art.get_height() * 0.12) + int(dip)
    picture.blit(art, (x, y))


def draw_hud(picture, font, stats, message, inventory=None, tiles=None, kick=0.0):
    shadowed(picture, font, f"Health {stats.health:g}", (8, 8))
    shadowed(picture, font, f"Score {stats.score:g}", (8, 26))
    if message:
        shadowed(picture, font, message, (picture.get_width() // 2, picture.get_height() // 2 + 40),
                 HIGHLIGHT, center=True)
    if inventory is None:
        return
    y = picture.get_height() - 8
    for name, count in sorted(inventory.items.items(), reverse=True):          # carried items, bottom left
        y -= 18
        shadowed(picture, font, f"{name} x{count}", (8, y), DIM)
    if inventory.items:
        shadowed(picture, font, "Inventory", (8, y - 18), HIGHLIGHT)
    for slot, state in enumerate(inventory.guns):                              # the guns, top right
        out = slot == inventory.equipped
        ammo = "reloading" if state.reloading else f"{state.mag}/{state.reserve}"
        text = f"{slot + 1} {state.gun.name}  {ammo}"
        label = font.render(text, True, HIGHLIGHT if out else DIM)
        shadowed(picture, font, text, (picture.get_width() - label.get_width() - 8, 8 + slot * 18),
                 HIGHLIGHT if out else DIM)
    if tiles is not None:
        draw_weapon(picture, tiles, inventory.current(), kick)
