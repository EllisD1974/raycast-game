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

Effects are none, score or health, picked from a drop-down list. Score and health show in the corner
of the game view.

Items can also move. An item has a list of animations (none by default); add one from the
Details pane's "+ Add animation" list and each one has its own settings:

| Animation | Settings |
|---|---|
| Float | speed (bobs per second) and height (how far it rises) |
| Rotate | speed (turns per second) |

Add both for an item that floats and spins.
`maps/items.json` is a small example.

## Prefabs

A prefab is an item you design once and reuse: its icon (the sprite the player sees in the world),
mode, effect, size and animations. Make them in the editor's **Prefabs** section (`P`): add a prefab,
click a tile in the atlas to set its icon, and set the rest in the Details pane. For example a "9mm
box" prefab with the Give ammo effect and a bullet icon, a "Heart" prefab that heals, or a "Pistol
pickup" that gives the pistol. They are saved in the map file.

To place them, choose the Entity tool (`N`): with nothing selected, the pane on the right lists
"Plain item" and your prefabs. Pick one and click cells. Items placed from a prefab stay linked to
it, so editing the prefab updates every copy in the map. Select a placed copy to switch it to another
prefab, or choose (none) to detach it, which keeps its settings so you can edit it on its own. A
plain item's pane also has "Save as a new prefab".

## Inventory and guns

Some items are kept instead of used up. Give an item the **Inventory item** effect (a name and a
count) and picking it up adds it to the inventory, which is listed at the bottom left of the game
view. The effects **Give a gun** and **Give ammo** hand out the guns defined in the map's Guns
section (below); picking a gun up loads it with its starting spare ammunition and equips it.

Playing: left mouse button fires (hold for full auto), `R` reloads, `1`-`9` take out that gun
(press it again to put it away), and the mouse wheel steps through your guns.

The editor's **Guns** section (`G`, or the Guns button) lists the map's guns. Select one to edit it in
the Details pane:

| Setting | |
|---|---|
| Name, Sprite, Sprite size | the picture drawn in your hands (click the Sprite row, then an atlas tile) |
| Fire mode | **Single shot**: one round per pull, reloads after every shot; **Semi-auto**: one round per pull; **Full auto**: fires while held |
| Shot type | **Single bullet**: one bullet per shot; **Multi bullet**: several bullets at once (a shotgun), each aimed a little differently by the spread; **Projectile**: reserved for rockets and the like, fires as a single bullet for now |
| Bullets / shot | how many bullets a multi shot sends (one round of ammunition either way) |
| Damage, Shots / second | per bullet, and shots per second |
| Ammo type | which kind of ammunition it uses (see below); guns using the same type share one pool of spare rounds |
| Rounds / mag, Spare rounds, Reload time | magazine size (not used by single shot), spare rounds of its ammo type given with the gun, seconds to reload |
| Spread | random aim error in degrees |

**Ammunition** is defined in the same section (the Ammunition list under the guns). An ammo type has
the bullet's sprite, size, speed and range and a damage multiplier (an armour-piercing round might be
x2). Give several guns the same ammo type and they draw on one shared pool of spare rounds, so a
pistol and an SMG can both use 9mm; each gun still has its own magazine. An item with the **Give
ammo** effect names an ammo type and adds rounds to that pool (even before you own a gun for it).
A gun with no ammo type fires a plain default bullet. Maps saved before ammo types existed
have one made for each gun from its old bullet settings, when they are loaded.

Bullets fly where you look (up and down included) and stop at walls, floors, ceilings and glass.
Nothing takes damage yet, so damage is stored on the bullet for when something can. `maps/guns.json`
has three example guns and pickups.

## Layout

    main.py, map_editor.py, ...   game and editor source
    assets/                       textures.png (the texture atlas)
    maps/                         map.json (default map) and the demo maps (items.json has pickups,
                                  guns.json guns, an inventory item and prefabs)
    tests/
