"""Renderer for a camera that is tilted up or down, drawn a screen line at a time.

When the camera is tilted, the world's vertical lines no longer stay vertical on the screen: they all lean
towards one vanishing point straight above the middle of the picture (looking up) or below it (looking down).
Each line through that point shows one vertical slice of the world, the slice along one map direction from the
eye. So the column renderer's method (raykernel.py: walk the map once along that direction, drawing each floor,
ceiling and wall as a run of samples) works along those lines just as it does down the columns of a level view.

The lines fan out from the vanishing point (see _plan), close enough together that no pixel is more than half a
pixel from one. A line steeper than 45 degrees on the picture has a sample on every pixel row it crosses, a flatter
one on every column, so each pixel takes the color and depth of the sample on its own row (or column) of the
nearest line.

Along a line the samples are placed by the slope m = (height - eye height) / distance of what they show, as rows
are in the column renderer (where row = horizon - m * focal). A sample d rows (or columns) from the vanishing point
shows slope m where

    d = K / p,   p = a * cos(pitch) + m * sin(pitch)

(a is how far the line's map direction points ahead, K is fixed for the line), and p * distance is the depth
along the camera's axis, which is what the depth picture, the fog and the shading use, as in raypitch.py (the
renderer that sends one ray per pixel, kept as the exact picture this one is checked against).
"""
import math

import numpy as np
from numba import njit, prange

from raykernel import EPS, MAX_BRANCHES, MAX_PANES, SIDE_SHADE, _clamp01, _shade, plane_z, side_of


@njit(cache=True, inline="always")
def _pos(z, t, eye_z, line):
    """Where along `line` (as a sample index, fractional) world height z at distance t lands. Samples run from
    high slopes to low ones, like rows down a column; a point behind the camera is past the end."""
    acp, sp, k, sigma, d_ref = line[0], line[1], line[2], line[3], line[4]
    p = acp + (z - eye_z) / t * sp
    if p <= 1e-9:
        return sigma * 1e9
    return sigma * (k / p - d_ref)


@njit(cache=True, inline="always")
def _slope(i, line):
    """The slope (height above the eye / distance) sample i of `line` shows, and its p (see the module)."""
    acp, sp, k, sigma, d_ref = line[0], line[1], line[2], line[3], line[4]
    p = k / max(d_ref + sigma * i, 1e-3)
    return (p - acp) / sp, p


@njit(cache=True, inline="always")
def _rows(z_high, z_low, t, eye_z, line, top, bot):
    """The samples [r0, r1) between world heights z_high and z_low at distance t, clipped to [top, bot)."""
    r0 = max(int(math.ceil(_pos(z_high, t, eye_z, line))), top)
    r1 = min(int(math.ceil(_pos(z_low, t, eye_z, line))), bot)
    return r0, r1


@njit(cache=True)
def _wall(cb, db, z_low, z_high, top, bot, t, tx, tex, own, band_low, band_high, side, eye_z, line, textures,
          fog_dist):
    """A wall strip between two world heights at distance t, of tile `tex` with the side's own tile `own` (-1:
    none) laid over it between band_low and band_high (its transparent pixels show `tex`)."""
    if z_high <= z_low:
        return
    tsize = textures.shape[1]
    r0, r1 = _rows(z_high, z_low, t, eye_z, line, top, bot)
    for r in range(r0, r1):
        m, p = _slope(r, line)
        z = eye_z + m * t
        ty = int(math.floor(-z * tsize)) & (tsize - 1)
        depth = t * p
        shade = _shade(depth, fog_dist) * side
        if own >= 0 and band_low <= z < band_high:
            a = textures[own, ty, tx, 3] / 255.0
            for c in range(3):
                cb[r, c] = np.uint8((textures[own, ty, tx, c] * a + textures[tex, ty, tx, c] * (1.0 - a)) * shade)
        else:
            for c in range(3):
                cb[r, c] = np.uint8(textures[tex, ty, tx, c] * shade)
        db[r] = depth


