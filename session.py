"""One game seen from one keyboard: playing alone, hosting others, or joining a host.

No pygame. The three sessions look the same to main.py:

    events = session.step(inputs, dt)   # this player's Inputs for the frame -> what happened to them
    session.me                          # their PlayerState (body, stats, inventory) to draw and show
    session.sprites()                   # what the renderer draws around them (items, bullets, others)
    session.ended                       # None, or why the game is over for them (host left, kicked...)

The host runs the real Game. Joiners send their steps and get back snapshots of it, which they draw;
a joiner predicts its own movement and smooths everyone else's (see ClientSession).
"""
import base64
import json
import math
import time
from collections import deque

import net
from constants import PLAYER_HEIGHT
from entities import Entities, PlayerStats
from game import MAX_STEP_DT, Events, Inputs, PlayerState, character_tile_for, move_body
from inventory import GunState, Inventory
from lighting import LightSystem, follow as follow_lights, item_lights
from mapfile import level_text, parse_level
from particles import ParticleSystem, emitters_in_view, follow
from physics import Player

LOCAL_ID = net.HOST_ID                          # whoever sits at the host's keyboard
SNAPSHOT_RATE = 60                              # snapshots a second sent to each joiner
MAX_QUEUE = 64                                  # steps kept per joiner waiting their turn; older ones are dropped
MAX_CREDIT = 1.0                                # seconds of steps a joiner may save up (to catch up after a stall)
INTERP_DELAY = 3 / SNAPSHOT_RATE                # other players are drawn this far in the past (three snapshots)
CLOCK_BLEND = 0.1                               # how fast our game time estimate follows each snapshot's
MAX_SAMPLES = 12                                # positions kept per other player to interpolate between
MAX_EXTRAPOLATION = 0.1                         # longest a bullet is carried on without a new snapshot
MAX_FX = 32                                     # particle effects sent to joiners in one snapshot


class LocalSession:
    """Playing alone: the game and the one player in it."""

    def __init__(self, game):
        self.game = game
        self.world = game.world
        self.me = game.add_player(LOCAL_ID)
        self.ended = None
        self.particles = ParticleSystem(game.level.effects, game.world)     # looks only; worked out on this machine
        self.lights = LightSystem(game.level, game.world)                   # likewise

    def step(self, wish, dt, elapsed=None):
        """`dt` is the frame time the game runs by (capped); `elapsed` the real time since the last frame,
        which a network session paces itself by (it is dt if not given)."""
        events = self.game.tick({LOCAL_ID: wish}, dt)[LOCAL_ID]
        self.animate(dt, self.game.take_fx(), self.game.take_flashes())
        return events

    def reload(self, level, world, character_tile=None, atlas_png=None):
        """Carry on in a new map (see Game.load_level). `atlas_png` is the textures it is drawn with, if they
        changed: a host passes them on to its joiners."""
        self.game.load_level(level, world, character_tile)
        self.world = world
        self.particles = ParticleSystem(level.effects, world)
        self.lights = LightSystem(level, world)

    def animate(self, dt, effects, flashes=()):
        """Move the particles and lights on: play the effects and flashes just fired, attach trails and lights
        to the bullets and emitters and lights to the items that have them, and age everything."""
        for name, x, y, z, dx, dy, dz, *offset in effects:
            self.particles.play(name, x, y, z, (dx, dy, dz), tuple(offset) if offset else None)
        for name, x, y, z in flashes:
            self.lights.flash(name, x, y, z)
        viewer = (self.me.body.x, self.me.body.y)
        keys = follow_lights(self.lights, [(b.ident, b.light, b.x, b.y, b.z) for b in self.game.projectiles.bullets])
        self.lights.keep(keys + item_lights(self.lights, self.game.items, viewer))
        self.lights.update(dt)
        bullets = [(b.ident, b.trail, b.x, b.y, b.z, b.vx, b.vy, b.vz, b.trail_offset)
                   for b in self.game.projectiles.bullets]
        keys = follow(self.particles, bullets, dt=dt)
        keys += emitters_in_view(self.particles, self.game.items, (self.me.body.x, self.me.body.y), dt)
        self.particles.keep(keys)
        self.particles.update(dt)

    def sprites(self):
        return self.game.sprites(LOCAL_ID) + self.particles.sprites()

    def lighting(self):
        """The Lighting to draw this player's view with (None when the map has no lights and is fully lit)."""
        body = self.me.body
        return self.lights.prepare((body.x, body.y, body.eye_z), self.particles)

    def status(self):
        """Text for the window title about the connection (nothing when playing alone)."""
        return ""

    def close(self):
        pass


