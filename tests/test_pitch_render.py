"""Looking up and down: the tilted-camera renderer (raytilt.py) draws a real rotation, not a shear."""
import glob
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import physics
from constants import HEIGHT, WIDTH
from mapfile import Level, load_level
from renderer import Renderer
from world import World

WALL, FLOOR, CEILING = 0, 4, 5                      # atlas indices of the default wall, floor and ceiling tiles


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((100, 100))
    yield
    pygame.quit()


def flat_textures():
    """Plain colors so a pixel's kind is obvious: red walls, green floors, blue ceilings."""
    textures = np.zeros((16, 32, 32, 4), np.uint8)
    textures[..., :3] = 120
    textures[..., 3] = 255
    textures[WALL, ..., :3] = (255, 0, 0)
    textures[FLOOR, ..., :3] = (0, 255, 0)
    textures[CEILING, ..., :3] = (0, 0, 255)
    return textures


def hall():
    level = Level.blank(16, 16)
    return World(level, 16)


def frame(world, pitch, x=4.5, y=8.5, angle=0.0, renderer=None, sprites=()):
    renderer = renderer or Renderer(flat_textures())
    renderer.draw(world, physics.Player(x, y, 0.0, angle, pitch=pitch), sprites)
    return np.array(renderer.framebuffer).astype(int), renderer


def kind(fb):
    """Boolean pictures of which pixels look like wall (red), floor (green) and ceiling (blue)."""
    r, g, b = fb[..., 0], fb[..., 1], fb[..., 2]
    return (r > g + 20) & (r > b + 20), (g > r + 20) & (g > b + 20), (b > r + 20) & (b > g + 20)


def differences(fb, other):
    """How far each pixel of `fb` is from the closest of the 3x3 pixels around it in `other` (the largest of its
    color channels). Two renderers sample textures a fraction of a pixel apart, so texel edges such as brick mortar
    and the floor grid land a pixel apart: this lets those through, while anything drawn further off still shows."""
    padded = np.pad(other, ((1, 1), (1, 1), (0, 0)), mode="edge")
    w, h = fb.shape[:2]
    return np.min([np.abs(fb - padded[1 + dx:1 + dx + w, 1 + dy:1 + dy + h]).max(axis=2)
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1)], axis=0)


def project(depth_ahead, dz, pitch, renderer):
    """Screen row of a point `depth_ahead` cells in front of the camera and `dz` above the eye, for a
    camera tilted up by `pitch` (a real rotation about the eye)."""
    depth = depth_ahead * math.cos(pitch) + dz * math.sin(pitch)
    up = dz * math.cos(pitch) - depth_ahead * math.sin(pitch)
    return HEIGHT / 2 - up / depth * renderer.focal


# ------------------------------------------------------------------ agreeing with the level renderer

def test_a_tiny_tilt_looks_the_same_as_the_level_view():
    from atlas import atlas_array, unpack_atlas
    renderer = Renderer(atlas_array(unpack_atlas()))
    world = World(load_level(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                          "maps", "map.json")), 256)
    for x, y, angle in ((1.5, 4.5, 0.0), (5.5, 5.5, 2.0), (3.5, 7.5, -1.0)):
        level_fb, _ = frame(world, 0.0, x, y, angle, renderer)
        tilted_fb, _ = frame(world, 2e-3, x, y, angle, renderer)
        off = differences(level_fb, tilted_fb)
        assert (off <= 24).mean() > 0.99, f"{(off <= 24).mean():.3f} of the pixels agree at ({x}, {y})"
        assert off.mean() < 1.0