@njit(cache=True)
def _surface(cb, db, r0, r1, m_near, m_far, t0, t1, px, py, rdx, rdy, tex, line, textures, fog_dist):
    """Samples r0..r1 of a floor or ceiling that runs from slope m_near (distance t0) to m_far (t1). Along a plane
    1 / distance changes linearly with the slope, which gives perspective-correct texturing."""
    tsize = textures.shape[1]
    tmask = tsize - 1
    inv0 = 1.0 / t0
    inv1 = 1.0 / t1
    span = m_far - m_near
    if abs(span) < 1e-12:
        span = 1e-12
    for r in range(r0, r1):
        m, p = _slope(r, line)
        u = (m - m_near) / span
        t = 1.0 / max(inv0 + (inv1 - inv0) * u, 1e-9)
        wx = px + rdx * t
        wy = py + rdy * t
        tx = int((wx - math.floor(wx)) * tsize) & tmask
        ty = int((wy - math.floor(wy)) * tsize) & tmask
        depth = t * p
        shade = _shade(depth, fog_dist)
        cb[r, 0] = np.uint8(textures[tex, ty, tx, 0] * shade)
        cb[r, 1] = np.uint8(textures[tex, ty, tx, 1] * shade)
        cb[r, 2] = np.uint8(textures[tex, ty, tx, 2] * shade)
        db[r] = depth


