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
import physics
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


# ------------------------------------------------------------------ where they start and which way they go

def still(**settings):
    """A one particle effect that does not move, so where it appears is where it was started."""
    return Effect("E", count=1, spread=0.0, speed=0.0, life=5.0, collide=False, **settings)


def test_an_effect_with_no_offset_or_direction_does_what_it_always_did():
    base = Effect("E", count=3, spread=0.0, speed=2.0, speed_var=0.0, life=5.0)
    assert (base.offset_x, base.offset_y, base.offset_z, base.aim, base.relative) == (0, 0, 0, "auto", False)
    ps = system(base)
    ps.play("E", 2.0, 3.0, 1.0, (0.0, 1.0, 0.0))
    assert all((p.x, p.y, p.z) == (2.0, 3.0, 1.0) and (p.vx, p.vy, p.vz) == pytest.approx((0, 2.0, 0)) for p in ps.particles)


def test_the_offset_moves_where_the_particles_start_along_the_maps_axes():
    ps = system(still(offset_x=0.5, offset_y=-0.25, offset_z=0.3))
    ps.play("E", 2.0, 2.0, 1.0)
    p, = ps.particles
    assert (p.x, p.y, p.z) == pytest.approx((2.5, 1.75, 1.3))


def test_a_relative_offset_follows_the_heading_and_an_item_has_none():
    ps = system(still(offset_x=1.0, offset_y=0.5, relative=True))
    ps.play("E", 5.0, 5.0, 1.0, (0.0, 1.0, 0.0))                     # heading along +y (south on the map)
    p, = ps.particles
    assert (p.x, p.y) == pytest.approx((5.0 - 0.5, 5.0 + 1.0))       # ahead is +y, to the right of that is -x
    ps = system(still(offset_x=1.0, offset_y=0.5, relative=True))
    ps.play("E", 5.0, 5.0, 1.0)                                      # up: no heading, so the map's axes
    p, = ps.particles
    assert (p.x, p.y) == pytest.approx((6.0, 5.5))
    ps = system(still(offset_x=1.0, relative=True))
    ps.play("E", 5.0, 5.0, 1.0, (1.0, 0.0, 0.0))                     # heading east: ahead is +x
    assert (ps.particles[0].x, ps.particles[0].y) == pytest.approx((6.0, 5.0))


def test_a_custom_direction_replaces_the_automatic_one():
    ps = system(Effect("E", count=5, spread=0.0, speed=4.0, speed_var=0.0, life=5.0, aim="custom", dir_x=3.0, dir_y=0.0, dir_z=0.0))
    ps.play("E", 0, 0, 0, (0.0, 1.0, 0.0))                           # the gun is aimed along +y but the effect says east
    assert all((p.vx, p.vy, p.vz) == pytest.approx((4.0, 0.0, 0.0)) for p in ps.particles)


def test_a_custom_direction_can_be_relative_to_the_heading():
    ps = system(Effect("E", count=3, spread=0.0, speed=4.0, speed_var=0.0, life=5.0, aim="custom", dir_x=1.0, dir_y=0.0,
                       dir_z=0.5, relative=True))
    ps.play("E", 0, 0, 0, (0.0, 1.0, 0.0))                           # heading +y: "forward" is +y
    v = ps.particles[0]
    length = math.sqrt(1.25)
    assert (v.vx, v.vy, v.vz) == pytest.approx((0.0, 4.0 / length, 2.0 / length))


def test_a_custom_direction_of_nothing_falls_back_to_automatic():
    ps = system(Effect("E", count=2, spread=0.0, speed=2.0, speed_var=0.0, life=5.0, aim="custom", dir_x=0.0, dir_y=0.0, dir_z=0.0))
    ps.play("E", 0, 0, 0, (0.0, 0.0, 1.0))
    assert all((p.vx, p.vy, p.vz) == pytest.approx((0, 0, 2.0)) for p in ps.particles)


def test_the_offset_applies_to_streams_and_trails_too():
    ps = system(Effect("T", kind="stream", rate=60.0, speed=0.0, life=5.0, offset_z=0.4, collide=False))
    ps.attach("b", "T", 0.0, 0.0, 1.0, dt=DT)
    for i in range(1, 11):
        ps.attach("b", "T", 0.3 * i, 0.0, 1.0, dt=DT)
    assert ps.particles and all(p.z == pytest.approx(1.4) for p in ps.particles)
    one_shot = system(Effect("S", kind="stream", rate=100.0, duration=0.2, speed=0.0, life=5.0, offset_x=2.0, collide=False))
    one_shot.play("S", 1.0, 1.0, 1.0)
    one_shot.update(0.1)
    assert one_shot.particles and all(p.x == pytest.approx(3.0) for p in one_shot.particles)


