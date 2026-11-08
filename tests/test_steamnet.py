"""steamnet.py over a pretend Steam: each player's SteamAPI is a FakeSteamAPI joined to the others through a
FakeSteam, which posts connection state changes the way Steam does, has a send buffer that fills up, moves
only so many bytes a pump and loses unreliable messages if asked to."""
import ctypes
import os
import random
from collections import deque

import pytest

import steamnet
from game import Inputs
from session import ClientSession, HostSession
from steamnet import (CLOSED_BY_PEER, CONNECTED, CONNECTING, MAX_MESSAGE, PROBLEM_DETECTED_LOCALLY, RESULT_LIMIT_EXCEEDED,
                      RESULT_OK, SteamClient, SteamConnection, SteamHost, SteamNetwork, StatusChange)
from test_session import DT, FIRST_CHARACTER, make_world, new_game

RESULT_NO_CONNECTION = 3


APP_ID = 480


class FakeSteam:
    """Everyone in it is friends with everyone else, and in the game (APP_ID) unless .playing says otherwise."""

    def __init__(self, loss=0.0, buffer=512 * 1024, rate=256 * 1024, seed=1):
        self.users = {}
        self.names = {}                 # steam id -> name (default "Player <id>")
        self.playing = {}               # steam id -> app id they are in (default APP_ID)
        self.offline = {}               # steam id -> app id, for friends who are not running a FakeSteamAPI
        self.loss, self.buffer, self.rate = loss, buffer, rate
        self.rng = random.Random(seed)

    def user(self, steam_id):
        self.users[steam_id] = FakeSteamAPI(self, steam_id)
        return SteamNetwork(self.users[steam_id])

    def carry(self):
        """Move what is on the wire on, as Steam does in the background whoever is pumping: up to `rate` bytes
        from each connection, then a closed one's last messages and its close."""
        for api in self.users.values():
            for end in list(api.ends.values()):
                moved = 0
                while end.wire and moved < self.rate:
                    moved += len(end.wire[0])
                    end.peer.inbox.append(end.wire.popleft())
                if end.closing is not None and not end.wire:
                    del api.ends[end.handle]
                    if end.peer is not None and end.peer.handle in end.peer.api.ends:
                        end.peer.api.changes.append(StatusChange(end.peer.handle, CLOSED_BY_PEER, 0, 1000, end.closing))


class FakeEnd:
    def __init__(self, api, handle):
        self.api, self.handle = api, handle
        self.peer = None
        self.connected = False
        self.wire = deque()             # reliable messages sent, not yet moved to the other end
        self.inbox = deque()
        self.closing = None             # the reason, once closed with linger (the wire still drains)


