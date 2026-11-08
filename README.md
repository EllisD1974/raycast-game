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
    ISCC packaging\installer.iss                           # then dist/RaycastGameSetup.exe (Inno Setup 6)

The first start compiles the renderer (about 20 seconds); it is cached in `%LOCALAPPDATA%\raycast-game\numba-cache`, so
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
`maps/tests/items.json` is a small example.

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
Nothing takes damage yet, so damage is stored on the bullet for when something can. `maps/tests/guns.json`
has three example guns and pickups.

## Map settings and the buy menu

The editor's **Map settings** section (`J`) says how a map is played; the settings are saved in the map.

**Game rules**:

| Setting | |
| --- | --- |
| Game mode | **Free for all** (everyone against everyone), **Two teams** (players are split between team 1 and team 2 as they join; a teammate's name shows white), **Co-op** (everyone on one team), **Bomb defusal** (rounds, as in Counter-Strike: see below) or **King of the Hill** (a capture point, as in Team Fortress 2: see below) |
| Friendly fire | whether bullets and blasts hurt teammates (your own blast always hurts you) |
| Max health | the health every player starts and comes back with |
| Start money | money a player has when they join |
| Score / kill, Money / kill | what knocking out an opponent earns |
| Starting gun | a gun every player comes in (and back) with |

Score and money are kept when a player is knocked out. The HUD shows money on maps where it means something.

**Buy menu**: turn it on and players open it with `B` in the game. **Costs** is **Free** (everything is free),
**Money** or **Score**: an entry is only given to a player who has its price, which is then taken off. Add entries
with "+ Add to buy menu" (or the buy menu row's "+ Add" list of the map's guns). An entry gives **a gun**, an
**inventory item** or **health** (ammo is not sold: guns come with their own, filled up again each bomb defusal
round), and has a price, an optional
button text and an icon (a gun shows its own picture when it has none); "Move up / down" orders the menu. Beside the
list is the menu as a player who just joined sees it. In the game, entries a player cannot afford are greyed out.
When you join someone, the host decides what each purchase gives, as with pickups.

## Bomb defusal

Counter-Strike's mode, played in rounds. Players are split into **Terrorists** (T, team 1) and **Counter-Terrorists**
(CT, team 2). One T carries the bomb; the Ts win the round by planting it in a bomb site and letting it explode, or
by eliminating the CTs. The CTs win by eliminating the Ts before the bomb is planted, by defusing it, or when the
round time runs out without a plant. A player knocked out stays out until the next round and watches a teammate
(click for the next one).

- **A round**: the **freeze time** (nobody can move; look around and buy), then the **round time** (the timer at the
  top). Once the bomb is planted the timer becomes the **bomb timer** (red). When the round is decided its result
  shows for the **round end pause**, then the next round starts: everyone back at their team's spawn points, those
  who lived keeping what they carry (with every gun's magazine full and its spare rounds back to what the gun comes
  with), the others coming back with the starting gun.
- **The bomb**: hold `E` standing in a bomb site to plant it (you cannot move meanwhile; letting go starts over).
  `G` throws it the way you look; it also drops where its carrier is knocked out, and any T walking over it picks it up. A CT holds `E`
  at the planted bomb to defuse it, faster with a **Defuse kit** (an inventory item of that name: sell it in the buy
  menu). The explosion hurts everyone in its radius, most at the bomb, through walls.
- **Buying**: the buy menu is open during the freeze time and the buy time after it.
- **Money** (as in Counter-Strike): the winners get the round win money (more for a win by the bomb exploding or
  being defused); the losers get the loss money, plus the loss bonus for each round they lost in a row before it, up
  to a most. Ts get the plant money when they planted but lost, and the planter or defuser a bonus. Ts still alive
  when the time runs out get nothing.
- **A match** is the rounds in a match (24): the teams swap sides (and start over with the start money) after half
  of them, and the first team to win more than half wins the match; a new one starts after it.

All of these are **Map settings** with Bomb defusal chosen, with Counter-Strike's defaults: freeze 15 s, round
1:55, buy time 20 s, bomb 40 s, plant 3.2 s, defuse 10 s (5 s with a kit), pause 7 s, 24 rounds, bomb damage 500 over
27 cells, $3250 a round won ($3500 by the bomb), $1400 a round lost plus $500 a loss in a row up to $3400, $800 to
the Ts when they planted, $300 for planting or defusing, at most $16000. Choose the explosion's particle effect and
light there too.

In the editor, the **Sites** layer (`9`) marks where the bomb can be planted: paint bomb site **A** or **B** (`R`
switches) on each floor, and erase it the same way. The Spawn tool's **Team** button gives spawn points to the Ts or
the CTs (or anyone); a team without spawn points of its own uses the others. `maps/sand2.json` is set up for it:
both bomb sites, spawn points for each team, and a buy menu with a defuse kit. The bomb's picture is tile 26 of
`textures.png`.

## King of the Hill

Team Fortress 2's mode. Players are split into **RED** (team 1) and **BLU** (team 2), who fight over one capture point,
the hill. Each team has its own clock (3:00). Owning the point runs your own clock down while the other team's stands
still, and the first team whose clock reaches zero wins the round.

- **The point** is neutral and locked for the first 30 seconds of a round (the timer at the top says when it unlocks).
- **Capturing**: stand on the point with nobody from the other team on it. One player alone takes the **capture time**;
  more take less, as in Team Fortress 2 (two players are 1.5 times as fast, three 1.83 times, and so on). With players
  of both teams on it the point is **contested** and the capture stands still. The owners standing on their point push
  the other team's capture back, and on a neutral point a team first pushes back what the other team has captured.
  With nobody on it, capture progress drains away over the **capture decay** time (90 s for a whole capture).
- **Time added per capture**: each capture adds a few seconds (10 by default) to the capturing team's clock, never past
  its full time, so a team that loses the point late has to hold it a little longer when it takes it back. (Team
  Fortress 2 does not do this: set it to 0 for its rules.)
- **Overtime**: when the owners' clock runs out while the other team has capture progress or stands on the point, the
  round goes on until that progress has drained away (six times faster than usual) or the other team captures.
- **Respawning**: a knocked out player comes back at their team's spawn points after the **respawn time** (5 s),
  watching a teammate meanwhile (click for the next one).
- **Rounds**: the round's result shows for the round end pause, during which the losers cannot shoot. Then everyone
  starts the next round at their spawn points with what a new player carries. The first team to win the **rounds to
  win** (2) wins the match, and a new one starts.

The game shows both clocks at the top (the running one bright and outlined) either side of the point, which is drawn in
its owner's color and ringed by the capture progress; standing on the point shows a capture bar. A marker floats over
the point in the world, in its owner's color.

All of these are **Map settings** with King of the Hill chosen. In the editor, paint the point on the **Sites** layer
(`9`): `R` steps through bomb site A, B and **Hill** (green, marked H). The Spawn tool's **Team** button gives spawn points to
RED or BLU, and the buy menu works as in the other modes. The marker's pictures are tiles 27-29 of `textures.png`
(neutral, RED, BLU).

## Barriers (spawn protection)

A barrier lets one team through and stops everyone else, as Team Fortress 2's spawn room doors do: that team's players
walk through it and its bullets fly through it, while other teams' players, and their bullets, are stopped as by glass.
Blasts, the bomb and particles do not go through it at all, and a player on no team (free for all) is always stopped.
It is drawn as a see-through, striped field in the team's color (tiles 30 and 31 of `textures.png`).

In the editor, paint barriers on the **Sites** layer (`9`): `R` steps through bomb site A, B, the hill, then **barrier
team 1** (T, RED; marked |1) and **barrier team 2** (CT, BLU; marked |2). Put them across the doorways of a team's spawn
room. Barriers only work on the ground floor (floor 1); they fill its room from floor to ceiling.

## Layout

    main.py, map_editor.py, ...   game and editor source
    assets/                       textures.png (the texture atlas), character.png (other players' pictures: make_character.py)
    maps/                         map.json (default map) and the other maps the game lists
    maps/tests/                   maps made for testing, which the game and editor do not list (items.json has
                                  pickups, guns.json guns, an inventory item and prefabs)
    tests/
