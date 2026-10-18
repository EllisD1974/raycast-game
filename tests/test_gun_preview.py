"""The live gun preview: the game itself firing a gun down a corridor, and its controls in the editor's Guns section."""
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import details
import map_editor
from atlas import atlas_array, unpack_atlas
from gunpreview import GunPreview
from mapfile import AmmoType, Effect, Entity, Gun, Level, Light

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1400, 860), pygame.RESIZABLE)
    yield
    pygame.quit()


@pytest.fixture(scope="module")
def textures():
    return atlas_array(unpack_atlas())


def level_with(*guns, effects=(), ammo=(), lights=()):
    level = Level.blank(8, 8)
    level.guns, level.effects, level.ammo_types, level.lights = list(guns), list(effects), list(ammo), list(lights)
    return level


def run(preview, seconds, firing):
    for _ in range(round(seconds / DT)):
        preview.update(DT, firing)


def preview_of(textures, gun, **extras):
    level = level_with(gun, **extras)
    preview = GunPreview(textures)
    preview.build(level, gun.name)
    return preview


# ------------------------------------------------------------------ the preview itself

def test_a_missing_gun_builds_nothing_and_updating_it_does_no_harm(textures):
    preview = GunPreview(textures)
    preview.build(level_with(Gun("A")), "Nope")
    assert not preview.ready
    preview.update(DT, True)


def test_it_does_not_fire_until_asked_to(textures):
    preview = preview_of(textures, Gun("Pistol", mode="auto"))
    run(preview, 1.0, False)
    assert preview.total_shots == 0


def test_a_full_auto_gun_fires_at_its_fire_rate_and_goes_on_reloading(textures):
    gun = Gun("Rifle", mode="auto", fire_rate=10.0, mag_size=5, reload_time=0.5)
    preview = preview_of(textures, gun)
    run(preview, 3.0, True)
    assert preview.total_shots > gun.capacity * 2                                   # more than two magazines: it reloaded
    assert 15 <= preview.total_shots <= 25                                          # ten a second, less the reloads
    assert 3 <= preview.shots_last_second() <= 10


def test_a_semi_auto_gun_is_pulled_again_and_again(textures):
    gun = Gun("Pistol", mode="semi", fire_rate=4.0, mag_size=100, reload_time=1.0)
    preview = preview_of(textures, gun)
    run(preview, 2.0, True)
    assert 7 <= preview.total_shots <= 9                                            # four a second for two seconds


def test_a_single_shot_gun_reloads_after_every_shot(textures):
    gun = Gun("Bolt", mode="single", fire_rate=10.0, reload_time=0.5)
    preview = preview_of(textures, gun)
    run(preview, 3.0, True)
    assert 4 <= preview.total_shots <= 6                                            # one every half second or so


def test_it_never_runs_out_of_rounds(textures):
    gun = Gun("Pistol", mode="auto", fire_rate=20.0, mag_size=4, start_ammo=0, reload_time=0.1)
    preview = preview_of(textures, gun)
    run(preview, 4.0, True)
    assert preview.total_shots > 40


def test_fire_once_fires_exactly_one_shot(textures):
    for mode in ("semi", "auto", "single"):
        preview = preview_of(textures, Gun("G", mode=mode, fire_rate=4.0))
        preview.fire_once()
        run(preview, 1.0, False)
        assert preview.total_shots == 1, mode


def test_the_muzzle_effect_flash_and_trail_all_play(textures):
    level = level_with(Gun("Pistol", mode="auto", fire_rate=5.0, muzzle="Puff", flash="Flash", ammo="Tracer"),
                       effects=[Effect("Puff", count=6, life=1.0), Effect("Smoke", kind="stream", rate=60.0, life=1.0, speed=0.0)],
                       ammo=[AmmoType("Tracer", trail="Smoke", light="Glow", speed=8.0, range=25.0)],
                       lights=[Light("Flash", duration=0.3), Light("Glow")])
    preview = GunPreview(textures)
    preview.build(level, "Pistol", dark=True)
    assert preview.session.game.level.ambient < 1.0
    run(preview, 0.5, True)
    session = preview.session
    assert session.particles.count() > 6                                            # the muzzle puff and the trail
    assert session.game.projectiles.bullets
    assert session.lighting() is not None and len(session.lighting().lights) >= 1


