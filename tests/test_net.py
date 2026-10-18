"""The socket transport: joining a host with a password, passing messages, and the ways it fails."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import net
from net import HOST_ID, Client, Host


@pytest.fixture
def host():
    h = Host("secret", port=0)
    yield h
    h.close()


def pump(*nets, until, timeout=3.0):
    """Poll every transport until `until(events)` is true, where events maps each one to everything
    it has reported so far. Fails the test if that takes too long."""
    events = {n: [] for n in nets}
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for n in nets:
            events[n] += n.poll()
        if until(events):
            return events
        time.sleep(0.005)
    raise AssertionError(f"timed out; events so far: {list(events.values())}")


def join(host, password="secret"):
    client = Client("127.0.0.1", host.port, password)
    events = pump(host, client, until=lambda e: e[client] and (e[host] or e[client][-1][0] == "disconnect"))
    return client, events


def kinds(events):
    return [e[0] for e in events]


def test_right_password_joins(host):
    client, events = join(host)
    assert events[host] == [("connect", 1, None)]
    assert events[client] == [("connect", HOST_ID, {"id": 1})]
    assert client.connected
    client.close()


def test_wrong_password_is_refused(host):
    client, events = join(host, "nope")
    assert events[client] == [("disconnect", HOST_ID, "wrong password")]
    assert events[host] == []
    assert not host.joined


def test_password_is_not_sent_in_the_clear(host):
    sent = []
    real = net.Connection.queue
    net.Connection.queue = lambda self, m: (sent.append(m), real(self, m))[1]
    try:
        join(host)
    finally:
        net.Connection.queue = real
    assert "secret" not in repr(sent)


def test_messages_go_both_ways(host):
    client, _ = join(host)
    client.send(HOST_ID, {"type": "input", "forward": 1})
    events = pump(host, client, until=lambda e: e[host])
    assert events[host] == [("message", 1, {"type": "input", "forward": 1})]
    host.send(1, {"type": "state", "x": 2.5})
    events = pump(host, client, until=lambda e: e[client])
    assert events[client] == [("message", HOST_ID, {"type": "state", "x": 2.5})]
    client.close()


def test_broadcast_reaches_every_client(host):
    a, _ = join(host)
    b, _ = join(host)
    host.broadcast({"type": "hi"})
    events = pump(host, a, b, until=lambda e: e[a] and e[b])
    assert events[a] == events[b] == [("message", HOST_ID, {"type": "hi"})]
    a.close()
    b.close()


def test_clients_get_different_ids(host):
    a, _ = join(host)
    b, _ = join(host)
    assert (a.id, b.id) == (1, 2)
    a.close()
    b.close()


def test_big_and_back_to_back_messages_arrive_whole_and_in_order(host):
    client, _ = join(host)
    messages = [{"n": i, "pad": "x" * 50000} for i in range(5)]
    for m in messages:
        client.send(HOST_ID, m)
    events = pump(host, client, until=lambda e: len(e[host]) == 5)
    assert [m for _, _, m in events[host]] == messages
    client.close()


def test_host_sees_a_client_leave(host):
    client, _ = join(host)
    client.close()
    events = pump(host, until=lambda e: e[host])
    assert events[host] == [("disconnect", 1, "connection closed")]
    assert not host.joined


def test_client_sees_the_host_go(host):
    client, _ = join(host)
    host.close()
    events = pump(client, until=lambda e: e[client])
    assert kinds(events[client]) == ["disconnect"]


def test_kick(host):
    client, _ = join(host)
    host.kick(1, "bye")
    events = pump(host, client, until=lambda e: e[client] and e[host])
    assert events[client] == [("disconnect", HOST_ID, "bye")]
    assert events[host] == [("disconnect", 1, "bye")]


def test_full_game_refuses_more_players():
    host = Host("secret", port=0, max_clients=1)
    try:
        a, _ = join(host)
        b, events = join(host)
        assert events[b] == [("disconnect", HOST_ID, "game is full")]
        a.close()
    finally:
        host.close()


def test_nobody_listening():
    probe = Host("x", port=0)
    port = probe.port
    probe.close()
    client = Client("127.0.0.1", port, "x")
    events = pump(client, until=lambda e: e[client])
    assert kinds(events[client]) == ["disconnect"]
    assert "cannot reach host" in events[client][0][2]


def test_a_stranger_that_never_answers_is_dropped(host, monkeypatch):
    import socket
    monkeypatch.setattr(net, "HANDSHAKE_TIMEOUT", 0.05)
    stranger = socket.create_connection(("127.0.0.1", host.port))
    try:
        pump(host, until=lambda e: host.pending)
        pump(host, until=lambda e: not host.pending)
    finally:
        stranger.close()


def test_garbage_does_not_hurt_the_host(host):
    import socket
    stranger = socket.create_connection(("127.0.0.1", host.port))
    stranger.sendall(b"\xff\xff\xff\xffnot a frame")
    pump(host, until=lambda e: not host.pending)
    stranger.close()
    client, events = join(host)                     # and a proper player still gets in
    assert client.connected
    client.close()
