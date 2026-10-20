"""A simple raycaster with textured walls, floors, ceilings, stairs, ramps and variable heights.

Run:  python make_atlas.py   (once: creates assets/textures.png, the 32x32 texture map)
      python main.py         controls:
          mouse            look around (left/right turns, up/down tilts the view, up to 45 degrees)
          WASD / arrows    move (the left/right arrows turn too); hold SHIFT to sprint
          SPACE jump, TAB let go of / take back the mouse, ESC quit, F11 fullscreen
      The game opens maximized and can be resized; the picture keeps its aspect ratio.
      python main.py --map other.json   (play a different map)
Multiplayer (one player hosts, the others join with the password):
      python main.py --host PASSWORD [--port 7777] [--bind 0.0.0.0]
      python main.py --join ADDRESS PASSWORD [--port 7777]
Edit the map with:  python map_editor.py
Debug: python main.py --snapshot out.png [--at X Y ANGLE_RADIANS [--span 0|1]] [--pitch DEGREES]
       (render one frame without a window; --span N stands on floor N, counting from 0)

The first start compiles the renderer with numba (some seconds); later starts use a cache.
"""
import math
import os
import sys
import time
import warnings

import pygame
from pygame._sdl2 import sdl2, video

import net
from atlas import ATLAS_PATH, atlas_array, transparent_tiles, unpack_atlas
from character import character_tiles
from constants import FPS_CAP, HEIGHT, MOUSE_SENSITIVITY, TURN_SPEED, WIDTH
from game import Game, Inputs
from hud import draw_hud
from mapfile import MAP_PATH, load_or_default
from physics import look
from renderer import BACKGROUND, Renderer, fit_rect  # noqa: F401  (re-exported: main.Renderer etc.)
from session import ClientSession, HostSession, LocalSession
from watch import FileWatcher
from window import maximize
from world import World

JOIN_TIMEOUT = 15.0                            # seconds to wait for the host's map after joining
CROSSHAIR = (255, 255, 255)
CROSSHAIR_OUTLINE = (0, 0, 0)


# ------------------------------------------------------------------ putting the picture on the window

def crosshair_bars(center, arm, thickness):
    """The two bars of a + centerd on `center`. `arm` is how far each reaches from the center, in pixels."""
    cx, cy = center
    half = thickness // 2
    return (pygame.Rect(cx - arm, cy - half, 2 * arm + 1, thickness),       # horizontal
            pygame.Rect(cx - half, cy - arm, thickness, 2 * arm + 1))       # vertical


