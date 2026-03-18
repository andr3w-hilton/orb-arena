# Orb Arena - Code Split TODO

Break `server.py` (~3,500 lines) and `index.html` (~5,500 lines) into logical modules.

**Approach:**
- Python: 7-file module split with clean import DAG
- JS: Plain `<script>` tags with shared `OrbArena` namespace object (NOT ES modules - HTTP whitelist blocks them)

**Do phases in order. Never start the next phase until the current one passes its validation check.**

---

## Phase 1 - Python Split

### Step 1 - Create `constants.py`
Extract from `server.py`:
- Lines 32-127: all constant definitions
- Lines 128-214: `_compute_rally_layout()` function + `RALLY_BARRIER_POSITIONS`, `RALLY_CHECKPOINT_POSITIONS` assignments
- Lines 249-265: `_dist_to_track()` utility function
- Lines 656-672: `DISASTER_TYPES`, `TURRET_POSITIONS`, challenge config constants

`constants.py` has no local imports - pure Python stdlib only (`math`, `random`).

### Step 2 - Create `entities.py`
Extract from `server.py`:
- Lines 341-648: all dataclasses - `BaseOrb`, `EnergyOrb`, `SpikeOrb`, `GoldenOrb`, `PowerUpOrb`, `Projectile`, `HomingMissile`, `WormholePortal`, `Mine`, `MinePickup`, `MissileTurret`, `Wall`, `Meteor`, `BlackHole`, `BossOrb`, `Player`, `Spectator`

Add at top: `from constants import *`
Imports: `dataclasses`, `math`, `random`, `typing`

### Step 3 - Create `utils.py`
Extract from `server.py`:
- `safe_float()` function
- `sanitize_name()` function

No local imports needed.

### Step 4 - Create `scores.py`
Extract from `server.py`:
- Score list globals: `missile_magnet_scores`, `rally_run_scores`, `all_time_scores`, `boss_hunt_scores`
- `SCORES_PATH` constant
- `load_scores()`, `save_scores()`
- All `record_*()` functions: `record_challenge_score`, `record_rally_score`, `record_boss_hunt_score`, `record_alltime_score`
- Call `load_scores()` at the bottom of the file (module-level, runs on import)

No local imports needed - `json`, `pathlib`, `typing` only.

### Step 5 - Create `disasters.py`
Extract from `server.py`:
- `DisasterManager` class (lines 699-1173)

**Critical - circular import fix:** `DisasterManager.__init__` takes a `game` parameter of type `GameState`, but `game.py` hasn't been created yet and importing it would cause a circular dependency.

Fix at top of `disasters.py`:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from game import GameState
```

The `self.game` attribute works fine at runtime - Python never actually imports `game.py` from within `disasters.py`. Only the type hint uses it, and only during static analysis.

Imports: `entities`, `constants`, `utils`, `math`, `random`, `asyncio`

### Step 6 - Create `game.py`
Extract from `server.py`:
- `GameState` class (lines 1176-2354)

Imports: `from constants import *`, `from entities import *`, `from utils import *`, `from disasters import DisasterManager`

### Step 7 - Create `challenges.py`
Extract from `server.py`:
- `ChallengeGame(GameState)` class
- `RallyRunGame(GameState)` class
- `BossHuntGame(GameState)` class

Imports: `from game import GameState`, `from entities import *`, `from constants import *`, `from utils import *`

### Step 8 - Update `server.py`
Remove all extracted code. Add imports at the top:
```python
from constants import *
from entities import *
from utils import safe_float, sanitize_name
from scores import (missile_magnet_scores, rally_run_scores,
                    all_time_scores, boss_hunt_scores,
                    record_challenge_score, record_rally_score,
                    record_boss_hunt_score, record_alltime_score)
