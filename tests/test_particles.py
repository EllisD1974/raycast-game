"""Particle effects: the map data, the particle engine, and effects played from guns, bullets and items."""
import json
import math
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import net
import particles
from game import Game, Inputs
from mapfile import AmmoType, Effect, Entity, Gun, Level, level_text, parse_level
from particles import MAX_PARTICLES, ParticleSystem, cone
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


def system(*effects, world=None, seed=1):
    return ParticleSystem(effects, world, random.Random(seed))


def run(ps, seconds, dt=DT):
    for _ in range(round(seconds / dt)):
        ps.update(dt)


# ------------------------------------------------------------------ the map data

def test_an_effect_survives_saving_and_loading_with_the_things_that_use_it():
    level = Level.blank(8, 8)
    level.effects = [Effect("Smoke", tile=3, kind="stream", rate=12.5, gravity=-1.5, collide=False)]
    level.guns = [Gun("Pistol", muzzle="Smoke")]
    level.ammo_types = [AmmoType("Tracer", trail="Smoke")]
    level.entities = [Entity(2.5, 2.5, mode="scenery", emits="Smoke", shown=False)]
    again = parse_level(json.loads(level_text(level)))
    assert again.effects == level.effects
    assert again.guns[0].muzzle == "Smoke" and again.ammo_types[0].trail == "Smoke"
    assert (again.entities[0].mode, again.entities[0].emits, again.entities[0].shown) == ("scenery", "Smoke", False)


def test_a_map_without_effects_has_no_effects_key_and_loads_fine():
    level = Level.blank(6, 6)
    assert '"effects"' not in level_text(level)
    assert parse_level(json.loads(level_text(level))).effects == []


def test_bad_effect_values_are_clamped_or_replaced():
    effect = Effect.from_dict({"name": "  ", "kind": "nonsense", "count": 99999, "life": -4, "spread": "wide",
                               "alpha_start": 7, "collide": 0, "tile": -3})
    assert effect.name == "Effect" and effect.kind == "burst"
    assert effect.count == 200 and effect.life == 0.05 and effect.spread == Effect().spread
    assert effect.alpha_start == 1.0 and effect.collide is False and effect.tile == 0


def test_effects_are_copied_with_the_level_and_found_by_name():
    level = Level.blank(6, 6)
    level.effects = [Effect("A"), Effect("B")]
    copy = level.copy()
    copy.effects[0].count = 99
    assert level.effects[0].count == 12
    assert level.effect_named("B") is level.effects[1] and level.effect_named("") is None


def test_items_follow_their_prefab_for_the_new_fields():
    level = Level.blank(6, 6)
    level.prefabs = [Entity(0, 0, name="Torch", mode="scenery", emits="Fire", shown=False)]
    level.entities = [Entity(2.5, 2.5, prefab="Torch")]
    level.apply_prefabs()
    assert (level.entities[0].mode, level.entities[0].emits, level.entities[0].shown) == ("scenery", "Fire", False)


# ------------------------------------------------------------------ the engine

def test_a_burst_makes_its_count_and_they_die_after_their_life():
    ps = system(Effect("Puff", count=20, life=0.5, life_var=0.0))
    ps.play("Puff", 1, 1, 0.5)
    assert ps.count() == 20
    run(ps, 0.3)
    assert ps.count() == 20
    run(ps, 0.3)
    assert ps.count() == 0


def test_an_unknown_or_empty_effect_does_nothing():
    ps = system(Effect("Puff"))
    ps.play("Nope", 1, 1, 1)
    ps.play("", 1, 1, 1)
    ps.attach("k", "Nope", 1, 1, 1, dt=DT)
    assert ps.count() == 0 and not ps.attached


def test_particles_leave_along_the_direction_within_the_spread():
    ps = system(Effect("Jet", count=100, spread=0.0, speed=4.0, speed_var=0.0, life=1.0))
    ps.play("Jet", 0, 0, 0, (1, 0, 0))
    assert all((p.vx, p.vy, p.vz) == pytest.approx((4.0, 0.0, 0.0)) for p in ps.particles)
    ps = system(Effect("Fan", count=200, spread=30.0, speed=1.0, speed_var=0.0))
    ps.play("Fan", 0, 0, 0, (0, 1, 0))
    angles = [math.degrees(math.acos(p.vy)) for p in ps.particles]
    assert max(angles) <= 30.0 + 1e-6 and max(angles) > 20.0
    assert all(math.sqrt(p.vx ** 2 + p.vy ** 2 + p.vz ** 2) == pytest.approx(1.0) for p in ps.particles)


