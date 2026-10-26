"""Importing prefabs, lights, effects, guns and ammo types from another map."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import map_editor
from mapfile import (MAX_NAME, AmmoType, Effect, Entity, Gun, Level, Light, import_things, save_level, things_named,
                     with_needs)


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1920, 1009), pygame.RESIZABLE)
    yield
    pygame.quit()


def armory():
    """A map with a rocket launcher (its ammo, effects and lights), a torch prefab, and a spare light."""
    level = Level.blank(8, 8)
    level.lights = [Light("Fire", r=255, g=120, b=40), Light("Glow", intensity=0.5), Light("Spare")]
    level.effects = [Effect("Smoke", light="Glow"), Effect("Sparks")]
    level.ammo_types = [AmmoType("Rocket", trail="Smoke", light="Fire", explosion_effects=("Smoke", "Sparks"),
                                 explosion_lights=("Fire",), explodes=True)]
    level.guns = [Gun("Launcher", ammo="Rocket", muzzle="Sparks", flash="Fire")]
    level.prefabs = [Entity(0.0, 0.0, name="Torch", light="Fire", emits="Smoke", mode="scenery", effect="none")]
    return level


def names(level, kind):
    return sorted(things_named(level, kind))


# ------------------------------------------------------------------ what comes with what

def test_a_picked_thing_brings_everything_it_uses():
    source = armory()
    assert with_needs(source, {("prefabs", "Torch")}) == {("prefabs", "Torch"), ("lights", "Fire"),
                                                         ("effects", "Smoke"), ("lights", "Glow")}
    gun = with_needs(source, {("guns", "Launcher")})
    assert {("ammo_types", "Rocket"), ("effects", "Sparks"), ("effects", "Smoke"), ("lights", "Glow")} <= gun
    assert ("lights", "Spare") not in gun


def test_importing_into_a_map_without_them_adds_them_all():
    level, source = Level.blank(8, 8), armory()
    result = import_things(level, source, {("guns", "Launcher"), ("prefabs", "Torch")})
    assert names(level, "guns") == ["Launcher"] and names(level, "prefabs") == ["Torch"]
    assert names(level, "lights") == ["Fire", "Glow"] and names(level, "effects") == ["Smoke", "Sparks"]
    assert level.ammo_types[0] == source.ammo_types[0] and level.ammo_types[0] is not source.ammo_types[0]
    assert result.needed == 5 and "Imported 7 things" in result.summary()


def test_what_this_map_already_has_the_same_is_left_alone():
    level, source = armory(), armory()
    result = import_things(level, source, {("guns", "Launcher")}, "copy")
    assert result.same and not result.renamed and len(level.guns) == 1
    assert "nothing" not in result.summary() and "already here" in result.summary()


def taken_level():
    """A map with its own, different light called Fire (and a gun that uses it)."""
    level = Level.blank(8, 8)
    level.lights = [Light("Fire", r=10, g=10, b=255)]
    level.guns = [Gun("Pistol", flash="Fire")]
    return level


def test_a_taken_name_can_keep_this_maps_thing():
    level = taken_level()
    import_things(level, armory(), {("prefabs", "Torch")}, "keep")
    assert level.light_named("Fire").b == 255                          # still the blue one
    assert level.prefab_named("Torch").light == "Fire"                 # and the torch uses it


def test_a_taken_name_can_be_replaced_and_what_used_it_follows():
    level = taken_level()
    level.prefabs = [Entity(0.0, 0.0, name="Torch", tile=3)]
    level.entities = [Entity(2.5, 2.5, prefab="Torch", tile=3)]
    import_things(level, armory(), {("prefabs", "Torch")}, "replace")
    assert level.light_named("Fire").r == 255 and names(level, "lights") == ["Fire", "Glow"]
    assert level.guns[0].flash == "Fire"                               # (the pistol now flashes the imported light)
    assert level.entities[0].light == "Fire" and level.entities[0].emits == "Smoke"   # the placed copy follows


def test_a_taken_name_can_come_in_as_a_copy_and_the_imported_things_use_the_copy():
    level = taken_level()
    result = import_things(level, armory(), {("guns", "Launcher")}, "copy")
    assert names(level, "lights") == ["Fire", "Fire 2", "Glow"] and result.renamed == {("lights", "Fire"): "Fire 2"}
    assert level.light_named("Fire").b == 255 and level.guns[0].flash == "Fire"   # ours: untouched
    launcher = next(g for g in level.guns if g.name == "Launcher")
    rocket = level.ammo_types[0]
    assert launcher.flash == "Fire 2" and rocket.light == "Fire 2" and rocket.explosion_lights == ("Fire 2",)
    again = import_things(level, armory(), {("guns", "Launcher")}, "copy")
    assert names(level, "lights") == ["Fire", "Fire 2", "Glow"] and len(level.guns) == 2   # no Fire 3, no 2nd gun
    assert not again.renamed and again.same


def test_a_copys_new_name_fits_the_name_limit():
    long_name = "L" * MAX_NAME
    level, source = Level.blank(8, 8), Level.blank(8, 8)
    level.lights, source.lights = [Light(long_name, r=1)], [Light(long_name, r=2)]
    import_things(level, source, {("lights", long_name)}, "copy")
    assert names(level, "lights") == sorted([long_name, "L" * (MAX_NAME - 2) + " 2"])


# ------------------------------------------------------------------ the editor's Import dialog

@pytest.fixture
def ed(tmp_path):
    save_level(str(tmp_path / "armory.json"), armory())
    save_level(str(tmp_path / "empty.json"), Level.blank(8, 8))
    (tmp_path / "broken.json").write_text("{ not json")
    editor = map_editor.Editor(str(tmp_path / "mine.json"))
    editor.level = taken_level()
    editor.save()
    editor.show_legend = False
    editor.draw(pygame.display.get_surface())
    return editor


def row(ed, label):
    """The screen point of a row (a map, a heading or a thing) whose text starts with `label`."""
    _box, _listing, shown, _buttons = ed.importing.rects(ed._size())
    for rect, (kind, value) in shown:
        text = {"map": lambda v: v[:-5], "kind": lambda v: map_editor.IMPORT_KINDS[v], "thing": lambda v: v[1]}[kind](value)
        if text == label:
            return rect.center
    raise AssertionError(f"no row {label}")


def press(ed, pos):
    ed.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    ed.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))


def button(ed, name):
    return ed.importing.rects(ed._size())[3][name].center


def test_the_import_dialog_picks_a_map_ticks_things_and_imports_them_in_one_undo_step(ed):
    ed.do("import")
    assert [value for _kind, value in ed.importing.rows()] == ["armory.json", "broken.json", "empty.json"]   # not mine
    ed.draw(pygame.display.get_surface())
    press(ed, row(ed, "broken"))
    assert ed.importing.source is None and "broken.json" in ed.importing.error
    press(ed, row(ed, "empty"))
    assert "has no prefabs" in ed.importing.error
    press(ed, button(ed, "back"))
    press(ed, row(ed, "armory"))
    ed.draw(pygame.display.get_surface())
    press(ed, row(ed, "Lights"))                                       # a heading ticks its whole group
    assert ed.importing.chosen == {("lights", "Fire"), ("lights", "Glow"), ("lights", "Spare")}
    press(ed, row(ed, "Lights"))                                       # ... and again unticks it
    press(ed, row(ed, "Launcher"))
    assert ed.importing.chosen == {("guns", "Launcher")} and ed.importing.state("lights", "Fire") == "taken"
    press(ed, button(ed, "taken:replace"))
    ed.draw(pygame.display.get_surface())
    press(ed, button(ed, "import"))
    assert ed.importing is None and "Imported" in ed.message
    assert names(ed.level, "guns") == ["Launcher", "Pistol"] and ed.level.light_named("Fire").r == 255
    ed.do("undo")
    assert names(ed.level, "guns") == ["Pistol"] and ed.level.light_named("Fire").b == 255


def test_what_comes_with_a_ticked_thing_is_marked_and_says_what_brings_it(ed):
    ed.do("import")
    press(ed, row(ed, "armory"))
    assert ed.importing.coming() == {}
    press(ed, row(ed, "Torch"))
    assert ed.importing.coming() == {("lights", "Fire"): "Torch", ("lights", "Glow"): "Torch",
                                     ("effects", "Smoke"): "Torch"}
    ed.draw(pygame.display.get_surface())                              # (blue boxes, "comes with Torch")
    press(ed, row(ed, "Fire"))                                         # ticking one makes it ticked, not coming
    assert ("lights", "Fire") in ed.importing.chosen and ("lights", "Fire") not in ed.importing.coming()
    press(ed, row(ed, "Torch"))                                        # unticking the torch: Fire stays, Glow goes
    assert ed.importing.coming() == {} and ed.importing.chosen == {("lights", "Fire")}


def test_each_thing_shows_its_picture_and_a_light_its_color(ed):
    ed.do("import")
    press(ed, row(ed, "armory"))
    dialog = ed.importing
    for kind, name in (("prefabs", "Torch"), ("guns", "Launcher"), ("ammo_types", "Rocket"), ("effects", "Smoke")):
        picture = dialog.icon(kind, name)
        assert picture is not None and picture.get_size() == (map_editor.IMPORT_ICON,) * 2
        assert pygame.mask.from_surface(picture).count() > 0          # something is drawn in it
    fire = dialog.icon("lights", "Fire")                               # r 255, g 120, b 40: an orange swatch
    assert tuple(fire.get_at((10, 10)))[:3] == (255, 120, 40)
    assert dialog.icon("lights", "Fire") is fire                       # (made once)
    ed.draw(pygame.display.get_surface())
    bare = map_editor.ImportDialog(dialog.folder, dialog.names, ed.level, ed.font, ed.small)   # no atlas given
    bare.pick("armory.json")
    assert bare.icon("prefabs", "Torch") is None and bare.icon("lights", "Fire") is not None


def test_escape_backs_out_of_the_import_dialog_and_importing_nothing_says_so(ed):
    ed.do("import")
    press(ed, row(ed, "armory"))
    press(ed, button(ed, "import"))
    assert ed.importing is not None and "Tick something" in ed.importing.error
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert ed.importing.source is None                                 # back to the maps
    ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert ed.importing is None and ed.message == "Nothing imported"


def test_import_says_so_when_there_is_no_other_map(tmp_path):
    editor = map_editor.Editor(str(tmp_path / "alone.json"))
    editor.save()
    editor.do("import")
    assert editor.importing is None and "no other maps" in editor.message
