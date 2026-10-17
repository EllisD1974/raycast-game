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

## Layout

    main.py, map_editor.py, ...   game and editor source
    assets/                       textures.png (the texture atlas)
    maps/                         map.json (default map) and the demo maps
    tests/
