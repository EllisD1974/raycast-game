"""Renderer for a camera that is tilted up or down: one real 3D ray per pixel.

raykernel.py draws a column at a time and fakes looking up and down by sliding the picture (a
shear). That is right when the camera is level and increasingly wrong as it tilts: wall edges stay
vertical instead of leaning, and floors and ceilings stretch. This file draws the same world with the
camera really rotated, so it looks right all the way to straight up and straight down.

Each pixel has a ray (dx, dy, dz) from the eye. It walks the map one cell at a time exactly like the
column renderer, but because it is a single ray it is always inside one span (open space) of the
current cell, with one question to answer per cell:
  - does it hit this span's floor or ceiling before it leaves the cell? (both are planes, flat or
    sloped, so the height of the ray above them changes linearly: a single division finds the hit)
  - if not, which span of the next cell does it enter at the boundary? If it is inside one, carry on
    there; if it is in solid material (a wall, a riser, the slab between floors, a drop under a
    lower ceiling) it hits a wall face and the pixel is that face's texture.
See-through walls are remembered along the way and blended over the result, farthest first.

Rays are scaled so that their distance t is the depth along the camera's viewing axis. That is the
same meaning of "distance" the column renderer uses, so fog, shading and the depth picture that
sprites hide behind agree between the two.
"""
import math

import numpy as np
from numba import njit, prange

from raykernel import MAX_PANES, SIDE_SHADE, _clamp01, _shade, plane_z


@njit(cache=True)
def _fetch(textures, tex, tx, ty, shade):
    """Color of a texel with fog shading applied."""
    return (textures[tex, ty, tx, 0] * shade, textures[tex, ty, tx, 1] * shade, textures[tex, ty, tx, 2] * shade)


@njit(cache=True)
def _wall_ty(z, tsize):
    """Texture row for a wall at world height z: world-aligned, one repeat per unit (as in the column renderer)."""
    return int(math.floor(-z * tsize)) & (tsize - 1)


