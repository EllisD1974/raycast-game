"""Playing over Steam: net.py's Host and Client over Steam Networking Sockets.

Players are reached by their SteamID instead of an address and port, through Valve's relays (no port to
forward, and nobody learns anyone's IP address). The game sees the same calls as over TCP:

    host = SteamHost(password, max_clients=7)      # others join it with host.steam_id
    client = SteamClient(host_steam_id, password)

Steam carries whole messages, reliable (all arrive, in order) or unreliable (may be lost or come out of
order), each up to 512 KB, and refuses more while its send buffer (512 KB) is full. Each message here is one byte saying what it is and then JSON:

    M   a whole message
    C   a piece of a big reliable message (PIECE bytes each), more to come
    E   the last piece of one

Reliable messages wait in the connection's outbox while Steam's send buffer is full, so a big map goes out
as fast as Steam will take it.

The Steam client must be running and logged in, steam_api64.dll (from the Steamworks SDK) must be next to
the game, and outside Steam the app id must be known: a steam_appid.txt next to the game holding it (480,
Valve's test game, until the game has its own).
"""
import ctypes
import json
import os
import sys
import time
from collections import deque, namedtuple

from net import MAX_FRAME, MAX_HOST_FRAME, BaseClient, BaseHost

VIRTUAL_PORT = 0                # like a port number, for telling apart several listeners of one app
MAX_MESSAGE = 512 * 1024        # Steam's largest message (k_cbMaxSteamNetworkingSocketsMessageSizeSend)
PIECE = 128 * 1024              # bytes of a big message in each piece (well under Steam's send buffer, 512 KB by default)
CONNECT_TIMEOUT = 20.0          # seconds a client waits for the host (finding a route through the relays takes a while)

# Results, connection states and flags from the Steamworks headers
RESULT_OK = 1                   # k_EResultOK
RESULT_LIMIT_EXCEEDED = 25      # k_EResultLimitExceeded: the send buffer is full, try again later
CONNECTING, FINDING_ROUTE, CONNECTED, CLOSED_BY_PEER, PROBLEM_DETECTED_LOCALLY = 1, 2, 3, 4, 5
END_APP_GENERIC = 1000          # k_ESteamNetConnectionEnd_App_Generic: closed by the game, the reason says why
SEND_UNRELIABLE_NO_NAGLE = 1    # k_nSteamNetworkingSend_UnreliableNoNagle
SEND_RELIABLE_NO_NAGLE = 9      # k_nSteamNetworkingSend_ReliableNoNagle

# What the backend reports about a connection whose state changed
StatusChange = namedtuple("StatusChange", "handle state listen_socket end_reason debug")