def test_it_renders_a_picture_with_the_weapon_and_effects(textures):
    tiles = unpack_atlas()
    level = level_with(Gun("Pistol", mode="auto", fire_rate=6.0, muzzle="Puff"), effects=[Effect("Puff", count=20, speed=3.0)])
    preview = GunPreview(textures)
    preview.build(level, "Pistol")
    still = preview.render(tiles, pygame.font.Font(None, 22)).copy()
    run(preview, 0.3, True)
    firing = preview.render(tiles, pygame.font.Font(None, 22))
    assert firing.get_size() == still.get_size() == (640, 360)
    assert pygame.image.tobytes(firing, "RGB") != pygame.image.tobytes(still, "RGB")


def test_a_dark_room_is_darker_and_a_rebuild_starts_over(textures):
    tiles = unpack_atlas()
    level = level_with(Gun("Pistol"))
    preview = GunPreview(textures)

    def mean(dark):
        preview.build(level, "Pistol", dark)
        picture = preview.render(tiles)
        return np.frombuffer(pygame.image.tobytes(picture, "RGB"), np.uint8).mean()
    assert mean(True) < mean(False) * 0.6
    run(preview, 1.0, True)
    preview.build(level, "Pistol")
    assert preview.total_shots == 0 and preview.shots_last_second() == 0


def test_changing_the_guns_settings_changes_what_is_built(textures):
    level = level_with(Gun("Pistol", mode="auto", fire_rate=2.0, mag_size=100))
    preview = GunPreview(textures)
    preview.build(level, "Pistol")
    run(preview, 2.0, True)
    slow = preview.total_shots
    level.guns[0].fire_rate = 8.0
    preview.build(level, "Pistol")
    run(preview, 2.0, True)
    assert preview.total_shots > slow * 2


# ------------------------------------------------------------------ in the editor

@pytest.fixture
def ed(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "m.json"))
    editor.level = Level.blank(10, 10)
    editor.level.start_x = editor.level.start_y = 1.5
    editor.show_legend = False
    editor.draw(pygame.display.get_surface())
    return editor


def click(ed, pos):
    ed.on_mouse_down(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    ed.on_mouse_up(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))


def row(ed, name):
    return next(r for r in ed.details_rows() if r.field.key == name)


def keys(ed):
    return [r.field.key for r in ed.details_rows()]


def choose(ed, name, choice):
    r = row(ed, name)
    click(ed, details.menu_anchor(r).center)
    for rect, option in details.menu_rects(r):
        if option == choice:
            click(ed, rect.center)
            return
    raise AssertionError(f"{choice} is not offered for {name}")


def add_gun(ed):
    if not ed.guns_mode:
        ed.do("guns")
    click(ed, ed.gun_rows()[1].center)
    return ed.level.guns[-1]


def controls(ed):
    return ed.gun_controls(ed.guns_card_rect())[0]


def step(ed, seconds):
    for _ in range(round(seconds / DT)):
        ed.update(DT, pygame.key.get_pressed())


def test_the_guns_section_has_a_live_preview_with_two_check_boxes_and_a_button(ed):
    gun = add_gun(ed)
    assert set(controls(ed)) == {"continuous", "dark", "once"}
    step(ed, 0.2)
    assert ed.gun_preview is not None and ed.gun_preview.ready and ed.gun_preview.gun_name == gun.name
    ed.draw(pygame.display.get_surface())
    assert ed.gun_continuous is False and ed.gun_dark is False


