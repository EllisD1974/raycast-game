"""PyInstaller runtime hook: runs before the game starts, from inside the built program.

numba keeps what it has compiled (the renderer) in a cache so later starts are quick. By default that is next to the source
files, which inside the program's folder may not be writable, so it is moved to the player's own folder. The first start
compiles the renderer (some seconds); later starts reuse it.
"""
import os
import tempfile

base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache") or tempfile.gettempdir()
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(base, "raycast-game", "numba-cache"))