from disasters import DisasterManager
from game import GameState
from challenges import ChallengeGame, RallyRunGame, BossHuntGame
```

Keep in `server.py`:
- `game = GameState()` module-level instance
- Rate limiting globals, `active_connections`
- All async handlers: `broadcast_state`, `run_challenge_loop`, `run_rally_loop`, `run_boss_loop`, `handle_client`
- `SafeHTTPHandler`, `start_http_server`, `main()`

### Phase 1 Validation Check
```bash
cd C:/Users/ahilt/PycharmProjects/orb-arena
python server.py
```
Server must start, bind ports, and accept a WebSocket connection before moving to Phase 2.
Also verify scores load: check that the score lists are populated (or empty lists on fresh run).

---

## Phase 2 - HTTP Server Update

### Step 9 - Update `SafeHTTPHandler.do_GET()` to serve JS files
In `server.py`, find `ALLOWED_HTTP_FILES = {"/", "/index.html"}` and the `do_GET` method.

Add handling for `static/js/` path:
```python
elif path.startswith("/static/js/") and path.endswith(".js"):
    file_path = os.path.join(os.path.dirname(__file__), path.lstrip("/"))
    if os.path.isfile(file_path):
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript")
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())
    else:
        self.send_error(404)
```

Also create the directory: `static/js/` inside the orb-arena project root.

### Phase 2 Validation Check
- Start the server
- Create a dummy file `static/js/test.js` containing `console.log("ok")`
- Fetch it: `curl http://localhost:8080/static/js/test.js`
- Must return the JS content with a 200, not a 404 HTML page
- Delete `test.js` after confirming

---

## Phase 3 - JavaScript Split

All files go in `static/js/`. Each file opens with:
```js
window.OrbArena = window.OrbArena || {};
```
Then attaches its exports to the namespace.

Load order in `index.html` matters - each file must load after its dependencies.

### Step 10 - Create `static/js/config.js`
Extract from `index.html`:
- `POWERUP_COLORS` object
- `DISASTER_NAMES` object
- `PROJECTILE_MIN_RADIUS` constant

```js
window.OrbArena = window.OrbArena || {};
OrbArena.config = {
    POWERUP_COLORS: { ... },
    DISASTER_NAMES: { ... },
    PROJECTILE_MIN_RADIUS: 25
};
```

No dependencies. Loads first.

### Step 11 - Create `static/js/state.js`
Extract from `index.html`:
- `state` object (central server snapshot)
- VFX arrays: `particles`, `killPopups`, `killRings`, `prevStrikeMap`
- Camera shake vars: `vfxShakeIntensity`, `vfxShakeX`, `vfxShakeY`
- Diff-tracking vars: `prevEnergyOrbs`, `prevGoldenOrbs`, `prevSpikeOrbs`, `prevMines`, `prevDisasterWarning`, `prevDisasterActive`, `prevActivePowerup`, `prevHomingMissiles`, `ambientStarted`, `supernovaPulsesPlayed`, `seenMeteorKeys`
- Zoom vars: `currentZoom`, `targetZoom`
- Input state vars: `mouseX`, `mouseY`, `isTouchDevice`, `isMouseDown`, `isShootBtnHeld`
- Touch vars: `touchOrigin`, `touchCurrent`
- `keysHeld` set

Attach all to `OrbArena.state = { ... }`.

Depends on: nothing. Loads after `config.js`.

### Step 12 - Create `static/js/audio.js`
Extract from `index.html`:
- `audioCtx` variable
- `sfx` object and all synth functions inside it
- `ambient` object and all ambient loop functions
- `disasterLoopTimer` variable

**Important:** `disasterLoopTimer` is both set and cleared inside `handleStateUpdate`. Keep the variable here but access it from `ui.js` via `OrbArena.audio.disasterLoopTimer`. Do not split the set/clear logic across files.

Attach as `OrbArena.audio = { audioCtx, sfx, ambient, disasterLoopTimer }`.

Depends on: nothing (Web Audio API only). Loads after `state.js`.

### Step 13 - Create `static/js/utils.js`
Extract from `index.html`:
- `lightenColor(color, amount)` - pure function
- `darkenColor(color, amount)` - pure function

Do NOT move `isOffScreen()` here - it references `state` and canvas dimensions. It stays in `render.js`.

Attach as `OrbArena.utils = { lightenColor, darkenColor }`.

Depends on: nothing. Loads after `audio.js`.

### Step 14 - Create `static/js/network.js`
Extract from `index.html`:
- `ws` variable declaration (`let ws`)
- `connect(onConnected)` function - assigns `ws` on open
- `handleMessage(data)` function
- All send functions: `sendMovement()`, `sendShoot()`, `sendBoost()`, `sendWormhole()`, `sendPlaceMine()`
- `joinGame(mode, challenge)` function

Cross-module calls inside these functions must use the namespace:
- `OrbArena.ui.showGame()` instead of `showGame()`
- `OrbArena.audio.sfx.*` instead of `sfx.*`
- `OrbArena.state.*` instead of bare variable refs

