"""Lighting, compiled with numba: point lights that color what the renderer has drawn.

The scene is drawn first (raykernel.py / raypitch.py) with its distance fog and a depth picture. Lighting is
a pass over that picture. Each pixel's place in the world is found from its depth and its ray, and every
light near enough adds to it:

    color = color * (ambient + light / fog_shade)

`ambient` is how bright the map is without lights (1 leaves a map exactly as it was before lights existed;
less is dark) and `light` is the sum over lights of color * intensity * (1 - (distance / radius)^2)^2 for the
lights that can see the spot (eased off above 1 so overlapping lights do not burn out to white). Dividing by the
fog shade lets a light shine through the distance fog, so a lit patch far away is not dimmed by being far
from the camera.

Walls stop light. For each light, `build_visibility` marks which map cells it can see (a line of sight over the
grid of wall cells), and a pixel reads that grid around the spot just in front of the surface it shows,
blending the four nearest cells so the edge of a shadow is not blocky. It is a flat map of cells: floors above
and below a light are not told apart, only the distance (so a light reaches through a slab a little).

lights is a float64 array, one row per light: x, y, z, red, green, blue (color * intensity, 0 to about 20) and
radius. vis is float32 [light, cell row, cell column]; occluder is uint8 [cell row, cell column], 1 where a wall
cell stops light.
"""
import math

import numpy as np
from numba import njit, prange

from raykernel import _shade

KNEE = 1.0               # light adds up linearly to this much, then eases off so stacked lights do not blow out
HEADROOM = 1.5           # and at most this much more is added beyond the knee, however many lights overlap
BACK_OFF = 0.04          # how far in front of a surface the spot that is looked up in the visibility map is
SIGHT_STEP = 0.2         # cells between the points checked along a line of sight
LIGHT_STEP = 2           # pixels between the ones lighting is worked out for; those between are blended
DEPTH_MATCH = 0.05       # a pixel is blended only from samples this close to its depth (as a fraction of it)


@njit(cache=True)
def _can_see(lx, ly, tx, ty, occluder):
    """True if no wall cell lies between (lx, ly) and (tx, ty) on the map. The light's own cell and the
    target's cell do not count."""
    h, w = occluder.shape
    dx, dy = tx - lx, ty - ly
    dist = math.sqrt(dx * dx + dy * dy)
    steps = max(1, int(math.ceil(dist / SIGHT_STEP)))
    start_x, start_y = int(math.floor(lx)), int(math.floor(ly))
    end_x, end_y = int(math.floor(tx)), int(math.floor(ty))
    for i in range(1, steps):
        f = i / steps
        cx, cy = int(math.floor(lx + dx * f)), int(math.floor(ly + dy * f))
        if (cx == start_x and cy == start_y) or (cx == end_x and cy == end_y):
            continue
        if cx < 0 or cy < 0 or cx >= w or cy >= h or occluder[cy, cx]:
            return False
    return True


@njit(cache=True)
def build_visibility(lights, occluder, vis):
    """Fill vis[i] (zeroed first) with 1 for each open map cell within light i's reach whose center it sees."""
    n = lights.shape[0]
    h, w = occluder.shape
    for i in range(n):
        vis[i, :, :] = 0.0
        lx, ly, radius = lights[i, 0], lights[i, 1], lights[i, 6]
        x0, x1 = max(0, int(math.floor(lx - radius)) - 1), min(w - 1, int(math.floor(lx + radius)) + 1)
        y0, y1 = max(0, int(math.floor(ly - radius)) - 1), min(h - 1, int(math.floor(ly + radius)) + 1)
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                if occluder[cy, cx]:
                    continue
                if _can_see(lx, ly, cx + 0.5, cy + 0.5, occluder):
                    vis[i, cy, cx] = 1.0


@njit(cache=True, inline="always")
def _sample_visibility(vis, occluder, i, x, y):
    """How much of the map around (x, y) light i can see: the four nearest open cells' centers, blended."""
    h, w = occluder.shape
    u, v = x - 0.5, y - 0.5
    cx0, cy0 = int(math.floor(u)), int(math.floor(v))
    fx, fy = u - cx0, v - cy0
    total = 0.0
    weight = 0.0
    for oy in range(2):
        for ox in range(2):
            cx, cy = cx0 + ox, cy0 + oy
            if cx < 0 or cy < 0 or cx >= w or cy >= h or occluder[cy, cx]:
                continue                               # a wall's own cell says nothing about the open space beside it
            k = (fx if ox else 1.0 - fx) * (fy if oy else 1.0 - fy)
            total += vis[i, cy, cx] * k
            weight += k
    return total / weight if weight > 1e-6 else 0.0


@njit(cache=True)
def _soft(v):
    """Light that adds up without limit, eased off above KNEE: v up to KNEE is unchanged, above it the rest
    approaches HEADROOM, so many overlapping lights brighten a surface but do not burn it out to white."""
    if v <= KNEE:
        return v
    return KNEE + HEADROOM * (1.0 - math.exp(-(v - KNEE) / HEADROOM))


@njit(cache=True, inline="always")
def _light_at(lights, vis, occluder, x, y, z, qx, qy):
    """(red, green, blue) light arriving at the world point (x, y, z), reading visibility at (qx, qy)."""
    r = g = b = 0.0
    for i in range(lights.shape[0]):
        dx, dy, dz = x - lights[i, 0], y - lights[i, 1], z - lights[i, 2]
        d2 = dx * dx + dy * dy + dz * dz
        r2 = lights[i, 6] * lights[i, 6]
        if d2 >= r2:
            continue
        seen = _sample_visibility(vis, occluder, i, qx, qy)
        if seen <= 0.0:
            continue
        a = 1.0 - d2 / r2
        k = a * a * seen
        r += lights[i, 3] * k
        g += lights[i, 4] * k
        b += lights[i, 5] * k
    return _soft(r), _soft(g), _soft(b)


