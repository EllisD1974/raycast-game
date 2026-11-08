"""Playing over a connection that loses and reorders what is sent unreliably, as the internet (and Steam's
unreliable messages) do. The connection here is in memory and seeded, so each test plays out the same."""
import json
import random

import pytest

import net
from game import Inputs
from mapfile import Entity, Gun
from session import ClientSession, HostSession
from test_session import DT, FIRST_CHARACTER, make_world, new_game, new_level


class End:
    """One end of an in-memory connection, with net.Connection's calls. Reliable messages arrive in order on the
    other end's next read; an unreliable one is lost with chance `loss`, or held back up to `max_delay` reads (so
    later ones can pass it)."""

    def __init__(self, rng, loss, max_delay):
        self.rng, self.loss, self.max_delay = rng, loss, max_delay
        self.peer = None
        self.inbox = []                     # [reads still to wait, message]
        self.closed = False
        self.reason = ""
        self.sent = []                      # (message, reliable) as queued, for the tests to look at

    def queue(self, message, reliable=True):
        message = json.loads(json.dumps(message))       # (only what json carries gets across)
        self.sent.append((message, reliable))
        if self.closed or self.peer.closed:
            return
        delay = 0
        if not reliable:
            if self.rng.random() < self.loss:
                return
            delay = self.rng.randint(0, self.max_delay)
        self.peer.inbox.append([delay, message])

    def flush(self):
        pass

    def read(self):
        out, kept = [], []
        for entry in self.inbox:
            if entry[0] <= 0:
                out.append(entry[1])
            else:
                entry[0] -= 1
                kept.append(entry)
        self.inbox = kept
        if self.peer.closed and not self.closed and not self.inbox:
            self.close("connection closed")
        return out

    def close(self, reason=""):
        if not self.closed:
            self.closed, self.reason = True, reason


class MemoryHost(net.BaseHost):
    def __init__(self, password, loss=0.0, max_delay=0, seed=1):
        super().__init__(password)
        self.rng, self.loss, self.max_delay = random.Random(seed), loss, max_delay
        self.arrivals = []

    def _incoming(self):
        new, self.arrivals = self.arrivals, []
        return new


class MemoryClient(net.BaseClient):
    def __init__(self, host, password):
        super().__init__(password)
        ours, theirs = (End(host.rng, host.loss, host.max_delay) for _ in range(2))
        ours.peer, theirs.peer = theirs, ours
        host.arrivals.append(theirs)
        self.end = ours

    def _establish(self):
        return self.end


def run(sessions, until, inputs=None, frames=2000):
    for _ in range(frames):
        for s in sessions:
            s.step((inputs or {}).get(s, Inputs()), DT)
        if until():
            return
    raise AssertionError("never happened")


def lossy_game(game=None, loss=0.4, max_delay=3):
    host = HostSession(game or new_game(), MemoryHost("pw", loss, max_delay))
    client = ClientSession(MemoryClient(host.host, "pw"), make_world, FIRST_CHARACTER)
    run([host, client], until=lambda: client.ready or client.ended)
    assert client.ready
    return host, client


def test_the_handshake_works_over_any_connection():
    host = HostSession(new_game(), MemoryHost("pw"))
    wrong = ClientSession(MemoryClient(host.host, "nope"), make_world, FIRST_CHARACTER)
    run([host, wrong], until=lambda: wrong.ended)
    assert wrong.ended == "wrong password"
    right = ClientSession(MemoryClient(host.host, "pw"), make_world, FIRST_CHARACTER)
    run([host, right], until=lambda: right.ready)
    assert right.id == 1 and set(host.game.players) == {0, 1}     # (no id is used up on the refused one)