def test_offsets_and_directions_survive_saving_and_bad_values_are_fixed():
    level = Level.blank(6, 6)
    level.effects = [Effect("E", offset_x=0.5, offset_y=-1.0, offset_z=0.25, aim="custom", dir_x=1.0, dir_y=-2.0,
                            dir_z=0.0, relative=True)]
    again = parse_level(json.loads(level_text(level)))
    assert again.effects == level.effects
    bad = Effect.from_dict({"offset_x": 999, "aim": "sideways", "dir_z": "up", "relative": 1})
    assert bad.offset_x == 10.0 and bad.aim == "auto" and bad.dir_z == 1.0 and bad.relative is True


# ------------------------------------------------------------------ an offset from whatever uses the effect

def test_an_offset_from_the_user_replaces_the_effects_own_and_follows_the_heading():
    ps = system(still(offset_x=9.0, offset_y=9.0, offset_z=9.0))                  # the effect's own offset is ignored
    ps.play("E", 5.0, 5.0, 1.0, (0.0, 1.0, 0.0), offset=(1.0, 0.5, 0.25))          # heading +y: ahead is +y, right is -x
    p, = ps.particles
    assert (p.x, p.y, p.z) == pytest.approx((4.5, 6.0, 1.25))


def test_an_offset_from_an_item_uses_the_maps_axes():
    ps = system(still())
    ps.play("E", 5.0, 5.0, 1.0, offset=(1.0, 0.5, 0.25))                           # up: no heading
    assert (ps.particles[0].x, ps.particles[0].y, ps.particles[0].z) == pytest.approx((6.0, 5.5, 1.25))


def test_no_override_leaves_the_effects_own_offset_and_a_zero_override_cancels_it():
    ps = system(still(offset_x=2.0))
    ps.play("E", 0.0, 0.0, 0.0)
    ps.play("E", 0.0, 0.0, 0.0, offset=(0.0, 0.0, 0.0))
    own, cancelled = ps.particles
    assert own.x == pytest.approx(2.0) and cancelled.x == 0.0


def test_a_trail_and_an_item_can_override_the_offset():
    ps = system(Effect("T", kind="stream", rate=60.0, speed=0.0, life=5.0, offset_z=5.0, collide=False))
    ps.attach("b", "T", 0.0, 0.0, 1.0, (-1.0, 0.0, 0.0), DT, offset=(0.0, 0.0, 0.5))
    for i in range(1, 6):
        ps.attach("b", "T", 0.3 * i, 0.0, 1.0, (-1.0, 0.0, 0.0), DT, offset=(0.0, 0.0, 0.5))
    assert ps.particles and all(p.z == pytest.approx(1.5) for p in ps.particles)
    via_follow = system(Effect("T", kind="stream", rate=60.0, speed=0.0, life=5.0, collide=False))
    for i in range(6):
        particles.follow(via_follow, [(1, "T", 0.3 * i, 0.0, 1.0, 1.0, 0.0, 0.0, (0.0, 0.0, 0.5))], dt=DT)
    assert via_follow.particles and all(p.z == pytest.approx(1.5) for p in via_follow.particles)


def test_an_item_that_overrides_the_offset_starts_its_particles_there():
    from entities import Entities
    level = Level.blank(10, 10)
    level.effects = [Effect("E", count=1, spread=0.0, speed=0.0, life=5.0, offset_x=9.0, collide=False)]
    level.entities = [Entity(4.5, 4.5, mode="scenery", emits="E", emits_override=True, emits_offset_x=1.0, emits_offset_z=0.5)]
    items = Entities(level, World(level, 16))
    ps = ParticleSystem(level.effects, None, random.Random(1))
    particles.emitters_in_view(ps, items, (4.5, 4.5), DT)
    p, = ps.particles
    item = items.items[0]
    assert (p.x, p.y) == pytest.approx((5.5, 4.5)) and p.z == pytest.approx(item.z + item.entity.size / 2 + 0.5)


