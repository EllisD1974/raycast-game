"""A live preview of a gun for the editor: the real game, a short corridor and one player firing the gun.

It is the game itself (Game, LocalSession and the Renderer) with the map's guns, ammunition, particle effects and
lights, so what you see is what the game does: the fire rate, the magazine and the reload, the weapon's recoil, the
muzzle effect and flash, bullets flying down the corridor with their trails and lights. Nothing here is a
simulation of its own.

    preview = GunPreview(textures)                  # textures as the renderer takes them (atlas_array)
    preview.build(level, "Pistol", dark=False)      # (again whenever the level or the gun changes)
    preview.update(dt, firing)                      # firing: hold the trigger; keeps reloading when it runs dry
    picture = preview.render(tiles, font)           # a WIDTH x HEIGHT surface
"""
import random
from collections import deque
from dataclasses import fields, replace

import hud
from atlas import transparent_tiles
from game import Game, Inputs
from mapfile import Level
from renderer import Renderer
from session import LocalSession
from world import World

LENGTH, WIDTH_CELLS = 30, 5         # the corridor the gun is fired down
DARK_AMBIENT = 0.2                  # how dark the "dark room" is, so muzzle flashes and bullet lights show
TAP_SECONDS = 0.07                  # how long the trigger is held for one "Fire once"
SPARE_ROUNDS = 100                  # the gun is given more spare rounds whenever it is about to run dry
KICK_DECAY = 8.0                    # how fast the weapon settles after a shot, per second (as in the game)
RATE_WINDOW = 1.0                   # seconds the "shots in the last second" count looks back over


class GunPreview:
    def __init__(self, textures):
        self.renderer = Renderer(textures)
        self.transparent = transparent_tiles(textures)
        self.session = None
        self.gun_name = ""
        self.kick = 0.0
        self.tap = 0.0                      # seconds of trigger left for a single "Fire once"
        self.frame = 0
        self.clock = 0.0
        self.shots = deque()                # when shots were fired, for the shots-in-the-last-second count
        self.total_shots = 0

    @property
    def ready(self):
        return self.session is not None

    def build(self, level, gun_name, dark=False):
        """Start over in a fresh corridor with copies of the level's guns, ammunition, effects and lights, and the
        named gun in the player's hands. Does nothing (and ready is False) if the level has no such gun."""
        gun = next((g for g in level.guns if g.name == gun_name), None)
        if gun is None:
            self.session = None
            return
        room = Level.blank(LENGTH, WIDTH_CELLS)
        room.guns = [replace(g) for g in level.guns]
        room.ammo_types = [replace(a) for a in level.ammo_types]
        room.effects = [replace(e) for e in level.effects]
        room.lights = [replace(light) for light in level.lights]
        room.ambient = DARK_AMBIENT if dark else 1.0
        tiles = len(self.transparent)
        world = World(room, tiles, self.transparent)
        game = Game(room, world, random.Random(7))
        self.session = LocalSession(game)
        body = self.session.me.body
        body.x, body.y, body.angle = 1.5, WIDTH_CELLS / 2, 0.0
        self.session.me.inventory.give_gun(next(g for g in room.guns if g.name == gun_name))
        self.gun_name = gun_name
        self.kick, self.tap, self.frame, self.clock, self.total_shots = 0.0, 0.0, 0, 0.0, 0
        self.shots.clear()

    def sync_gun(self, gun):
        """Copy the settings of the gun being edited onto the preview's own copy of it, so a change (dragging where
        its bullets come from) shows at once without starting over."""
        state = self.session.me.inventory.current() if self.session is not None else None
        if state is None or state.gun.name != gun.name:
            return
        for f in fields(gun):
            if f.name != "name":
                setattr(state.gun, f.name, getattr(gun, f.name))

    def fire_once(self):
        """Pull the trigger once (held a moment, released)."""
        self.tap = TAP_SECONDS

    def update(self, dt, firing):
        """Run the game on by dt seconds. `firing` holds the trigger down for as long as it is true; a gun that
        needs a fresh pull for every shot (single, semi-auto) is pulled again as soon as it is allowed to be."""
        if self.session is None:
            return
        dt = min(dt, 0.05)
        state = self.session.me.inventory.current()
        self.frame += 1
        pull = self.tap > 0.0
        if firing and state is not None:
            pull = pull or state.gun.mode == "auto" or self.frame % 2 == 0     # release every other frame to pull again
            if state.reserve < state.gun.capacity:
                self.session.me.inventory.add_ammo(state.gun.ammo, SPARE_ROUNDS)     # never run out: keep reloading
        self.tap = max(0.0, self.tap - dt)
        events = self.session.step(Inputs(fire=pull), dt)
        self.clock += dt
        if events.fired:
            self.kick = 1.0
            self.total_shots += events.fired
            self.shots.extend([self.clock] * events.fired)
        self.kick = max(0.0, self.kick - dt * KICK_DECAY)
        while self.shots and self.clock - self.shots[0] > RATE_WINDOW:
            self.shots.popleft()

    def shots_last_second(self):
        return len(self.shots)

    def render(self, tiles, font=None):
        """The picture the player would see: the corridor with its effects and lights, then the weapon (kicked
        back after a shot, dipped while it reloads) and the ammunition counter."""
        session = self.session
        picture = self.renderer.draw(session.world, session.me.body, session.sprites(), session.lighting())
        state = session.me.inventory.current()
        hud.draw_weapon(picture, tiles, state, self.kick)
        if font is not None and state is not None:
            text = "reloading" if state.reloading else f"{state.mag}/{state.reserve}"
            hud.shadowed(picture, font, f"{state.gun.name}  {text}", (8, picture.get_height() - 22), hud.HIGHLIGHT)
        return picture