def test_snapshots_and_steps_go_unreliably_and_the_rest_reliably():
    pistol = Gun("Pistol", mag_size=10, start_ammo=30)
    host, client = lossy_game(new_game(Entity(1.5, 1.5, effect="gun", gun="Pistol", mode="persistent"), guns=[pistol]),
                              loss=0.0, max_delay=0)
    run([host, client], until=lambda: client.me.inventory.guns)
    run([host, client], until=lambda: client.me.inventory.current().mag < 10, inputs={client: Inputs(fire=True)})
    kinds = {}
    for end in (client.client.end, client.client.end.peer):
        for message, reliable in end.sent:
            kinds.setdefault(message.get("type"), set()).add(reliable)
    assert kinds["state"] == {False} and kinds["inputs"] == {False}
    assert kinds["welcome"] == kinds["events"] == kinds["hello"] == {True}


def test_moving_through_a_lossy_connection_ends_where_the_host_says():
    host, client = lossy_game()
    moves = {client: Inputs(forward=1, strafe=1, turn=0.01, sprint=True)}
    run([host, client], until=lambda: client.seq >= 90, inputs=moves)
    run([host, client], until=lambda: client.seq >= 300)                    # then stand still a while
    theirs, ours = host.game.players[1].body, client.me.body
    assert theirs.x > 3.0                                                   # most steps got there
    assert (ours.x, ours.y, ours.angle) == pytest.approx((theirs.x, theirs.y, theirs.angle), abs=1e-6)


def test_repeated_steps_make_up_for_lost_packets():
    host, client = lossy_game(loss=0.3, max_delay=0)
    got = set()                                         # the joiner's steps the host has queued
    accept = host.accept

    def recording(peer, message):
        before = host.last_seq(peer)
        accept(peer, message)
        if host.last_seq(peer) != before:
            got.add(host.last_seq(peer))
    host.accept = recording
    first = client.seq + 1
    run([host, client], until=lambda: client.seq >= first + 199, inputs={client: Inputs(forward=1)})
    run([host, client], until=lambda: client.acked >= first + 199)
    sent = set(range(first, first + 200))
    assert len(sent - got) <= 3                         # each lost only if the four packets carrying it all are (0.3 ** 4)


def test_every_shot_reaches_the_joiner_however_many_snapshots_are_lost():
    rifle = Gun("Rifle", mode="auto", mag_size=30, start_ammo=30, fire_rate=20.0)
    host, client = lossy_game(new_game(Entity(1.5, 1.5, effect="gun", gun="Rifle", mode="persistent"), guns=[rifle]),
                              loss=0.6)
    run([host, client], until=lambda: client.me.inventory.guns)
    fired = 0
    for frame in range(400):
        trigger = host.game.players[1].inventory.current().mag > 20
        host.step(Inputs(), DT)
        fired += client.step(Inputs(fire=trigger), DT).fired
    shots_on_host = 30 - host.game.players[1].inventory.current().mag
    assert shots_on_host >= 10
    assert fired == shots_on_host


def test_a_late_snapshot_is_not_drawn_over_a_newer_one():
    host, client = lossy_game(loss=0.0, max_delay=0)
    run([host, client], until=lambda: client.snapshot_time and client.snapshot_time > 0.2)
    late = {"type": "state", "map": client.map_number, "time": client.snapshot_time - 0.1}
    assert not client.current(late)
    assert client.current(dict(late, time=client.snapshot_time + 0.1))


def test_a_snapshot_from_before_a_reload_is_not_drawn_on_the_new_map():
    host, client = lossy_game(loss=0.0, max_delay=0)
    run([host, client], until=lambda: client.snapshot_time and client.snapshot_time > 0.1)
    old_map = client.map_number
    level = new_level(20, 9)
    host.reload(level, make_world(level))
    run([host, client], until=lambda: client.loads == 2 and client.ready)
    assert client.map_number == old_map + 1
    assert not client.current({"type": "state", "map": old_map, "time": 1e9})


def test_a_reload_gets_through_a_lossy_connection():
    host, client = lossy_game()
    level = new_level(20, 9, Entity(5.5, 5.5))
    host.reload(level, make_world(level))
    run([host, client], until=lambda: client.loads == 2 and client.ready)
    assert client.level.width == 20 and len(client.items.items) == 1
    run([host, client], until=lambda: host.game.players[1].body.x > 3.0, inputs={client: Inputs(forward=1)})