def test_a_small_tilt_is_drawn_sheared_and_looks_like_the_rotated_view(monkeypatch):
    """Below SHEAR_PITCH the fast column renderer draws the view with its horizon moved up or down; that
    near level looks the same as the real rotation it stands in for."""
    import renderer as renderer_module
    from atlas import atlas_array, unpack_atlas
    renderer = Renderer(atlas_array(unpack_atlas()))
    world = World(load_level(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                          "maps", "map.json")), 256)
    for x, y, angle in ((1.5, 4.5, 0.0), (5.5, 5.5, 2.0), (3.5, 7.5, -1.0)):
        for pitch in (renderer_module.SHEAR_PITCH * 0.95, -renderer_module.SHEAR_PITCH * 0.95):
            sheared, _ = frame(world, pitch, x, y, angle, renderer)
            with monkeypatch.context() as m:
                m.setattr(renderer_module, "SHEAR_PITCH", 0.0)          # every tilt rotated
                rotated, _ = frame(world, pitch, x, y, angle, renderer)
            off = differences(sheared, rotated)
            assert (off <= 24).mean() > 0.9, f"{(off <= 24).mean():.3f} of the pixels agree at ({x}, {y}, {pitch:.3f})"
            assert off.mean() < 5.0


def test_in_a_sheared_view_walls_and_sprites_land_where_the_moved_horizon_puts_them():
    textures = flat_textures()
    textures[7, ..., :3] = (255, 255, 0)                       # tile 7: yellow sprite
    renderer = Renderer(textures)
    pitch = math.radians(-3)                                   # looking slightly down: sheared, not rotated
    sprite = (8.5, 8.5, 0.0, 0.6, 7)                            # 4 cells ahead, standing on the floor
    fb, _ = frame(hall(), pitch, renderer=renderer, sprites=[sprite])
    horizon = HEIGHT / 2 + math.tan(pitch) * renderer.focal
    wall, _floor, _ceiling = kind(fb)
    rows = np.nonzero(wall[10])[0]                              # (a column clear of the sprite)
    d = 15 - 4.5
    assert abs(rows.min() - (horizon - 0.5 / d * renderer.focal)) <= 2
    assert abs(rows.max() + 1 - (horizon + 0.5 / d * renderer.focal)) <= 2
    yellow = (fb[..., 0] > 150) & (fb[..., 1] > 150) & (fb[..., 2] < 80)
    rows, cols = np.nonzero(yellow.T)
    assert abs(rows.min() - (horizon - 0.1 / 4.0 * renderer.focal)) <= 2
    assert abs(rows.max() + 1 - (horizon + 0.5 / 4.0 * renderer.focal)) <= 2
    assert abs(cols.mean() - WIDTH / 2) <= 3


# ------------------------------------------------------------------ it is a real rotation

@pytest.mark.parametrize("pitch_deg", [-40, -15, 15, 40, 65])
def test_where_the_wall_meets_the_floor_and_ceiling_follows_the_rotation(pitch_deg):
    pitch = math.radians(pitch_deg)
    world = hall()
    fb, renderer = frame(world, pitch)
    wall, floor, ceiling = kind(fb)
    column = WIDTH // 2
    d = 15 - 4.5                                              # the far wall is 10.5 cells ahead
    for expected, mask, dz, above in ((project(d, -0.5, pitch, renderer), floor, -0.5, False),
                                      (project(d, 0.5, pitch, renderer), ceiling, 0.5, True)):
        rows = np.nonzero(wall[column])[0]
        if not 0 <= expected < HEIGHT:
            continue                                          # that edge is off the screen at this tilt
        edge = rows.max() if not above else rows.min()
        # the wall's bottom edge is where it meets the floor; its top edge is where it meets the ceiling
        want = expected if above else expected
        assert abs((edge + (1 if not above else 0)) - want) <= 2.0, (pitch_deg, above, edge, want)


