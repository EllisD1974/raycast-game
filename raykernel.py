"""Raycasting core, compiled with numba. Pure numbers in, pixels out.

Every open cell has up to S vertical spans (open spaces, e.g. a lower and an upper floor).
For each screen column (in parallel) the ray walks cell by cell, carrying a small set of
*branches*: each branch is a span of the current cell plus the screen rows (window) still
visible through it. In every cell, for each branch:
  1. draw that span's floor and ceiling between where the ray enters and leaves the cell,
  2. compare the span's height range at the cell boundary with the spans of the next cell.
     Where ranges overlap the branch continues into that next span with a narrower window;
     where they don't, draw wall: a riser below a higher floor, the slab between two
     spans, the drop below a lower ceiling, or a full wall for a solid cell.
Spans of one cell never overlap in height, so the branches of a column occupy separate screen
rows and never fight over pixels. A column ends when it has no branches left or the ray is
too long. Floors/ceilings are planes (flat or sloped); 1/distance is linear in screen y
across a plane, which gives perspective-correct texturing without per-pixel ray casting.

Transparent walls (fences, windows, glass) are cells the ray passes straight through. Each face the
ray passes is remembered, and after the column is drawn the faces are blended over it, farthest
first, using the texture's alpha channel. Floor and ceiling textures ignore alpha.

Span 0 of a cell is always below span 1. Array shapes: planes (S, H, W, 3), span_on and the
texture grids (S, H, W), solid_from (the lowest floor each cell is a wall on, or S for none) and
wall_tex (H, W).
"""
import math

import numpy as np
from numba import njit, prange

MIN_SHADE = 0.2
SIDE_SHADE = 0.7        # walls facing along y are darker than those facing along x
EPS = 1e-6
MAX_PANES = 24          # see-through wall faces remembered per screen column (the nearest ones)


@njit(cache=True)
def plane_z(planes, s, cx, cy, fx, fy):
    """Height of span s's plane in cell (cx, cy) at local coordinates fx, fy in [0, 1]."""
    return planes[s, cy, cx, 0] + planes[s, cy, cx, 1] * fx + planes[s, cy, cx, 2] * fy


@njit(cache=True)
def _proj(z, t, eye_z, horizon, focal):
    """Screen row (float) of world height z at perpendicular distance t."""
    return horizon + (eye_z - z) / t * focal


@njit(cache=True)
def _clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


@njit(cache=True)
def _shade(t, fog):
    s = 1.0 - t / fog
    return MIN_SHADE if s < MIN_SHADE else s


@njit(cache=True)
def _put(fb, x, r, textures, tex, tx, ty, shade):
    fb[x, r, 0] = np.uint8(textures[tex, ty, tx, 0] * shade)
    fb[x, r, 1] = np.uint8(textures[tex, ty, tx, 1] * shade)
    fb[x, r, 2] = np.uint8(textures[tex, ty, tx, 2] * shade)


@njit(cache=True)
def _wall(fb, zb, x, z_low, z_high, ytop, ybot, t, tx, tex, shade, eye_z, horizon, focal, textures):
    """Draw a vertical wall strip between two world heights, clipped to the window."""
    if z_high <= z_low:
        return
    tsize = textures.shape[1]
    r0 = max(int(math.ceil(_proj(z_high, t, eye_z, horizon, focal))), ytop)
    r1 = min(int(math.ceil(_proj(z_low, t, eye_z, horizon, focal))), ybot)
    for r in range(r0, r1):
        z = eye_z + (horizon - (r + 0.5)) * t / focal     # world height of this row
        ty = int(math.floor(-z * tsize)) & (tsize - 1)    # world-aligned, one repeat per unit
        _put(fb, x, r, textures, tex, tx, ty, shade)
        zb[x, r] = t


@njit(cache=True)
def _surface(fb, zb, x, r0, r1, y_near, y_far, t0, t1, px, py, rdx, rdy, tex, textures, fog_dist):
    """Texture rows r0..r1 of a floor or ceiling that spans screen rows y_near..y_far."""
    tsize = textures.shape[1]
    tmask = tsize - 1
    inv0 = 1.0 / t0
    inv1 = 1.0 / t1
    span = y_far - y_near
    for r in range(r0, r1):
        u = (r + 0.5 - y_near) / span
        t = 1.0 / max(inv0 + (inv1 - inv0) * u, 1e-9)
        wx = px + rdx * t
        wy = py + rdy * t
        tx = int((wx - math.floor(wx)) * tsize) & tmask
        ty = int((wy - math.floor(wy)) * tsize) & tmask
        _put(fb, x, r, textures, tex, tx, ty, _shade(t, fog_dist))
        zb[x, r] = t