@njit(cache=True)
def _render_line(cb, db, n, px, py, eye_z, eye_span, rdx, rdy, line,
                 floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top, wall_tex, wall_sides, floor_tex,
                 ceil_tex, textures, max_dist, fog_dist, bg, branches, pane_f, pane_i):
    """Draw samples 0..n of one line into cb (n, 3) and db (n,): raykernel._render_column, walking the map along the
    unit direction (rdx, rdy), with the line's samples in place of a column's rows. branches (6, MAX_BRANCHES),
    pane_f and pane_i (4, MAX_PANES) are room to work in, reused from line to line."""
    nspans = span_on.shape[0]
    mh, mw = solid_from.shape
    tmask = textures.shape[1] - 1
    tsize = textures.shape[1]

    cx = int(math.floor(px))
    cy = int(math.floor(py))
    ddx = abs(1.0 / rdx) if rdx != 0.0 else 1e30
    ddy = abs(1.0 / rdy) if rdy != 0.0 else 1e30
    if rdx < 0.0:
        step_x, side_x = -1, (px - cx) * ddx
    else:
        step_x, side_x = 1, (cx + 1.0 - px) * ddx
    if rdy < 0.0:
        step_y, side_y = -1, (py - cy) * ddy
    else:
        step_y, side_y = 1, (cy + 1.0 - py) * ddy

    cur_s, cur_top, cur_bot, nxt_s, nxt_top, nxt_bot = (branches[0], branches[1], branches[2], branches[3],
                                                         branches[4], branches[5])
    # See-through wall faces met along the line, nearest first: pane_f holds distance, side shading and the heights
    # (from, to), pane_i the texture column, the tile and the samples still open when the walk reached them.
    n_panes = 0
    n_cur = 0
    if 0 <= cx < mw and 0 <= cy < mh and span_on[eye_span, cy, cx] != 0:
        cur_s[0], cur_top[0], cur_bot[0] = eye_span, 0, n
        n_cur = 1
    t0 = 1e-3

    while n_cur > 0:
        if side_x < side_y:
            t1 = side_x
            side_x += ddx
            nx, ny, side = cx + step_x, cy, 0
        else:
            t1 = side_y
            side_y += ddy
            nx, ny, side = cx, cy + step_y, 1
        if t1 > max_dist:
            break
        if t1 < t0 + 1e-6:
            t1 = t0 + 1e-6

        e0x = _clamp01(px + rdx * t0 - cx)
        e0y = _clamp01(py + rdy * t0 - cy)
        e1x = _clamp01(px + rdx * t1 - cx)
        e1y = _clamp01(py + rdy * t1 - cy)
        nfx = _clamp01(px + rdx * t1 - nx)
        nfy = _clamp01(py + rdy * t1 - ny)

        if side == 0:
            wallx = py + rdy * t1
        else:
            wallx = px + rdx * t1
        wallx -= math.floor(wallx)
        if (side == 0 and rdx > 0.0) or (side == 1 and rdy < 0.0):
            wallx = 1.0 - wallx
        wtx = int(wallx * tsize) & tmask
        side_shade = 1.0 if side == 0 else SIDE_SHADE

        inside = 0 <= nx < mw and 0 <= ny < mh
        face = side_of(side, step_x, step_y)
        own = int(wall_sides[ny, nx, face, 0]) if inside else -1
        band_low = wall_sides[ny, nx, face, 1] if inside else 0.0
        band_high = wall_sides[ny, nx, face, 2] if inside else 0.0
        n_next = 0

        for b in range(n_cur):
            s = cur_s[b]
            top = cur_top[b]
            bot = cur_bot[b]
            next_solid = (not inside) or s >= solid_from[ny, nx]

            zf0 = plane_z(floor_plane, s, cx, cy, e0x, e0y)
            zf1 = plane_z(floor_plane, s, cx, cy, e1x, e1y)
            zc0 = plane_z(ceil_plane, s, cx, cy, e0x, e0y)
            zc1 = plane_z(ceil_plane, s, cx, cy, e1x, e1y)

            # floor: from its far edge (zf1 at t1) to its near edge (zf0 at t0)
            r0 = max(int(math.ceil(_pos(zf1, t1, eye_z, line))), top)
            r1 = min(int(math.ceil(_pos(zf0, t0, eye_z, line))), bot)
            if r1 > r0:
                _surface(cb, db, r0, r1, (zf0 - eye_z) / t0, (zf1 - eye_z) / t1, t0, t1, px, py, rdx, rdy,
                         floor_tex[s, cy, cx], line, textures, fog_dist)
            # ceiling: from its near edge (zc0 at t0) to its far edge (zc1 at t1)
            r0 = max(int(math.ceil(_pos(zc0, t0, eye_z, line))), top)
            r1 = min(int(math.ceil(_pos(zc1, t1, eye_z, line))), bot)
            if r1 > r0:
                _surface(cb, db, r0, r1, (zc0 - eye_z) / t0, (zc1 - eye_z) / t1, t0, t1, px, py, rdx, rdy,
                         ceil_tex[s, cy, cx], line, textures, fog_dist)

            if next_solid:
                wtex = wall_tex[ny, nx] if inside else 0
                _wall(cb, db, zf1, zc1, top, bot, t1, wtx, wtex, own, band_low, band_high, side_shade, eye_z, line,
                      textures, fog_dist)
                continue

            cur = zf1
            tex_above = 0
            for k in range(nspans):
                if span_on[k, ny, nx] == 0:
                    continue
                zfn = plane_z(floor_plane, k, nx, ny, nfx, nfy)
                zcn = plane_z(ceil_plane, k, nx, ny, nfx, nfy)
                tex_above = ceil_tex[k, ny, nx]
                if zcn <= cur:
                    continue
                if zfn > cur:
                    hi = min(zfn, zc1)
                    _wall(cb, db, cur, hi, top, bot, t1, wtx, floor_tex[k, ny, nx], own, band_low, band_high,
                          side_shade, eye_z, line, textures, fog_dist)
                    cur = hi
                    if cur >= zc1:
                        break
                hi = min(zcn, zc1)
                if hi - cur > EPS:
                    if k == 0 and pane_tex[ny, nx] >= 0 and n_panes < MAX_PANES:
                        face_top = min(hi, pane_top[ny, nx])
                        face_low = cur          # (from another see-through cell: only above its top, as raykernel)
                        if s == 0 and pane_tex[cy, cx] >= 0:
                            face_low = max(cur, pane_top[cy, cx])
                        if face_top - face_low > EPS:
                            pane_f[0, n_panes], pane_f[1, n_panes] = t1, side_shade
                            pane_f[2, n_panes], pane_f[3, n_panes] = face_low, face_top
                            pane_i[0, n_panes], pane_i[1, n_panes] = wtx, pane_tex[ny, nx]
                            pane_i[2, n_panes], pane_i[3, n_panes] = top, bot
                            n_panes += 1
                    ntop, nbot = _rows(hi, cur, t1, eye_z, line, top, bot)
                    if ntop < nbot and n_next < MAX_BRANCHES:
                        nxt_s[n_next], nxt_top[n_next], nxt_bot[n_next] = k, ntop, nbot
                        n_next += 1
                    cur = hi
                if cur >= zc1:
                    break
            if cur < zc1:
                if inside and solid_from[ny, nx] < nspans:
                    tex_above = wall_tex[ny, nx]
                _wall(cb, db, cur, zc1, top, bot, t1, wtx, tex_above, own, band_low, band_high, side_shade, eye_z,
                      line, textures, fog_dist)

        for b in range(n_next):
            cur_s[b], cur_top[b], cur_bot[b] = nxt_s[b], nxt_top[b], nxt_bot[b]
        n_cur = n_next
        cx, cy = nx, ny
        t0 = t1

    for b in range(n_cur):               # samples still open where the view distance ends
        for r in range(cur_top[b], cur_bot[b]):
            for c in range(3):
                cb[r, c] = bg[c]
            db[r] = 1e9

    # See-through faces, blended over what is behind them from the farthest to the nearest.
    for q in range(n_panes - 1, -1, -1):
        t = pane_f[0, q]
        r0, r1 = _rows(pane_f[3, q], pane_f[2, q], t, eye_z, line, pane_i[2, q], pane_i[3, q])
        tex = pane_i[1, q]
        tx = pane_i[0, q]
        for r in range(r0, r1):
            m, p = _slope(r, line)
            z = eye_z + m * t
            ty = int(math.floor(-z * tsize)) & (tsize - 1)
            alpha = textures[tex, ty, tx, 3]
            if alpha == 0:
                continue
            shade = _shade(t * p, fog_dist) * pane_f[1, q]
            a = alpha / 255.0
            for c in range(3):
                cb[r, c] = np.uint8(textures[tex, ty, tx, c] * shade * a + cb[r, c] * (1.0 - a))