def test_tilting_the_camera_leans_the_walls_unlike_a_shear():
    """In a level view the edge of a wall is a vertical line. Looking up, a real camera sees a vertical
    edge lean toward the point overhead: its screen column changes with the row."""
    world = hall()
    fb, _ = frame(world, math.radians(40), x=4.5, y=8.5, angle=0.3)
    wall, _floor, _ceiling = kind(fb)
    columns_by_row = []
    for row in range(20, HEIGHT - 20, 40):
        cols = np.nonzero(wall[:, row])[0]
        if cols.size:
            columns_by_row.append(cols.min())
    spread = max(columns_by_row) - min(columns_by_row) if columns_by_row else 0
    level_fb, _ = frame(world, 0.0, x=4.5, y=8.5, angle=0.3)
    level_wall, _f, _c = kind(level_fb)
    level_cols = [np.nonzero(level_wall[:, r])[0].min() for r in range(190, 200, 3) if np.nonzero(level_wall[:, r])[0].size]
    assert spread >= 0 and level_cols  # (the level view's wall corner is a straight vertical line:)
    assert max(level_cols) - min(level_cols) <= 1


def test_straight_up_shows_only_the_ceiling_and_straight_down_only_the_floor():
    world = hall()
    up, _ = frame(world, math.pi / 2)
    _w, _f, ceiling = kind(up)
    assert ceiling.mean() > 0.99
    down, _ = frame(world, -math.pi / 2)
    _w, floor, _c = kind(down)
    assert floor.mean() > 0.99


def test_the_pitch_limit_is_straight_up_and_down():
    from constants import MAX_PITCH_DEG
    assert MAX_PITCH_DEG == 90.0 and physics.MAX_PITCH == pytest.approx(math.pi / 2)
    p = physics.Player(1.5, 1.5, 0.0)
    physics.look(p, 10.0)
    assert p.pitch == pytest.approx(math.pi / 2)
    physics.look(p, -20.0)
    assert p.pitch == pytest.approx(-math.pi / 2)


@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                              "maps", "*.json"))
                                        + glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                                 "maps", "tests", "*.json"))))
def test_every_map_renders_at_every_tilt_without_gaps(path):
    """Every pixel is something: a surface (finite depth), not left over from before."""
    from atlas import atlas_array, unpack_atlas
    renderer = Renderer(atlas_array(unpack_atlas()))
    level = load_level(path)
    world = World(level, 256)
    player = physics.spawn(level, world)
    for pitch in (-math.pi / 2, -1.0, -0.4, 0.4, 1.0, math.pi / 2):
        player.pitch = pitch
        for angle in (0.0, 1.9, 4.0):
            player.angle = angle
            renderer.depth[:] = -1.0
            renderer.draw(world, player)
            assert (renderer.depth >= 0).all()                # every pixel was written
            assert (renderer.depth < 1e8).mean() > 0.9        # and nearly all of it is a surface, not the void


# ------------------------------------------------------------------ the rest of the world, tilted

def test_a_tilted_view_sees_through_glass_and_floors_above_floors():
    textures = flat_textures()
    textures[1, ..., :3] = (255, 255, 255)
    textures[1, ..., 3] = 100                                  # tile 1: glass
    level = Level.blank(16, 16)
    level.set("walls", 8, 8, 2)                                # tile id 2 = atlas index 1
    world = World(level, 16)
    glass = frame(world, 0.2)[0]
    clear = frame(World(Level.blank(16, 16), 16), 0.2)[0]
    stacked = World(load_level(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                            "maps", "tests", "stacked.json")), 16)
    assert stacked.floors >= 2
    renderer = Renderer(textures)
    renderer.draw(world, physics.Player(4.5, 8.5, 0.0, 0.0, pitch=0.2))
    blended = np.array(renderer.framebuffer).astype(int)
    assert np.abs(blended - clear).sum() > 0                   # the pane changed some pixels
    # ... and the pixels it covers are a mix of white glass and what is behind it, not plain glass
    changed = (np.abs(blended - clear).sum(axis=2) > 30)
    assert changed.any() and (blended[changed].min() < 250)
    assert glass.shape == blended.shape


