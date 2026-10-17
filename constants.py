"""Numbers shared by the game, the physics and the map checks.

World units: one grid cell is 1 x 1. Default rooms are 1.0 tall (floor 0, ceiling 1.0),
which matches how walls looked before heights existed.
"""
TILE = 32                       # texture size in pixels

# view
WIDTH, HEIGHT = 640, 360        # internal render resolution (16:9)
FOV_DEG = 66.0
MAX_DEPTH = 20.0
FOG_DIST = 12.0                 # distance at which surfaces reach minimum brightness

# player
EYE_HEIGHT = 0.5                # eye above the feet
PLAYER_HEIGHT = 0.8             # needs this much space between floor and ceiling
PLAYER_RADIUS = 0.2             # how close the camera may get to a wall
STEP_HEIGHT = 0.3               # tallest ledge you can walk up (stairs of 0.25 are fine)
MOVE_SPEED = 3.0                # cells per second
SPRINT_MULTIPLIER = 1.6         # holding Shift with a movement key: MOVE_SPEED * this
TURN_SPEED = 2.0                # radians per second (keyboard turning)
MOUSE_SENSITIVITY = 0.0025      # radians of turning per screen pixel the mouse moves
MAX_PITCH_DEG = 90.0            # how far up or down you can look (90 = straight up / down)
GRAVITY = 9.0
JUMP_SPEED = 2.6                # peak jump height = JUMP_SPEED^2 / (2 * GRAVITY), about 0.37
