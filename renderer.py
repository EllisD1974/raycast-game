"""Draws the world from a player's point of view. Shared by the game and the editor's 3D preview."""
import math

import numpy as np
import pygame

from atlas import ensure_rgba
from constants import FOG_DIST, FOV_DEG, HEIGHT, MAX_DEPTH, WIDTH
from raykernel import draw_sprites, render_scene_depth
from particles import IDENTITY
from raylight import apply_lights, sprite_light
from raypitch import render_scene_pitch

BACKGROUND = np.array((18, 18, 26), np.uint8)       # shown only where the view distance ends
SHEAR_PITCH = math.radians(5)                       # a view tilted less than this is drawn by the faster column renderer


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

    def project(self, player, x, y, z):
        """(column, row, depth) where the world point (x, y, z) lands in the picture drawn from `player` (the same
        camera draw() uses, sheared or rotated), or None if it is behind the camera."""
        dir_x, dir_y = math.cos(player.angle), math.sin(player.angle)
        if abs(player.pitch) < SHEAR_PITCH:
            pitch, horizon = 0.0, self.horizon(player)
        else:
            pitch, horizon = player.pitch, HEIGHT / 2
        cp, sp = math.cos(pitch), math.sin(pitch)
        dx, dy, dz = x - player.x, y - player.y, z - player.eye_z
        ahead = dx * dir_x + dy * dir_y
        depth = ahead * cp + dz * sp
        if depth < 0.05:
            return None
        right, up = -dx * dir_y + dy * dir_x, dz * cp - ahead * sp
        return WIDTH / 2 + right / depth * self.focal, horizon - up / depth * self.focal, depth

    def draw(self, world, player, sprites=(), lighting=None):
        """Render the view from `player` and return the WIDTH x HEIGHT picture. `sprites` are
        (x, y, z, size, tile[, spin[, alpha[, glow[, color[, facing]]]]]) items drawn as flat pictures that face the
        player, or with a facing (map angle) hung flat on a wall facing that way (color None: its own colors).
        `lighting` (lighting.Lighting, or None for a map with no lights and full ambient) lights the picture.

        A view within SHEAR_PITCH of level is drawn a column at a time (fast), with the horizon moved up or down
        the screen: a shear, which near level looks the same as tilting. A view tilted further is drawn with one
        real 3D ray per pixel (raypitch.py), so looking well up and down is a true rotation."""
        dir_x, dir_y = math.cos(player.angle), math.sin(player.angle)
        scene = (world.floor_plane, world.ceil_plane, world.span_on, world.solid_from, world.pane_tex,
                 world.pane_top, world.wall_tex, world.wall_sides, world.floor_tex, world.ceil_tex)
        if abs(player.pitch) < SHEAR_PITCH:
            pitch, horizon = 0.0, self.horizon(player)  # (lighting and sprites: a level camera with the horizon moved)
            render_scene_depth(
                self.framebuffer, self.depth, player.x, player.y, player.eye_z, player.span, dir_x, dir_y,
                -dir_y * self.half_fov_tan, dir_x * self.half_fov_tan,   # camera plane: right vector
                horizon, self.focal, *scene, self.textures, MAX_DEPTH, FOG_DIST, BACKGROUND)
        else:
            pitch, horizon = player.pitch, HEIGHT / 2
            render_scene_pitch(
                self.framebuffer, self.depth, player.x, player.y, player.eye_z, player.span, dir_x, dir_y,
                player.pitch, self.focal, *scene, self.textures, MAX_DEPTH, FOG_DIST, BACKGROUND)
        ambient = 1.0
        if lighting is not None:
            ambient = lighting.ambient
            apply_lights(self.framebuffer, self.depth, player.x, player.y, player.eye_z, dir_x, dir_y, pitch, horizon,
                         self.focal, lighting.lights, lighting.vis, lighting.occluder, ambient, FOG_DIST)
        if sprites:
            far_first = sorted(sprites, key=lambda s: -((s[0] - player.x) ** 2 + (s[1] - player.y) ** 2))
            cols = np.array([tuple(s[:8]) + (0.0, 1.0, 0.0)[len(s) - 5:] for s in far_first], np.float64).reshape(-1, 8)
            colors = np.array([s[8] if len(s) > 8 and s[8] is not None else IDENTITY for s in far_first],
                              np.float64).reshape(-1, 3, 3)
            faces = np.array([s[9] if len(s) > 9 else math.nan for s in far_first], np.float64)
            xs, ys, zs, sizes = (np.ascontiguousarray(cols[:, i]) for i in range(4))
            lit = np.zeros((len(cols), 3), np.float64)
            if lighting is not None:
                sprite_light(xs, ys, zs, sizes, lighting.lights, lighting.vis, lighting.occluder, lit)
            draw_sprites(self.framebuffer, self.depth, player.x, player.y, player.eye_z, dir_x, dir_y,
                         pitch, horizon, self.focal, xs, ys, zs, sizes,
                         np.clip(cols[:, 4], 0, len(self.textures) - 1).astype(np.int64),
                         np.ascontiguousarray(cols[:, 5]), faces, np.ascontiguousarray(cols[:, 6]), lit,
                         np.ascontiguousarray(cols[:, 7]), colors, ambient, self.textures, MAX_DEPTH, FOG_DIST)
        pygame.surfarray.blit_array(self.surface, self.framebuffer)
        return self.surface


def fit_rect(window_size, logical=(WIDTH, HEIGHT)):
    """The largest rectangle with the picture's aspect ratio that fits the window, centerd in it."""
    window_w, window_h = window_size
    scale = min(window_w / logical[0], window_h / logical[1])
    w = max(1, min(window_w, round(logical[0] * scale)))        # round, not truncate: 16:9 in a 1009-high
    h = max(1, min(window_h, round(logical[1] * scale)))        # window must still fill all 1009 rows
    return pygame.Rect((window_w - w) // 2, (window_h - h) // 2, w, h)