class SteamConnection:
    """One Steam connection with net.Connection's calls (queue, flush, read, close, closed, reason)."""

    def __init__(self, network, handle, max_frame=MAX_FRAME):
        self.network = network
        self.handle = handle
        self.max_frame = max_frame
        self.outbox = deque()               # reliable messages (or pieces) Steam has not taken yet
        self.pieces = []                    # the pieces of a big message read so far
        self.size = 0                       # their bytes
        self.connected = False              # Steam says the connection is up
        self.ended = None                   # why the other end or Steam closed it, until what came before is read
        self.closed = False
        self.reason = ""
        network.connections[handle] = self

    def queue(self, message, reliable=True):
        if self.closed:
            return
        body = json.dumps(message, separators=(",", ":")).encode()
        if not reliable and len(body) < PIECE:
            self.network.api.send(self.handle, b"M" + body, False)  # (lost if Steam has no room: the next one replaces it)
            return
        if len(body) <= PIECE:
            self.outbox.append(b"M" + body)
            return
        pieces = [body[i:i + PIECE] for i in range(0, len(body), PIECE)]
        self.outbox.extend(b"C" + piece for piece in pieces[:-1])
        self.outbox.append(b"E" + pieces[-1])

    def flush(self):
        while self.outbox and not self.closed and self.connected:
            result = self.network.api.send(self.handle, self.outbox[0], True)
            if result == RESULT_LIMIT_EXCEEDED:
                return                      # Steam's send buffer is full: the rest goes on a later flush
            if result != RESULT_OK:
                self.close(f"connection lost (Steam error {result})")
                return
            self.outbox.popleft()

    def read(self):
        """Every complete message that has arrived. Marks the connection closed if it was closed."""
        messages = []
        if self.closed:
            return messages
        for data in self.network.api.receive(self.handle):
            kind, body = data[:1], data[1:]
            if kind == b"M":
                whole = body
            elif kind in (b"C", b"E"):
                self.size += len(body)
                self.pieces.append(body)
                if self.size > self.max_frame:
                    self.close("message too large")
                    return messages
                if kind == b"C":
                    continue
                whole, self.pieces, self.size = b"".join(self.pieces), [], 0
            else:
                self.close("garbled message")
                return messages
            if len(whole) > self.max_frame:
                self.close("message too large")
                return messages
            try:
                message = json.loads(whole)
            except ValueError:
                self.close("garbled message")
                return messages
            if isinstance(message, dict):
                messages.append(message)
        if self.ended is not None:
            self.close(self.ended, linger=False)
        return messages

    def close(self, reason="", linger=True):
        """Close it; with `linger`, what is already queued still goes to the other end (a refusal, a kick)."""
        if not self.closed:
            self.flush()
            self.closed = True
            self.reason = reason
            self.network.api.close(self.handle, END_APP_GENERIC, reason[:120], linger)
            self.network.connections.pop(self.handle, None)


class SteamNetwork:
    """Our end of Steam's networking: hands each connection's state changes to it. One per running game
    (see network()); the hosts and clients using it pump it on each of their polls."""

    def __init__(self, api):
        self.api = api
        self.connections = {}               # handle -> SteamConnection
        self.listeners = {}                 # listen socket -> SteamHost

    def pump(self):
        for change in self.api.run_callbacks():
            conn = self.connections.get(change.handle)
            if conn is None:
                host = self.listeners.get(change.listen_socket)
                if host is not None and change.state == CONNECTING:
                    host.arrived(change.handle)
                elif change.state in (CLOSED_BY_PEER, PROBLEM_DETECTED_LOCALLY):
                    self.api.close(change.handle, 0, "", False)     # (one we already gave up on)
            elif change.state == CONNECTED:
                conn.connected = True
            elif change.state in (CLOSED_BY_PEER, PROBLEM_DETECTED_LOCALLY) and conn.ended is None:
                conn.ended = ended_reason(change)

    @property
    def steam_id(self):
        return self.api.steam_id()


def ended_reason(change):
    """Why a connection ended, as shown to the player."""
    if change.state == CLOSED_BY_PEER:
        return change.debug or "connection closed"
    return f"connection lost ({change.debug})" if change.debug else "connection lost"


class SteamHost(BaseHost):
    """BaseHost over Steam: others join with this player's SteamID (.steam_id)."""

    def __init__(self, password, max_clients=7, network=None):
        super().__init__(password, max_clients)
        self.network = network or default_network()
        self.socket = self.network.api.listen(VIRTUAL_PORT)
        if not self.socket:
            raise OSError("Steam would not let us listen for players")
        self.network.listeners[self.socket] = self
        self.arriving = []                  # connections accepted that Steam has not finished making

    @property
    def steam_id(self):
        return self.network.steam_id

    def arrived(self, handle):
        if self.network.api.accept(handle) == RESULT_OK:
            self.arriving.append(SteamConnection(self.network, handle))
        else:
            self.network.api.close(handle, 0, "", False)

    def poll(self):
        self.network.pump()
        return super().poll()

    def _incoming(self):
        ready = [conn for conn in self.arriving if conn.connected and conn.ended is None]
        for conn in self.arriving:
            if conn.ended is not None:
                conn.close(conn.ended, linger=False)
        self.arriving = [conn for conn in self.arriving if not conn.connected and not conn.closed]
        return ready

    def _shut(self):
        for conn in self.arriving:
            conn.close("host closed")
        self.arriving = []
        self.network.listeners.pop(self.socket, None)
        self.network.api.close_listen(self.socket)