@njit(cache=True)
def _clip(vx, vy, gx, gy, width, height):
    """The distances (from, to) along the half-line from (vx, vy) in direction (gx, gy) that lie within the
    picture; from > to when it misses it."""
    lo, hi = 0.0, 1e30
    if abs(gx) < 1e-12:
        if vx < 0.0 or vx > width:
            return 1.0, 0.0
    else:
        a, b = (0.0 - vx) / gx, (width - vx) / gx
        lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
    if abs(gy) < 1e-12:
        if vy < 0.0 or vy > height:
            return 1.0, 0.0
    else:
        a, b = (0.0 - vy) / gy, (height - vy) / gy
        lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
    return lo, hi


MAX_LEVELS = 8          # how many times the fan of lines may halve towards the vanishing point (see _plan)


@njit(cache=True)
def _sector_point(sector, d, t):
    """The picture point (x, y, from the vanishing point) `d` out along the major axis of `sector` with slope t."""
    if sector == 0:
        return t * d, d                 # down: rows below the point
    if sector == 1:
        return t * d, -d                # up
    if sector == 2:
        return d, t * d                 # right: columns to the right of the point
    return -d, t * d                    # left


@njit(cache=True)
def _plan(width, height, pitch, focal, dir_x, dir_y):
    """The fan of lines for a camera tilted by `pitch` looking along (dir_x, dir_y): (fan, lines, offsets).

    The lines leave the vanishing point in four sectors: down and up, where they are steeper than 45 degrees on the
    picture and have a sample on every row, and right and left, flatter, with a sample on every column. In a sector
    the lines are spread evenly in slope (sideways pixels per row, or per column), close enough that no pixel is
    more than half a pixel from one. Nearer the point they crowd together, so each sector is built in levels: every
    2^k-th line alone is still close enough out to 1 / 2^k of the sector's reach, and a line that is an odd
    multiple of 2^k only starts there.

    fan (4, 6): per sector, its first line, line count, first slope, slope step, levels and reach.
    lines (n, 8): the line's _pos numbers (a cos(pitch), sin(pitch), K, sigma, where along the major axis sample
    0 is), its map direction (x, y) and its sample count. offsets (n + 1): where each line's samples start in the
    shared buffer. Distances along a major axis are measured from the vanishing point to pixel centers."""
    cp, sp = math.cos(pitch), math.sin(pitch)
    vx, vy = width * 0.5, height * 0.5 - focal * cp / sp           # the vanishing point
    x0, x1 = 0.5 - vx, width - 0.5 - vx                             # the pixel centers, from the point
    y0, y1 = 0.5 - vy, height - 0.5 - vy
    sigma = 1.0 if sp > 0.0 else -1.0                               # samples run outwards looking up, inwards down
    fan = np.zeros((4, 6), np.float64)
    total = 0
    for sector in range(4):
        # The part of the picture on this side of the point: major axis from d0 to d1, minor axis m0 to m1.
        if sector == 0:
            d0, d1, m0, m1 = y0, y1, x0, x1
        elif sector == 1:
            d0, d1, m0, m1 = -y1, -y0, x0, x1
        elif sector == 2:
            d0, d1, m0, m1 = x0, x1, y0, y1
        else:
            d0, d1, m0, m1 = -x1, -x0, y0, y1
        fan[sector, 0] = total
        if d1 <= 0.0:
            continue                                                # the picture is all on the other side
        d0 = max(d0, 0.5)
        t_lo = max(-1.0, min(m0 / d0, m0 / d1))
        t_hi = min(1.0, max(m1 / d0, m1 / d1))
        if t_hi < t_lo:
            continue
        levels = min(MAX_LEVELS, max(0, int(math.floor(math.log2(d1 / d0)))))
        base = max(1, int(math.ceil((t_hi - t_lo) * d1 / (1 << levels))))
        n = (base << levels) + 1
        fan[sector, 1], fan[sector, 2], fan[sector, 3] = n, t_lo, (t_hi - t_lo) / (base << levels)
        fan[sector, 4], fan[sector, 5] = levels, d1
        total += n
    lines = np.zeros((total, 8), np.float64)
    offsets = np.zeros(total + 1, np.int64)
    for sector in range(4):
        first, n_sector, t_lo, dt = int(fan[sector, 0]), int(fan[sector, 1]), fan[sector, 2], fan[sector, 3]
        levels, reach = int(fan[sector, 4]), fan[sector, 5]
        # where pixel centers fall along the major axis (they are a whole number of pixels apart)
        if sector == 0:
            frac = y0 - math.floor(y0)
        elif sector == 1:
            frac = -y1 - math.floor(-y1)
        elif sector == 2:
            frac = x0 - math.floor(x0)
        else:
            frac = -x1 - math.floor(-x1)
        for k in range(n_sector):
            j = first + k
            t = t_lo + k * dt
            level = levels
            if k != 0:
                level = 0
                while level < levels and (k >> level) & 1 == 0:
                    level += 1
            # The stretch of the major axis where the line is on the picture (a pixel wider each side, for the
            # pixels half a pixel off it) and its level is needed.
            lo, hi = max(0.5, reach / (1 << (level + 1)) - 1.0), 1e30
            if sector <= 1:
                lo, hi = max(lo, -y1 if sector == 1 else y0), min(hi, -y0 if sector == 1 else y1)
                m0, m1 = x0 - 1.0, x1 + 1.0
            else:
                lo, hi = max(lo, -x1 if sector == 3 else x0), min(hi, -x0 if sector == 3 else x1)
                m0, m1 = y0 - 1.0, y1 + 1.0
            if t > 1e-12:
                lo, hi = max(lo, m0 / t), min(hi, m1 / t)
            elif t < -1e-12:
                lo, hi = max(lo, m1 / t), min(hi, m0 / t)
            elif m0 > 0.0 or m1 < 0.0:
                hi = -1.0
            d_from = math.ceil(lo - frac) + frac
            count = int(math.floor(hi - d_from)) + 1 if hi >= d_from else 0
            # The map direction the line shows: a ahead, b to the right, from its direction on the picture.
            sx, sy = _sector_point(sector, 1.0, t)
            norm = math.sqrt(sx * sx + sy * sy)
            gx, gy = sx / norm, sy / norm
            g = 1.0 / math.sqrt(gx * gx + sp * sp * gy * gy)
            a, b = g * sp * gy, g * gx
            lines[j, 0], lines[j, 1], lines[j, 2], lines[j, 3] = a * cp, sp, focal * g / norm, sigma
            lines[j, 4] = d_from if sigma > 0.0 else d_from + (count - 1)
            lines[j, 5], lines[j, 6], lines[j, 7] = a * dir_x - b * dir_y, a * dir_y + b * dir_x, count
            offsets[j + 1] = offsets[j] + count
    return fan, lines, offsets


