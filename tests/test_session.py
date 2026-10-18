"""A host and joiners playing one game over real sockets on this machine, without a window."""
import os
import random
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import pytest

import net
import physics
import session
from character import SHIRTS, character_tiles
from game import Game, Inputs
from mapfile import Entity, Gun, Level
from session import ClientSession, HostSession, LocalSession
from world import World

DT = 1 / 60
FIRST_CHARACTER = 16


def make_world(level):
    return World(level, 16)


def new_game(*entities, guns=()):
    level = Level.blank(12, 12)
    level.entities = list(entities)
    level.guns = list(guns)
    return Game(level, make_world(level), random.Random(1), character_tile=FIRST_CHARACTER)


@pytest.fixture
def host_session():
    session = HostSession(new_game(), net.Host("pw", port=0))
    yield session
    session.close()


def join(host_session, password="pw"):
    session = ClientSession(net.Client("127.0.0.1", host_session.host.port, password), make_world, FIRST_CHARACTER)
    run([host_session, session], until=lambda: session.ready or session.ended)
    return session


def run(sessions, until, inputs=None, timeout=3.0):
    """Step every session (host first) like frames until `until()`; `inputs` maps a session to its Inputs."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for s in sessions:
            s.step((inputs or {}).get(s, Inputs()), DT)
        if until():
            return
        time.sleep(0.005)
    raise AssertionError("timed out")


def test_a_joiner_gets_the_map_a_player_and_snapshots(host_session):
    client = join(host_session)
    assert client.ready and client.id == 1
    assert set(host_session.game.players) == {0, 1}
    assert (client.level.width, client.level.height) == (12, 12)
    assert client.me.body.x == pytest.approx(host_session.game.players[1].body.x)


def test_a_wrong_password_never_joins(host_session):
    client = join(host_session, "wrong")
    assert client.ended == "wrong password" and not client.ready
    assert set(host_session.game.players) == {0}


def test_the_joiners_keys_move_them_on_the_host(host_session):
    client = join(host_session)
    start_x = host_session.game.players[1].body.x
    run([host_session, client], until=lambda: host_session.game.players[1].body.x > start_x + 1.0,
        inputs={client: Inputs(forward=1)})
    assert host_session.game.players[0].body.x == pytest.approx(start_x)       # the host did not move


def test_each_sees_the_other_as_a_character(host_session):
    client = join(host_session)
    run([host_session, client], until=lambda: client.history)
    assert [s[4] for s in client.sprites() if s[4] >= FIRST_CHARACTER] == [FIRST_CHARACTER]    # the host: id 0
    assert all(s[3] == pytest.approx(0.8) for s in client.sprites() if s[4] >= FIRST_CHARACTER)
    seen_by_host = [s for s in host_session.sprites() if s[4] >= FIRST_CHARACTER]
    assert [s[4] for s in seen_by_host] == [FIRST_CHARACTER + 1]
    assert seen_by_host[0][:2] == (host_session.game.players[1].body.x, host_session.game.players[1].body.y)


# ------------------------------------------------------------------ prediction

def test_the_joiner_moves_before_the_host_has_answered(host_session):
    client = join(host_session)
    start = client.me.body.x
    for _ in range(10):
        client.step(Inputs(forward=1), DT)                  # (the host is not stepped at all)
    assert client.me.body.x > start + 0.3
    assert host_session.game.players[1].body.x == pytest.approx(start)


def test_prediction_and_the_host_end_up_in_the_same_place(host_session):
    client = join(host_session)
    moves = {client: Inputs(forward=1, strafe=1, turn=0.01, sprint=True)}
    run([host_session, client], until=lambda: False if client.seq < 90 else True, inputs=moves)
    run([host_session, client], until=lambda: client.seq > 150)             # then stand still
    for _ in range(10):                                                      # let the last snapshot arrive
        run([host_session, client], until=lambda: True)
    theirs, ours = host_session.game.players[1].body, client.me.body
    assert (ours.x, ours.y, ours.angle) == pytest.approx((theirs.x, theirs.y, theirs.angle), abs=1e-6)


def test_a_snapshot_pulls_the_joiner_to_where_the_host_says(host_session):
    client = join(host_session)
    host_session.game.players[1].body.x += 3.0              # the host disagrees about where they are
    wanted = host_session.game.players[1].body.x
    run([host_session, client], until=lambda: abs(client.me.body.x - wanted) < 0.01)


def test_steps_the_host_has_not_carried_out_are_replayed_on_its_position(host_session):
    client = join(host_session)
    client.pending = []
    for _ in range(5):
        client.step(Inputs(forward=1), DT)                  # five steps the host has not seen
    sent = list(client.pending)
    snapshot = {"type": "state", "time": 1.0, "bullets": [], "items": "0" * len(client.items.items),
                "players": {"0": [1.5] * 3 + [0.0] * 4 + [0.0] * 3, "1": [1.5, 1.5, 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, True]},
                "you": {"body": [1.5, 1.5, 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, True], "score": 0, "health": 100.0,
                        "max_health": 100.0, "items": {}, "ammo": {}, "equipped": None, "guns": [],
                        "fired": 0, "picked": [], "ack": sent[1][0]}}     # it has done the first two
    client.apply_snapshot(snapshot)
    assert [step[0] for step in client.pending] == [step[0] for step in sent[2:]]
    twin = physics.Player(1.5, 1.5, 0.0)
    for _ in range(3):
        physics.step(client.world, twin, 1, 0, 0.0, False, DT, False)
    assert client.me.body.x == pytest.approx(twin.x)


def test_a_joiner_cannot_move_faster_than_real_time(host_session):
    client = join(host_session)
    start = host_session.game.players[1].body.x
    for seq in range(client.seq + 1, client.seq + 101):     # five seconds of steps, all at once
        client.client.send(net.HOST_ID, {"type": "input", "seq": seq, "dt": 0.05, "forward": 1})
    for _ in range(12):                                     # but only a fifth of a second passes
        host_session.step(Inputs(), DT)
        time.sleep(0.005)
    moved = host_session.game.players[1].body.x - start
    assert 0.1 < moved < 1.2


def test_a_long_step_counts_for_no_more_than_the_longest_allowed(host_session):
    client = join(host_session)
    start = host_session.game.players[1].body.x
    seq = client.seq + 1                                    # (the joiner's own first steps used the earlier ones)
    client.client.send(net.HOST_ID, {"type": "input", "seq": seq, "dt": 10.0, "forward": 1})
    run([host_session], until=lambda: host_session.acked[1] == seq)
    assert 0 < host_session.game.players[1].body.x - start < 0.3


def test_steps_that_are_old_repeated_or_malformed_are_ignored(host_session):
    client = join(host_session)
    send = lambda **m: client.client.send(net.HOST_ID, dict({"type": "input", "dt": 0.01, "forward": 1}, **m))
    base = client.seq + 10
    send(seq=base)
    send(seq=base)                                          # repeated
    send(seq=base - 5)                                      # older
    send(seq="x")
    send(seq=True)
    send(seq=6, dt="fast")
    send()                                                  # no seq at all
    run([host_session], until=lambda: host_session.acked[1] == base)
    for _ in range(5):
        host_session.step(Inputs(), DT)
        time.sleep(0.01)
    assert host_session.acked[1] == base and not host_session.queue[1]


# ------------------------------------------------------------------ interpolation

def test_interpolate_between_two_samples():
    samples = [(1.0, 0.0, 0.0, 0.0), (2.0, 10.0, 4.0, 1.0)]
    assert session.interpolate(samples, 1.5) == pytest.approx((5.0, 2.0, 0.5))
    assert session.interpolate(samples, 1.0) == pytest.approx((0.0, 0.0, 0.0))
    assert session.interpolate(samples, 0.0) == (0.0, 0.0, 0.0)             # before the first: hold it
    assert session.interpolate(samples, 9.0) == (10.0, 4.0, 1.0)            # after the last: hold it, no guessing


def test_interpolate_picks_the_right_pair():
    samples = [(0.0, 0.0, 0.0, 0.0), (1.0, 1.0, 0.0, 0.0), (2.0, 5.0, 0.0, 0.0)]
    assert session.interpolate(samples, 1.5)[0] == pytest.approx(3.0)
    assert session.interpolate([(1.0, 7.0, 7.0, 7.0)], 3.0) == (7.0, 7.0, 7.0)


def test_other_players_are_drawn_a_little_in_the_past(host_session):
    client = join(host_session)
    client.history = {5: [(1.0, 0.0, 2.0, 0.0), (2.0, 10.0, 2.0, 0.0)]}
    client.game_time = 1.5 + session.INTERP_DELAY
    drawn = [s for s in client.sprites() if s[4] == FIRST_CHARACTER + 5]
    assert len(drawn) == 1 and drawn[0][:3] == pytest.approx((5.0, 2.0, 0.0))


def test_bullets_carry_on_between_snapshots(host_session):
    client = join(host_session)
    client.bullets, client.bullet_age = [[1.0, 1.0, 0.5, 10.0, 0.0, 0.0, 0.1, 14, 1, "", ""]], 0.05
    bullet = [s for s in client.sprites() if s[4] == 14]
    assert bullet and bullet[0][:5] == pytest.approx((1.5, 1.0, 0.45, 0.1, 14))


def test_the_host_does_not_see_itself(host_session):
    assert host_session.sprites() == []


def test_a_joiners_shot_and_pickup_come_back_to_them():
    pistol = Gun("Pistol", mag_size=10, start_ammo=30)
    game = new_game(Entity(1.5, 1.5, effect="gun", gun="Pistol", mode="persistent"), guns=[pistol])
    host = HostSession(game, net.Host("pw", port=0))
    try:
        client = join(host)
        run([host, client], until=lambda: client.me.inventory.guns)       # (they spawn on the pickup)
        assert client.me.inventory.current().gun.name == "Pistol"
        run([host, client], until=lambda: client.me.inventory.current().mag < 10, inputs={client: Inputs(fire=True)})
        assert game.projectiles.bullets or client.bullets
    finally:
        host.close()


def test_a_pickup_gone_on_the_host_is_gone_for_the_joiner():
    game = new_game(Entity(5.5, 5.5, effect="score", amount=10, mode="once"))
    host = HostSession(game, net.Host("pw", port=0))
    try:
        client = join(host)
        game.players[0].body.x = game.players[0].body.y = 5.5
        run([host, client], until=lambda: client.me.stats.score == 0 and not client.items.items[0].present)
        assert game.players[0].stats.score == 10 and client.me.stats.score == 0
    finally:
        host.close()


def test_a_joiner_leaving_removes_their_player(host_session):
    client = join(host_session)
    client.close()
    run([host_session], until=lambda: set(host_session.game.players) == {0})


def test_the_joiner_is_told_when_the_host_goes(host_session):
    client = join(host_session)
    host_session.close()
    run([client], until=lambda: client.ended)
    assert client.ended


def test_junk_from_a_joiner_does_not_hurt_the_host(host_session):
    client = join(host_session)
    client.client.send(net.HOST_ID, {"type": "input", "forward": "lots", "turn": None, "equip": 5, "cycle": 1e99})
    client.client.send(net.HOST_ID, {"type": "nonsense"})
    for _ in range(20):
        host_session.step(Inputs(), DT)
        time.sleep(0.01)
    assert 1 in host_session.game.players


def test_character_pictures_are_see_through_around_the_figure():
    tiles = character_tiles()
    assert len(tiles) == len(SHIRTS)
    for tile in tiles:
        assert tile.get_at((0, 0)).a == 0 and tile.get_at((16, 8)).a == 255      # corner empty, head solid


def test_a_local_session_is_just_the_game():
    session = LocalSession(new_game())
    start = session.me.body.x
    for _ in range(30):
        session.step(Inputs(forward=1), DT)
    assert session.me.body.x > start and session.sprites() == []


def test_joiners_are_paced_by_real_time_not_the_capped_frame_time(host_session):
    client = join(host_session)
    seq = client.seq
    for i in range(1, 11):                                  # half a second of steps
        client.client.send(net.HOST_ID, {"type": "input", "seq": seq + i, "dt": 0.05, "forward": 0})
    deadline = time.monotonic() + 1
    while len(host_session.queue[1]) < 10 and time.monotonic() < deadline:
        host_session.step(Inputs(), 0.0, 0.0)
        time.sleep(0.005)
    host_session.credit[1] = 0.0
    host_session.step(Inputs(), 0.05, 0.5)                  # a slow frame: 0.5 s passed, the game ran 0.05
    assert host_session.acked[1] == seq + 10                # so all half second of steps was allowed


def test_the_joiner_measures_its_ping_and_the_host_its_backlog(host_session):
    client = join(host_session)
    run([host_session, client], until=lambda: client.ping > 0)
    assert 0 < client.ping < 1.0
    assert host_session.backlog() >= 0.0
    assert "ping" in client.status() and "hosting" in host_session.status()
