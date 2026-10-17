"""A simple raycaster with textured walls, floors, ceilings, stairs, ramps and variable heights.

Run:  python make_atlas.py   (once: creates assets/textures.png, the 32x32 texture map)
      python main.py         controls:
          mouse            look around (left/right turns, up/down tilts the view, up to 45 degrees)
          WASD / arrows    move (the left/right arrows turn too); hold SHIFT to sprint
          SPACE jump, TAB let go of / take back the mouse, ESC quit, F11 fullscreen
      The game opens maximized and can be resized; the picture keeps its aspect ratio.
      python main.py --map other.json   (play a different map)
Edit the map with:  python map_editor.py
Debug: python main.py --snapshot out.png [--at X Y ANGLE_RADIANS [--span 0|1]] [--pitch DEGREES]
       (render one frame without a window; --span N stands on floor N, counting from 0)

The first start compiles the renderer with numba (some seconds); later starts use a cache.
"""
import math
import os
import sys

import pygame

from atlas import ATLAS_PATH, atlas_array, transparent_tiles, unpack_atlas
from constants import FPS_CAP, HEIGHT, MOUSE_SENSITIVITY, TURN_SPEED, WIDTH
from entities import Entities, PlayerStats
from hud import draw_hud
from inventory import Inventory
from mapfile import MAP_PATH, load_or_default
from physics import look, spawn, step
from projectiles import Projectiles
from renderer import BACKGROUND, Renderer, fit_rect  # noqa: F401  (re-exported: main.Renderer etc.)
from window import maximize
from world import World

CROSSHAIR = (255, 255, 255)
CROSSHAIR_OUTLINE = (0, 0, 0)


# ------------------------------------------------------------------ putting the picture on the window

def draw_crosshair(surface, center, arm, thickness):
    """A thin + centred on `center`: white with a one pixel dark outline so it shows on any
    background. `arm` is how far each bar reaches from the centre, in pixels."""
    cx, cy = center
    half = thickness // 2
    bars = (pygame.Rect(cx - arm, cy - half, 2 * arm + 1, thickness),       # horizontal
            pygame.Rect(cx - half, cy - arm, thickness, 2 * arm + 1))       # vertical
    for bar in bars:
        pygame.draw.rect(surface, CROSSHAIR_OUTLINE, bar.inflate(2, 2))
    for bar in bars:
        pygame.draw.rect(surface, CROSSHAIR, bar)


def present(screen, frame):
    """Scale the picture up to the window (keeping its aspect ratio, black bars around it) and
    draw the crosshair at screen resolution, so it stays thin however big the window is."""
    screen.fill((0, 0, 0))
    rect = fit_rect(screen.get_size())
    pygame.transform.scale(frame, rect.size, screen.subsurface(rect))
    draw_crosshair(screen, rect.center, max(6, rect.height // 60), max(1, rect.height // 450))


# ------------------------------------------------------------------ input

class MouseLook:
    """Captures the mouse and turns its movement into looking around.

    While captured the cursor is hidden and held in the window, and movement is reported without
    limit (so you can keep turning). Mouse movement is in screen pixels, so how far the view turns
    for a given hand movement does not depend on the window size."""

    def __init__(self):
        self.captured = False
        self.dx = 0
        self.dy = 0

    def set_captured(self, captured):
        self.captured = captured
        pygame.event.set_grab(captured)
        pygame.mouse.set_visible(not captured)
        try:
            pygame.mouse.set_relative_mode(captured)
        except pygame.error:                        # some drivers have no relative mouse mode
            pass
        pygame.mouse.get_rel()                      # forget movement from before the change
        self.dx = self.dy = 0

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION and self.captured:
            self.dx += event.rel[0]
            self.dy += event.rel[1]
        elif event.type == pygame.MOUSEBUTTONDOWN and not self.captured:
            self.set_captured(True)                 # click back into the game
        elif event.type == pygame.WINDOWFOCUSLOST and self.captured:
            self.set_captured(False)                # let go when the window is switched away from

    def take(self):
        """(turn, tilt) in radians for the movement since the last call: mouse right turns right,
        mouse up tilts the view up."""
        turn, tilt = self.dx * MOUSE_SENSITIVITY, -self.dy * MOUSE_SENSITIVITY
        self.dx = self.dy = 0
        return turn, tilt


def read_movement(keys):
    """(forward, strafe, turn, sprint) for the pressed keys, as given by pygame.key.get_pressed().

    forward, strafe and turn are -1, 0 or 1. Sprint is Shift (either one); the physics only
    sprints while a movement key is held too, so Shift on its own does nothing."""
    forward = int(keys[pygame.K_w] or keys[pygame.K_UP]) - int(keys[pygame.K_s] or keys[pygame.K_DOWN])
    strafe = int(keys[pygame.K_d]) - int(keys[pygame.K_a])
    turn = int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT])
    sprint = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
    return forward, strafe, turn, sprint