def test_cone_covers_every_direction_at_180():
    rng = random.Random(3)
    zs = [cone((0, 0, 1), math.pi, rng)[2] for _ in range(500)]
    assert min(zs) < -0.8 and max(zs) > 0.8
    assert cone((0, 0, 0), 0.5, rng)[2] > 0.8                       # no direction: up


def test_gravity_pulls_down_and_negative_gravity_floats_up():
    ps = system(Effect("Drop", count=1, spread=0.0, speed=0.0, gravity=9.0, life=2.0, life_var=0.0, collide=False),
                Effect("Float", count=1, spread=0.0, speed=0.0, gravity=-2.0, life=2.0, life_var=0.0, collide=False))
    ps.play("Drop", 0, 0, 5)
    ps.play("Float", 1, 0, 5)
    run(ps, 0.5)
    drop, rise = ps.particles
    assert drop.z < 5 - 0.5 and rise.z > 5.1


def test_drag_slows_particles():
    ps = system(Effect("Slow", count=1, spread=0.0, speed=10.0, speed_var=0.0, drag=4.0, life=3.0, life_var=0.0))
    ps.play("Slow", 0, 0, 0, (1, 0, 0))
    run(ps, 1.0)
    assert ps.particles[0].vx < 1.0


def test_size_and_alpha_change_over_a_particles_life():
    ps = system(Effect("Fade", count=1, life=1.0, life_var=0.0, speed=0.0, size_start=0.4, size_end=0.0,
                       alpha_start=1.0, alpha_end=0.0))
    ps.play("Fade", 2, 3, 1.0)
    run(ps, 0.5)
    (x, y, z, size, tile, spin, alpha, glow), = ps.sprites()
    assert size == pytest.approx(0.2, abs=0.02) and alpha == pytest.approx(0.5, abs=0.05)
    assert (x, y) == (2, 3) and z == pytest.approx(1.0 - size / 2)


def test_invisible_particles_are_not_drawn():
    ps = system(Effect("Gone", count=3, life=1.0, size_start=0.0, size_end=0.0))
    ps.play("Gone", 0, 0, 0)
    assert ps.sprites() == []


def test_a_stream_sends_its_rate_for_its_duration():
    ps = system(Effect("Spray", kind="stream", rate=100.0, duration=0.5, life=5.0, speed=0.0))
    ps.play("Spray", 0, 0, 0)
    run(ps, 1.0)
    assert 45 <= ps.count() <= 55                                    # 100 a second for half a second
    assert not ps.streams


def test_a_stream_with_no_duration_still_ends():
    ps = system(Effect("Flash", kind="stream", rate=100.0, duration=0.0, life=5.0))
    ps.play("Flash", 0, 0, 0)
    run(ps, 1.0)
    assert 0 < ps.count() < 30 and not ps.streams


def test_an_attached_stream_leaves_a_trail_along_the_path_with_no_gaps():
    ps = system(Effect("Trail", kind="stream", rate=60.0, speed=0.0, life=5.0, radius=0.0))
    ps.attach("b", "Trail", 0.0, 0.0, 0.0, dt=DT)                    # first sight: nothing yet
    for i in range(1, 31):                                           # a fast mover: 0.5 cells a frame
        ps.attach("b", "Trail", 0.5 * i, 0.0, 0.0, dt=DT)
    xs = sorted(p.x for p in ps.particles)
    assert len(xs) == 30 and xs[0] > 0 and xs[-1] == pytest.approx(15.0)
    assert all(b - a < 1.0 for a, b in zip(xs, xs[1:]))             # one particle every half cell or so


def test_an_attached_burst_plays_once_then_repeats_at_its_interval():
    once = system(Effect("Pop", count=5, interval=0.0, life=9.0))
    repeat = system(Effect("Pop", count=5, interval=0.5, life=9.0))
    for ps in (once, repeat):
        for _ in range(120):                                         # two seconds
            ps.attach("k", "Pop", 1, 1, 1, dt=DT)
            ps.update(DT)
    assert once.count() == 5
    assert repeat.count() in (20, 25)                                # at the start, then every half second


