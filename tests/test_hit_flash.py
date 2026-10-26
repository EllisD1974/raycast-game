"""Being hurt: the screen flashes red for the player hit, and the others see them flash red."""
import os
import random
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import game as game_module
import net
from game import HIT_FLASH, IDENTITY, Game, Inputs, character_sprite, hit_tint
from hud import draw_hurt, hurt_flash
from mapfile import Level
from session import LOCAL_ID, ClientSession, HostSession, LocalSession
from test_session import FIRST_CHARACTER, make_world, new_game, run

DT = 1 / 60


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


# ------------------------------------------------------------------ in the game

def test_damage_is_reported_once_and_the_player_shows_hurt_for_a_moment():
    game = new_game()
    game.add_player(1)
    game.add_player(2)
    game.hurt(1, 10.0)
    game.hurt(1, 5.0)
    game.hurt(2, 0.0)                                                  # (no damage: no flash)
    assert game.players[1].hit == HIT_FLASH and game.players[2].hit == 0.0
    assert game.take_hurts() == {1: 15.0} and game.take_hurts() == {}
    game.hurt(2, 7.0)
    events = game.tick({}, DT)
    assert events[2].hurt == 7.0 and events[1].hurt == 0.0
    for _ in range(round(HIT_FLASH / DT) + 2):
        game.tick({}, DT)
    assert game.players[2].hit == 0.0                                  # the flash runs out


def test_a_hit_that_knocks_a_player_out_still_counts():
    game = new_game()
    game.add_player(1)
    game.hurt(1, 500.0)
    assert game.players[1].stats.health == game.players[1].stats.max_health      # back in, at full health
    assert game.take_hurts() == {1: 500.0} and game.players[1].hit == HIT_FLASH


def test_a_hurt_player_is_drawn_red_fading_back_to_their_own_colors():
    body = game_module.spawn(Level.blank(8, 8), make_world(Level.blank(8, 8)))
    assert len(character_sprite(body, FIRST_CHARACTER, 1)) == 5         # not hurt: plain
    red = character_sprite(body, FIRST_CHARACTER, 1, hit=HIT_FLASH)
    assert red[8] == pytest.approx(game_module.HIT_TINT)
    half = hit_tint(HIT_FLASH / 2)
    assert IDENTITY[4] > half[4] > game_module.HIT_TINT[4]             # green: on its way back
    assert hit_tint(0.0) is None


def test_the_others_see_a_hurt_player_red_but_not_themselves():
    game = new_game()
    for pid in (1, 2):
        game.add_player(pid)
    game.hurt(2, 10.0)
    seen_by_1 = {sprite[4]: sprite for sprite in game.player_sprites(viewer=1)}
    assert len(seen_by_1) == 1 and len(next(iter(seen_by_1.values()))) == 9          # player 2, tinted
    assert all(len(sprite) == 5 for sprite in game.player_sprites(viewer=2))         # player 1, plain


# ------------------------------------------------------------------ on the screen

def test_the_screen_flash_comes_with_a_hit_is_stronger_for_more_and_fades():
    small, big = hurt_flash(0.0, 5.0, 0.0), hurt_flash(0.0, 40.0, 0.0)
    assert 0.0 < small < big <= 1.0
    flash = big
    for _ in range(30):
        flash = hurt_flash(flash, 0.0, DT)
    assert flash == 0.0                                                # gone within half a second
    picture = pygame.Surface((64, 36))
    picture.fill((100, 100, 100))
    draw_hurt(picture, 1.0)
    r, g, b = picture.get_at((10, 10))[:3]
    assert r > 100 > g and g == b and g > 40                           # redder, but the picture still shows
    plain = pygame.Surface((64, 36))
    plain.fill((100, 100, 100))
    draw_hurt(plain, 0.0)
    assert tuple(plain.get_at((10, 10))[:3]) == (100, 100, 100)


def test_playing_alone_the_step_reports_the_damage():
    level = Level.blank(10, 10)
    session = LocalSession(Game(level, make_world(level), random.Random(1)))
    session.game.hurt(LOCAL_ID, 12.0)
    assert session.step(Inputs(), DT).hurt == 12.0
    assert session.step(Inputs(), DT).hurt == 0.0


# ------------------------------------------------------------------ over the network

def test_a_joiner_feels_its_hits_and_sees_the_host_flash_red():
    host = HostSession(new_game(), net.Host("pw", port=0))
    client = ClientSession(net.Client("127.0.0.1", host.host.port, "pw"), make_world, FIRST_CHARACTER)
    try:
        run([host, client], until=lambda: client.ready)
        host.game.hurt(1, 9.0)                                         # the joiner is hit
        felt = 0.0
        end = time.monotonic() + 3.0
        while felt == 0.0 and time.monotonic() < end:                 # (what the joiner's own steps report)
            host.step(Inputs(), DT)
            felt += client.step(Inputs(), DT).hurt
            time.sleep(0.005)
        assert felt == 9.0
        host.game.hurt(0, 4.0)                                         # the host is hit
        assert host.step(Inputs(), DT).hurt == 4.0
        run([host, client], until=lambda: any(len(s) == 9 and s[4] >= FIRST_CHARACTER for s in client.sprites()))
        run([host, client], until=lambda: all(len(s) != 9 for s in client.sprites() if s[3] > 0.5),
            timeout=2.0)                                               # and back to normal after a moment
    finally:
        host.close()
        client.close()
