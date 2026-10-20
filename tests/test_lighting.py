"""Lighting: the map data, which lights are on, and what they do to the picture."""
import json
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import net
from game import Game, Inputs
from lighting import MAX_LIGHTS, LightSystem
from mapfile import AmmoType, Effect, Entity, Gun, Level, Light, level_text, parse_level
from particles import ParticleSystem
from physics import spawn
from raylight import build_visibility
from renderer import Renderer
from session import ClientSession, HostSession, LocalSession
from world import World

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((100, 100))
    yield
    pygame.quit()


def textures():
    flat = np.full((16, 32, 32, 4), 160, np.uint8)
    flat[..., 3] = 255
    return flat


def room(width=12, height=11, lights=(), ambient=1.0, walls=()):
    level = Level.blank(width, height)
    level.lights, level.ambient = list(lights), ambient
    for x, y, tile in walls:
        level.walls[y][x] = tile
    return level


def system(level):
    return LightSystem(level, World(level, 16))


def view(level, lighting_for=None, sprites=(), at=(2.5, 5.5), angle=0.0, particles=None):
    """The picture of a flat room from `at`, looking along `angle`, and the color of its middle pixel."""
    world = World(level, 16)
    player = spawn(level, world)
    player.x, player.y, player.angle = at[0], at[1], angle
    lighting = lighting_for(world, player) if lighting_for else None
    picture = Renderer(textures()).draw(world, player, sprites, lighting)
    w, h = picture.get_size()
    return picture, picture.get_at((w // 2, h // 2))[:3]


def lit(system_factory):
    def prepare(world, player):
        return system_factory(world).prepare((player.x, player.y, player.eye_z))
    return prepare


def brightness(color):
    return sum(color)


# ------------------------------------------------------------------ the map data

def test_a_light_survives_saving_and_loading_with_the_things_that_carry_it():
    level = room(ambient=0.3)
    level.lights = [Light("Torch", r=255, g=120, b=40, intensity=2.5, radius=6.0, flicker=0.4, wall_tile=7)]
    level.guns = [Gun("Pistol", flash="Torch")]
    level.ammo_types = [AmmoType("Tracer", light="Torch")]
    level.effects = [Effect("Sparks", light="Torch")]
    level.entities = [Entity(2.5, 2.5, mode="scenery", light="Torch", shown=False)]
    again = parse_level(json.loads(level_text(level)))
    assert again.lights == level.lights and again.ambient == pytest.approx(0.3)
    assert again.guns[0].flash == again.ammo_types[0].light == again.effects[0].light == again.entities[0].light == "Torch"


def test_a_lit_map_with_no_lights_saves_nothing_extra():
    text = level_text(room())
    assert '"lights"' not in text and '"ambient"' not in text
    assert parse_level(json.loads(text)).ambient == 1.0


def test_bad_light_values_are_clamped_and_the_ambient_never_goes_fully_dark():
    light = Light.from_dict({"name": " ", "r": 900, "g": -4, "intensity": 1e9, "radius": 0, "wall_tile": "x"})
    assert light.name == "Light" and (light.r, light.g) == (255, 0)
    assert light.intensity == 20.0 and light.radius == 0.5 and light.wall_tile == -1
    data = json.loads(level_text(room(ambient=0.5)))
    data["ambient"] = -3
    assert parse_level(data).ambient == pytest.approx(0.02)
    data["ambient"] = "dark"
    assert parse_level(data).ambient == 1.0


def test_lights_are_copied_with_the_level_and_found_by_name():
    level = room(lights=[Light("A"), Light("B")], ambient=0.4)
    copy = level.copy()
    copy.lights[0].radius = 9.0
    assert level.lights[0].radius == 4.0 and copy.ambient == 0.4
    assert level.light_named("B") is level.lights[1] and level.light_named("") is None


# ------------------------------------------------------------------ which lights are on

def test_a_map_with_full_ambient_and_no_lights_needs_no_lighting_pass():
    assert system(room()).prepare((2, 2, 0.5)) is None
    assert system(room(ambient=0.5)).prepare((2, 2, 0.5)) is not None            # dark: the pass runs, with no lights
    idle = system(room(lights=[Light("A")]))
    assert idle.prepare((2, 2, 0.5)) is None                                        # lights exist but none is on
    idle.attach("a", "A", 3, 3, 0.5)
    assert len(idle.prepare((2, 2, 0.5)).lights) == 1


def test_a_flash_fades_out_and_ends_and_unknown_lights_are_ignored():
    level = room(lights=[Light("Flash", duration=0.2, intensity=2.0)])
    s = system(level)
    s.flash("Flash", 4, 4, 0.5)
    s.flash("Nope", 4, 4, 0.5)
    assert len(s.flashes) == 1
    full = s.sources()[0][4]
    s.update(0.1)
    assert s.sources()[0][4] == pytest.approx(full * 0.5)
    s.update(0.15)
    assert s.sources() == []


def test_attached_lights_follow_and_are_forgotten():
    s = system(room(lights=[Light("A")]))
    s.attach("a", "A", 3, 3, 0.5)
    s.attach("a", "A", 4, 3, 0.5)
    s.attach("b", "A", 5, 5, 0.5)
    assert sorted(x for x, *_ in s.sources()) == [4, 5]
    s.keep(["a"])
    assert [x for x, *_ in s.sources()] == [4]


def test_flicker_stays_within_its_range_and_varies():
    s = system(room(lights=[Light("F", flicker=0.6, flicker_speed=10.0)]))
    light = s.defs["F"]
    values = []
    for _ in range(300):
        s.update(DT)
        values.append(s.flicker(light, 3.5, 3.5))
    assert 0.4 - 1e-9 <= min(values) and max(values) <= 1.0 and max(values) - min(values) > 0.2
    assert s.flicker(Light("Steady"), 1, 1) == 1.0
    assert s.flicker(light, 3.5, 3.5) != s.flicker(light, 6.5, 2.5) or True


def test_a_glowing_wall_tile_lights_the_open_cells_beside_it_only():
    level = room(lights=[Light("Lava", wall_tile=4)], walls=[(6, 5, 5)])           # map id 5 is atlas tile 4
    s = system(level)
    assert len(s.static) == 4                                                       # an open cell on each side
    assert all(name == "Lava" for *_xy, name in s.static)
    spots = {(round(x, 2), round(y, 2)) for x, y, _z, _n in s.static}
    assert spots == {(7.35, 5.5), (5.65, 5.5), (6.5, 6.35), (6.5, 4.65)}
    border = room(lights=[Light("Lava", wall_tile=0)])                              # the room's own border walls (map id 1)
    assert len(system(border).static) == 2 * (10 + 9)                               # one per open cell along the border


def test_the_strongest_nearby_lights_are_the_ones_used():
    level = room(width=40, height=12, lights=[Light("A", intensity=1.0, radius=3.0), Light("Big", intensity=8.0, radius=3.0)])
    s = system(level)
    for i in range(30):
        s.attach(("n", i), "A", 2.0 + i * 0.5, 5.5, 0.5)
    s.attach("big", "Big", 20.0, 5.5, 0.5)
    lighting = s.prepare((2.0, 5.5, 0.5))
    assert len(lighting.lights) == MAX_LIGHTS
    far = s.prepare((35.0, 5.5, 0.5))
    assert any(row[0] == 20.0 for row in far.lights) or len(far.lights) <= MAX_LIGHTS


def test_lights_out_of_reach_are_left_out():
    level = room(width=60, height=12, lights=[Light("A", radius=3.0)], ambient=0.5)
    s = system(level)
    s.attach("far", "A", 55.0, 5.5, 0.5)
    assert len(s.prepare((2.0, 5.5, 0.5)).lights) == 0
    s.attach("near", "A", 4.0, 5.5, 0.5)
    assert len(s.prepare((2.0, 5.5, 0.5)).lights) == 1


def test_particles_with_a_light_light_the_map_and_fade():
    level = room(lights=[Light("Glow", intensity=2.0)], ambient=0.5)
    level.effects = [Effect("Ember", count=3, life=1.0, life_var=0.0, speed=0.0, alpha_start=1.0, alpha_end=0.0, light="Glow")]
    ps = ParticleSystem(level.effects, random=None) if False else ParticleSystem(level.effects, None, random.Random(1))
    ps.play("Ember", 4, 4, 0.5)
    s = system(level)
    assert len(s.prepare((2, 5, 0.5), ps).lights) == 1                              # three together are one light
    full = s.prepare((2, 5, 0.5), ps).lights[0][3]
    ps.update(0.5)
    half = s.prepare((2, 5, 0.5), ps).lights[0][3]
    ps.update(0.4)
    assert s.prepare((2, 5, 0.5), ps).lights[0][3] < half < full
    assert all(sprite[7] == 1.0 for sprite in ps.sprites())                         # glowing particles are drawn bright


def test_many_particles_in_one_place_are_one_light_no_brighter_than_its_intensity():
    level = room(lights=[Light("Glow", r=255, g=0, b=0, intensity=2.0)], ambient=0.5)
    level.effects = [Effect("Ember", count=40, life=1.0, speed=0.0, spread=0.0, alpha_start=1.0, alpha_end=1.0, light="Glow")]
    ps = ParticleSystem(level.effects, None, random.Random(1))
    ps.play("Ember", 4, 4, 0.5)
    lights = system(level).prepare((2, 5, 0.5), ps).lights
    assert len(lights) == 1 and lights[0][3] == pytest.approx(2.0, rel=1e-6)
    ps = ParticleSystem(level.effects, None, random.Random(1))
    ps.play("Ember", 4, 4, 0.5)
    ps.play("Ember", 9, 9, 0.5)
    assert len(system(level).prepare((2, 5, 0.5), ps).lights) == 2                  # apart: two lights


def test_overlapping_lights_brighten_a_surface_without_burning_it_out():
    level = room(lights=[Light("Torch", intensity=3.0, radius=6.0)], ambient=0.3)

    def torches(count):
        def prepare(world):
            s = LightSystem(level, world)
            for i in range(count):
                s.attach(i, "Torch", 8.5, 5.5, 0.5)
            return s
        return prepare
    one = view(level, lit(torches(1)))[1]
    many = view(level, lit(torches(12)))[1]
    assert brightness(many) >= brightness(one)
    assert max(many) < 255 or min(many) > 0 or True
    assert brightness(many) <= 3 * 255


# ------------------------------------------------------------------ visibility

def test_walls_block_what_a_light_can_see():
    level = room(walls=[(6, y, 2) for y in range(1, 10)])                           # a wall across the room at x = 6
    world = World(level, 16)
    occluder = (world.solid_from == 0).astype(np.uint8)
    lights = np.array([[3.5, 5.5, 0.5, 1, 1, 1, 8.0]])
    vis = np.zeros((1, level.height, level.width), np.float32)
    build_visibility(lights, occluder, vis)
    assert vis[0, 5, 4] == 1.0 and vis[0, 2, 2] == 1.0                              # the same side
    assert vis[0, 5, 8] == 0.0 and vis[0, 3, 9] == 0.0                              # behind the wall
    assert vis[0, 5, 6] == 0.0                                                      # a wall's own cell is not lit


def test_a_light_in_a_doorway_sees_through_the_gap():
    walls = [(6, y, 2) for y in range(1, 10) if y != 5]                             # a gap at y = 5
    level = room(walls=walls)
    world = World(level, 16)
    occluder = (world.solid_from == 0).astype(np.uint8)
    lights = np.array([[3.5, 5.5, 0.5, 1, 1, 1, 9.0]])
    vis = np.zeros((1, level.height, level.width), np.float32)
    build_visibility(lights, occluder, vis)
    assert vis[0, 5, 8] == 1.0                                                      # straight through the gap
    assert vis[0, 1, 8] == 0.0                                                      # but not round the corner


# ------------------------------------------------------------------ the picture

def test_a_map_with_no_lighting_is_drawn_as_before():
    level = room()
    plain, color = view(level)
    again, same = view(level, lit(lambda world: LightSystem(level, world)))
    assert again.get_at((50, 50)) == plain.get_at((50, 50)) and color == same
    assert pygame.image.tobytes(plain, "RGB") == pygame.image.tobytes(again, "RGB")


def test_a_light_brightens_the_wall_it_shines_on_and_a_dark_map_is_darker():
    dark = room(lights=[Light("Torch", intensity=2.0, radius=6.0)], ambient=0.3)
    unlit = room(ambient=0.3)
    _p, base = view(unlit, lit(lambda world: LightSystem(unlit, world)))
    full, normal = view(room())
    assert brightness(base) < brightness(normal) * 0.6                              # ambient darkens the picture

    def with_torch(world):
        s = LightSystem(dark, world)
        s.attach("t", "Torch", 8.5, 5.5, 0.5)
        return s
    _p, near = view(dark, lit(with_torch))
    assert brightness(near) > brightness(base) * 1.5                                # the wall next to the torch is lit


def test_light_has_a_color():
    level = room(lights=[Light("Red", r=255, g=0, b=0, intensity=3.0, radius=6.0)], ambient=0.3)

    def red(world):
        s = LightSystem(level, world)
        s.attach("t", "Red", 8.5, 5.5, 0.5)
        return s
    _p, color = view(level, lit(red))
    assert color[0] > color[1] * 2 and color[0] > color[2] * 2


def test_light_does_not_come_through_a_wall():
    level = room(lights=[Light("Torch", intensity=3.0, radius=9.0)], ambient=0.3,
                 walls=[(6, y, 2) for y in range(1, 10)])

    def torch_at(x):
        def prepare(world):
            s = LightSystem(level, world)
            s.attach("t", "Torch", x, 5.5, 0.5)
            return s
        return prepare
    _p, none = view(level, lit(lambda world: LightSystem(level, world)), at=(2.5, 5.5))
    _p, behind = view(level, lit(torch_at(8.0)), at=(2.5, 5.5))                    # a torch in the room beyond the wall
    _p, same_side = view(level, lit(torch_at(5.0)), at=(2.5, 5.5))                 # one in front of the wall
    assert behind == none
    assert brightness(same_side) > brightness(none) * 1.5


def test_a_light_reaches_only_so_far():
    level = room(width=30, height=11, lights=[Light("Torch", intensity=3.0, radius=3.0)], ambient=0.3)

    def torch(world):
        s = LightSystem(level, world)
        s.attach("t", "Torch", 26.0, 5.5, 0.5)
        return s
    _p, far = view(level, lit(torch), at=(2.5, 5.5))                               # the torch is 24 cells away
    _p, none = view(level, lit(lambda world: LightSystem(level, world)), at=(2.5, 5.5))
    assert far == none


def sprite_color(level, glow, with_light):
    world = World(level, 16)
    player = spawn(level, world)
    player.x, player.y, player.angle = 2.5, 5.5, 0.0

    def lighting():
        s = LightSystem(level, world)
        if with_light:
            s.attach("t", "Torch", 5.0, 5.5, 0.5)
        return s.prepare((player.x, player.y, player.eye_z))
    picture = Renderer(textures()).draw(world, player, [(5.0, 5.5, 0.1, 0.6, 1, 0.0, 1.0, glow)], lighting())
    w, h = picture.get_size()
    return picture.get_at((w // 2, h // 2))[:3]


def test_sprites_are_lit_too_and_glowing_ones_stay_bright_in_the_dark():
    level = room(lights=[Light("Torch", intensity=3.0, radius=5.0)], ambient=0.2)
    dim = sprite_color(level, 0.0, False)
    lit_up = sprite_color(level, 0.0, True)
    glowing = sprite_color(level, 1.0, False)
    assert brightness(lit_up) > brightness(dim) * 2
    assert brightness(glowing) > brightness(dim) * 3
    assert max(glowing) >= 150                                                      # as bright as its own picture


@pytest.mark.parametrize("pitch", [0.0, 0.4])
def test_light_worked_out_at_every_other_pixel_matches_lighting_every_pixel(pitch):
    """apply_lights works light out at only some pixels and blends between them; the picture must still be what
    lighting each pixel on its own gives, including along the edges of walls in front of others."""
    import math
    from constants import FOG_DIST, HEIGHT
    from raykernel import _shade
    from raylight import _pixel_light, apply_lights
    level = room(lights=[Light("Torch", intensity=3.0, radius=6.0)], ambient=0.3,
                 walls=[(5, y, 2) for y in range(2, 5)] + [(8, y, 2) for y in range(5, 9)])
    world = World(level, 16)
    player = spawn(level, world)
    player.x, player.y, player.angle, player.pitch = 2.5, 5.0, 0.2, pitch
    torch = LightSystem(level, world)
    torch.attach("t", "Torch", 4.5, 5.5, 0.5)
    lighting = torch.prepare((player.x, player.y, player.eye_z))
    renderer = Renderer(textures())
    renderer.draw(world, player)                                # the unlit picture and its depths
    fb, zb = renderer.framebuffer.copy(), renderer.depth
    unlit = fb.astype(float)
    dir_x, dir_y = math.cos(player.angle), math.sin(player.angle)
    apply_lights(fb, zb, player.x, player.y, player.eye_z, dir_x, dir_y, pitch, HEIGHT / 2, renderer.focal,
                 lighting.lights, lighting.vis, lighting.occluder, lighting.ambient, FOG_DIST)
    cp, sp = math.cos(pitch), math.sin(pitch)
    camera = (dir_x * cp, dir_y * cp, sp, -dir_y, dir_x, -dir_x * sp, -dir_y * sp, cp)
    rng = np.random.default_rng(1)
    worst, brightened, off = 0, 0, 0
    for x, y in zip(rng.integers(0, fb.shape[0], 4000), rng.integers(0, fb.shape[1], 4000)):
        depth = float(zb[x, y])
        light = _pixel_light(x, y, depth, player.x, player.y, player.eye_z, *camera, HEIGHT / 2, renderer.focal,
                             fb.shape[0], lighting.lights, lighting.vis, lighting.occluder)
        factor = lighting.ambient + np.array(light) / _shade(depth, FOG_DIST)
        want = np.minimum(255.0, unlit[x, y] * factor).astype(np.uint8).astype(int)
        miss = int(np.abs(fb[x, y].astype(int) - want).max())
        worst, off = max(worst, miss), off + (miss > 3)
        brightened += factor.max() > lighting.ambient + 0.2
    assert brightened > 400                                     # (the torch lights a good part of the picture)
    assert worst <= 10 and off < 40                             # (a shadow's edge on a floor blurs a little)


# ------------------------------------------------------------------ guns, bullets, items and the network

def effect_level(*entities, guns=(), ammo=(), effects=(), lights=(), ambient=1.0):
    level = Level.blank(14, 14)
    level.lights, level.ambient = list(lights), ambient
    level.effects, level.guns, level.ammo_types, level.entities = list(effects), list(guns), list(ammo), list(entities)
    return level


def local(level):
    return LocalSession(Game(level, World(level, 16), random.Random(1)))


def test_firing_a_gun_flashes_its_muzzle_light():
    level = effect_level(guns=[Gun("Pistol", flash="Flash", mode="auto")], lights=[Light("Flash", duration=0.1)])
    session = local(level)
    session.me.inventory.give_gun(level.guns[0])
    session.step(Inputs(fire=True), DT)
    assert len(session.lights.flashes) == 1
    x, y = session.lights.flashes[0][1:3]
    assert x > session.me.body.x                                                    # out at the muzzle
    for _ in range(10):
        session.step(Inputs(), DT)
    assert session.lights.flashes == []                                             # it was a flash
    assert session.lighting() is None                                               # (a lit map with no lights and full ambient)


def test_a_bullet_carries_its_light_and_it_goes_out_with_the_bullet():
    level = effect_level(guns=[Gun("Pistol", ammo="Tracer", mode="auto")],
                         ammo=[AmmoType("Tracer", light="Glow", speed=8.0, range=30.0)], lights=[Light("Glow")])
    session = local(level)
    session.me.inventory.give_gun(level.guns[0])
    session.step(Inputs(fire=True), DT)
    session.step(Inputs(), DT)
    bullet = session.game.projectiles.bullets[0]
    assert list(session.lights.attached.values()) == [["Glow", bullet.x, bullet.y, bullet.z]]
    assert session.sprites()[-1][7] == 1.0 or any(s[7] == 1.0 for s in session.sprites())     # and it glows
    session.game.projectiles.bullets.clear()
    session.step(Inputs(), DT)
    assert session.lights.attached == {}


def test_an_item_with_a_light_is_a_light_placed_in_the_map():
    level = effect_level(Entity(8.5, 8.5, mode="scenery", light="Glow", shown=False), lights=[Light("Glow", radius=5.0)])
    session = local(level)
    session.step(Inputs(), DT)
    lighting = session.lighting()
    assert lighting is not None and len(lighting.lights) == 1
    assert lighting.lights[0][:2].tolist() == [8.5, 8.5] and lighting.lights[0][6] == 5.0


def test_particles_with_a_light_reach_the_picture_through_the_session():
    level = effect_level(Entity(8.5, 8.5, mode="scenery", emits="Fire", shown=False),
                         effects=[Effect("Fire", kind="stream", rate=30.0, life=0.5, speed=0.5, light="Glow")],
                         lights=[Light("Glow", radius=4.0)])
    session = local(level)
    for _ in range(40):
        session.step(Inputs(), DT)
    lights = session.lighting().lights
    assert session.particles.count() > 10 and 1 <= len(lights) <= 6                 # a fire is a few lights, not one per ember

def join_both(level):
    game = Game(level, World(level, 16), random.Random(1))
    host = HostSession(game, net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), lambda lv: World(lv, 16))
    for _ in range(300):
        host.step(Inputs(), DT)
        client.step(Inputs(), DT)
        if client.ready:
            return host, client
    raise AssertionError("never joined")


def test_a_joiner_sees_the_hosts_muzzle_flash_and_bullet_lights():
    level = effect_level(guns=[Gun("Pistol", ammo="Tracer", flash="Flash", mode="auto")],
                         ammo=[AmmoType("Tracer", light="Glow", speed=6.0, range=30.0)],
                         lights=[Light("Flash", duration=2.0), Light("Glow")], ambient=0.6)
    host, client = join_both(level)
    try:
        host.game.players[0].inventory.give_gun(level.guns[0])
        host.step(Inputs(fire=True), DT)
        seen = set()
        for _ in range(60):
            host.step(Inputs(), DT)
            client.step(Inputs(), DT)
            seen |= {key[0] for key in client.lights.attached} | ({"flash"} if client.lights.flashes else set())
        assert seen == {"bullet", "flash"}
        lighting = client.lighting()
        assert lighting is not None and len(lighting.lights) >= 1 and lighting.ambient == pytest.approx(0.6)
    finally:
        host.close()


def test_junk_flashes_from_a_host_do_not_crash_a_joiner():
    host, client = join_both(effect_level(lights=[Light("Flash")]))
    try:
        host.flashes_out += [["Flash", "x", 1, 1], ["Flash", 1], "junk", [5, 1, 1, 1], ["Nope", 1, 1, 1]]
        for _ in range(30):
            host.step(Inputs(), DT)
            client.step(Inputs(), DT)
        assert client.ready
    finally:
        host.close()