def test_keep_forgets_emitters_whose_thing_is_gone():
    ps = system(Effect("T", kind="stream"))
    ps.attach("a", "T", 0, 0, 0, dt=DT)
    ps.attach("b", "T", 0, 0, 0, dt=DT)
    ps.keep(["a"])
    assert set(ps.attached) == {"a"}


def test_particles_stop_at_walls_when_they_collide():
    level = Level.blank(8, 8)
    world = World(level, 16)
    solid = system(Effect("S", count=50, spread=180.0, speed=6.0, life=3.0, collide=True), world=world)
    ghost = system(Effect("G", count=50, spread=180.0, speed=6.0, life=3.0, collide=False), world=world)
    solid.play("S", 4, 4, 0.5)
    ghost.play("G", 4, 4, 0.5)
    run(solid, 3.0 - DT)
    run(ghost, 3.0 - DT)
    assert solid.count() < ghost.count()
    assert all(world.point_open(p.x, p.y, p.z) for p in solid.particles)


def test_there_is_a_limit_to_how_many_particles_live_at_once():
    ps = system(Effect("Flood", count=200, life=10.0))
    for _ in range(10):
        ps.play("Flood", 0, 0, 0)
    assert ps.count() == MAX_PARTICLES


# ------------------------------------------------------------------ guns, bullets and items

def effect_level(*entities, guns=(), ammo=(), effects=()):
    level = Level.blank(14, 14)
    level.effects, level.guns, level.ammo_types, level.entities = list(effects), list(guns), list(ammo), list(entities)
    return level


def local(level):
    return LocalSession(Game(level, World(level, 16), random.Random(1)))


def test_firing_a_gun_plays_its_muzzle_effect():
    level = effect_level(guns=[Gun("Pistol", muzzle="Flash", mode="auto")],
                         effects=[Effect("Flash", count=6, life=0.3, speed=1.0)])
    session = local(level)
    session.me.inventory.give_gun(level.guns[0])
    session.step(Inputs(fire=True), DT)
    assert session.particles.count() == 6
    assert all(p.x > session.me.body.x for p in session.particles.particles)        # out in front of the player


def test_a_gun_with_no_muzzle_effect_plays_nothing():
    level = effect_level(guns=[Gun("Pistol", mode="auto")], effects=[Effect("Flash")])
    session = local(level)
    session.me.inventory.give_gun(level.guns[0])
    session.step(Inputs(fire=True), DT)
    assert session.particles.count() == 0 and session.game.take_fx() == []


def test_a_bullet_drags_its_trail_through_the_air():
    level = effect_level(guns=[Gun("Pistol", ammo="Tracer", mode="auto")],
                         ammo=[AmmoType("Tracer", trail="Smoke", speed=10.0, range=30.0)],
                         effects=[Effect("Smoke", kind="stream", rate=60.0, speed=0.0, life=2.0)])
    session = local(level)
    session.me.inventory.give_gun(level.guns[0])
    session.step(Inputs(fire=True), DT)
    for _ in range(30):
        session.step(Inputs(), DT)
    xs = [p.x for p in session.particles.particles]
    bullet = session.game.projectiles.bullets[0]
    assert len(xs) > 10 and max(xs) <= bullet.x + 1e-6 and max(xs) - min(xs) > 2.0   # spread out behind it
    session.game.projectiles.bullets.clear()
    session.step(Inputs(), DT)
    assert not session.particles.attached                                           # the trail ended with the bullet


def test_an_item_that_emits_sends_its_effect_while_it_is_there():
    level = effect_level(Entity(7.5, 7.5, mode="scenery", emits="Fire", shown=False),
                         effects=[Effect("Fire", kind="stream", rate=40.0, speed=1.0, spread=10.0, life=1.0)])
    session = local(level)
    for _ in range(60):
        session.step(Inputs(), DT)
    assert session.particles.count() > 20
    assert all(abs(p.x - 7.5) < 1.0 and p.z > 0 for p in session.particles.particles)
    assert [s for s in session.game.items.sprites()] == []                           # hidden: only the particles show


