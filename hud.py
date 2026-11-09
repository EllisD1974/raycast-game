"""What is drawn over the game picture: health, score and money, the inventory, the equipped gun, the red flash of
being hurt, and in bomb defusal and King of the Hill the round: the score, the timers, the bomb or the capture point,
and what the player can do."""
import math

import pygame

from bomb import can_defuse, can_plant, clock_text, site_under
from constants import HEIGHT, WIDTH
from koth import HillView, on_hill
from respawn import RespawnView
from zombies import REVIVE_REACH, REVIVE_UP, ZombieView
from mapfile import CT_TEAM, DEFUSE_KIT, KOTH_NAMES, SITE_NAMES, T_TEAM, TEAM_NAMES

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
KOTH_COLORS = {T_TEAM: (200, 60, 50), CT_TEAM: (70, 115, 205)}         # RED and BLU
KOTH_TEXT = {T_TEAM: (255, 120, 105), CT_TEAM: (140, 180, 255)}
NEUTRAL = (150, 150, 158)
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
    do (or who they are watching while out of the round). `view` is the bomb.RoundView, `me` their PlayerState.
    King of the Hill (a koth.HillView) is drawn by draw_hill instead."""
    if view is None:
        return
    if isinstance(view, HillView):
        draw_hill(picture, font, big, view, me_id, me, level, watching)
        return
    if isinstance(view, RespawnView):
        draw_respawn(picture, font, view, me_id, watching)
        return
    if isinstance(view, ZombieView):
        draw_zombies(picture, font, big, view, me_id, watching)
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
            text += f" - watching {watching} (left / right click: next / previous)"
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
        shadowed(picture, font, "You have the bomb: plant it in a site (G throws it)", (middle, HEIGHT - 70),
                 TEAM_COLORS[T_TEAM], center=True)


def draw_zombies(picture, font, big, view, me_id, watching=None):
    """Zombies: the round at the top (in red) with how many enemies are left, or the countdown to the next round;
    the round's news in the middle; and, for a player who is out, that they are back next round."""
    middle = WIDTH // 2
    if view.number:
        shadowed(picture, big, f"Round {view.number}", (middle, 6), DANGER, center=True)
    if view.phase == "live":
        under = f"{view.left} zombie{'' if view.left == 1 else 's'} left"
    elif view.phase == "intermission":
        under = f"{'Next round' if view.number else 'First round'} in {max(1, math.ceil(view.clock))}"
    else:
        under = f"New game in {max(1, math.ceil(view.clock))}"
    shadowed(picture, font, under, (middle, 32 if view.number else 10), DIM, center=True)
    if view.message and view.message_left > 0:
        shadowed(picture, big, view.message, (middle, HEIGHT // 2 - 70), HIGHLIGHT, center=True)
    if me_id not in view.alive and view.phase != "over":
        text = "You are out until the next round"
        if watching:
            text += f" - watching {watching} (left / right click: next / previous)"
        shadowed(picture, font, text, (middle, HEIGHT - 70), DIM, center=True)


def draw_downed(picture, font, big, renderer, camera, view, me_id, me, level):
    """Zombies: a marker over each downed teammate (with their bleed-out time), at the edge of the picture toward them
    when they are not in view; and what this player can do about it: "Hold E to revive", the revive's progress, or,
    when they are down themselves, how long they have left and who is reviving them."""
    if not isinstance(view, ZombieView) or me_id not in view.alive:
        return
    width, height = picture.get_size()
    revive_time = max(0.01, level.settings.revive_time)
    for pid, (left, x, y, z, name) in view.downed.items():
        if pid == me_id or math.hypot(x - camera.x, y - camera.y) <= REVIVE_REACH * 2:
            continue                                    # (close by, the revive prompt says it)
        text = f"+ {name or 'Teammate'} {max(0, math.ceil(left))}s"
        spot = renderer.project(camera, x, y, z + 0.4)
        if spot is not None and 0 <= spot[0] < width:
            shadowed(picture, font, text, (int(spot[0]), max(48, min(height - 90, int(spot[1]) - 24))), DANGER,
                     center=True)
            continue
        turn = math.atan2(y - camera.y, x - camera.x) - camera.angle
        turn = (turn + math.pi) % math.tau - math.pi
        text = "< " + text if turn < 0 else text + " >"         # (to the left of the view, or to the right)
        x = 8 if turn < 0 else width - 8 - font.size(text)[0]
        shadowed(picture, font, text, (x, height // 2), DANGER)
    if me_id in view.downed:
        left = view.downed[me_id][0]
        shadowed(picture, big, f"DOWNED - {max(0, math.ceil(left))}s", (WIDTH // 2, HEIGHT // 2 + 30), DANGER,
                 center=True)
        helper = view.revives.get(me_id)
        if helper is not None:
            draw_bar(picture, font, "Being revived...", helper[1] / revive_time)
        else:
            shadowed(picture, font, "Wait for a teammate to revive you", (WIDTH // 2, HEIGHT - 70), DIM,
                     center=True)
        return
    mine = next((pid for pid, (reviver, _) in view.revives.items() if reviver == me_id), None)
    if mine is not None:
        name = view.downed.get(mine, (0, 0, 0, 0, ""))[4] or "teammate"
        draw_bar(picture, font, f"Reviving {name}...", view.revives[mine][1] / revive_time)
        return
    body = me.body
    near = [(pid, entry) for pid, entry in view.downed.items() if pid != me_id and pid not in view.revives
            and math.hypot(entry[1] - body.x, entry[2] - body.y) <= REVIVE_REACH and abs(entry[3] - body.z) <= REVIVE_UP]
    if near:
        shadowed(picture, font, f"Hold E to revive {near[0][1][4] or 'your teammate'}", (WIDTH // 2, HEIGHT // 2 + 44),
                 HIGHLIGHT, center=True)


def draw_respawn(picture, font, view, me_id, watching=None):
    """Free for all, two teams and co-op with a respawn delay: how long until this player comes back (and who they
    are watching meanwhile)."""
    if me_id in view.alive:
        return
    left = view.respawns.get(me_id)
    text = f"Respawning in {max(1, math.ceil(left))}" if left is not None else "Waiting to respawn"
    if watching:
        text += f" - watching {watching} (left / right click: next / previous)"
    shadowed(picture, font, text, (WIDTH // 2, HEIGHT - 70), DIM, center=True)


def draw_hill(picture, font, big, view, me_id, me, level, watching=None):
    """King of the Hill: each team's clock either side of the point (in its owner's color, ringed by the capture
    progress) at the top, what is happening under them, the round's result in the middle, and what this player is
    doing on the point (or how long until they respawn)."""
    middle, radius = WIDTH // 2, 13
    height = big.get_height() + 6
    for team, side in ((T_TEAM, -1), (CT_TEAM, 1)):
        text = clock_text(view.clocks[team])
        box = pygame.Rect(0, 4, big.size(text)[0] + 16, height)
        box.centerx = middle + side * (radius + 10 + box.w // 2)
        running = view.owner == team and view.phase == "live"
        pygame.draw.rect(picture, KOTH_COLORS[team] if running else tuple(c // 2 for c in KOTH_COLORS[team]), box,
                         border_radius=4)
        if running:
            pygame.draw.rect(picture, TEXT, box, 2, border_radius=4)
        shadowed(picture, big, text, (box.centerx, box.y + 4), TEXT if running or not view.owner else DIM, center=True)
        label = f"{KOTH_NAMES[team]} {view.score[team]}"
        x = box.left - 8 - font.size(label)[0] if side < 0 else box.right + 8
        shadowed(picture, font, label, (x, box.y + 7), KOTH_TEXT[team])
    center = (middle, 4 + height // 2)
    pygame.draw.circle(picture, SHADOW, center, radius + 3)
    pygame.draw.circle(picture, KOTH_COLORS.get(view.owner, NEUTRAL), center, radius)
    if view.phase == "setup":                                   # locked: a bar across it
        pygame.draw.rect(picture, SHADOW, (center[0] - radius + 4, center[1] - 2, 2 * radius - 8, 4))
    if view.capper and view.progress > 0:
        ring = pygame.Rect(0, 0, 2 * radius + 6, 2 * radius + 6)
        ring.center = center
        start = math.pi / 2
        pygame.draw.arc(picture, KOTH_TEXT[view.capper], ring, start, start + view.progress * math.tau, 3)
    if view.phase == "setup":
        status, color = f"The point unlocks in {clock_text(view.clock)}", TEXT
    elif view.phase == "over":
        status, color = f"Next round in {clock_text(view.clock)}", DIM
    elif view.overtime:
        status, color = "OVERTIME", DANGER
    elif view.contested:
        status, color = "The point is contested", HIGHLIGHT
    elif view.capper and view.progress > 0:
        status, color = f"{KOTH_NAMES[view.capper]} is capturing the point", KOTH_TEXT[view.capper]
    elif view.owner:
        status, color = f"{KOTH_NAMES[view.owner]} holds the point", KOTH_TEXT[view.owner]
    else:
        status, color = "Capture the point", TEXT
    shadowed(picture, font, status, (middle, 8 + height), color, center=True)
    if view.message and view.message_left > 0:
        shadowed(picture, big, view.message, (middle, HEIGHT // 2 - 70), HIGHLIGHT, center=True)
    if me_id not in view.alive:
        left = view.respawns.get(me_id)
        text = f"Respawning in {max(1, math.ceil(left))}" if left is not None else "Waiting to respawn"
        if watching:
            text += f" - watching {watching} (left / right click: next / previous)"
        shadowed(picture, font, text, (middle, HEIGHT - 70), DIM, center=True)
        return
    if view.phase == "over" and view.winner and me.team != view.winner:
        shadowed(picture, font, "Your team lost the round: no shooting until the next one", (middle, HEIGHT - 70),
                 DIM, center=True)
    if not on_hill(level, me.body):
        return
    if view.phase == "setup":
        shadowed(picture, font, "The point is locked", (middle, HEIGHT // 2 + 44), DIM, center=True)
    elif view.phase == "live" and view.contested:
        draw_bar(picture, font, "Contested!", view.progress)
    elif view.phase == "live" and view.capper and view.capper != me.team:
        draw_bar(picture, font, "Pushing the capture back...", view.progress)
    elif view.phase == "live" and view.capper == me.team:
        draw_bar(picture, font, "Capturing the point...", view.progress)