class HostSession(LocalSession):
    """Playing at the keyboard that runs the game: joiners' steps are carried out as they come and
    snapshots of the result go back out.

    Each joiner step arrives with its own dt and is run with that dt (game.move_player), the same
    numbers the joiner predicted it with, so the two agree. The host only lets a joiner use as much
    time as has really passed, so sending extra or long steps does not make them faster."""

    def __init__(self, game, host, atlas_png=None):
        super().__init__(game)
        self.host = host
        self.level_text = level_text(game.level)
        self.atlas = base64.b64encode(atlas_png).decode() if atlas_png else None    # the textures joiners draw with
        self.queue = {}                         # joiner -> deque of (seq, Inputs, dt) not yet carried out
        self.credit = {}                        # joiner -> seconds of steps they may still use
        self.acked = {}                         # joiner -> seq of the last step carried out
        self.owed = {}                          # joiner -> Events since the last snapshot sent to them
        self.since_snapshot = 0.0
        self.time = 0.0                         # game time, stamped on snapshots for interpolating
        self.fx_out = []                        # effects to tell joiners to play, until the next snapshot
        self.flashes_out = []                   # lights to tell joiners to flash, until the next snapshot

    def step(self, wish, dt, elapsed=None):
        elapsed = dt if elapsed is None else elapsed
        for kind, peer, payload in self.host.poll():
            if kind == "connect":
                self.game.add_player(peer)
                self.queue[peer], self.credit[peer] = deque(maxlen=MAX_QUEUE), MAX_STEP_DT
                self.acked[peer], self.owed[peer] = 0, Events()
                self.host.send(peer, {"type": "welcome", "id": peer, "level": self.level_text, "atlas": self.atlas})
            elif kind == "disconnect":
                self.game.remove_player(peer)
                for table in (self.queue, self.credit, self.acked, self.owed):
                    table.pop(peer, None)
            elif kind == "message" and payload.get("type") == "input" and peer in self.queue:
                self.accept(peer, payload)
        events = Events(fired=self.game.move_player(LOCAL_ID, wish, dt))
        for peer, queue in self.queue.items():
            self.credit[peer] = min(self.credit[peer] + elapsed, MAX_CREDIT)     # real time, not the capped dt
            while queue and self.credit[peer] > 0:
                seq, cmd, cmd_dt = queue.popleft()
                self.owed[peer].fired += self.game.move_player(peer, cmd, cmd_dt)
                self.credit[peer] -= cmd_dt
                self.acked[peer] = seq
        for pid, picked in self.game.advance_world(dt).items():
            (events if pid == LOCAL_ID else self.owed[pid]).picked += picked
        effects, flashes = self.game.take_fx(), self.game.take_flashes()
        self.fx_out += effects
        self.flashes_out += flashes
        self.animate(dt, effects, flashes)
        self.time += dt
        self.since_snapshot += elapsed
        if self.since_snapshot >= 1 / SNAPSHOT_RATE:
            self.since_snapshot = min(self.since_snapshot - 1 / SNAPSHOT_RATE, 1 / SNAPSHOT_RATE)
            self.send_snapshots()
        return events

    def reload(self, level, world, character_tile=None, atlas_png=None):
        """Carry on in a new map and send it (with the textures, if they changed) to every joiner, who
        switch to it between two snapshots."""
        super().reload(level, world, character_tile, atlas_png)
        self.level_text = level_text(level)
        if atlas_png:
            self.atlas = base64.b64encode(atlas_png).decode()
        self.fx_out, self.flashes_out = [], []
        self.host.broadcast({"type": "reload", "level": self.level_text, "atlas": self.atlas})

    def backlog(self):
        """Seconds of joiner steps waiting their turn, for the worst joiner (0 when keeping up)."""
        return max((sum(step[2] for step in queue) for queue in self.queue.values()), default=0.0)

    def accept(self, peer, message):
        """Queue one step from a joiner. Anything that is not a well formed, newer step is ignored."""
        seq, dt = message.get("seq"), message.get("dt")
        if (not isinstance(seq, int) or isinstance(seq, bool) or seq <= self.last_seq(peer)
                or not isinstance(dt, (int, float)) or isinstance(dt, bool)):
            return
        self.queue[peer].append((seq, Inputs.from_dict(message), max(0.0, min(float(dt), MAX_STEP_DT))))

    def last_seq(self, peer):
        queue = self.queue[peer]
        return queue[-1][0] if queue else self.acked[peer]

    def send_snapshots(self):
        common = {
            "type": "state", "time": self.time,
            "players": {str(pid): body_fields(state.body) for pid, state in self.game.players.items()},
            "bullets": [[b.x, b.y, b.z, b.vx, b.vy, b.vz, b.size, b.tile, b.ident, b.trail, b.light,
                         list(b.trail_offset) if b.trail_offset else None]
                        for b in self.game.projectiles.bullets],
            "fx": [list(e) for e in self.fx_out[-MAX_FX:]],
            "flashes": [list(f) for f in self.flashes_out[-MAX_FX:]],
            "items": "".join("1" if item.present else "0" for item in self.game.items.items),
        }
        for peer, owed in self.owed.items():
            state = self.game.players[peer]
            self.host.send(peer, dict(common, you=private_fields(state, owed, self.acked[peer])))
            self.owed[peer] = Events()
        self.fx_out, self.flashes_out = [], []

    def status(self):
        return f" - hosting {len(self.queue)} joined, backlog {self.backlog() * 1000:.0f} ms"

    def close(self):
        self.host.close()