@njit(cache=True)
def _composite_panes(fb, x, n, pane_t, pane_tx, pane_id, pane_zlo, pane_zhi, pane_shade,
                     pane_ytop, pane_ybot, textures, eye_z, horizon, focal):
    """Blend the see-through wall faces recorded for a column over what is already drawn.

    The ray walked past each pane (it could see through it), so by now the column holds
    everything behind the panes. They are laid on top from the farthest to the nearest, each
    only in the rows that were still visible when the ray reached it, so a pane never shows
    through a nearer opaque wall. Alpha 0 leaves the picture alone, 255 replaces it, and
    anything between mixes the texture with what is behind it (glass)."""
    tsize = textures.shape[1]
    for p in range(n - 1, -1, -1):
        t = pane_t[p]
        r0 = max(int(math.ceil(_proj(pane_zhi[p], t, eye_z, horizon, focal))), pane_ytop[p])
        r1 = min(int(math.ceil(_proj(pane_zlo[p], t, eye_z, horizon, focal))), pane_ybot[p])
        tex = pane_id[p]
        shade = pane_shade[p]
        for r in range(r0, r1):
            z = eye_z + (horizon - (r + 0.5)) * t / focal      # world height of this row
            ty = int(math.floor(-z * tsize)) & (tsize - 1)
            alpha = textures[tex, ty, pane_tx[p], 3]
            if alpha == 0:
                continue
            if alpha == 255:
                for c in range(3):
                    fb[x, r, c] = np.uint8(textures[tex, ty, pane_tx[p], c] * shade)
            else:
                a = alpha / 255.0
                for c in range(3):
                    fb[x, r, c] = np.uint8(textures[tex, ty, pane_tx[p], c] * shade * a
                                           + fb[x, r, c] * (1.0 - a))


