"""The game's and the map editor's version, shown on the home screen and in the window titles.

A built program reads it from version.txt, which the build (raycast-game.spec) puts next to its other files. Run from
the source it is worked out from the git tags (v0.7b, v0.8b, ...):

    release_version()  the tag on the checked-out commit without its "v" (0.7b), or the dev version when it has none
    dev_version()      the latest tag one minor version on, marked as a dev build (0.8b-dev after v0.7b)

`uv run build` (buildtool.py) always builds a dev version; the Build workflow builds the release version, so a build
made from a tag carries that tag and one made from anything else is marked dev.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = "version.txt"
TAG_PATTERN = "v[0-9]*"                          # release tags; not backup/... and the like
UNKNOWN = "unknown"


def _git(*args):
    """The output of a git command run in the project folder, or None when it fails (no git, no tags)."""
    try:
        done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None


def next_minor(tag):
    """`tag` one minor version on, with its "v" taken off and the rest kept: v0.7b -> 0.8b, v1.2.3 -> 1.3."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.\d+)?(.*)", tag)
    if not match:
        return None
    major, minor, rest = match.groups()
    return f"{major}.{int(minor) + 1}{rest}"


def dev_version():
    """The version a build made between releases carries: the latest tag one minor version on, then -dev."""
    tag = _git("describe", "--tags", "--abbrev=0", "--match", TAG_PATTERN)
    upcoming = next_minor(tag) if tag else None
    return f"{upcoming or '0.1'}-dev"


def release_version():
    """The tag on the checked-out commit (its "v" taken off), or the dev version when the commit has no tag."""
    tag = _git("describe", "--tags", "--exact-match", "--match", TAG_PATTERN)
    return tag[1:] if tag and tag.startswith("v") else tag or dev_version()


def _read_version():
    folder = getattr(sys, "_MEIPASS", ROOT)       # a built program's files are in _MEIPASS
    try:
        with open(os.path.join(folder, VERSION_FILE), encoding="utf-8") as f:
            return f.read().strip() or UNKNOWN
    except OSError:
        pass
    if getattr(sys, "frozen", False):
        return UNKNOWN                            # built without version.txt: no git to ask
    return dev_version()


VERSION = _read_version()


def label():
    """How the version is shown: v0.7b, v0.8b-dev."""
    return VERSION if VERSION == UNKNOWN else f"v{VERSION}"