def test_nothing_fires_until_the_checkbox_is_ticked_and_it_stops_when_unticked(ed):
    add_gun(ed)
    step(ed, 1.0)
    assert ed.gun_preview.total_shots == 0
    click(ed, controls(ed)["continuous"][0].center)
    assert ed.gun_continuous is True
    step(ed, 2.0)
    fired = ed.gun_preview.total_shots
    assert fired >= 4                                                               # the default pistol: four a second
    ed.draw(pygame.display.get_surface())
    click(ed, controls(ed)["continuous"][0].center)
    assert ed.gun_continuous is False
    step(ed, 1.0)
    assert ed.gun_preview.total_shots == fired


def test_fire_once_fires_one_shot_and_dark_room_rebuilds_the_preview(ed):
    add_gun(ed)
    step(ed, 0.2)
    click(ed, controls(ed)["once"][0].center)
    step(ed, 0.5)
    assert ed.gun_preview.total_shots == 1
    first = ed.gun_preview
    click(ed, controls(ed)["dark"][0].center)
    assert ed.gun_dark is True
    step(ed, 0.2)
    assert ed.gun_preview is first and first.total_shots == 0 and first.session.game.level.ambient < 1.0


def test_editing_the_gun_restarts_the_preview_with_the_new_settings(ed):
    gun = add_gun(ed)
    click(ed, controls(ed)["continuous"][0].center)
    step(ed, 1.0)
    before = ed.gun_preview.total_shots
    assert before > 0
    ed.set_gun("fire_rate", 20.0)
    step(ed, 0.05)
    assert ed.gun_preview.total_shots < before                                      # started over
    step(ed, 1.0)
    assert ed.gun_preview.total_shots >= 10                                         # a magazine of 12 at 20 a second
    assert ed.level.guns[0].fire_rate == 20.0 and gun.name == ed.level.guns[0].name


def test_selecting_another_gun_builds_that_one_and_leaving_the_section_stops_it(ed):
    first = add_gun(ed)
    second = add_gun(ed)
    step(ed, 0.1)
    assert ed.gun_preview.gun_name == second.name
    click(ed, ed.gun_rows()[0][0][0].center)
    step(ed, 0.1)
    assert ed.gun_preview.gun_name == first.name
    ed.do("guns")
    shots = ed.gun_preview.total_shots
    step(ed, 0.5)
    assert ed.gun_preview.total_shots == shots


def test_the_preview_with_effects_draws_in_the_editor_even_when_the_gun_has_an_ammo_and_a_missing_effect(ed):
    gun = add_gun(ed)
    ed.level.effects = [Effect("Puff")]
    ed.level.lights = [Light("Flash")]
    ed.set_gun("muzzle", "Puff")
    ed.set_gun("flash", "Flash")
    ed.set_gun("ammo", "Gone")                                                      # an ammo type that does not exist
    click(ed, controls(ed)["continuous"][0].center)
    step(ed, 0.5)
    ed.draw(pygame.display.get_surface())
    assert ed.gun_preview.session.particles.count() > 0 or ed.gun_preview.total_shots >= 1


def test_the_controls_wrap_onto_a_second_row_on_a_narrow_card(ed):
    add_gun(ed)
    card = ed.guns_card_rect()
    wide, _ = ed.gun_controls(card)
    narrow, below = ed.gun_controls(pygame.Rect(card.x, card.y, 200, 112))
    assert len({rect.centery for rect, _label in narrow.values()}) >= 2 and below > max(r.bottom for r, _l in narrow.values())
    assert len({rect.centery for rect, _label in wide.values()}) == 1


# ------------------------------------------------------------------ the offset override rows