`ws` stays module-scoped (`let ws` at top of file) - `sendX()` functions close over it. It never needs to be on the namespace.

Attach as `OrbArena.network = { connect, joinGame, sendMovement, sendShoot, sendBoost, sendWormhole, sendPlaceMine }`.

Depends on: `state`, `audio`. Loads after `utils.js`.

### Step 15 - Create `static/js/render.js`
Extract from `index.html`:
- `canvas`, `ctx`, `minimapCanvas`, `minimapCtx` declarations
- All `drawX()` functions - the entire draw pipeline
- `isOffScreen(x, y, radius)` - keep here (uses `ctx`/canvas dimensions)
- `update()` per-frame logic (camera, zoom, movement sending)
- `render()` main render function

`ctx` stays as a module-scoped `let` - all draw functions in this file close over it. Do not put it on the namespace or pass it as a parameter.

Cross-module calls:
- `OrbArena.network.sendMovement()` inside `update()`
- `OrbArena.state.*` for all state reads
- `OrbArena.utils.lightenColor()` etc.

Attach as `OrbArena.render = { render, update, canvas, ctx }`.

Depends on: `state`, `audio`, `utils`, `network`. Loads after `network.js`.

### Step 16 - Create `static/js/ui.js`
Extract from `index.html`:
- `showGame()`, `showDeathScreen()`, `hideDeathScreen()`
- `handleStateUpdate(data)` - keep this function intact, do not split it further

Inside `handleStateUpdate`, replace bare references:
- `sfx.*` -> `OrbArena.audio.sfx.*`
- `ambient.*` -> `OrbArena.audio.ambient.*`
- `disasterLoopTimer` -> `OrbArena.audio.disasterLoopTimer`
- `particles`, `killPopups`, `killRings` etc. -> `OrbArena.state.*`

Attach as `OrbArena.ui = { showGame, showDeathScreen, hideDeathScreen, handleStateUpdate }`.

Depends on: `state`, `audio`, `network`. Loads after `render.js`.

### Step 17 - Create `static/js/input.js`
Extract from `index.html`:
- All keyboard event listeners (`keydown`, `keyup`)
- All mouse event listeners (`mousemove`, `mousedown`, `mouseup`, `click`)
- All touch event listeners (`touchstart`, `touchmove`, `touchend`)
- Button click handlers (shoot button, boost button, etc.)

All send calls go via `OrbArena.network.*`.
All state mutations go via `OrbArena.state.*`.

No exports needed - this file just registers event listeners on load.

Depends on: `state`, `network`, `render`. Loads after `ui.js`.

### Step 18 - Create `static/js/main.js`
- `gameLoop()` function - calls `OrbArena.render.update()` and `OrbArena.render.render()`, then `requestAnimationFrame(gameLoop)`
- Any top-level init that was previously inline in the `<script>` block
- Call `OrbArena.network.connect()` to kick off the connection

Depends on: all modules. Loads last.

### Step 19 - Update `index.html` script tags
Remove the large inline `<script>` block. Replace with:
```html
<script src="/static/js/config.js"></script>
<script src="/static/js/state.js"></script>
<script src="/static/js/audio.js"></script>
<script src="/static/js/utils.js"></script>
<script src="/static/js/network.js"></script>
<script src="/static/js/render.js"></script>
<script src="/static/js/ui.js"></script>
<script src="/static/js/input.js"></script>
<script src="/static/js/main.js"></script>
```

Keep all HTML markup and CSS in `index.html`. Only the JS moves out.

### Phase 3 Validation Check
Open the game in browser. Check:
- [ ] No errors in browser console (no `ReferenceError`, no 404s on JS files)
- [ ] Start screen renders
- [ ] Can enter name and join
- [ ] Player appears and moves with mouse
- [ ] Orb collection plays sound
- [ ] Leaderboard updates
- [ ] Death screen appears on death
- [ ] Challenges accessible and functional
- [ ] Mobile: touch joystick works

---

## Dockerfile note
The `COPY . .` in the Dockerfile copies everything. The new `static/` directory will be included automatically - no Dockerfile changes needed.

---

## Branch strategy
Do this on a dedicated branch, not directly on master.
```bash
git checkout -b code-split
```
Commit after each phase passes its validation check. Merge to master once Phase 3 is fully validated.
