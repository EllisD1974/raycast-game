# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe: builds the game and the map editor as two programs in one folder (dist/RaycastGame/).

    uv run pyinstaller raycast-game.spec --noconfirm

dist/RaycastGame/RaycastGame.exe   the game          (RaycastGame.exe --map maps/other.json, --host ..., --join ...)
dist/RaycastGame/RaycastEditor.exe the map editor    (its "Play" button starts RaycastGame.exe next to it)

On Linux the same command makes dist/RaycastGame/RaycastGame and RaycastEditor (no .exe), with libsteam_api.so in place
of steam_api64.dll. PyInstaller cannot cross-build: the Linux build is made on Linux (.github/workflows/build-linux.yml).

The folder carries assets/textures.png, assets/character.png and the maps next to the programs' own files. The renderer's numba source files are
included too: numba compiles from them (and caches the result) when the program starts.
"""
import glob
import os
import sys

root = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(root, "assets", "textures.png"), "assets"),
    (os.path.join(root, "assets", "character.png"), "assets"),
] + [(path, "maps") for path in glob.glob(os.path.join(root, "maps", "*.json"))]    # (not maps/tests: made for testing)
for source in ("raykernel.py", "raypitch.py", "raylight.py"):     # numba reads these to compile and cache the renderer
    datas.append((os.path.join(root, source), "."))
binaries = []
steam_api = os.path.join(root, "steamworks", *({"win32": ("win64", "steam_api64.dll")}.get(sys.platform)
                                              or ("linux64", "libsteam_api.so")))   # for playing over Steam (steamworks/README.md)
if os.path.exists(steam_api):
    binaries.append((steam_api, "."))

analysis_options = dict(
    pathex=[root],
    datas=datas,
    binaries=binaries,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[os.path.join(root, "packaging", "pyi_rth_numba.py")],
    excludes=["tkinter", "pytest", "matplotlib", "scipy", "pandas", "IPython"],
    noarchive=False,
)

game = Analysis([os.path.join(root, "main.py")], **analysis_options)
editor = Analysis([os.path.join(root, "map_editor.py")], **analysis_options)
MERGE((game, "main", "RaycastGame"), (editor, "map_editor", "RaycastEditor"))

game_pyz = PYZ(game.pure)
editor_pyz = PYZ(editor.pure)

game_exe = EXE(game_pyz, game.scripts, [], exclude_binaries=True, name="RaycastGame", console=False, upx=False)
editor_exe = EXE(editor_pyz, editor.scripts, [], exclude_binaries=True, name="RaycastEditor", console=False, upx=False)

COLLECT(game_exe, game.binaries, game.datas,
        editor_exe, editor.binaries, editor.datas,
        strip=False, upx=False, name="RaycastGame")