def arg_values(flag, count):
    """Values following a command line flag, or None if the flag is absent."""
    if flag not in sys.argv:
        return None
    i = sys.argv.index(flag)
    return sys.argv[i + 1:i + 1 + count]


def main():
    pygame.init()
    # A normal resizable window: the picture is scaled onto it by present(), not by pygame, so
    # mouse movement arrives in plain screen pixels.
    screen = pygame.display.set_mode((WIDTH * 2, HEIGHT * 2), pygame.RESIZABLE)
    pygame.display.set_caption("simple raycaster")
    clock = pygame.time.Clock()
    if not os.path.exists(ATLAS_PATH):
        sys.exit("textures.png not found - run `python make_atlas.py` first")
    tiles = unpack_atlas(ATLAS_PATH)

    map_path = (arg_values("--map", 1) or [MAP_PATH])[0]
    if "--map" in sys.argv and not os.path.exists(map_path):
        sys.exit(f"map file not found: {map_path}")          # don't silently play another map
    level = load_or_default(map_path)
    textures = atlas_array(tiles)
    world = World(level, len(tiles), transparent_tiles(textures))   # tiles with alpha make see-through walls
    player = spawn(level, world)
    renderer = Renderer(textures)
    items = Entities(level, world)
    stats = PlayerStats()
    inventory = Inventory()
    projectiles = Projectiles()
    kick = 0.0                                    # 1 right after a shot, fading to 0 (the gun's recoil)
    font = pygame.font.Font(None, 22)
    message, message_left = "", 0.0

    # `--snapshot out.png` renders one frame and exits (for checking).
    if "--snapshot" in sys.argv:
        at = arg_values("--at", 3)
        if at:
            player.x, player.y, player.angle = (float(v) for v in at)
            floor = int((arg_values("--span", 1) or ["0"])[0])      # index of the floor to stand on
            player.span = floor
            player.z = world.floor_of(floor, player.x, player.y)
        pitch = arg_values("--pitch", 1)
        if pitch:
            look(player, math.radians(float(pitch[0])))
        pygame.image.save(renderer.draw(world, player, items.sprites()), arg_values("--snapshot", 1)[0])
        return

    maximize()                       # the game opens maximized; the picture scales to fit
    mouse = MouseLook()
    mouse.set_captured(True)
    print("Compiling the renderer (first run only; later runs use the cache)...")
    jump_pressed = reload_pressed = False
    running = True
    while running:
        dt = min(clock.tick(FPS_CAP) / 1000, 0.05)
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                pygame.display.toggle_fullscreen()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                jump_pressed = True
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
                mouse.set_captured(not mouse.captured)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                reload_pressed = True
            elif event.type == pygame.KEYDOWN and pygame.K_1 <= event.key <= pygame.K_9:
                inventory.equip(event.key - pygame.K_1)        # 1-9 take out that gun (again: put it away)
            elif event.type == pygame.MOUSEWHEEL and mouse.captured:
                inventory.cycle(-event.y)                      # the wheel steps through the guns
            else:
                mouse.handle_event(event)

        forward, strafe, key_turn, sprint = read_movement(pygame.key.get_pressed())
        mouse_turn, tilt = mouse.take()
        step(world, player, forward, strafe, key_turn * TURN_SPEED * dt + mouse_turn, jump_pressed, dt, sprint)
        look(player, tilt)
        jump_pressed = False
        trigger = mouse.captured and pygame.mouse.get_pressed()[0]
        for gun in inventory.update(dt, trigger, reload_pressed):
            projectiles.fire(player, gun, level.ammo_for(gun))
            kick = 1.0
        reload_pressed = False
        kick = max(0.0, kick - dt * 8.0)
        projectiles.update(world, dt)
        picked = items.update(player, stats, dt, inventory)
        if picked:
            message, message_left = ", ".join(picked), 1.5
        message_left = max(0.0, message_left - dt)

        picture = renderer.draw(world, player, items.sprites() + projectiles.sprites())
        draw_hud(picture, font, stats, message if message_left > 0 else "", inventory, tiles, kick)
        present(pygame.display.get_surface(), picture)
        pygame.display.set_caption(f"simple raycaster - {clock.get_fps():.0f} fps")
        pygame.display.flip()
    mouse.set_captured(False)
    pygame.quit()


if __name__ == "__main__":
    main()
