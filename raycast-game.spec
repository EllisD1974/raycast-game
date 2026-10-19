# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe: builds the game and the map editor as two programs in one folder (dist/RaycastGame/).

    uv run pyinstaller raycast-game.spec --noconfirm

dist/RaycastGame/RaycastGame.exe   the game          (RaycastGame.exe --map maps/other.json, --host ..., --join ...)
dist/RaycastGame/RaycastEditor.exe the map editor    (its "Play" button starts RaycastGame.exe next to it)

The folder carries assets/textures.png, assets/character.png and the maps next to the programs' own files. The renderer's numba source files are
included too: numba compiles from them (and caches the result) when the program starts.
"""
import os

root = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(root, "assets", "textures.png"), "assets"),
    (os.path.join(root, "assets", "character.png"), "assets"),
    (os.path.join(root, "maps"), "maps"),
]
for source in ("raykernel.py", "raypitch.py", "raylight.py"):     # numba reads these to compile and cache the renderer
    datas.append((os.path.join(root, source), "."))

analysis_options = dict(
    pathex=[root],
    datas=datas,
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