def test_an_override_row_appears_only_once_an_effect_is_chosen_and_offsets_only_while_it_is_on(ed):
    ed.level.effects = [Effect("Puff")]
    gun = add_gun(ed)
    assert "muzzle_override" not in keys(ed)
    choose(ed, "muzzle", "Puff")
    assert "muzzle_override" in keys(ed) and "muzzle_offset_x" not in keys(ed)
    choose(ed, "muzzle_override", True)
    assert [k for k in keys(ed) if k.startswith("muzzle_offset")] == ["muzzle_offset_x", "muzzle_offset_y", "muzzle_offset_z"]
    click(ed, row(ed, "muzzle_offset_x").plus.center)
    click(ed, row(ed, "muzzle_offset_z").minus.center)
    assert (ed.level.guns[0].muzzle_offset_x, ed.level.guns[0].muzzle_offset_z) == (0.05, -0.05)
    choose(ed, "muzzle_override", False)
    assert "muzzle_offset_x" not in keys(ed)
    assert gun.name == ed.level.guns[0].name


def test_ammo_trails_and_items_have_the_same_override_rows(ed):
    ed.level.effects = [Effect("Smoke")]
    ed.do("guns")
    click(ed, ed.ammo_rows()[1].center)
    assert "trail_override" not in keys(ed)
    choose(ed, "trail", "Smoke")
    choose(ed, "trail_override", True)
    assert [k for k in keys(ed) if k.startswith("trail_offset")] == ["trail_offset_x", "trail_offset_y", "trail_offset_z"]
    click(ed, row(ed, "trail_offset_z").plus.center)
    assert ed.level.ammo_types[0].trail_offset_z == 0.05 and ed.level.ammo_types[0].trail_override is True
    ed.do("tool:entity")
    ed.map_click((4, 4), 1)
    assert "emits_override" not in keys(ed)
    choose(ed, "emits", "Smoke")
    choose(ed, "emits_override", True)
    assert [k for k in keys(ed) if k.startswith("emits_offset")] == ["emits_offset_x", "emits_offset_y", "emits_offset_z"]
    click(ed, row(ed, "emits_offset_x").plus.center)
    assert ed.level.entities[0].emits_offset_x == 0.05


def test_a_prefab_carries_its_override_to_its_copies(ed):
    ed.level.effects = [Effect("Smoke")]
    ed.level.prefabs = [Entity(0, 0, name="Vent", emits="Smoke")]
    ed.level.entities = [Entity(3.5, 3.5, prefab="Vent")]
    ed.do("prefabs")
    ed.prefab_selected = 0
    choose(ed, "emits_override", True)
    click(ed, row(ed, "emits_offset_x").plus.center)
    assert (ed.level.entities[0].emits_override, ed.level.entities[0].emits_offset_x) == (True, 0.05)


# ------------------------------------------------------------------ where the bullets come from

def fire_from(gun, angle=0.0, pitch=0.0, effects=(), lights=()):
    """Fire `gun` once from a player at (4, 4) facing `angle`; returns the session so bullets and effects can be read."""
    import random
    from game import Game, Inputs
    from session import LocalSession
    from world import World
    level = Level.blank(12, 12)
    level.guns, level.effects, level.lights = [gun], list(effects), list(lights)
    session = LocalSession(Game(level, World(level, 16), random.Random(1)))
    body = session.me.body
    body.x, body.y, body.angle, body.pitch = 4.0, 4.0, angle, pitch
    session.me.inventory.give_gun(gun)
    session.step(Inputs(fire=True), 0.001)
    return session


def test_bullets_come_from_the_usual_muzzle_point_unless_the_gun_says_otherwise():
    session = fire_from(Gun("G", mode="auto"))
    bullet, body = session.game.projectiles.bullets[0], session.me.body
    assert (bullet.x, bullet.y) == pytest.approx((body.x + 0.25, body.y), abs=0.03)      # (it has flown a hair already)
    assert bullet.z == pytest.approx(body.eye_z - 0.03, abs=0.01)


