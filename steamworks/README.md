# Steamworks SDK files

The parts of Valve's Steamworks SDK the game needs to play over Steam (`steamnet.py`), copied from the SDK's
`redistributable_bin` folder. The SDK itself is only downloadable after logging in at
https://partner.steamgames.com/downloads, so the files the build needs are kept here; the SDK's licence lets
them be shipped with the game.

| File | From the SDK | SDK version | SHA-256 |
|---|---|---|---|
| `win64/steam_api64.dll` | `sdk/redistributable_bin/win64/steam_api64.dll` | 1.65 (23 July 2026) | `e6d9bafb9a41e42fba7b21553db49f8719027af3f0deb23ff86cfc44d60e776d` |

`steamnet.py` loads it from here when run from source, and `raycast-game.spec` bundles it into the built game.

To update: download the new SDK, copy the file over, update the table, and check `steamnet.py`'s structs and
interface versions against the new headers (`sdk/public/steam/steam_api_flat.h`, `steamnetworkingtypes.h`).