class FakeSteamAPI:
    def __init__(self, steam, steam_id):
        self.steam, self.id = steam, steam_id
        self.ends = {}
        self.listening = {}             # listen socket -> virtual port
        self.changes = []
        self.next_handle = 100
        self.presence = {}

    def _end(self):
        self.next_handle += 1
        end = self.ends[self.next_handle] = FakeEnd(self, self.next_handle)
        return end

    def steam_id(self):
        return self.id

    def app_id(self):
        return APP_ID

    def persona_name(self):
        return self.steam.names.get(self.id, f"Player {self.id}")

    def friends(self):
        everyone = {**self.steam.offline, **{sid: self.steam.playing.get(sid, APP_ID) for sid in self.steam.users}}
        return [(sid, self.steam.names.get(sid, f"Player {sid}"), game) for sid, game in everyone.items()
                if sid != self.id]

    def friend_presence(self, steam_id, key):
        other = self.steam.users.get(steam_id)
        return other.presence.get(key, "") if other else ""

    def set_presence(self, key, value):
        self.presence[key] = value

    def listen(self, virtual_port):
        self.next_handle += 1
        self.listening[self.next_handle] = virtual_port
        return self.next_handle

    def close_listen(self, socket):
        self.listening.pop(socket, None)

    def connect(self, steam_id, virtual_port):
        ours = self._end()
        other = self.steam.users.get(steam_id)
        socket = next((s for s, port in (other.listening.items() if other else ()) if port == virtual_port), None)
        if socket is None:
            self.changes.append(StatusChange(ours.handle, PROBLEM_DETECTED_LOCALLY, 0, 5000, "no route to that player"))
            return ours.handle
        theirs = other._end()
        ours.peer, theirs.peer = theirs, ours
        self.changes.append(StatusChange(ours.handle, CONNECTING, 0, 0, ""))
        other.changes.append(StatusChange(theirs.handle, CONNECTING, socket, 0, ""))
        return ours.handle

    def accept(self, handle):
        end = self.ends[handle]
        end.connected = end.peer.connected = True
        self.changes.append(StatusChange(handle, CONNECTED, 0, 0, ""))
        end.peer.api.changes.append(StatusChange(end.peer.handle, CONNECTED, 0, 0, ""))
        return RESULT_OK

    def send(self, handle, data, reliable):
        end = self.ends.get(handle)
        if end is None or not end.connected or end.closing is not None:
            return RESULT_NO_CONNECTION
        assert len(data) <= MAX_MESSAGE
        if not reliable:
            if self.steam.rng.random() >= self.steam.loss:
                end.peer.inbox.append(bytes(data))
            return RESULT_OK
        if sum(map(len, end.wire)) + len(data) > self.steam.buffer:
            return RESULT_LIMIT_EXCEEDED
        end.wire.append(bytes(data))
        return RESULT_OK

    def receive(self, handle):
        end = self.ends.get(handle)
        if end is None:
            return []
        out = list(end.inbox)
        end.inbox.clear()
        return out

    def close(self, handle, reason, debug, linger):
        end = self.ends.get(handle)
        if end is None:
            return
        if not linger:
            end.wire.clear()
        end.closing = debug

    def run_callbacks(self):
        self.steam.carry()
        changes, self.changes = self.changes, []
        return changes


def run(sessions, until, inputs=None, frames=3000):
    for _ in range(frames):
        for s in sessions:
            s.step((inputs or {}).get(s, Inputs()), DT)
        if until():
            return
    raise AssertionError("never happened")


HOST_ID, JOINER_ID = 76561198000000001, 76561198000000002


def steam_game(steam=None, password="pw", atlas=None, use_atlas=None):
    steam = steam or FakeSteam()
    host = HostSession(new_game(), SteamHost("pw", network=steam.user(HOST_ID)), atlas)
    client = ClientSession(SteamClient(HOST_ID, password, network=steam.user(JOINER_ID)), make_world, FIRST_CHARACTER,
                           use_atlas)
    run([host, client], until=lambda: client.ready or client.ended)
    return host, client


def test_a_joiner_reaches_the_host_by_its_steam_id_and_plays():
    host, client = steam_game()
    assert client.ready and client.id == 1 and host.host.steam_id == HOST_ID
    run([host, client], until=lambda: host.game.players[1].body.x > 3.0, inputs={client: Inputs(forward=1)})


def test_a_wrong_password_is_told_why():
    host, client = steam_game(password="nope")
    assert client.ended == "wrong password"
    assert set(host.game.players) == {0}


def test_nobody_hosting_at_that_steam_id():
    steam = FakeSteam()
    client = ClientSession(SteamClient(HOST_ID, "pw", network=steam.user(JOINER_ID)), make_world, FIRST_CHARACTER)
    run([client], until=lambda: client.ended)
    assert client.ended.startswith("cannot reach host") and "no route" in client.ended


def test_textures_bigger_than_a_steam_message_arrive_whole_through_a_small_send_buffer():
    atlas = os.urandom(1_500_000)                       # ~2 MB once in base64: four pieces, more than the buffer holds
    got = []
    host, client = steam_game(FakeSteam(buffer=300_000, rate=100_000), atlas=atlas,
                              use_atlas=lambda png: got.append(png) or FIRST_CHARACTER)
    assert client.ready and got == [atlas]


