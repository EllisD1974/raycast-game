"""Networking over plain sockets: one player hosts behind a password, the others join with it.

Nothing here knows about the game; it carries small dicts between a Host and its Clients. Both
have the same four calls and are polled once a frame (no threads, nothing blocks):

    events = net.poll()          # [(kind, peer_id, payload), ...] since the last call
    net.send(peer_id, message)   # message is a dict that json can carry
    net.broadcast(message)       # the host: to every joined client. A client: to the host
    net.close()

The events are ("connect", id, None), ("message", id, dict) and ("disconnect", id, reason). The
host is always HOST_ID, so a client sends with net.send(HOST_ID, ...). A client gets "connect" once
the host accepted the password (the payload is {"id": its own id}); a wrong password or an
unreachable host arrives as ("disconnect", HOST_ID, reason) instead.

The password never crosses the wire: the host sends a random salt and the client answers with
sha256(salt + password). Messages are length-prefixed JSON over TCP, which also works across the
internet through a forwarded port or a VPN such as Tailscale. A transport for Steam would offer the
same calls.
"""
import errno
import hashlib
import hmac
import json
import os
import select
import socket
import struct
import time

HOST_ID = 0
DEFAULT_PORT = 7777
MAX_FRAME = 1 << 20             # bytes in one message; anything bigger is a broken or hostile peer
MAX_HOST_FRAME = 32 << 20       # the same for what a client reads from its host (the map and textures are big)
HANDSHAKE_TIMEOUT = 5.0         # seconds a new connection has to give the right password
CONNECT_TIMEOUT = 5.0           # seconds a client waits for the host to answer

_HEADER = struct.Struct(">I")
_PENDING = {0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EAGAIN, 10035}   # 10035: WSAEWOULDBLOCK


def proof(salt, password):
    """What a client sends to show it knows the password without sending the password."""
    return hashlib.sha256(salt.encode() + password.encode()).hexdigest()


class Connection:
    """One socket carrying length-prefixed JSON messages, read and written without blocking."""

    def __init__(self, sock, max_frame=MAX_FRAME):
        self.sock = sock
        self.max_frame = max_frame
        self.sock.setblocking(False)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.inbox = bytearray()
        self.outbox = bytearray()
        self.closed = False
        self.reason = ""

    def queue(self, message):
        body = json.dumps(message, separators=(",", ":")).encode()
        self.outbox += _HEADER.pack(len(body)) + body

    def flush(self):
        while self.outbox and not self.closed:
            try:
                sent = self.sock.send(self.outbox)
            except (BlockingIOError, InterruptedError):
                return
            except OSError as e:
                self.close(f"connection lost ({e.strerror or e})")
                return
            del self.outbox[:sent]

    def read(self):
        """Every complete message that has arrived. Marks the connection closed if it dropped."""
        while not self.closed:
            try:
                data = self.sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                break
            except OSError as e:
                self.close(f"connection lost ({e.strerror or e})")
                break
            if not data:
                self.close("connection closed")
                break
            self.inbox += data
        messages = []
        while len(self.inbox) >= _HEADER.size:
            (size,) = _HEADER.unpack_from(self.inbox)
            if size > self.max_frame:
                self.close("message too large")
                break
            if len(self.inbox) < _HEADER.size + size:
                break
            body = bytes(self.inbox[_HEADER.size:_HEADER.size + size])
            del self.inbox[:_HEADER.size + size]
            try:
                message = json.loads(body)
            except ValueError:
                self.close("garbled message")
                break
            if isinstance(message, dict):
                messages.append(message)
        return messages

    def close(self, reason=""):
        if not self.closed:
            self.closed = True
            self.reason = reason
            try:
                self.sock.close()
            except OSError:
                pass