def test_a_far_away_emitter_is_not_worked_out():
    level = effect_level(Entity(12.5, 12.5, mode="scenery", emits="Fire"),
                         effects=[Effect("Fire", kind="stream", rate=40.0)])
    session = local(level)
    session.me.body.x = session.me.body.y = 1.5
    monkey = particles.EMIT_RANGE
    particles.EMIT_RANGE = 5.0
    try:
        for _ in range(30):
            session.step(Inputs(), DT)
    finally:
        particles.EMIT_RANGE = monkey
    assert session.particles.count() == 0


def test_scenery_cannot_be_picked_up_but_other_items_can():
    level = effect_level(Entity(1.5, 1.5, mode="scenery", effect="score", amount=10),
                         Entity(1.5, 1.5, mode="persistent", effect="score", amount=5))
    session = local(level)
    events = session.step(Inputs(), DT)
    assert events.picked == ["+5 score"] and session.me.stats.score == 5


def test_hidden_items_are_not_drawn_but_shown_ones_are():
    level = effect_level(Entity(5.5, 5.5, shown=False), Entity(6.5, 6.5, shown=True))
    sprites = local(level).game.items.sprites()
    assert len(sprites) == 1 and sprites[0][0] == 6.5


# ------------------------------------------------------------------ over the network

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


def test_a_joiner_plays_the_hosts_muzzle_flash_and_draws_bullet_trails():
    level = effect_level(guns=[Gun("Pistol", ammo="Tracer", muzzle="Flash", mode="auto")],
                         ammo=[AmmoType("Tracer", trail="Smoke", speed=8.0, range=30.0)],
                         effects=[Effect("Flash", count=8, life=2.0, speed=0.5),
                                  Effect("Smoke", kind="stream", rate=60.0, speed=0.0, life=2.0)])
    host, client = join_both(level)
    try:
        host.game.players[0].inventory.give_gun(level.guns[0])
        host.step(Inputs(fire=True), DT)                              # the host shoots
        for _ in range(60):
            host.step(Inputs(), DT)
            client.step(Inputs(), DT)
        sprites = client.sprites()
        assert client.particles.count() > 8                           # the flash and the trail were played here
        assert any(len(s) == 8 for s in sprites)                      # particles come with an alpha and a glow
        assert not client.particles.attached or all(k[0] == "bullet" for k in client.particles.attached)
    finally:
        host.close()


def test_junk_effect_events_from_a_host_do_not_crash_a_joiner():
    host, client = join_both(effect_level(effects=[Effect("Flash")]))
    try:
        host.fx_out += [["Flash", "x", 1, 1, 0, 0, 1], ["Flash", 1], "junk", [5, 1, 1, 1, 0, 0, 1], ["Nope", 1, 1, 1, 0, 0, 1]]
        for _ in range(30):
            host.step(Inputs(), DT)
            client.step(Inputs(), DT)
        assert client.ready
    finally:
        host.close()


# ------------------------------------------------------------------ drawing

def test_sprite_alpha_blends_a_particle_into_the_picture():
    pygame.display.set_mode((100, 100))
    textures = np.zeros((2, 32, 32, 4), np.uint8)
    textures[0, ..., :3] = 120
    textures[0, ..., 3] = 255
    textures[1, ..., :3] = 255
    textures[1, ..., 3] = 255
    renderer = Renderer(textures)
    level = Level.blank(8, 8)
    world = World(level, 2)
    from physics import spawn
    player = spawn(level, world)
    player.x, player.y, player.angle = 2.5, 4.0, 0.0
    seen = {}
    for alpha in (0.0, 0.5, 1.0):
        picture = renderer.draw(world, player, [(4.0, 4.0, 0.2, 0.6, 1, 0.0, alpha)])
        w, h = picture.get_size()
        seen[alpha] = picture.get_at((w // 2, h // 2))[:3]
    assert seen[0.0][0] < seen[0.5][0] < seen[1.0][0]
    assert renderer.draw(world, player, [(4.0, 4.0, 0.2, 0.6, 1)]).get_at((w // 2, h // 2))[:3] == seen[1.0]