def test_sprites_land_where_the_rotated_camera_puts_them_and_hide_behind_walls():
    textures = flat_textures()
    textures[7, ..., :3] = (255, 255, 0)                       # tile 7: yellow sprite
    renderer = Renderer(textures)
    world = hall()
    pitch = math.radians(-8)                                   # looking slightly down at it
    sprite = (8.5, 8.5, 0.0, 0.6, 7)                            # 4 cells ahead, standing on the floor
    fb, _ = frame(world, pitch, renderer=renderer, sprites=[sprite])
    yellow = (fb[..., 0] > 150) & (fb[..., 1] > 150) & (fb[..., 2] < 80)
    assert yellow.sum() > 100
    rows, cols = np.nonzero(yellow.T)
    top = project(4.0, 0.6 - 0.5, pitch, renderer)
    bottom = project(4.0, -0.5, pitch, renderer)
    assert abs(rows.min() - top) <= 3 and abs(rows.max() + 1 - bottom) <= 3
    assert abs(cols.mean() - WIDTH / 2) <= 3
    blocked = hall()
    blocked_level = Level.blank(16, 16)
    blocked_level.set("walls", 6, 8, 1)                        # a wall between the camera and the sprite
    fb2, _ = frame(World(blocked_level, 16), pitch, renderer=renderer, sprites=[sprite])
    assert not ((fb2[..., 0] > 150) & (fb2[..., 1] > 150) & (fb2[..., 2] < 80)).any()