class ClientSession:
    """Joined to a host: sends our steps and draws the host's snapshots.

    Our own movement is predicted: each step is run on our body at once (the same game.move_body the
    host uses) and kept until the host says it has carried it out. A snapshot then resets the body to
    the host's and replays the steps it has not caught up with yet, so we move without waiting for the
    round trip and still end up where the host says.

    Other players are drawn a little in the past (INTERP_DELAY), between the two snapshots either side
    of that moment, so their movement is smooth although it only arrives 30 times a second. Bullets
    come with their velocity and are carried on from the last snapshot.

    `make_world(level)` builds the World to draw (it needs the textures, which only main.py has).
    The host sends its textures with the map: `use_atlas(png_bytes)` is called with them before the world is
    built, and returns the tile where the character pictures start (it must raise ValueError for a picture
    it cannot use). Without it, or with a host that sent none, we draw with the textures we already have."""

    def __init__(self, client, make_world, character_tile=None, use_atlas=None):
        self.client = client
        self.make_world = make_world
        self.use_atlas = use_atlas
        self.character_tile = character_tile
        self.id = None
        self.loads = 0                          # maps loaded so far: the first, then one for each reload
        self.level = self.world = self.items = None
        self.me = PlayerState(Player(0.0, 0.0, 0.0))
        self.pending = []                       # (seq, Inputs, dt) sent and not yet carried out by the host
        self.seq = 0
        self.history = {}                       # other player id -> [(game time, x, y, z, angle)], oldest first
        self.game_time = None                   # our estimate of the host's game time
        self.bullets = []                       # as sent: [x, y, z, vx, vy, vz, size, tile, id, trail, light]
        self.lights = None                      # looks only, like the particles
        self.particles = None                   # looks only; worked out here from what the host says happens
        self.bullet_age = 0.0                   # seconds since the snapshot they came in
        self.ended = None
        self.owed = Events()
        self.ready = False                      # the host has sent the map and a first snapshot
        self.sent_at = {}                       # seq -> when it was sent, until the host acknowledges it
        self.ping = 0.0                         # seconds from sending a step to hearing the host has run it

    def step(self, wish, dt, elapsed=None):
        elapsed = dt if elapsed is None else elapsed
        for kind, _, payload in self.client.poll():
            if kind == "disconnect":
                self.ended = payload or "disconnected"
            elif kind == "message":
                self.receive(payload)
        dt = max(0.0, min(dt, MAX_STEP_DT))
        if self.ready and not self.ended:
            wish = Inputs.from_dict(wish.to_dict())     # exactly what the host will read it as
            self.seq += 1
            self.client.send(net.HOST_ID, dict(wish.to_dict(), type="input", seq=self.seq, dt=dt))
            self.pending.append((self.seq, wish, dt))
            self.sent_at[self.seq] = time.monotonic()
            move_body(self.world, self.me.body, wish, dt)
        if self.items:
            self.items.clock += dt              # (only the bobbing: the host decides what is picked up)
        if self.game_time is not None:
            self.game_time += elapsed
        self.bullet_age = min(self.bullet_age + elapsed, MAX_EXTRAPOLATION)
        if self.particles is not None:
            bullets = [(b[8], b[9], *position, b[3], b[4], b[5], self.bullet_offset(b)) for b, position in self.bullets_now()]
            viewer = (self.me.body.x, self.me.body.y)
            keys = follow(self.particles, bullets, dt=dt)
            keys += emitters_in_view(self.particles, self.items, viewer, dt)
            self.particles.keep(keys)
            self.particles.update(dt)
            lit = follow_lights(self.lights, [(b[8], b[10], *position) for b, position in self.bullets_now()])
            self.lights.keep(lit + item_lights(self.lights, self.items, viewer))
            self.lights.update(dt)
        events, self.owed = self.owed, Events()
        return events

    @staticmethod
    def bullet_offset(bullet):
        """The trail offset a bullet came with (three numbers), or None for the effect's own."""
        offset = bullet[11] if len(bullet) > 11 else None
        if isinstance(offset, list) and len(offset) == 3 and all(isinstance(v, (int, float)) for v in offset):
            return tuple(offset)
        return None

    def bullets_now(self):
        """[(bullet, (x, y, z))]: each bullet carried on from the last snapshot by the time since."""
        age = self.bullet_age
        return [(b, (b[0] + b[3] * age, b[1] + b[4] * age, b[2] + b[5] * age)) for b in self.bullets]

    def receive(self, message):
        kind = message.get("type")
        if kind == "welcome":
            self.id = message.get("id")
            self.load(message)
        elif kind == "reload" and self.level is not None:
            self.load(message)
        elif kind == "state" and self.level is not None:
            self.apply_snapshot(message)

    def load(self, message):
        """Switch to the map (and textures) in a welcome or reload message. A reload drops what we knew
        about the old game: the others' positions, the bullets and the clock."""
        try:
            level = parse_level(json.loads(message["level"]), "the host's map")
            if self.use_atlas and message.get("atlas"):
                self.character_tile = self.use_atlas(base64.b64decode(message["atlas"]))
            world = self.make_world(level)
        except (ValueError, KeyError, TypeError) as e:      # a broken map or picture from the host
            self.ended = f"the host sent a game that cannot be loaded ({e})"
            return
        self.level, self.world = level, world
        self.items = Entities(level, world)
        self.particles = ParticleSystem(level.effects, world)
        self.lights = LightSystem(level, world)
        self.loads += 1
        self.history, self.bullets, self.game_time = {}, [], None
        self.ready = False                      # until the first snapshot of the new map

    def apply_snapshot(self, message):
        players = {int(pid): fields for pid, fields in message["players"].items()}
        mine = message["you"]
        if self.id not in players:
            return
        body = body_from(mine["body"])          # where the host has us, then what it has not caught up with
        if mine["ack"] in self.sent_at:
            self.ping = time.monotonic() - self.sent_at[mine["ack"]]
        self.sent_at = {seq: t for seq, t in self.sent_at.items() if seq > mine["ack"]}
        self.pending = [step for step in self.pending if step[0] > mine["ack"]]
        for _, wish, dt in self.pending:
            move_body(self.world, body, wish, dt)
        self.me.body = body
        self.me.stats = PlayerStats(mine["score"], mine["health"], mine["max_health"])
        self.me.inventory = inventory_from(mine, self.level)
        now = message["time"]
        self.game_time = now if self.game_time is None else self.game_time + (now - self.game_time) * CLOCK_BLEND
        for pid in list(self.history):
            if pid not in players:
                del self.history[pid]
        for pid, fields in players.items():
            if pid != self.id:
                samples = self.history.setdefault(pid, [])
                samples.append((now, fields[0], fields[1], fields[2], fields[3]))
                del samples[:-MAX_SAMPLES]
        self.bullets, self.bullet_age = message["bullets"], 0.0
        for event in message.get("fx", [])[:MAX_FX]:
            if (isinstance(event, list) and len(event) in (7, 10) and isinstance(event[0], str)
                    and all(isinstance(v, (int, float)) for v in event[1:])):
                self.particles.play(event[0], *event[1:4], tuple(event[4:7]), tuple(event[7:10]) if len(event) == 10 else None)
        for flash in message.get("flashes", [])[:MAX_FX]:
            if (isinstance(flash, list) and len(flash) == 4 and isinstance(flash[0], str)
                    and all(isinstance(v, (int, float)) for v in flash[1:])):
                self.lights.flash(*flash)
        for item, present in zip(self.items.items, message["items"]):
            item.present = present == "1"
        self.owed.fired += mine["fired"]
        self.owed.picked += mine["picked"]
        self.ready = True

    def sprites(self):
        if self.items is None:
            return []
        sprites = self.items.sprites()
        for bullet, (x, y, z) in self.bullets_now():
            sprites.append((x, y, z - bullet[6] / 2, bullet[6], bullet[7], 0.0, 1.0, 1.0 if bullet[10] else 0.0))
        if self.character_tile is not None and self.game_time is not None:
            for pid, samples in self.history.items():
                x, y, z, *angle = interpolate(samples, self.game_time - INTERP_DELAY)
                tile = character_tile_for(self.character_tile, pid, self.me.body.angle, angle[0] if angle else None)
                sprites.append((x, y, z, PLAYER_HEIGHT, tile))
        if self.particles is not None:
            sprites += self.particles.sprites()
        return sprites

    def lighting(self):
        """The Lighting to draw our view with (None until the map is known, or when it has no lights and is fully lit)."""
        if self.lights is None:
            return None
        body = self.me.body
        return self.lights.prepare((body.x, body.y, body.eye_z), self.particles)

    def status(self):
        return f" - ping {self.ping * 1000:.0f} ms, {len(self.pending)} steps unconfirmed"

    def close(self):
        self.client.close()