class SteamClient(BaseClient):
    """BaseClient over Steam, to the host with SteamID `host_id`."""

    def __init__(self, host_id, password, network=None):
        super().__init__(password)
        self.network = network or default_network()
        self.started = time.monotonic()
        self.link = SteamConnection(self.network, self.network.api.connect(int(host_id), VIRTUAL_PORT), MAX_HOST_FRAME)

    def poll(self):
        self.network.pump()
        return super().poll()

    def _establish(self):
        link = self.link
        if link.ended is not None:
            link.close(link.ended, linger=False)
            raise ConnectionError(link.reason if link.connected else f"cannot reach host: {link.reason}")
        if link.connected:
            return link
        if time.monotonic() - self.started > CONNECT_TIMEOUT:
            link.close("gave up", linger=False)
            raise ConnectionError("host did not answer")
        return None

    def _abandon(self):
        self.link.close("closed", linger=False)


_network = None


def default_network():
    """The game's SteamNetwork, starting Steam the first time. Raises OSError if Steam cannot be used."""
    global _network
    if _network is None:
        _network = SteamNetwork(SteamAPI())
    return _network


# ------------------------------------------------------------------ the Steam API, through ctypes
#
# The "flat" C functions of steam_api64.dll (steam_api_flat.h in the Steamworks SDK) and the few structs
# they pass. Callbacks are fetched by hand each pump (SteamAPI_ManualDispatch_*) rather than through the
# SDK's C++ callback classes, which ctypes cannot make.

class CallbackMsg(ctypes.Structure):
    _fields_ = [("user", ctypes.c_int32), ("callback", ctypes.c_int), ("param", ctypes.c_void_p), ("size", ctypes.c_int)]


class IPAddr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("ipv6", ctypes.c_uint8 * 16), ("port", ctypes.c_uint16)]


class Identity(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("size", ctypes.c_int), ("data", ctypes.c_uint8 * 128)]


class ConnectionInfo(ctypes.Structure):
    _fields_ = [("identity_remote", Identity), ("user_data", ctypes.c_int64), ("listen_socket", ctypes.c_uint32),
                ("addr_remote", IPAddr), ("pad", ctypes.c_uint16), ("pop_remote", ctypes.c_uint32),
                ("pop_relay", ctypes.c_uint32), ("state", ctypes.c_int), ("end_reason", ctypes.c_int),
                ("end_debug", ctypes.c_char * 128), ("description", ctypes.c_char * 128), ("flags", ctypes.c_int),
                ("reserved", ctypes.c_uint32 * 63)]


class StatusChanged(ctypes.Structure):
    """SteamNetConnectionStatusChangedCallback_t"""
    CALLBACK = 1221                         # k_iSteamNetworkingSocketsCallbacks + 1
    _fields_ = [("conn", ctypes.c_uint32), ("info", ConnectionInfo), ("old_state", ctypes.c_int)]


class NetMessage(ctypes.Structure):
    """The start of SteamNetworkingMessage_t (only these fields are read; Steam frees it)."""
    _fields_ = [("data", ctypes.c_void_p), ("size", ctypes.c_int), ("conn", ctypes.c_uint32)]


def library_path():
    """Where steam_api's library is: next to the program when built, else next to this file."""
    folder = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    name = {"win32": "steam_api64.dll", "darwin": "libsteam_api.dylib"}.get(sys.platform, "libsteam_api.so")
    return os.path.join(folder, name)