def test_the_joiner_is_told_when_the_host_goes():
    host, client = steam_game()
    host.close()
    run([client], until=lambda: client.ended)
    assert client.ended == "host closed"


def test_a_kicked_joiner_is_told_why():
    host, client = steam_game()
    host.host.kick(1, "too many pings")
    run([host, client], until=lambda: client.ended)
    assert client.ended == "too many pings"
    assert set(host.game.players) == {0}


def test_a_joiner_leaving_removes_their_player():
    host, client = steam_game()
    client.close()
    run([host], until=lambda: set(host.game.players) == {0})


def test_playing_through_lost_unreliable_messages():
    host, client = steam_game(FakeSteam(loss=0.4))
    moves = {client: Inputs(forward=1, strafe=1, turn=0.01)}
    run([host, client], until=lambda: client.seq >= 90, inputs=moves)
    run([host, client], until=lambda: client.seq >= 300)
    theirs, ours = host.game.players[1].body, client.me.body
    assert theirs.x > 3.0
    assert (ours.x, ours.y, ours.angle) == pytest.approx((theirs.x, theirs.y, theirs.angle), abs=1e-6)


def test_pieces_and_whole_messages_can_interleave():
    """An unreliable message can arrive between the pieces of a big reliable one."""
    steam = FakeSteam()
    network = steam.user(HOST_ID)
    conn = SteamConnection(network, 1, max_frame=10 ** 7)
    network.api.ends[1] = end = FakeEnd(network.api, 1)
    end.inbox.extend([b'C{"type":"big","pad":"', b'M{"type":"small"}', b'E' + b"x" * 10 + b'"}'])
    assert conn.read() == [{"type": "small"}, {"type": "big", "pad": "x" * 10}]


def test_junk_or_oversized_messages_close_the_connection():
    for data, why in ((b"Zwhat", "garbled message"), (b"M{not json", "garbled message"),
                      (b"C" + b"x" * 200, "message too large")):
        network = FakeSteam().user(HOST_ID)
        conn = SteamConnection(network, 1, max_frame=100)
        network.api.ends[1] = end = FakeEnd(network.api, 1)
        end.inbox.append(data)
        conn.read()
        assert conn.closed and conn.reason == why


def test_the_structs_match_the_steamworks_headers():
    """Sizes and offsets of what Steam hands over, as laid out in steamnetworkingtypes.h and
    isteamnetworkingsockets.h (8 byte packing on Windows): checked against SDK 1.65 by compiling sizeof / offsetof."""
    assert ctypes.sizeof(steamnet.Identity) == 136
    assert ctypes.sizeof(steamnet.IPAddr) == 18
    assert ctypes.sizeof(steamnet.ConnectionInfo) == 696
    assert steamnet.ConnectionInfo.state.offset == 176 and steamnet.ConnectionInfo.end_debug.offset == 184
    assert steamnet.StatusChanged.info.offset == 8 and ctypes.sizeof(steamnet.StatusChanged) == 712
    assert ctypes.sizeof(steamnet.CallbackMsg) == 24


def test_without_steam_there_is_a_clear_error(tmp_path):
    with pytest.raises(OSError, match="cannot load"):
        steamnet.SteamAPI(str(tmp_path / "steam_api64.dll"))


def test_friends_in_the_game_are_listed_with_those_hosting_first():
    steam = FakeSteam()
    steam.names.update({HOST_ID: "zed", JOINER_ID: "me", 3: "amy", 4: "bob"})
    steam.offline.update({3: APP_ID, 4: 730})                   # bob is in another game
    network = steam.user(JOINER_ID)
    host = SteamHost("pw", network=steam.user(HOST_ID))
    assert network.friends_playing() == [(HOST_ID, "zed", True), (3, "amy", False)]
    host.close()
    assert network.friends_playing() == [(3, "amy", False), (HOST_ID, "zed", False)]    # no longer hosting
