# raycast-game

A raycaster with stacked floors, ramps and a built-in map editor.

## Setup

Requires [uv](https://docs.astral.sh/uv/). It installs Python 3.13 and the dependencies into `.venv`:

    uv sync

## Run

    uv run python main.py            # the home screen: host or join a game, or change the settings
    uv run python main.py --map maps/map.json    # straight into a map, as the editor's Play does
    uv run python map_editor.py      # edit a map (F5 saves and plays)

The home screen's **Host game** picks a map from the `maps` folder, a password (needed) and the most players
to let in (2 to 16, the host included); **Join game** takes the host's IP address, its port (7777, unless the
host uses another) and its password. The map and the most players are remembered for next time (passwords
are not). Leaving a game from its menu, or the host ending it, goes back to the home screen.

## Particle effects

Design effects in the editor's Effects section (X): pick a particle picture from the atlas, choose a burst
or a stream, and shape how many, how long they live, speed, spread, gravity, drag, size and fade while a
live side view plays them. Effects are saved in the map and used by name:

An effect can start its particles away from the point it is played at (**Start offset X / Y** and **Start height**)
and send them in a fixed **Direction** instead of the automatic one (up from an item, along the aim from a gun,
back along the path from a bullet). Offsets and a custom direction are along the map's axes (x east, y south,
z up), or with **Heading** axes, x ahead and y to the right of the automatic direction. A gun, an ammo type or an
item that uses an effect can also **override** the start offset for itself (its *Start offset* row), always along
the heading (map axes for an item).

- a gun's **Bullets ahead / right / up** say where its bullets come from (and where its muzzle effect and flash start);
  rather than typing numbers, drag the orange disc (bullets) and the cyan diamond (muzzle effect) on the gun
  preview picture itself (sideways and up), and use the Depth slider to move the picked one in and out of the screen;
  the wheel scrolls the Guns section if it does not all fit;
- a gun's **Muzzle effect** plays where it fires (the Guns section shows it live: tick *Fire continuously* to see the
  gun fire, reload, and play its effects and lights on repeat);
- an ammo type's **Trail effect** follows its bullets through the air;
- an item's **Emits** sends the effect up from the item. Set its Mode to *Scenery* (it cannot be picked
  up) and Sprite to *Hidden* to see only the particles.

Effects only change how things look. Each player's machine works the particles out itself; when you host,
joiners are only told "play this effect here" (for shots), and bullet trails and item emitters are drawn
from what they already see. Particles need small pictures in `assets/textures.png` (a soft dot with
transparent edges works best).

## Lighting

Design lights in the editor's Lights section (L): a color, brightness, reach, flicker and flash length, with a
preview from above. The first row, **Map ambient light**, sets how bright the map is without lights (1 is
fully lit, as maps always were; lower makes it dark so lights show). Lights are saved in the map and used by
name:

- a gun's **Muzzle light** flashes where it fires, and an ammo type's **Bullet light** travels with its bullets;
- an effect's **Particle light** makes every particle glow (nearby ones merge into one light, and the particles
  are drawn at full brightness);
- an item's **Light** lights up around it; with Mode *Scenery* and Sprite *Hidden* an item is just a light placed
  in the map;
- **Glowing wall tile** (on a light) makes every wall made from that atlas tile light the open cells beside it.

Walls stop light (a lit room does not light the room behind its wall), but lights do not tell floors above and
below apart. Only the 12 strongest lights near the camera are used for a picture, and lighting adds a few
milliseconds to a frame. Like particles, lights are only for looks and are worked out on each player's machine.

## Multiplayer

One player hosts with a password and the others join with it. The host runs the game and sends its map
(guns, items, effects, lights and all) and its `textures.png` to every joiner as they join, so joiners need
no map or textures of their own, only the same code.

To publish an update, save the map (from the editor) or `textures.png` on the host's machine. The host
notices within a second, loads them and sends them to everyone playing, who switch over without
rejoining. A reload starts everyone over at the map's start with full health and no guns (scores are
kept), because the new map may not have the old guns. A map or picture that cannot be read is reported on
screen and the game carries on with the old one. This works when playing alone too.

The host can also move everyone to another map while playing: Esc opens the menu, and **Host settings >
Change map** lists the maps in the current map's folder. Everyone switches over the same way, without
rejoining, and the host's live reload then follows the new map.

In the game, Esc opens a menu: **Resume**, **Settings** (mouse sensitivity and fullscreen, kept between runs),
**Host settings** (for the host) and **Leave game** (back to the home screen; **Exit game** when the game was
started straight into a map). Playing alone, the menu pauses the game; in a hosted game
it carries on for everyone else.

From the command line, without the home screen:

    uv run python main.py --host SECRET                      # host (listens on 0.0.0.0:7777)
    uv run python main.py --join 127.0.0.1 SECRET            # join (use the host's address)

Add `--port N` to either to use another port (and `--bind 127.0.0.1` to the host to accept only this
machine). Over the internet the host needs the port forwarded, or a VPN such as Tailscale.

## Build an exe (Windows)

GitHub: **Actions > Build exe > Run workflow** (choose the branch; it runs the tests first unless you untick that). When it
finishes, download the `RaycastGame-windows-<run number>` artifact from the run's page: unzip it and run
`RaycastGame.exe` (the game) or `RaycastEditor.exe` (the map editor; its Play button starts the game next to it). The
flags work as on the command line, e.g. `RaycastGame.exe --host SECRET`.

To build the same thing on your own machine:

    uv sync --group dev
    uv run pyinstaller raycast-game.spec --noconfirm        # makes dist/RaycastGame/

The first start compiles the renderer (about 20 seconds); it is cached in `%LOCALAPPDATA%
aycast-game
umba-cache`, so
later starts take a second or two. Maps are read from and saved to the `maps` folder next to the programs.

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
A gun with no ammo type fires a plain default bullet.

An ammo type can **explode** (set Explosion to "Explodes"): where it strikes it blows up, hurting and throwing
every player within the Blast radius, the one who fired it included. Damage and knockback are greatest at the
center and fade to nothing at the edge; a player the bullet hits directly takes its own damage plus the full
Blast damage, so a direct hit does the most. Knockback (cells per second, along the line from the blast to the
player) is multiplied by "Air knockback x" for a player who is in the air. Self damage x and Self knockback x
scale what the shooter takes from their own blast: a small damage multiplier with full knockback makes the
ammo rocket-jumpable. Walls, floors and glass shield: the share of a player's body in sight of the blast
scales both. The Explosion effect and light rows play at the blast, on top of the ordinary hit effects. Maps saved before ammo types existed
have one made for each gun from its old bullet settings, when they are loaded.

Bullets fly where you look (up and down included) and stop at walls, floors, ceilings and glass.
Nothing takes damage yet, so damage is stored on the bullet for when something can. `maps/guns.json`
has three example guns and pickups.

## Layout

    main.py, map_editor.py, ...   game and editor source
    assets/                       textures.png (the texture atlas), character.png (other players' pictures: make_character.py)
    maps/                         map.json (default map) and the demo maps (items.json has pickups,
                                  guns.json guns, an inventory item and prefabs)
    tests/