@njit(cache=True, parallel=True)
def _draw_lines(colors, depths, lines, offsets, px, py, eye_z, eye_span,
                floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top, wall_tex, wall_sides, floor_tex,
                ceil_tex, textures, max_dist, fog_dist, bg):
    """Draw every line of the fan into its stretch of colors (samples, 3) and depths (samples,)."""
    n_lines = lines.shape[0]
    chunks = 64
    for chunk in prange(chunks):
        branches = np.empty((6, MAX_BRANCHES), np.int64)
        pane_f = np.empty((4, MAX_PANES), np.float64)
        pane_i = np.empty((4, MAX_PANES), np.int64)
        for j in range(chunk, n_lines, chunks):
            n = offsets[j + 1] - offsets[j]
            if n == 0:
                continue
            o = offsets[j]
            _render_line(colors[o:o + n], depths[o:o + n], n, px, py, eye_z, eye_span, lines[j, 5], lines[j, 6],
                         lines[j], floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top, wall_tex,
                         wall_sides, floor_tex, ceil_tex, textures, max_dist, fog_dist, bg, branches, pane_f, pane_i)


@njit(cache=True, parallel=True)
def _gather(fb, zb, vx, vy, fan, lines, offsets, colors, depths, bg):
    """Every pixel takes the sample on its own row (or column) of the nearest line of its sector."""
    width, height = fb.shape[0], fb.shape[1]
    for x in prange(width):
        ox = x + 0.5 - vx
        for y in range(height):
            oy = y + 0.5 - vy
            if abs(ox) <= abs(oy):
                sector = 0 if oy > 0.0 else 1
                d, minor = abs(oy), ox
            else:
                sector = 2 if ox > 0.0 else 3
                d, minor = abs(ox), oy
            d = max(d, 1e-9)
            levels = int(fan[sector, 4])
            level = 0
            if levels > 0:                                          # the level of the fan fine enough here
                _m, e = math.frexp(fan[sector, 5] / d)
                level = min(max(e - 1, 0), levels)
            k = int(math.floor((minor / d - fan[sector, 2]) / (fan[sector, 3] * (1 << level)) + 0.5)) << level
            k = min(max(k, 0), int(fan[sector, 1]) - 1)
            j = int(fan[sector, 0]) + k
            n = offsets[j + 1] - offsets[j]
            if n <= 0:
                fb[x, y, 0], fb[x, y, 1], fb[x, y, 2] = bg[0], bg[1], bg[2]
                zb[x, y] = 1e9
                continue
            i = offsets[j] + min(max(int(math.floor(lines[j, 3] * (d - lines[j, 4]) + 0.5)), 0), n - 1)
            fb[x, y, 0], fb[x, y, 1], fb[x, y, 2] = colors[i, 0], colors[i, 1], colors[i, 2]
            zb[x, y] = depths[i]