@njit(cache=True)
def _render_column(fb, zb, x, px, py, eye_z, eye_span, rdx, rdy, horizon, focal,
                   floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top, wall_tex, floor_tex, ceil_tex,
                   textures, max_dist, fog_dist, bg):
    height = fb.shape[1]
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

    # Branches active in the current cell (span index and visible window), and for the next cell.
    cur_s = np.empty(nspans, np.int64)
    cur_top = np.empty(nspans, np.int64)
    cur_bot = np.empty(nspans, np.int64)
    nxt_s = np.empty(nspans, np.int64)
    nxt_top = np.empty(nspans, np.int64)
    nxt_bot = np.empty(nspans, np.int64)
    # See-through wall faces met by this ray, nearest first (see _composite_panes).
    pane_t = np.empty(MAX_PANES, np.float64)
    pane_tx = np.empty(MAX_PANES, np.int64)
    pane_id = np.empty(MAX_PANES, np.int64)
    pane_zlo = np.empty(MAX_PANES, np.float64)
    pane_zhi = np.empty(MAX_PANES, np.float64)
    pane_shade = np.empty(MAX_PANES, np.float64)
    pane_ytop = np.empty(MAX_PANES, np.int64)
    pane_ybot = np.empty(MAX_PANES, np.int64)
    n_panes = 0
    n_cur = 0
    if span_on[eye_span, cy, cx] != 0:
        cur_s[0], cur_top[0], cur_bot[0] = eye_span, 0, height
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
            # The viewer is exactly on a grid line and the ray leaves their cell straight away
            # (distance 0). Keep every cell's exit a hair past its entry, so nothing divides by 0.
            t1 = t0 + 1e-6

        # Where the ray crosses the cell, in local coordinates (same for every branch).
        e0x = _clamp01(px + rdx * t0 - cx)
        e0y = _clamp01(py + rdy * t0 - cy)
        e1x = _clamp01(px + rdx * t1 - cx)
        e1y = _clamp01(py + rdy * t1 - cy)
        nfx = _clamp01(px + rdx * t1 - nx)
        nfy = _clamp01(py + rdy * t1 - ny)

        # The wall face at the boundary: texture column and shading.
        if side == 0:
            wallx = py + rdy * t1
        else:
            wallx = px + rdx * t1
        wallx -= math.floor(wallx)
        if (side == 0 and rdx > 0.0) or (side == 1 and rdy < 0.0):
            wallx = 1.0 - wallx                         # keep texture orientation consistent
        wtx = int(wallx * tsize) & tmask
        shade = _shade(t1, fog_dist) * (1.0 if side == 0 else SIDE_SHADE)

        inside = 0 <= nx < mw and 0 <= ny < mh
        n_next = 0

        for b in range(n_cur):
            s = cur_s[b]
            ytop = cur_top[b]
            ybot = cur_bot[b]
            # A wall fills the cell on its own floor and the ones above it, not the floors below.
            next_solid = (not inside) or s >= solid_from[ny, nx]

            zf0 = plane_z(floor_plane, s, cx, cy, e0x, e0y)
            zf1 = plane_z(floor_plane, s, cx, cy, e1x, e1y)
            zc0 = plane_z(ceil_plane, s, cx, cy, e0x, e0y)
            zc1 = plane_z(ceil_plane, s, cx, cy, e1x, e1y)
            yf0 = _proj(zf0, t0, eye_z, horizon, focal)
            yf1 = _proj(zf1, t1, eye_z, horizon, focal)
            yc0 = _proj(zc0, t0, eye_z, horizon, focal)
            yc1 = _proj(zc1, t1, eye_z, horizon, focal)

            # floor: rows between the far edge (yf1) and the near edge (yf0)
            r0 = max(int(math.ceil(yf1)), ytop)
            r1 = min(int(math.ceil(yf0)), ybot)
            if r1 > r0:
                _surface(fb, zb, x, r0, r1, yf0, yf1, t0, t1, px, py, rdx, rdy,
                         floor_tex[s, cy, cx], textures, fog_dist)
            # ceiling: rows between the near edge (yc0) and the far edge (yc1)
            r0 = max(int(math.ceil(yc0)), ytop)
            r1 = min(int(math.ceil(yc1)), ybot)
            if r1 > r0:
                _surface(fb, zb, x, r0, r1, yc0, yc1, t0, t1, px, py, rdx, rdy,
                         ceil_tex[s, cy, cx], textures, fog_dist)

            # Boundary: this span covers heights zf1..zc1 at distance t1.
            if next_solid:
                wtex = wall_tex[ny, nx] if inside else 0
                _wall(fb, zb, x, zf1, zc1, ytop, ybot, t1, wtx, wtex, shade,
                      eye_z, horizon, focal, textures)
                continue

            cur = zf1                    # everything below `cur` is already accounted for
            tex_above = 0
            for k in range(nspans):      # spans of the next cell, lowest first
                if span_on[k, ny, nx] == 0:
                    continue
                zfn = plane_z(floor_plane, k, nx, ny, nfx, nfy)
                zcn = plane_z(ceil_plane, k, nx, ny, nfx, nfy)
                tex_above = ceil_tex[k, ny, nx]
                if zcn <= cur:
                    continue             # this span lies entirely below what is left
                if zfn > cur:            # solid below it: riser or slab side, up to its floor
                    top = min(zfn, zc1)
                    _wall(fb, zb, x, cur, top, ytop, ybot, t1, wtx, floor_tex[k, ny, nx], shade,
                          eye_z, horizon, focal, textures)
                    cur = top
                    if cur >= zc1:
                        break
                hi = min(zcn, zc1)
                if hi - cur > EPS:       # overlap: the ray continues into span k
                    if k == 0 and pane_tex[ny, nx] >= 0 and n_panes < MAX_PANES:
                        # The next cell is a see-through wall: remember its face, over the heights
                        # the ray can reach up to the wall's top (a short wall can be seen over),
                        # and keep going. It is blended in at the end.
                        face_top = min(hi, pane_top[ny, nx])
                        if face_top - cur > EPS:
                            pane_t[n_panes], pane_tx[n_panes] = t1, wtx
                            pane_id[n_panes], pane_shade[n_panes] = pane_tex[ny, nx], shade
                            pane_zlo[n_panes], pane_zhi[n_panes] = cur, face_top
                            pane_ytop[n_panes], pane_ybot[n_panes] = ytop, ybot
                            n_panes += 1
                    ntop = max(ytop, int(math.ceil(_proj(hi, t1, eye_z, horizon, focal))))
                    nbot = min(ybot, int(math.ceil(_proj(cur, t1, eye_z, horizon, focal))))
                    if ntop < nbot:
                        nxt_s[n_next], nxt_top[n_next], nxt_bot[n_next] = k, ntop, nbot
                        n_next += 1
                    cur = hi
                if cur >= zc1:
                    break
            if cur < zc1:                # solid above the last span: the drop under a ceiling
                if inside and solid_from[ny, nx] < nspans:      # a wall above this floor: its side shows
                    tex_above = wall_tex[ny, nx]
                _wall(fb, zb, x, cur, zc1, ytop, ybot, t1, wtx, tex_above, shade,
                      eye_z, horizon, focal, textures)

        for b in range(n_next):
            cur_s[b], cur_top[b], cur_bot[b] = nxt_s[b], nxt_top[b], nxt_bot[b]
        n_cur = n_next
        cx, cy = nx, ny
        t0 = t1

    for b in range(n_cur):               # rays that left the view distance with rows still open
        for r in range(cur_top[b], cur_bot[b]):
            for c in range(3):
                fb[x, r, c] = bg[c]

    _composite_panes(fb, x, n_panes, pane_t, pane_tx, pane_id, pane_zlo, pane_zhi, pane_shade,
                     pane_ytop, pane_ybot, textures, eye_z, horizon, focal)