class Host:
    """Listens for players, lets in those who know the password, and relays messages with them."""

    def __init__(self, password, port=DEFAULT_PORT, bind="127.0.0.1", max_clients=7):
        self.password = password
        self.max_clients = max_clients
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name != "nt":                         # Windows would let a second host share the port
            self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((bind, port))
        self.listener.listen()
        self.listener.setblocking(False)
        self.port = self.listener.getsockname()[1]  # the real port when 0 was asked for
        self.joined = {}                            # id -> Connection, after the password was accepted
        self.pending = {}                           # Connection -> (salt, when it arrived)
        self.next_id = HOST_ID + 1

    def poll(self):
        events = []
        self._accept()
        for conn, (salt, since) in list(self.pending.items()):
            for message in conn.read():
                self._handshake(conn, salt, message, events)
                if conn not in self.pending:
                    break
            if conn in self.pending and not conn.closed and time.monotonic() - since > HANDSHAKE_TIMEOUT:
                conn.close("handshake timed out")
            conn.flush()
            if conn.closed:
                self.pending.pop(conn, None)
        for peer_id, conn in list(self.joined.items()):
            for message in conn.read():
                events.append(("message", peer_id, message))
            conn.flush()
            if conn.closed:
                del self.joined[peer_id]
                events.append(("disconnect", peer_id, conn.reason))
        return events

    def send(self, peer_id, message):
        conn = self.joined.get(peer_id)
        if conn:
            conn.queue(message)
            conn.flush()

    def broadcast(self, message):
        for peer_id in list(self.joined):
            self.send(peer_id, message)

    def kick(self, peer_id, reason="kicked"):
        conn = self.joined.get(peer_id)
        if conn:
            conn.queue({"type": "kicked", "reason": reason})
            conn.flush()
            conn.close(reason)                      # poll() reports the disconnect

    def close(self):
        for conn in list(self.joined.values()) + list(self.pending):
            conn.close("host closed")
        self.joined.clear()
        self.pending.clear()
        self.listener.close()

    def _accept(self):
        while True:
            try:
                sock, _ = self.listener.accept()
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                return
            conn = Connection(sock)
            salt = os.urandom(16).hex()
            conn.queue({"type": "hello", "salt": salt})
            conn.flush()
            self.pending[conn] = (salt, time.monotonic())

    def _handshake(self, conn, salt, message, events):
        if message.get("type") != "join":
            return
        if len(self.joined) >= self.max_clients:
            self._refuse(conn, "game is full")
        elif not hmac.compare_digest(str(message.get("proof", "")), proof(salt, self.password)):
            self._refuse(conn, "wrong password")
        else:
            peer_id = self.next_id
            self.next_id += 1
            del self.pending[conn]
            self.joined[peer_id] = conn
            conn.queue({"type": "accepted", "id": peer_id})
            events.append(("connect", peer_id, None))

    def _refuse(self, conn, reason):
        conn.queue({"type": "rejected", "reason": reason})
        conn.flush()
        conn.close(reason)
        self.pending.pop(conn, None)


class Client:
    """Joins a Host with its password. Poll it until "connect" (accepted) or "disconnect"."""

    def __init__(self, address, port, password):
        self.password = password
        self.conn = None
        self.id = None
        self.connected = False                      # accepted by the host
        self.started = time.monotonic()
        self.dead = False                           # the final "disconnect" was already reported
        self.told = ""                              # why the host turned us away or kicked us
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        self.connecting = True
        try:
            code = sock.connect_ex((address, port))
        except OSError as e:                        # e.g. a host name that does not resolve
            sock.close()
            self.failure = f"cannot reach host ({e})"
            self.sock = None
            return
        self.failure = None
        self.sock = sock
        if code not in _PENDING:
            sock.close()
            self.sock = None
            self.failure = f"cannot reach host ({os.strerror(code)})"

    def poll(self):
        if self.dead:
            return []
        events = []
        if self.failure:
            return self._die(self.failure)
        if self.connecting:
            if time.monotonic() - self.started > CONNECT_TIMEOUT:
                self.sock.close()
                return self._die("host did not answer")
            _, writable, failed = select.select([], [self.sock], [self.sock], 0)
            if failed or (writable and self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)):
                self.sock.close()
                return self._die("cannot reach host (connection refused)")
            if not writable:
                return events
            self.connecting = False
            self.conn = Connection(self.sock, MAX_HOST_FRAME)
        for message in self.conn.read():
            kind = message.get("type")
            if kind == "hello" and not self.connected:
                self.conn.queue({"type": "join", "proof": proof(message.get("salt", ""), self.password)})
            elif kind == "accepted" and not self.connected:
                self.connected, self.id = True, message.get("id")
                events.append(("connect", HOST_ID, {"id": self.id}))
            elif kind in ("rejected", "kicked"):
                self.told = str(message.get("reason", kind))    # beats "connection closed", which follows
            elif self.connected:
                events.append(("message", HOST_ID, message))
        self.conn.flush()
        if self.conn.closed:
            events += self._die(self.told or self.conn.reason)
        return events

    def send(self, peer_id, message):
        if self.connected and not self.conn.closed:
            self.conn.queue(message)
            self.conn.flush()

    def broadcast(self, message):
        self.send(HOST_ID, message)

    def close(self):
        self.dead = True
        if self.conn:
            self.conn.close("closed")
        elif self.sock:
            self.sock.close()

    def _die(self, reason):
        self.dead = True
        return [("disconnect", HOST_ID, reason)]