def crosshair_size(rect):
    """(arm, thickness) of the crosshair over a picture shown in `rect`: thin however big the window is."""
    return max(6, rect.height // 60), max(1, rect.height // 450)


def draw_crosshair(surface, center, arm, thickness):
    """A thin + centerd on `center`: white with a one pixel dark outline so it shows on any
    background. `arm` is how far each bar reaches from the center, in pixels."""
    bars = crosshair_bars(center, arm, thickness)
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
    draw_crosshair(screen, rect.center, *crosshair_size(rect))


class Screen:
    """The game's window, and putting each picture on it.

    The picture is handed to the graphics card, which stretches it to the window (keeping its aspect ratio,
    black bars around it) and draws the crosshair over it at the window's resolution. Where no GPU renderer
    can be made (some drivers, some remote desktops), the window's own surface is used instead and
    present() scales the picture on the CPU, which looks the same but is slower in a big window."""

    def __init__(self, title, size):
        self.window = pygame.Window(title, size, resizable=True)
        self.fullscreen = False
        self.gpu = self.texture = None
        try:                                        # (the graphics card's renderer if there is one)
            self.gpu = video.Renderer(self.window)
            self.texture = video.Texture(self.gpu, (WIDTH, HEIGHT), streaming=True)
        except (pygame.error, sdl2.error):
            self.gpu = self.texture = None

    @property
    def title(self):
        return self.window.title

    @title.setter
    def title(self, text):
        if text != self.window.title:
            self.window.title = text

    def toggle_fullscreen(self):
        """Fill the whole screen, or go back to a window."""
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.window.set_fullscreen(desktop=True)
        else:
            self.window.set_windowed()

    def show(self, frame):
        """Put `frame` (a WIDTH x HEIGHT surface) on the window, with the crosshair."""
        if self.gpu is None:
            present(self.window.get_surface(), frame)
            self.window.flip()
            return
        rect = fit_rect(self.window.size)
        self.texture.update(frame)
        self.gpu.draw_color = (0, 0, 0, 255)
        self.gpu.clear()
        self.texture.draw(dstrect=rect)
        bars = crosshair_bars(rect.center, *crosshair_size(rect))
        self.gpu.draw_color = (*CROSSHAIR_OUTLINE, 255)
        for bar in bars:
            self.gpu.fill_rect(bar.inflate(2, 2))
        self.gpu.draw_color = (*CROSSHAIR, 255)
        for bar in bars:
            self.gpu.fill_rect(bar)
        self.gpu.present()


# ------------------------------------------------------------------ input

class MouseLook:
    """Captures the mouse and turns its movement into looking around.

    While captured the cursor is hidden and held in the window, and movement is reported without
    limit (so you can keep turning). Mouse movement is in screen pixels, so how far the view turns
    for a given hand movement does not depend on the window size.

    `window` is the pygame.Window to hold the mouse in; without one it is the window pygame.display opened."""

    def __init__(self, window=None):
        self.window = window
        self.captured = False
        self.dx = 0
        self.dy = 0

    def set_captured(self, captured):
        self.captured = captured
        if self.window is not None:
            self.window.grab_mouse = captured
        else:
            pygame.event.set_grab(captured)
        pygame.mouse.set_visible(not captured)
        try:
            with warnings.catch_warnings():         # (pygame warns about relative mode without display.set_mode,
                warnings.simplefilter("ignore", DeprecationWarning)     # but it works with a pygame.Window)
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


class Graphics:
    """What the picture is drawn from: the atlas's tiles, the character pictures after them, and the renderer
    built on all of those. It is empty until load() is given an atlas (a path or PNG bytes)."""

    def __init__(self):
        self.tiles = []
        self.character_tile = 0
        self.see_through = None
        self.renderer = None

    def load(self, atlas):
        tiles = unpack_atlas(atlas)
        textures = atlas_array(tiles + character_tiles())       # the character pictures follow the atlas's tiles
        self.tiles, self.character_tile = tiles, len(tiles)
        self.see_through = transparent_tiles(textures)[:len(tiles)]   # tiles with alpha make see-through walls
        self.renderer = Renderer(textures)

    def make_world(self, level):
        if self.renderer is None:
            raise ValueError("no textures: the host sent none and textures.png is missing here")
        return World(level, len(self.tiles), self.see_through)


def join(address, password, port, graphics):
    """Connect to a host and wait for its map, textures and first snapshot; exits with a message if that fails.
    The host's textures replace whatever `graphics` had loaded, so the joiner needs no map or textures of its own."""
    def use_atlas(png):
        try:
            graphics.load(png)
        except pygame.error as e:
            raise ValueError(f"textures: {e}")
        return graphics.character_tile

    session = ClientSession(net.Client(address, port, password), graphics.make_world, graphics.character_tile, use_atlas)
    print(f"Joining {address}:{port}...")
    give_up = time.monotonic() + JOIN_TIMEOUT
    while not session.ready and not session.ended:
        pygame.event.pump()
        session.step(Inputs(), 0.0)
        if time.monotonic() > give_up:
            session.close()
            sys.exit("the host did not send the game")
        time.sleep(0.01)
    if session.ended:
        sys.exit(f"could not join: {session.ended}")
    return session


def reload_game(session, graphics, map_path):
    """Read the map and textures again and carry on in them (a host tells its joiners). Raises if either
    cannot be read, leaving the game as it was."""
    level = load_or_default(map_path)
    with open(ATLAS_PATH, "rb") as f:
        png = f.read()
    graphics.load(png)
    session.reload(level, graphics.make_world(level), graphics.character_tile, png)


def main():
    pygame.init()
    # A normal resizable window: the picture is scaled onto it by Screen (on the graphics card), not by
    # pygame.display, so mouse movement arrives in plain screen pixels.
    screen = Screen("simple raycaster", (WIDTH * 2, HEIGHT * 2))
    clock = pygame.time.Clock()
    graphics = Graphics()
    joining = bool(arg_values("--join", 2))
    if os.path.exists(ATLAS_PATH):
        graphics.load(ATLAS_PATH)
    elif not joining:                                       # a joiner is sent the host's textures
        sys.exit("textures.png not found - run `python make_atlas.py` first")
    port = int((arg_values("--port", 1) or [net.DEFAULT_PORT])[0])
    watcher = None                                          # a joiner is sent new maps by its host instead
    if joining:
        address, password = arg_values("--join", 2)
        session = join(address, password, port, graphics)
    else:
        map_path = (arg_values("--map", 1) or [MAP_PATH])[0]
        if "--map" in sys.argv and not os.path.exists(map_path):
            sys.exit(f"map file not found: {map_path}")      # don't silently play another map
        level = load_or_default(map_path)
        game = Game(level, graphics.make_world(level), character_tile=graphics.character_tile)
        if arg_values("--host", 1):
            bind = (arg_values("--bind", 1) or ["0.0.0.0"])[0]
            try:
                host = net.Host(arg_values("--host", 1)[0], port, bind)
            except OSError as e:
                sys.exit(f"cannot host on {bind}:{port}: {e}")
            with open(ATLAS_PATH, "rb") as f:               # joiners draw with the host's textures
                session = HostSession(game, host, f.read())
            print(f"Hosting on {bind}:{host.port}; others join with --join <your address> <password>")
        else:
            session = LocalSession(game)
        watcher = FileWatcher([map_path, ATLAS_PATH])       # a saved map or texture change is picked up live
    kick = 0.0                                   # 1 right after a shot, fading to 0 (the gun's recoil)
    font = pygame.font.Font(None, 22)
    message, message_left = "", 0.0

    # `--snapshot out.png` renders one frame and exits (for checking).
    if "--snapshot" in sys.argv:
        player, world = session.me.body, session.game.world
        at = arg_values("--at", 3)
        if at:
            player.x, player.y, player.angle = (float(v) for v in at)
            floor = int((arg_values("--span", 1) or ["0"])[0])      # index of the floor to stand on
            player.span = floor
            player.z = world.floor_of(floor, player.x, player.y)
        pitch = arg_values("--pitch", 1)
        if pitch:
            look(player, math.radians(float(pitch[0])))
        pygame.image.save(graphics.renderer.draw(world, player, session.game.items.sprites(), session.lighting()), arg_values("--snapshot", 1)[0])
        return

    maximize(screen.window)          # the game opens maximized; the picture scales to fit
    mouse = MouseLook(screen.window)
    mouse.set_captured(True)
    print("Compiling the renderer (first run only; later runs use the cache)...")
    jump_pressed = reload_pressed = False
    equips, cycle = [], 0
    loads = getattr(session, "loads", 0)
    running = True
    while running:
        elapsed = clock.tick(FPS_CAP) / 1000
        dt = min(elapsed, 0.05)
        for event in pygame.event.get():
            if (event.type in (pygame.QUIT, pygame.WINDOWCLOSE)
                    or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE)):
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                screen.toggle_fullscreen()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                jump_pressed = True
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
                mouse.set_captured(not mouse.captured)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                reload_pressed = True
            elif event.type == pygame.KEYDOWN and pygame.K_1 <= event.key <= pygame.K_9:
                equips.append(event.key - pygame.K_1)          # 1-9 take out that gun (again: put it away)
            elif event.type == pygame.MOUSEWHEEL and mouse.captured:
                cycle -= event.y                               # the wheel steps through the guns
            else:
                mouse.handle_event(event)

        forward, strafe, key_turn, sprint = read_movement(pygame.key.get_pressed())
        mouse_turn, tilt = mouse.take()
        wish = Inputs(forward, strafe, key_turn * TURN_SPEED * dt + mouse_turn, tilt, jump_pressed, sprint,
                      mouse.captured and pygame.mouse.get_pressed()[0], reload_pressed, tuple(equips), cycle)
        jump_pressed = reload_pressed = False
        equips, cycle = [], 0
        if watcher and watcher.changed():
            try:
                reload_game(session, graphics, map_path)
                message, message_left = "Map reloaded", 2.0
            except (OSError, ValueError, KeyError, TypeError, pygame.error) as e:   # keep playing the old map
                print(f"Reload failed: {e}")
                message, message_left = f"Reload failed: {e}"[:80], 4.0
        happened = session.step(wish, dt, elapsed)
        if getattr(session, "loads", 0) > loads:            # (a joiner) the host switched to a new map
            loads, message, message_left = session.loads, "The host loaded a new map", 2.0
        if session.ended:
            print(f"Game over: {session.ended}")
            running = False
        if happened.fired:
            kick = 1.0
        kick = max(0.0, kick - dt * 8.0)
        if happened.picked:
            message, message_left = ", ".join(happened.picked), 1.5
        message_left = max(0.0, message_left - dt)

        me = session.me
        picture = graphics.renderer.draw(session.world, me.body, session.sprites(), session.lighting())
        draw_hud(picture, font, me.stats, message if message_left > 0 else "", me.inventory, graphics.tiles, kick)
        screen.show(picture)
        screen.title = f"simple raycaster - {clock.get_fps():.0f} fps{session.status()}"
    mouse.set_captured(False)
    session.close()
    pygame.quit()


if __name__ == "__main__":
    main()