class TiltScratch:
    """The sample buffers render_scene_tilt draws the lines into, kept from frame to frame (they only grow)."""

    def __init__(self):
        self.colors = np.empty((0, 3), np.uint8)
        self.depths = np.empty(0, np.float32)

    def ensure(self, samples):
        if samples > len(self.depths):
            size = int(samples * 1.25)
            self.colors = np.empty((size, 3), np.uint8)
            self.depths = np.empty(size, np.float32)
        return self.colors, self.depths


def render_scene_tilt(fb, zb, px, py, eye_z, eye_span, dir_x, dir_y, pitch, focal,
                      floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top, wall_tex, wall_sides, floor_tex,
                      ceil_tex, textures, max_dist, fog_dist, bg, scratch=None):
    """Fill `fb` (W, H, 3) and `zb` (W, H) for a camera looking along (dir_x, dir_y) tilted up by `pitch`
    radians (negative looks down; not level), with `focal` the focal length in pixels: the same picture as
    raypitch.render_scene_pitch, to within half a pixel's placing. `scratch` (a TiltScratch) keeps the buffers
    between frames."""
    width, height = fb.shape[0], fb.shape[1]
    fan, lines, offsets = _plan(width, height, pitch, focal, dir_x, dir_y)
    colors, depths = (scratch or TiltScratch()).ensure(int(offsets[-1]))
    _draw_lines(colors, depths, lines, offsets, px, py, eye_z, eye_span, floor_plane, ceil_plane, span_on, solid_from,
                pane_tex, pane_top, wall_tex, wall_sides, floor_tex, ceil_tex, textures, max_dist, fog_dist, bg)
    _gather(fb, zb, width * 0.5, height * 0.5 - focal * math.cos(pitch) / math.sin(pitch), fan, lines, offsets,
            colors, depths, bg)