class SteamAPI:
    """The real Steam, with the calls SteamNetwork uses. Raises OSError if it cannot be started."""

    RECEIVE_BATCH = 32

    def __init__(self, path=None):
        path = path or library_path()
        try:
            self.lib = ctypes.CDLL(path)
        except OSError as e:
            raise OSError(f"cannot load {os.path.basename(path)} ({e})")
        lib, c = self.lib, ctypes
        self._fn("SteamAPI_Shutdown", None)
        self._fn("SteamAPI_GetHSteamPipe", c.c_int32)
        self._fn("SteamAPI_ManualDispatch_Init", None)
        self._fn("SteamAPI_ManualDispatch_RunFrame", None, c.c_int32)
        self._fn("SteamAPI_ManualDispatch_GetNextCallback", c.c_bool, c.c_int32, c.POINTER(CallbackMsg))
        self._fn("SteamAPI_ManualDispatch_FreeLastCallback", None, c.c_int32)
        self._fn("SteamAPI_ISteamUser_GetSteamID", c.c_uint64, c.c_void_p)
        self._fn("SteamAPI_ISteamNetworkingUtils_InitRelayNetworkAccess", None, c.c_void_p)
        self._fn("SteamAPI_ISteamNetworkingSockets_CreateListenSocketP2P", c.c_uint32, c.c_void_p, c.c_int, c.c_int,
                 c.c_void_p)
        self._fn("SteamAPI_ISteamNetworkingSockets_ConnectP2P", c.c_uint32, c.c_void_p, c.POINTER(Identity), c.c_int,
                 c.c_int, c.c_void_p)
        self._fn("SteamAPI_ISteamNetworkingSockets_AcceptConnection", c.c_int, c.c_void_p, c.c_uint32)
        self._fn("SteamAPI_ISteamNetworkingSockets_CloseConnection", c.c_bool, c.c_void_p, c.c_uint32, c.c_int,
                 c.c_char_p, c.c_bool)
        self._fn("SteamAPI_ISteamNetworkingSockets_CloseListenSocket", c.c_bool, c.c_void_p, c.c_uint32)
        self._fn("SteamAPI_ISteamNetworkingSockets_SendMessageToConnection", c.c_int, c.c_void_p, c.c_uint32,
                 c.c_void_p, c.c_uint32, c.c_int, c.c_void_p)
        self._fn("SteamAPI_ISteamNetworkingSockets_ReceiveMessagesOnConnection", c.c_int, c.c_void_p, c.c_uint32,
                 c.POINTER(c.POINTER(NetMessage)), c.c_int)
        self._fn("SteamAPI_SteamNetworkingMessage_t_Release", None, c.POINTER(NetMessage))
        self._fn("SteamAPI_SteamNetworkingIdentity_SetSteamID64", None, c.POINTER(Identity), c.c_uint64)

        self._start()
        lib.SteamAPI_ManualDispatch_Init()
        self.pipe = lib.SteamAPI_GetHSteamPipe()
        self.user = self._interface("SteamAPI_SteamUser_v023", "SteamAPI_SteamUser_v022", "SteamAPI_SteamUser_v021")
        self.utils = self._interface("SteamAPI_SteamNetworkingUtils_SteamAPI_v004",
                                     "SteamAPI_SteamNetworkingUtils_SteamAPI_v003")
        self.sockets = self._interface("SteamAPI_SteamNetworkingSockets_SteamAPI_v013",
                                       "SteamAPI_SteamNetworkingSockets_SteamAPI_v012",
                                       "SteamAPI_SteamNetworkingSockets_SteamAPI_v011")
        lib.SteamAPI_ISteamNetworkingUtils_InitRelayNetworkAccess(self.utils)   # start finding the relays now
        self.status_size = ctypes.sizeof(StatusChanged)

    def _fn(self, name, restype, *argtypes):
        try:
            fn = getattr(self.lib, name)
        except AttributeError:
            raise OSError(f"this steam_api library has no {name} (too old or too new a Steamworks SDK?)")
        fn.restype, fn.argtypes = restype, list(argtypes)
        return fn

    def _start(self):
        """SteamAPI_InitFlat on newer SDKs (it says what is wrong), SteamAPI_Init on older ones."""
        if hasattr(self.lib, "SteamAPI_InitFlat"):
            message = ctypes.create_string_buffer(1024)
            init = self._fn("SteamAPI_InitFlat", ctypes.c_int, ctypes.c_char_p)
            if init(message) != 0:
                raise OSError(f"Steam did not start: {message.value.decode(errors='replace') or 'is it running?'}")
        elif not self._fn("SteamAPI_Init", ctypes.c_bool)():
            raise OSError("Steam did not start (is it running, and is the app id known?)")

    def _interface(self, *names):
        for name in names:
            if hasattr(self.lib, name):
                pointer = self._fn(name, ctypes.c_void_p)()
                if pointer:
                    return pointer
        raise OSError(f"Steam has none of {', '.join(names)}")

    def steam_id(self):
        return self.lib.SteamAPI_ISteamUser_GetSteamID(self.user)

    def run_callbacks(self):
        lib, changes = self.lib, []
        lib.SteamAPI_ManualDispatch_RunFrame(self.pipe)
        msg = CallbackMsg()
        while lib.SteamAPI_ManualDispatch_GetNextCallback(self.pipe, ctypes.byref(msg)):
            try:
                if msg.callback == StatusChanged.CALLBACK and msg.size >= self.status_size:
                    status = StatusChanged.from_address(msg.param)
                    info = status.info
                    changes.append(StatusChange(status.conn, info.state, info.listen_socket, info.end_reason,
                                                info.end_debug.decode(errors="replace")))
            finally:
                lib.SteamAPI_ManualDispatch_FreeLastCallback(self.pipe)
        return changes

    def listen(self, virtual_port):
        return self.lib.SteamAPI_ISteamNetworkingSockets_CreateListenSocketP2P(self.sockets, virtual_port, 0, None)

    def close_listen(self, socket):
        self.lib.SteamAPI_ISteamNetworkingSockets_CloseListenSocket(self.sockets, socket)

    def connect(self, steam_id, virtual_port):
        identity = Identity()
        self.lib.SteamAPI_SteamNetworkingIdentity_SetSteamID64(ctypes.byref(identity), steam_id)
        return self.lib.SteamAPI_ISteamNetworkingSockets_ConnectP2P(self.sockets, ctypes.byref(identity), virtual_port,
                                                                     0, None)

    def accept(self, handle):
        return self.lib.SteamAPI_ISteamNetworkingSockets_AcceptConnection(self.sockets, handle)

    def close(self, handle, reason, debug, linger):
        self.lib.SteamAPI_ISteamNetworkingSockets_CloseConnection(self.sockets, handle, reason,
                                                                  debug.encode(errors="replace"), linger)

    def send(self, handle, data, reliable):
        flags = SEND_RELIABLE_NO_NAGLE if reliable else SEND_UNRELIABLE_NO_NAGLE
        return self.lib.SteamAPI_ISteamNetworkingSockets_SendMessageToConnection(self.sockets, handle, data, len(data),
                                                                                 flags, None)

    def receive(self, handle):
        lib, out = self.lib, []
        batch = (ctypes.POINTER(NetMessage) * self.RECEIVE_BATCH)()
        while True:
            count = lib.SteamAPI_ISteamNetworkingSockets_ReceiveMessagesOnConnection(self.sockets, handle, batch,
                                                                                     self.RECEIVE_BATCH)
            for i in range(max(count, 0)):
                message = batch[i].contents
                out.append(ctypes.string_at(message.data, message.size))
                lib.SteamAPI_SteamNetworkingMessage_t_Release(batch[i])
            if count < self.RECEIVE_BATCH:
                return out

    def shutdown(self):
        self.lib.SteamAPI_Shutdown()