def test_override_fields_survive_saving_and_prefabs_pass_them_on():
    level = Level.blank(6, 6)
    level.guns = [Gun("G", muzzle="E", muzzle_override=True, muzzle_offset_x=0.4, muzzle_offset_y=-0.2, muzzle_offset_z=-0.1)]
    level.ammo_types = [AmmoType("A", trail="E", trail_override=True, trail_offset_z=0.3)]
    level.prefabs = [Entity(0, 0, name="Torch", emits="E", emits_override=True, emits_offset_x=1.0)]
    level.entities = [Entity(2.5, 2.5, prefab="Torch")]
    level.apply_prefabs()
    again = parse_level(json.loads(level_text(level)))
    assert again.guns == level.guns and again.ammo_types == level.ammo_types
    assert (again.entities[0].emits_override, again.entities[0].emits_offset_x) == (True, 1.0)
    bad = Gun.from_dict({"muzzle_offset_x": 999, "muzzle_override": 1})
    assert bad.muzzle_offset_x == 10.0 and bad.muzzle_override is True


def test_a_gun_with_an_override_plays_its_muzzle_effect_at_that_offset():
    level = effect_level(guns=[Gun("Pistol", muzzle="Flash", mode="auto", muzzle_override=True, muzzle_offset_x=1.0,
                                   muzzle_offset_y=0.5, muzzle_offset_z=-0.2)],
                         effects=[Effect("Flash", count=1, spread=0.0, speed=0.0, life=2.0, offset_x=9.0, collide=False)])
    session = local(level)
    session.me.inventory.give_gun(level.guns[0])
    session.me.body.angle = 0.0                                                    # facing +x: ahead is +x, right is +y
    session.step(Inputs(fire=True), DT)
    p, = session.particles.particles
    body = session.me.body
    assert p.x == pytest.approx(body.x + 0.25 + 1.0, abs=0.01) and p.y == pytest.approx(body.y + 0.5, abs=0.01)
    assert p.z == pytest.approx(body.eye_z - 0.03 - 0.2, abs=0.01)


def test_a_muzzle_event_is_longer_only_when_the_gun_overrides_the_offset():
    from game import muzzle_event
    body = physics.spawn(effect_level(), World(effect_level(), 16))
    assert len(muzzle_event("Flash", body)) == 7
    assert muzzle_event("Flash", body, (0.5, 0.0, 0.1))[7:] == (0.5, 0.0, 0.1)


def test_a_bullets_trail_offset_comes_from_its_ammo_and_reaches_a_joiner():
    level = effect_level(guns=[Gun("Pistol", ammo="Tracer", mode="auto")],
                         ammo=[AmmoType("Tracer", trail="Smoke", speed=6.0, range=30.0, trail_override=True, trail_offset_z=0.4)],
                         effects=[Effect("Smoke", kind="stream", rate=60.0, speed=0.0, life=3.0, collide=False)])
    host, client = join_both(level)
    try:
        host.game.players[0].inventory.give_gun(level.guns[0])
        host.step(Inputs(fire=True), DT)
        assert host.game.projectiles.bullets[0].trail_offset == (0.0, 0.0, 0.4)
        for _ in range(40):
            host.step(Inputs(), DT)
            client.step(Inputs(), DT)
        bullet = host.game.projectiles.bullets[0]
        assert client.bullet_offset(client.bullets[0]) == (0.0, 0.0, 0.4)
        for who in (host, client):                                                  # both see the trail raised by 0.4
            assert who.particles.particles
            assert all(p.z == pytest.approx(bullet.z + 0.4, abs=0.02) for p in who.particles.particles)
    finally:
        host.close()


def test_a_joiner_plays_a_muzzle_effect_with_an_offset_and_ignores_junk_offsets():
    host, client = join_both(effect_level(effects=[Effect("Flash", count=1, spread=0.0, speed=0.0, life=5.0, collide=False)]))
    try:
        host.fx_out += [["Flash", 3.0, 3.0, 0.5, 1.0, 0.0, 0.0, 0.5, 0.0, 0.25], ["Flash", 1, 1, 1, 0, 0, 1, "x", 0, 0],
                        ["Flash", 1, 1, 1, 0, 0, 1, 0.5]]
        for _ in range(30):
            host.step(Inputs(), DT)
            client.step(Inputs(), DT)
        spots = [(round(p.x, 2), round(p.y, 2), round(p.z, 2)) for p in client.particles.particles]
        assert (3.5, 3.0, 0.75) in spots and client.ready
    finally:
        host.close()
