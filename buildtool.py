"""`uv run build`: builds the game and the map editor locally (dist/RaycastGame/), for testing.

The build is given the dev version (version.dev_version(): the latest tag one minor version on, marked -dev, so 0.8b-dev
after v0.7b); releases are built by the Build workflow, from their tag. Anything after `uv run build` is handed on to
PyInstaller (uv run build --clean).
"""
import os
import subprocess
import sys

import version


def main():
    build_version = version.dev_version()
    print(f"Building version {build_version} into dist/RaycastGame/")
    env = dict(os.environ, RAYCAST_VERSION=build_version)
    command = [sys.executable, "-m", "PyInstaller", os.path.join(version.ROOT, "raycast-game.spec"), "--noconfirm",
               *sys.argv[1:]]
    sys.exit(subprocess.run(command, cwd=version.ROOT, env=env).returncode)


if __name__ == "__main__":
    main()
