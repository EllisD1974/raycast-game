"""What is drawn over the game picture: health, score and money, the inventory, the equipped gun, the red flash of
being hurt, and in bomb defusal the round: the score, the timers, the bomb and what the player can do."""
import pygame

from bomb import can_defuse, can_plant, clock_text, site_under
from constants import HEIGHT, WIDTH
from mapfile import CT_TEAM, DEFUSE_KIT, SITE_NAMES, T_TEAM, TEAM_NAMES

TEXT = (255, 255, 255)
SHADOW = (0, 0, 0)
HIGHLIGHT = (255, 240, 120)
DIM = (170, 170, 180)
UNIT = HEIGHT / 8                      # a gun's size of 1.0 draws its 32 pixel tile this many pixels tall
NAME_TEAMMATE, NAME_OPPONENT = (235, 235, 240), (255, 70, 70)   # a name over a teammate's head, and anyone else's
NAME_DISTANCE = 24.0                   # names further away than this are not shown
NAME_LIFT = 0.12                       # how far above the head a name floats, in cells
HURT_COLOR = (220, 20, 20)
HURT_ALPHA = 64                        # how strong the red over the picture is just after a hit (of 255)
HURT_FADE = 3.0                        # the flash fades out in 1 / HURT_FADE seconds
TEAM_COLORS = {T_TEAM: (240, 175, 70), CT_TEAM: (120, 165, 255)}
DANGER = (255, 80, 60)
BAR_BACK, BAR_FILL = (20, 20, 24), (250, 210, 90)


def draw_names(picture, font, renderer, viewer, labels, team):
    """Each other player's name floating over their head: white for a teammate of `team`, red for anyone else.
    A name is hidden when a wall or floor stands between the viewer and that player's head, and far away."""
    from game import same_team                  # (hud draws; game knows the teams)
    width, height = picture.get_size()
    depths = renderer.depth
    for x, y, z, name, their_team in labels:
        spot = renderer.project(viewer, x, y, z + NAME_LIFT)
        if spot is None or spot[2] > NAME_DISTANCE:
            continue
        column, row, depth = spot
        head = renderer.project(viewer, x, y, z - 0.05)                     # just under the top of the head
        if head is None:
            continue
        cx, cy = int(head[0]), int(head[1])
        if 0 <= cx < width and 0 <= cy < height and depths[cx, cy] < head[2] - 0.15:
            continue                                                       # something is in front of them
        color = NAME_TEAMMATE if same_team(team, their_team) else NAME_OPPONENT
        label = font.render(name, True, color)
        left, top = int(column - label.get_width() / 2), int(row - label.get_height())
        if top + label.get_height() < 0 or top > height or left + label.get_width() < 0 or left > width:
            continue
        picture.blit(font.render(name, True, SHADOW), (left + 1, top + 1))
        picture.blit(label, (left, top))


def hurt_flash(flash, damage, dt):
    """How strong the red flash is now (0 to 1): a hit (`damage` taken this frame) brings it up - more for a bigger
    hit - and it fades over a third of a second."""
    if damage > 0:
        flash = max(flash, min(1.0, 0.5 + damage / 50.0))
    return max(0.0, flash - dt * HURT_FADE)


def draw_hurt(picture, flash):
    """Lay a see-through red over the picture, `flash` (0 to 1) of HURT_ALPHA strong."""
    if flash <= 0.0:
        return
    veil = pygame.Surface(picture.get_size(), pygame.SRCALPHA)
    veil.fill((*HURT_COLOR, round(HURT_ALPHA * flash)))
    picture.blit(veil, (0, 0))


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


def draw_hud(picture, font, stats, message, inventory=None, tiles=None, kick=0.0, money=False, team=None, buy_key=False):
    """`money` shows the player's money (on maps where it means something), `team` their team (None: not on one),
    and `buy_key` a reminder that B opens the buy menu."""
    shadowed(picture, font, f"Health {stats.health:g}", (8, 8))
    shadowed(picture, font, f"Score {stats.score:g}", (8, 26))
    y = 44
    if money:
        shadowed(picture, font, f"Money ${stats.money:g}", (8, y), HIGHLIGHT)
        y += 18
    if team is not None:
        shadowed(picture, font, team if isinstance(team, str) else f"Team {team}", (8, y), DIM)
        y += 18
    if buy_key:
        shadowed(picture, font, "B: buy menu", (8, y), DIM)
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