@njit(cache=True, parallel=True)
def render_scene_depth(fb, zb, px, py, eye_z, eye_span, dir_x, dir_y, plane_x, plane_y, horizon, focal,
                       floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top, wall_tex, floor_tex,
                       ceil_tex, textures, max_dist, fog_dist, bg):
    """Fill `fb` (shape (W, H, 3) uint8) with the view from the given camera, and `zb` (W, H) with the
    perpendicular distance of what was drawn in each pixel (for sprites to hide behind it).

    `textures` is uint8 [tile, y, x, rgba]. pane_tex (H, W) is the tile index of a see-through
    wall in a cell, or -1 for every other cell."""
    width = fb.shape[0]
    for x in prange(width):
        zb[x, :] = 1e9
        camera_x = 2.0 * (x + 0.5) / width - 1.0
        _render_column(fb, zb, x, px, py, eye_z, eye_span,
                       dir_x + plane_x * camera_x, dir_y + plane_y * camera_x,
                       horizon, focal, floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top,
                       wall_tex, floor_tex, ceil_tex, textures, max_dist, fog_dist, bg)


@njit(cache=True)
def render_scene(fb, px, py, eye_z, eye_span, dir_x, dir_y, plane_x, plane_y, horizon, focal,
                 floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top, wall_tex, floor_tex, ceil_tex,
                 textures, max_dist, fog_dist, bg):
    """render_scene_depth without the depth picture, for callers that only want the walls."""
    zb = np.empty((fb.shape[0], fb.shape[1]), np.float32)
    render_scene_depth(fb, zb, px, py, eye_z, eye_span, dir_x, dir_y, plane_x, plane_y, horizon, focal,
                       floor_plane, ceil_plane, span_on, solid_from, pane_tex, pane_top, wall_tex, floor_tex,
                       ceil_tex, textures, max_dist, fog_dist, bg)


@njit(cache=True, parallel=True)
def draw_sprites(fb, zb, px, py, eye_z, dir_x, dir_y, plane_x, plane_y, horizon, focal,
                 sp_x, sp_y, sp_z, sp_size, sp_tex, textures, max_dist, fog_dist):
    """Draw flat sprites that always face the camera, over a picture already drawn by
    render_scene_depth. The sprites must be sorted farthest first. sp_z is the height of a sprite's
    bottom, sp_size its height and width in world units. A sprite pixel shows only where it is
    nearer than what is already there (zb), so walls, ledges and floors hide it; texture alpha
    blends it (0 is see-through, 255 opaque)."""
    width, height = fb.shape[0], fb.shape[1]
    tsize = textures.shape[1]
    det = dir_x * plane_y - dir_y * plane_x
    n = sp_x.shape[0]
    for x in prange(width):
        for i in range(n):
            dx, dy = sp_x[i] - px, sp_y[i] - py
            depth = (dx * plane_y - dy * plane_x) / det
            if depth < 0.05 or depth > max_dist:
                continue
            centre = ((dir_x * dy - dir_y * dx) / det / depth + 1.0) * 0.5 * width
            half = sp_size[i] * focal / depth * 0.5
            if x + 0.5 < centre - half or x + 0.5 >= centre + half:
                continue
            tx = min(tsize - 1, int((x + 0.5 - (centre - half)) / (2.0 * half) * tsize))
            ytop = _proj(sp_z[i] + sp_size[i], depth, eye_z, horizon, focal)
            ybot = _proj(sp_z[i], depth, eye_z, horizon, focal)
            if ybot <= ytop:
                continue
            shade = _shade(depth, fog_dist)
            for r in range(max(0, int(math.ceil(ytop))), min(height, int(math.ceil(ybot)))):
                if depth >= zb[x, r]:
                    continue
                ty = min(tsize - 1, int((r + 0.5 - ytop) / (ybot - ytop) * tsize))
                alpha = textures[sp_tex[i], ty, tx, 3]
                if alpha == 0:
                    continue
                a = alpha / 255.0
                for c in range(3):
                    fb[x, r, c] = np.uint8(textures[sp_tex[i], ty, tx, c] * shade * a + fb[x, r, c] * (1.0 - a))