@njit(cache=True, inline="always")
def _pixel_light(x, y, depth, px, py, eye_z, fx, fy, fz, rx, ry, ux, uy, uz, horizon, focal, width,
                 lights, vis, occluder):
    """The light (r, g, b) falling on what pixel (x, y) shows, `depth` along its ray."""
    u = (x + 0.5 - width * 0.5) / focal
    v = (horizon - (y + 0.5)) / focal
    ddx, ddy, ddz = fx + u * rx + v * ux, fy + u * ry + v * uy, fz + v * uz
    wx, wy, wz = px + depth * ddx, py + depth * ddy, eye_z + depth * ddz
    norm = math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz)
    qx, qy = wx - ddx / norm * BACK_OFF, wy - ddy / norm * BACK_OFF
    return _light_at(lights, vis, occluder, wx, wy, wz, qx, qy)


@njit(cache=True, parallel=True)
def apply_lights(fb, zb, px, py, eye_z, dir_x, dir_y, pitch, horizon, focal, lights, vis, occluder, ambient, fog_dist):
    """Light the picture in fb (W, H, 3) in place, using the depth picture zb (W, H) (1e9 where nothing was
    drawn). The camera is at (px, py, eye_z) looking along (dir_x, dir_y) tilted up by `pitch`, with the middle
    of its view at screen row `horizon` (the middle row, unless a level camera is sheared to look up or down).

    Light changes slowly across a surface, so it is worked out only at every LIGHT_STEP-th pixel across and down
    and blended between those for the pixels in between. Where the samples around a pixel are not all on its
    surface (their depths differ: the edge of a wall, a sprite's outline), the pixel is worked out on its own."""
    width, height = fb.shape[0], fb.shape[1]
    cp, sp = math.cos(pitch), math.sin(pitch)
    fx, fy, fz = dir_x * cp, dir_y * cp, sp                  # where the camera looks
    rx, ry = -dir_y, dir_x                                   # to the right of the picture
    ux, uy, uz = -dir_x * sp, -dir_y * sp, cp                # up the picture
    sw = (width + LIGHT_STEP - 2) // LIGHT_STEP + 1          # samples across, the last on the last column
    sh = (height + LIGHT_STEP - 2) // LIGHT_STEP + 1
    sample = np.zeros((sw, sh, 3), np.float64)
    sample_depth = np.empty((sw, sh), np.float64)
    for i in prange(sw):
        x = min(i * LIGHT_STEP, width - 1)
        for j in range(sh):
            y = min(j * LIGHT_STEP, height - 1)
            depth = zb[x, y]
            sample_depth[i, j] = depth
            if depth > 1e8:
                continue
            sample[i, j, 0], sample[i, j, 1], sample[i, j, 2] = _pixel_light(
                x, y, depth, px, py, eye_z, fx, fy, fz, rx, ry, ux, uy, uz, horizon, focal, width, lights, vis, occluder)
    for x in prange(width):
        i0 = x // LIGHT_STEP
        i1 = min(i0 + 1, sw - 1)
        x0, x1 = min(i0 * LIGHT_STEP, width - 1), min(i1 * LIGHT_STEP, width - 1)
        ax = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
        for y in range(height):
            depth = zb[x, y]
            if depth > 1e8:
                continue
            j0 = y // LIGHT_STEP
            j1 = min(j0 + 1, sh - 1)
            y0, y1 = min(j0 * LIGHT_STEP, height - 1), min(j1 * LIGHT_STEP, height - 1)
            ay = (y - y0) / (y1 - y0) if y1 > y0 else 0.0
            lr = lg = lb = 0.0
            same_surface = True
            for oi in range(2):
                wi = ax if oi else 1.0 - ax
                if wi <= 0.0:
                    continue
                i = i1 if oi else i0
                for oj in range(2):
                    w = wi * (ay if oj else 1.0 - ay)
                    if w <= 0.0:
                        continue
                    j = j1 if oj else j0
                    if abs(sample_depth[i, j] - depth) > DEPTH_MATCH * depth:
                        same_surface = False
                        break
                    lr += sample[i, j, 0] * w
                    lg += sample[i, j, 1] * w
                    lb += sample[i, j, 2] * w
                if not same_surface:
                    break
            if not same_surface:
                lr, lg, lb = _pixel_light(x, y, depth, px, py, eye_z, fx, fy, fz, rx, ry, ux, uy, uz, horizon, focal,
                                          width, lights, vis, occluder)
            shade = _shade(depth, fog_dist)
            fb[x, y, 0] = np.uint8(min(255.0, fb[x, y, 0] * (ambient + lr / shade)))
            fb[x, y, 1] = np.uint8(min(255.0, fb[x, y, 1] * (ambient + lg / shade)))
            fb[x, y, 2] = np.uint8(min(255.0, fb[x, y, 2] * (ambient + lb / shade)))


@njit(cache=True)
def sprite_light(sp_x, sp_y, sp_z, sp_size, lights, vis, occluder, out):
    """out[i] = the light (r, g, b) at the middle of sprite i, for draw_sprites to color it with."""
    for i in range(sp_x.shape[0]):
        r, g, b = _light_at(lights, vis, occluder, sp_x[i], sp_y[i], sp_z[i] + sp_size[i] * 0.5, sp_x[i], sp_y[i])
        out[i, 0], out[i, 1], out[i, 2] = r, g, b