def draw_bar(picture, font, text, share):
    """A progress bar under the crosshair (planting, defusing), `share` (0 to 1) full."""
    width, height = 160, 10
    x, y = WIDTH // 2 - width // 2, HEIGHT // 2 + 62
    pygame.draw.rect(picture, BAR_BACK, (x - 1, y - 1, width + 2, height + 2))
    pygame.draw.rect(picture, BAR_FILL, (x, y, round(width * max(0.0, min(1.0, share))), height))
    shadowed(picture, font, text, (WIDTH // 2, y - 18), center=True)


def draw_round(picture, font, big, view, me_id, me, level, watching=None):
    """Bomb defusal: the score and the timer at the top, the round's result in the middle, and what this player can
    do (or who they are watching while out of the round). `view` is the bomb.RoundView, `me` their PlayerState."""
    if view is None:
        return
    settings = level.settings
    middle = WIDTH // 2
    # the score either side of the timer
    if view.phase == "planted":
        timer, color = f"BOMB {clock_text(view.bomb.left)}", DANGER
    elif view.phase == "over":
        timer, color = clock_text(view.clock), DIM
    else:
        timer = clock_text(view.clock)
        color = DANGER if view.phase == "live" and view.clock <= 10 else TEXT
    shadowed(picture, big, timer, (middle, 6), color, center=True)
    half = big.size(timer)[0] // 2 + 14
    t_score, ct_score = str(view.score[T_TEAM]), str(view.score[CT_TEAM])
    shadowed(picture, big, t_score, (middle - half - big.size(t_score)[0], 6), TEAM_COLORS[T_TEAM])
    shadowed(picture, big, ct_score, (middle + half, 6), TEAM_COLORS[CT_TEAM])
    shadowed(picture, font, TEAM_NAMES[T_TEAM], (middle - half - big.size(t_score)[0] - 26, 10), TEAM_COLORS[T_TEAM])
    shadowed(picture, font, TEAM_NAMES[CT_TEAM], (middle + half + big.size(ct_score)[0] + 8, 10), TEAM_COLORS[CT_TEAM])
    under = f"Round {view.number} of {view.max_rounds}"
    if view.phase == "freeze":
        under = "Freeze time - " + ("buy now (B)" if settings.buy_menu else "get ready")
    elif view.phase == "planted":
        under = f"The bomb is planted at {SITE_NAMES.get(view.bomb.site, '?')}"
    shadowed(picture, font, under, (middle, 32), DIM, center=True)
    if view.message and view.message_left > 0:
        shadowed(picture, big, view.message, (middle, HEIGHT // 2 - 70), HIGHLIGHT, center=True)
    # what this player is doing, or can do
    if me_id not in view.alive:
        text = "You are out until the next round"
        if watching:
            text += f" - watching {watching} (click: next)"
        shadowed(picture, font, text, (middle, HEIGHT - 70), DIM, center=True)
        return
    body = me.body
    if view.planting[0] == me_id:
        draw_bar(picture, font, "Planting the bomb...", view.planting[1] / max(0.01, settings.plant_time))
    elif view.defusing[0] == me_id:
        kit = " (with a kit)" if me.inventory.count(DEFUSE_KIT) > 0 else ""
        draw_bar(picture, font, f"Defusing the bomb{kit}...", view.defusing[1] / max(0.01, view.defuse_needed))
    elif can_plant(view, me_id, body, level):
        shadowed(picture, font, f"Hold E to plant the bomb at {SITE_NAMES.get(site_under(level, body), '?')}",
                 (middle, HEIGHT // 2 + 44), HIGHLIGHT, center=True)
    elif can_defuse(view, me_id, body):
        shadowed(picture, font, "Hold E to defuse the bomb", (middle, HEIGHT // 2 + 44), HIGHLIGHT, center=True)
    if view.bomb.state == "carried" and view.bomb.carrier == me_id:
        shadowed(picture, font, "You have the bomb: plant it in a site (G drops it)", (middle, HEIGHT - 70),
                 TEAM_COLORS[T_TEAM], center=True)
