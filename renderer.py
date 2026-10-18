"""Draws the world from a player's point of view. Shared by the game and the editor's 3D preview."""
import math

import numpy as np
import pygame

from atlas import ensure_rgba
from constants import FOG_DIST, FOV_DEG, HEIGHT, MAX_DEPTH, WIDTH
from raykernel import draw_sprites, render_scene_depth
from raylight import apply_lights, sprite_light
from raypitch import render_scene_pitch

BACKGROUND = np.array((18, 18, 26), np.uint8)       # shown only where the view distance ends
LEVEL_PITCH = 1e-4                                  # radians: a view this close to level uses the faster column renderer


class Renderer:
    def __init__(self, textures):
        self.textures = ensure_rgba(textures)       # uint8 array [tile, y, x, rgba]
        self.framebuffer = np.zeros((WIDTH, HEIGHT, 3), np.uint8)    # indexed [x, y, rgb]
        self.surface = pygame.Surface((WIDTH, HEIGHT))
        self.depth = np.zeros((WIDTH, HEIGHT), np.float32)           # distance of what is drawn in each pixel
        self.half_fov_tan = math.tan(math.radians(FOV_DEG) / 2)
        self.focal = (WIDTH / 2) / self.half_fov_tan                 # focal length in pixels

    def horizon(self, player):
        """Screen row of the horizon: where the level ground meets the sky. Looking up moves it down the
        screen and looking down moves it up."""
        return HEIGHT / 2 + math.tan(player.pitch) * self.focal

    def draw(self, world, player, sprites=(), lighting=None):
        """Render the view from `player` and return the WIDTH x HEIGHT picture. `sprites` are
        (x, y, z, size, tile[, spin[, alpha[, glow]]]) items drawn as flat pictures that face the player.
        `lighting` (lighting.Lighting, or None for a map with no lights and full ambient) lights the picture.

        A level view is drawn a column at a time (fast). A tilted view is drawn with one real 3D ray
        per pixel (raypitch.py), so looking up and down is a true rotation, not a shear."""
        dir_x, dir_y = math.cos(player.angle), math.sin(player.angle)
        scene = (world.floor_plane, world.ceil_plane, world.span_on, world.solid_from, world.pane_tex,
                 world.pane_top, world.wall_tex, world.floor_tex, world.ceil_tex)
        if abs(player.pitch) < LEVEL_PITCH:
            render_scene_depth(
                self.framebuffer, self.depth, player.x, player.y, player.eye_z, player.span, dir_x, dir_y,
                -dir_y * self.half_fov_tan, dir_x * self.half_fov_tan,   # camera plane: right vector
                HEIGHT / 2, self.focal, *scene, self.textures, MAX_DEPTH, FOG_DIST, BACKGROUND)
        else:
            render_scene_pitch(
                self.framebuffer, self.depth, player.x, player.y, player.eye_z, player.span, dir_x, dir_y,
                player.pitch, self.focal, *scene, self.textures, MAX_DEPTH, FOG_DIST, BACKGROUND)
        ambient = 1.0
        if lighting is not None:
            ambient = lighting.ambient
            apply_lights(self.framebuffer, self.depth, player.x, player.y, player.eye_z, dir_x, dir_y, player.pitch,
                         self.focal, lighting.lights, lighting.vis, lighting.occluder, ambient, FOG_DIST)
        if sprites:
            far_first = sorted(sprites, key=lambda s: -((s[0] - player.x) ** 2 + (s[1] - player.y) ** 2))
            cols = np.array([tuple(s) + (0.0, 1.0, 0.0)[len(s) - 5:] for s in far_first], np.float64).reshape(-1, 8)
            xs, ys, zs, sizes = (np.ascontiguousarray(cols[:, i]) for i in range(4))
            lit = np.zeros((len(cols), 3), np.float64)
            if lighting is not None:
                sprite_light(xs, ys, zs, sizes, lighting.lights, lighting.vis, lighting.occluder, lit)
            draw_sprites(self.framebuffer, self.depth, player.x, player.y, player.eye_z, dir_x, dir_y,
                         player.pitch, self.focal, xs, ys, zs, sizes,
                         np.clip(cols[:, 4], 0, len(self.textures) - 1).astype(np.int64),
                         np.ascontiguousarray(cols[:, 5]), np.ascontiguousarray(cols[:, 6]), lit,
                         np.ascontiguousarray(cols[:, 7]), ambient, self.textures, MAX_DEPTH, FOG_DIST)
        pygame.surfarray.blit_array(self.surface, self.framebuffer)
        return self.surface


def fit_rect(window_size, logical=(WIDTH, HEIGHT)):
    """The largest rectangle with the picture's aspect ratio that fits the window, centred in it."""
    window_w, window_h = window_size
    scale = min(window_w / logical[0], window_h / logical[1])
    w = max(1, min(window_w, round(logical[0] * scale)))        # round, not truncate: 16:9 in a 1009-high
    h = max(1, min(window_h, round(logical[1] * scale)))        # window must still fill all 1009 rows
    return pygame.Rect((window_w - w) // 2, (window_h - h) // 2, w, h)