def test_the_bullet_offset_is_ahead_right_and_up_of_the_aim():
    gun = Gun("G", mode="auto", bullet_offset_x=0.5, bullet_offset_y=0.3, bullet_offset_z=-0.25)
    plain = fire_from(Gun("G", mode="auto"))
    shifted = fire_from(gun)
    a, b = plain.game.projectiles.bullets[0], shifted.game.projectiles.bullets[0]
    assert (b.x - a.x, b.y - a.y, b.z - a.z) == pytest.approx((0.5, 0.3, -0.25), abs=0.01)    # facing +x: right is +y
    assert (b.vx, b.vy, b.vz) == pytest.approx((a.vx, a.vy, a.vz))                              # still flies along the aim
    turned = fire_from(gun, angle=math.pi / 2).game.projectiles.bullets[0]                     # facing +y: ahead is +y, right is -x
    plain_turned = fire_from(Gun("G", mode="auto"), angle=math.pi / 2).game.projectiles.bullets[0]
    assert (turned.x - plain_turned.x, turned.y - plain_turned.y) == pytest.approx((-0.3, 0.5), abs=0.01)


def test_every_pellet_of_a_shotgun_comes_from_the_offset_point():
    gun = Gun("S", mode="auto", shot="multi", pellets=5, spread=4.0, bullet_offset_y=0.4)
    bullets = fire_from(gun).game.projectiles.bullets
    assert len(bullets) == 5 and all(abs(b.y - 4.4) < 0.05 for b in bullets)


def test_the_muzzle_effect_and_flash_start_at_the_bullet_origin():
    gun = Gun("G", mode="auto", muzzle="Puff", flash="Flash", bullet_offset_x=0.5, bullet_offset_y=0.3, bullet_offset_z=-0.25)
    session = fire_from(gun, effects=[Effect("Puff", count=1, spread=0.0, speed=0.0, life=5.0, collide=False)],
                        lights=[Light("Flash", duration=1.0)])
    bullet = session.game.projectiles.bullets[0]
    puff, = session.particles.particles
    assert (puff.x, puff.y, puff.z) == pytest.approx((bullet.x, bullet.y, bullet.z), abs=0.03)
    flash, = session.lights.flashes
    assert tuple(flash[1:4]) == pytest.approx((bullet.x, bullet.y, bullet.z), abs=0.03)


def test_the_bullet_offset_survives_saving_and_bad_values_are_clamped():
    import json
    from mapfile import level_text, parse_level
    level = Level.blank(6, 6)
    level.guns = [Gun("G", bullet_offset_x=0.5, bullet_offset_y=-0.3, bullet_offset_z=0.1)]
    assert parse_level(json.loads(level_text(level))).guns == level.guns
    bad = Gun.from_dict({"bullet_offset_x": 99, "bullet_offset_y": "right"})
    assert bad.bullet_offset_x == 5.0 and bad.bullet_offset_y == 0.0


def test_the_live_preview_fires_from_the_offset(textures):
    gun = Gun("Pistol", mode="auto", fire_rate=2.0, bullet_offset_y=0.4, bullet_offset_z=-0.2)
    preview = GunPreview(textures)
    preview.build(level_with(gun), "Pistol")
    preview.update(DT, True)
    body = preview.session.me.body
    bullet = preview.session.game.projectiles.bullets[0]
    assert bullet.y == pytest.approx(body.y + 0.4, abs=0.02) and bullet.z == pytest.approx(body.eye_z - 0.23, abs=0.02)


def test_the_pane_has_rows_for_where_the_bullets_come_from(ed):
    gun = add_gun(ed)
    assert keys(ed)[keys(ed).index("spread") + 1:keys(ed).index("spread") + 4] == [
        "bullet_offset_x", "bullet_offset_y", "bullet_offset_z"]
    click(ed, row(ed, "bullet_offset_y").plus.center)
    click(ed, row(ed, "bullet_offset_z").minus.center)
    shown = ed.level.guns[0]
    assert (shown.bullet_offset_y, shown.bullet_offset_z) == (0.05, -0.05) and gun.name == shown.name
