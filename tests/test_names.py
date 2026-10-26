"""Player names: set on the home screen, sent to the host, and drawn over the other players' heads."""
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pygame
import pytest

import net
import physics
from constants import HEIGHT, PLAYER_HEIGHT, WIDTH
from game import MAX_PLAYER_NAME, NO_TEAM, clean_name, same_team, shown_name
from home import Home
from hud import NAME_OPPONENT, NAME_TEAMMATE, draw_names
from mapfile import Level
from menu import GameSettings
from renderer import Renderer
from session import ClientSession, HostSession
from test_session import FIRST_CHARACTER, make_world, new_game, run
from world import World



@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


# ------------------------------------------------------------------ the names themselves

def test_names_are_trimmed_printable_and_short_and_a_player_without_one_is_numbered():
    assert clean_name("  Ace\n\t ") == "Ace" and clean_name(42) == "" and clean_name(None) == ""
    assert clean_name("x" * 40) == "x" * MAX_PLAYER_NAME
    assert shown_name("Ace", 3) == "Ace" and shown_name("", 0) == "Player 1"


def test_teammates_share_a_team_and_players_on_no_team_have_none():
    assert same_team(1, 1) and not same_team(1, 2)
    assert not same_team(NO_TEAM, NO_TEAM)                             # no teams yet: everyone is an opponent


def test_the_game_labels_every_other_player_above_their_head():
    game = new_game()
    for pid in (0, 1, 2):
        game.add_player(pid)
    game.players[1].name, game.players[2].team = "Ace", 2
    labels = {name: (x, y, z, team) for x, y, z, name, team in game.labels(viewer=0)}
    assert set(labels) == {"Ace", "Player 3"}                          # not the viewer's own
    body = game.players[1].body
    assert labels["Ace"][:3] == (body.x, body.y, body.z + PLAYER_HEIGHT) and labels["Player 3"][3] == 2


# ------------------------------------------------------------------ on the screen

def flat_textures():
    textures = np.full((16, 32, 32, 4), 90, np.uint8)
    textures[..., 3] = 255
    return textures


def test_a_point_projects_where_the_renderer_draws_it():
    renderer = Renderer(flat_textures())
    for pitch in (0.0, math.radians(3), -0.4):                         # level, sheared and rotated
        viewer = physics.Player(2.5, 4.5, 0.0, 0.0, pitch=pitch)
        column, row, depth = renderer.project(viewer, 6.5, 4.5, viewer.eye_z)
        assert column == pytest.approx(WIDTH / 2)
        assert row == pytest.approx(renderer.horizon(viewer) if abs(pitch) < math.radians(5) else
                                    HEIGHT / 2 + math.tan(pitch) * renderer.focal, abs=0.5)
    assert renderer.project(physics.Player(2.5, 4.5, 0.0, 0.0), 1.5, 4.5, 0.5) is None     # behind


def name_pixels(picture, color):
    rgb = pygame.surfarray.array3d(picture).astype(int)
    return (np.abs(rgb - np.array(color)) < 30).all(axis=2)


def scene(walls=()):
    level = Level.blank(16, 9)
    for x, y in walls:
        level.walls[y][x] = 1
    world = World(level, 16)
    renderer = Renderer(flat_textures())
    viewer = physics.Player(2.5, 4.5, 0.0, 0.0)
    renderer.draw(world, viewer)
    return renderer, viewer


def labelled(renderer, viewer, labels, team=NO_TEAM):
    picture = renderer.surface.copy()
    draw_names(picture, pygame.font.Font(None, 18), renderer, viewer, labels, team)
    return picture


def test_a_name_floats_above_the_head_red_for_an_opponent_and_white_for_a_teammate():
    renderer, viewer = scene()
    label = [(8.5, 4.5, PLAYER_HEIGHT, "Ace", 1)]
    red = name_pixels(labelled(renderer, viewer, label, team=NO_TEAM), NAME_OPPONENT)
    assert red.sum() > 20 and not name_pixels(labelled(renderer, viewer, label, team=NO_TEAM), NAME_TEAMMATE).any()
    columns, rows = np.nonzero(red)
    head_row = renderer.project(viewer, 8.5, 4.5, PLAYER_HEIGHT)[1]
    assert rows.max() < head_row and abs(columns.mean() - WIDTH / 2) < 6          # above the head, over it
    assert name_pixels(labelled(renderer, viewer, label, team=1), NAME_TEAMMATE).sum() > 20


def test_a_name_is_hidden_behind_a_wall_and_far_away():
    renderer, viewer = scene(walls=[(5, y) for y in range(1, 8)])     # a wall between us and them
    assert not name_pixels(labelled(renderer, viewer, [(8.5, 4.5, PLAYER_HEIGHT, "Ace", 1)]), NAME_OPPONENT).any()
    renderer, viewer = scene()
    far = Level.blank(60, 9)
    renderer.draw(World(far, 16), viewer)
    assert not name_pixels(labelled(renderer, viewer, [(55.5, 4.5, PLAYER_HEIGHT, "Ace", 1)]), NAME_OPPONENT).any()


# ------------------------------------------------------------------ over the network

def test_names_go_from_the_joiners_to_the_host_and_back_out_to_everyone():
    host = HostSession(new_game(), net.Host("pw", port=0), name="Hosty")
    joiners = [ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER, name=n)
               for n in ("Ace", "")]
    try:
        run([host, *joiners], until=lambda: all(j.ready for j in joiners))
        run([host, *joiners], until=lambda: all(len(j.labels()) == 2 for j in joiners)
            and host.game.players[1].name == "Ace")
        assert sorted(name for *_, name, _team in host.labels()) == ["Ace", "Player 3"]
        assert sorted(name for *_, name, _team in joiners[0].labels()) == ["Hosty", "Player 3"]
        assert sorted(name for *_, name, _team in joiners[1].labels()) == ["Ace", "Hosty"]
        assert joiners[0].me.name == "Ace" and all(team == NO_TEAM for *_, team in joiners[0].labels())
    finally:
        for s in (*joiners, host):
            s.close()


# ------------------------------------------------------------------ the home screen

def test_the_name_is_typed_on_the_home_screen_and_kept(tmp_path):
    settings = GameSettings()
    home = Home(settings, str(tmp_path))
    box = next(i for i in home.items((1280, 900)) if i.action == "input:name")
    home.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=box.rect.center, button=1), (1280, 900))
    for char in "  Ace of Spades and more ":
        home.handle(pygame.event.Event(pygame.KEYDOWN, key=0, mod=0, unicode=char), (1280, 900))
    assert home.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""), (1280, 900)) == "settings"
    assert settings.name == "Ace of Spades"            # typing stops at 16 characters, and the spaces are trimmed
    path = str(tmp_path / "game.json")
    settings.save(path)
    assert GameSettings.load(path).name == settings.name
