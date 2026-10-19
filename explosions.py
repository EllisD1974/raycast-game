"""Explosions: who a blast reaches, how hard it hurts them and which way it throws them. No pygame.

A blast is centered where the bullet struck. A player's reach from it is the distance to the nearest
point of their body, and damage and knockback fall off in a straight line from full at the center to
nothing at the blast radius. Walls shield: three points on the body (feet, middle, head) are each checked
for a clear line to the blast, and the share that can be seen scales the damage and knockback.
"""
import math

from constants import PLAYER_HEIGHT, PLAYER_RADIUS

LIFT = 0.35                     # upward lean added to the throw, so a blast at your feet launches you up
SAMPLES = (0.1, PLAYER_HEIGHT / 2, PLAYER_HEIGHT - 0.1)     # heights above the feet that are checked for cover


def body_distance(x, y, z, body):
    """How far (x, y, z) is from the nearest point of the player's upright cylinder."""
    flat = max(0.0, math.hypot(x - body.x, y - body.y) - PLAYER_RADIUS)
    up = max(body.z - z, z - (body.z + PLAYER_HEIGHT), 0.0)
    return math.hypot(flat, up)


def exposure(world, x, y, z, body):
    """The share (0 to 1) of the player's body in sight of the blast."""
    seen = sum(world.line_clear((x, y, z), (body.x, body.y, body.z + h)) for h in SAMPLES)
    return seen / len(SAMPLES)


def throw(x, y, z, body, speed):
    """(vx, vy, vz) of a throw of `speed` from the blast at (x, y, z) to the player's middle, leaning upward."""
    dx, dy, dz = body.x - x, body.y - y, body.z + PLAYER_HEIGHT / 2 - z + LIFT
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-9:
        return 0.0, 0.0, speed
    return dx / length * speed, dy / length * speed, dz / length * speed


def blast_results(world, blast, x, y, z, owner, bodies):
    """What an explosion of the ammo type `blast` at (x, y, z) does: [(player id, damage, (vx, vy, vz))] for each
    player it reaches. `owner` fired it (they take the self multipliers) and `bodies` is [(id, body)]. A player
    the bullet struck head on is at the center, so takes the full blast on top of the bullet's own damage."""
    out = []
    for pid, body in bodies:
        reach = body_distance(x, y, z, body)
        if reach >= blast.blast_radius:
            continue
        share = (1.0 - reach / blast.blast_radius) * exposure(world, x, y, z, body)
        if share <= 0.0:
            continue
        damage = blast.blast_damage * share
        speed = blast.knockback * share * (blast.air_knockback_mult if not body.on_ground else 1.0)
        if pid == owner:
            damage *= blast.self_damage_mult
            speed *= blast.self_knockback_mult
        out.append((pid, damage, throw(x, y, z, body, speed)))
    return out
