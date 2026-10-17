# raycast-game

A raycaster with stacked floors, ramps and a built-in map editor.

## Setup

Requires [uv](https://docs.astral.sh/uv/). It installs Python 3.13 and the dependencies into `.venv`:

    uv sync

## Run

    uv run python main.py            # play (uses maps/map.json)
    uv run python map_editor.py      # edit a map (F5 saves and plays)

## Test

    uv run pytest

## Items

Maps can hold items: flat sprites that always face the player. Touching one picks it up. In the
editor use the Entity tool (N); each item has a mode and an effect:

| Mode | When touched |
|---|---|
| Pick up once | gives its effect and disappears for good |
| Respawns | gives its effect, disappears, and comes back after a set time |
| Stays | gives its effect and stays; it counts again only after you step away and return |

Effects are none, score or health. Score and health show in the corner of the game view.
`maps/items.json` is a small example.

## Layout

    main.py, map_editor.py, ...   game and editor source
    assets/                       textures.png (the texture atlas)
    maps/                         map.json (default map) and the demo maps (items.json has pickups)
    tests/