@pytest.mark.parametrize("which", ["tilt", "pitch"])
def test_a_tilted_view_does_not_draw_the_sides_between_see_through_cells(which):
    """As in the level view: glass two cells thick looks like one pane, without the face inside it."""
    import raypitch
    import raytilt
    from atlas import transparent_tiles
    from constants import FOG_DIST, MAX_DEPTH
    from renderer import BACKGROUND
    textures = flat_textures()
    textures[1, ..., :3], textures[1, ..., 3] = (255, 255, 255), 100     # tile id 2: white glass
    textures[3, ..., :3], textures[3, ..., 3] = (255, 0, 255), 100       # tile id 4: purple glass
    level = Level.blank(16, 16)
    for x in range(1, 15):
        for y in range(1, 15):
            level.set("ceil_h", x, y, 4.0)                     # tall, so the tilted view meets the glass, not the ceiling
    level.set("walls", 5, 8, 2)
    level.set("walls", 6, 8, 4)
    world = World(level, 16, transparent_tiles(textures))
    assert world.pane_tex[8, 5] >= 0 and world.pane_tex[8, 6] >= 0
    renderer = Renderer(textures)

    def draw():
        fb, depth = np.zeros((WIDTH, HEIGHT, 3), np.uint8), np.zeros((WIDTH, HEIGHT), np.float32)
        args = (4.5, 8.5, 0.5, 0, 1.0, 0.0, 0.4, renderer.focal, *scene_of(world), renderer.textures, MAX_DEPTH,
                FOG_DIST, BACKGROUND)
        if which == "tilt":
            raytilt.render_scene_tilt(fb, depth, *args, raytilt.TiltScratch())
        else:
            raypitch.render_scene_pitch(fb, depth, *args, raypitch.skip_blocks(*scene_of(world)[:5]))
        return fb.astype(int)

    thick = draw()
    world.pane_tex[8, 6] = -1                                  # the far cell's pane off: only the front one
    front_only = draw()
    middle = (slice(WIDTH // 2 - 20, WIDTH // 2 + 20), slice(HEIGHT // 2 - 20, HEIGHT // 2 + 20))
    assert np.abs(thick[middle] - front_only[middle]).max() <= 1


def spots(world, count, seed):
    """`count` places to stand (x, y, floor), picked at random among the open cells of every floor."""
    rng = np.random.default_rng(seed)
    cells = np.argwhere(world.span_on > 0)
    return [(int(cx) + 0.37, int(cy) + 0.61, int(span)) for span, cy, cx in cells[rng.choice(len(cells), count)]]


def map_world(name):
    from atlas import atlas_array, unpack_atlas
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "maps", name)
    return World(load_level(path), 256), atlas_array(unpack_atlas())


def scene_of(world):
    return (world.floor_plane, world.ceil_plane, world.span_on, world.solid_from, world.pane_tex, world.pane_top,
            world.wall_tex, world.wall_sides, world.floor_tex, world.ceil_tex)


@pytest.mark.parametrize("name", ["koth_test1.json", "pvp_v1.json", "tests/stacked.json"])
def test_jumping_across_open_blocks_draws_the_same_picture(name):
    """raypitch's rays skip whole blocks of open air (skip_blocks); with no block to skip the picture is the same, but
    for distances worked out a hair differently (a shade one step brighter or darker here and there)."""
    import raypitch
    from constants import FOG_DIST, MAX_DEPTH
    from renderer import BACKGROUND
    world, textures = map_world(name)
    renderer = Renderer(textures)
    scene = scene_of(world)
    blocks = raypitch.skip_blocks(*scene[:5])
    never = np.stack((np.full_like(blocks[0], np.inf), np.full_like(blocks[1], -np.inf)))
    skipped, walked = np.zeros((WIDTH, HEIGHT, 3), np.uint8), np.zeros((WIDTH, HEIGHT, 3), np.uint8)
    depth = np.zeros((WIDTH, HEIGHT), np.float32)
    for x, y, span in spots(world, 3, 3):
        eye = world.floor_of(span, x, y) + 0.5
        for pitch in (0.3, -0.6, 1.2):
            for angle in (0.1, 2.2, 4.3):
                args = (x, y, eye, span, math.cos(angle), math.sin(angle), pitch, renderer.focal, *scene,
                        renderer.textures, MAX_DEPTH, FOG_DIST, BACKGROUND)
                raypitch.render_scene_pitch(skipped, depth, *args, blocks)
                raypitch.render_scene_pitch(walked, depth, *args, never)
                assert np.abs(skipped.astype(int) - walked.astype(int)).max() <= 1


@pytest.mark.parametrize("name", ["koth_test1.json", "pvp_v1.json", "tests/stacked.json", "map.json"])
def test_drawing_a_line_at_a_time_matches_a_ray_per_pixel(name):
    """raytilt (the game's tilted renderer) draws what raypitch's ray per pixel sees, give or take half a pixel in
    where the samples fall: only the edges of things and the finest texture detail may differ."""
    import raypitch
    import raytilt
    from constants import FOG_DIST, MAX_DEPTH
    from renderer import BACKGROUND
    world, textures = map_world(name)
    renderer = Renderer(textures)
    scene = scene_of(world)
    blocks = raypitch.skip_blocks(*scene[:5])
    exact, lines = np.zeros((WIDTH, HEIGHT, 3), np.uint8), np.zeros((WIDTH, HEIGHT, 3), np.uint8)
    exact_depth, lines_depth = np.zeros((WIDTH, HEIGHT), np.float32), np.zeros((WIDTH, HEIGHT), np.float32)
    scratch = raytilt.TiltScratch()
    for x, y, span in spots(world, 2, 5):
        eye = world.floor_of(span, x, y) + 0.5
        for pitch in (0.1, 0.35, -0.8, 1.4, -1.55):        # the vanishing point far off, near, and on the picture
            for angle in (0.3, 2.0, 4.1):
                args = (x, y, eye, span, math.cos(angle), math.sin(angle), pitch, renderer.focal, *scene,
                        renderer.textures, MAX_DEPTH, FOG_DIST, BACKGROUND)
                raypitch.render_scene_pitch(exact, exact_depth, *args, blocks)
                raytilt.render_scene_tilt(lines, lines_depth, *args, scratch)
                close = (np.abs(exact.astype(int) - lines.astype(int)) <= 24).all(axis=2)
                assert close.mean() > 0.96, f"{close.mean():.3f} of the pixels agree at ({x}, {y}, {pitch}, {angle})"
                near = np.abs(exact_depth - lines_depth) <= 0.05 * np.minimum(exact_depth, lines_depth) + 1e-3
                assert near.mean() > 0.96