@njit(cache=True, inline="always")
def _trace_pixel(fb, zb, x, y, px, py, eye_z, eye_span, dx, dy, dz,
                 floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top, wall_tex, floor_tex, ceil_tex,
                 textures, max_dist, fog_dist, bg, pane_t, pane_tx, pane_ty, pane_id, pane_shade):
    nspans = span_on.shape[0]
    mh, mw = solid_from.shape
    tsize = textures.shape[1]
    tmask = tsize - 1
    cx = int(math.floor(px))
    cy = int(math.floor(py))
    ddx = abs(1.0 / dx) if abs(dx) > 1e-12 else 1e30
    ddy = abs(1.0 / dy) if abs(dy) > 1e-12 else 1e30
    if dx < 0.0:
        step_x, side_x = -1, (px - cx) * ddx
    else:
        step_x, side_x = 1, (cx + 1.0 - px) * ddx
    if dy < 0.0:
        step_y, side_y = -1, (py - cy) * ddy
    else:
        step_y, side_y = 1, (cy + 1.0 - py) * ddy

    red, green, blue = float(bg[0]), float(bg[1]), float(bg[2])
    depth = 1e9
    n_panes = 0
    if not (0 <= cx < mw and 0 <= cy < mh) or span_on[eye_span, cy, cx] == 0:
        fb[x, y, 0], fb[x, y, 1], fb[x, y, 2] = np.uint8(red), np.uint8(green), np.uint8(blue)
        zb[x, y] = depth
        return
    s = eye_span
    t0 = 1e-3
    while True:
        if side_x < side_y:
            t1 = side_x
            side_x += ddx
            nx, ny, side = cx + step_x, cy, 0
        else:
            t1 = side_y
            side_y += ddy
            nx, ny, side = cx, cy + step_y, 1
        if t1 < t0 + 1e-9:
            t1 = t0 + 1e-9
        t1c = min(t1, max_dist)

        e0x = _clamp01(px + dx * t0 - cx)
        e0y = _clamp01(py + dy * t0 - cy)
        e1x = _clamp01(px + dx * t1c - cx)
        e1y = _clamp01(py + dy * t1c - cy)
        z0 = eye_z + dz * t0
        z1 = eye_z + dz * t1c
        g0 = z0 - plane_z(floor_plane, s, cx, cy, e0x, e0y)          # height above the floor
        g1 = z1 - plane_z(floor_plane, s, cx, cy, e1x, e1y)
        h0 = plane_z(ceil_plane, s, cx, cy, e0x, e0y) - z0           # height below the ceiling
        h1 = plane_z(ceil_plane, s, cx, cy, e1x, e1y) - z1

        hit_floor = g1 < 0.0
        hit_ceil = h1 < 0.0
        t_floor = t_ceil = 1e30
        if hit_floor:
            t_floor = t0 if g0 <= 0.0 else t0 + (t1c - t0) * g0 / (g0 - g1)
        if hit_ceil:
            t_ceil = t0 if h0 <= 0.0 else t0 + (t1c - t0) * h0 / (h0 - h1)
        if hit_floor or hit_ceil:
            on_floor = t_floor <= t_ceil
            t = t_floor if on_floor else t_ceil
            wx = px + dx * t
            wy = py + dy * t
            tx = int((wx - math.floor(wx)) * tsize) & tmask
            ty = int((wy - math.floor(wy)) * tsize) & tmask
            tex = floor_tex[s, cy, cx] if on_floor else ceil_tex[s, cy, cx]
            shade = _shade(t, fog_dist)
            red, green, blue = _fetch(textures, tex, tx, ty, shade)
            depth = t
            break
        if t1 > max_dist:
            break                                                   # nothing hit within the view distance

        # The ray leaves the cell at t1 with height z1, inside this span. What is on the other side?
        if side == 0:
            wallx = py + dy * t1
        else:
            wallx = px + dx * t1
        wallx -= math.floor(wallx)
        if (side == 0 and dx > 0.0) or (side == 1 and dy < 0.0):
            wallx = 1.0 - wallx
        wtx = int(wallx * tsize) & tmask
        shade = _shade(t1, fog_dist) * (1.0 if side == 0 else SIDE_SHADE)
        inside = 0 <= nx < mw and 0 <= ny < mh
        if (not inside) or s >= solid_from[ny, nx]:
            tex = wall_tex[ny, nx] if inside else 0
            red, green, blue = _fetch(textures, tex, wtx, _wall_ty(z1, tsize), shade)
            depth = t1
            break

        nfx = _clamp01(px + dx * t1 - nx)
        nfy = _clamp01(py + dy * t1 - ny)
        found = -1
        for k in range(nspans):
            if span_on[k, ny, nx] == 0:
                continue
            zfn = plane_z(floor_plane, k, nx, ny, nfx, nfy)
            zcn = plane_z(ceil_plane, k, nx, ny, nfx, nfy)
            if zfn - 1e-7 <= z1 < zcn:
                found = k
                break
        if found < 0:
            # Solid material between the spans: a riser under a higher floor (drawn with that floor's
            # texture), the slab between floors, or the drop under a lower ceiling.
            tex = 0
            below_a_floor = False
            for k in range(nspans):
                if span_on[k, ny, nx] == 0:
                    continue
                tex = ceil_tex[k, ny, nx]
                if plane_z(floor_plane, k, nx, ny, nfx, nfy) > z1:
                    tex = floor_tex[k, ny, nx]
                    below_a_floor = True
                    break
            if (not below_a_floor) and solid_from[ny, nx] < nspans:
                tex = wall_tex[ny, nx]                              # a wall hanging above the room below
            red, green, blue = _fetch(textures, tex, wtx, _wall_ty(z1, tsize), shade)
            depth = t1
            break
        if found == 0 and pane_tex[ny, nx] >= 0 and z1 < pane_top[ny, nx] and n_panes < MAX_PANES:
            pane_t[n_panes], pane_tx[n_panes] = t1, wtx
            pane_ty[n_panes], pane_id[n_panes] = _wall_ty(z1, tsize), pane_tex[ny, nx]
            pane_shade[n_panes] = shade
            n_panes += 1
        s = found
        cx, cy = nx, ny
        t0 = t1

    # Blend the see-through faces the ray went through over what it finally hit, farthest first.
    for p in range(n_panes - 1, -1, -1):
        alpha = textures[pane_id[p], pane_ty[p], pane_tx[p], 3]
        if alpha == 0:
            continue
        a = alpha / 255.0
        pr, pg, pb = _fetch(textures, pane_id[p], pane_tx[p], pane_ty[p], pane_shade[p])
        red, green, blue = pr * a + red * (1.0 - a), pg * a + green * (1.0 - a), pb * a + blue * (1.0 - a)
    fb[x, y, 0], fb[x, y, 1], fb[x, y, 2] = np.uint8(red), np.uint8(green), np.uint8(blue)
    zb[x, y] = depth


@njit(cache=True, parallel=True)
def render_scene_pitch(fb, zb, px, py, eye_z, eye_span, dir_x, dir_y, pitch, focal,
                       floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top, wall_tex, floor_tex,
                       ceil_tex, textures, max_dist, fog_dist, bg):
    """Fill `fb` (W, H, 3) and `zb` (W, H) for a camera looking along (dir_x, dir_y) tilted up by `pitch`
    radians (negative looks down), with `focal` the focal length in pixels."""
    width, height = fb.shape[0], fb.shape[1]
    cp, sp = math.cos(pitch), math.sin(pitch)
    fx, fy, fz = dir_x * cp, dir_y * cp, sp                  # where the camera looks
    rx, ry = -dir_y, dir_x                                   # to the right of the picture
    ux, uy, uz = -dir_x * sp, -dir_y * sp, cp                # up the picture
    for x in prange(width):
        pane_t = np.empty(MAX_PANES, np.float64)
        pane_tx = np.empty(MAX_PANES, np.int64)
        pane_ty = np.empty(MAX_PANES, np.int64)
        pane_id = np.empty(MAX_PANES, np.int64)
        pane_shade = np.empty(MAX_PANES, np.float64)
        u = (x + 0.5 - width * 0.5) / focal
        for y in range(height):
            v = (height * 0.5 - (y + 0.5)) / focal
            _trace_pixel(fb, zb, x, y, px, py, eye_z, eye_span,
                         fx + u * rx + v * ux, fy + u * ry + v * uy, fz + v * uz,
                         floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top, wall_tex, floor_tex,
                         ceil_tex, textures, max_dist, fog_dist, bg, pane_t, pane_tx, pane_ty, pane_id, pane_shade)