def interpolate(samples, t):
    """(x, y, z[, angle]) at game time t from [(time, x, y, z[, angle]), ...] oldest first: on the line
    between the two samples either side of t, and the nearest sample if t is outside them (no guessing
    ahead). An angle takes the short way round."""
    if t <= samples[0][0]:
        return tuple(samples[0][1:])
    for (t0, *a), (t1, *b) in zip(samples, samples[1:]):
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
            if len(a) > 3:
                b[3] = a[3] + (b[3] - a[3] + math.pi) % math.tau - math.pi
            return tuple(p + (q - p) * f for p, q in zip(a, b))
    return tuple(samples[-1][1:])


# ------------------------------------------------------------------ what goes in a snapshot

BODY_FIELDS = ("x", "y", "z", "angle", "pitch", "span", "vx", "vy", "vz", "on_ground")


def body_fields(body):
    return [getattr(body, name) for name in BODY_FIELDS]


def body_from(fields):
    return Player(**dict(zip(BODY_FIELDS, fields)))


def private_fields(state, owed, ack):
    """What one player is told about themselves: their body, stats, inventory, what just happened and
    the last of their steps the host has carried out."""
    inventory = state.inventory
    return {
        "body": body_fields(state.body),
        "score": state.stats.score, "health": state.stats.health, "max_health": state.stats.max_health,
        "items": dict(inventory.items), "ammo": dict(inventory.ammo), "equipped": inventory.equipped,
        "guns": [{"name": g.gun.name, "mag": g.mag, "reload_left": g.reload_left} for g in inventory.guns],
        "fired": owed.fired, "picked": owed.picked, "ack": ack,
    }


def inventory_from(fields, level):
    """A copy of the player's inventory to show on the HUD, with the guns' definitions from the map."""
    inventory = Inventory(items=dict(fields["items"]), ammo=dict(fields["ammo"]), equipped=fields["equipped"])
    known = {gun.name: gun for gun in level.guns}
    for g in fields["guns"]:
        if g["name"] in known:
            inventory.guns.append(GunState(known[g["name"]], mag=g["mag"], reload_left=g["reload_left"],
                                           inventory=inventory))
    if inventory.equipped is not None and not 0 <= inventory.equipped < len(inventory.guns):
        inventory.equipped = None
    return inventory
