# Orb Arena

Multiplayer browser game. Players grow orbs by consuming energy, shoot projectiles, survive disasters. Python async WebSocket server + vanilla JS Canvas client. Also has three solo challenge modes with persistent leaderboards.

## Architecture

```
server.py        # Async WebSocket server, all game logic (~3,870 lines)
index.html       # Canvas client, rendering + input (~5,800 lines)
Dockerfile       # Python 3.11-slim, ports 8080 (HTTP) + 8765 (WS)
requirements.txt # websockets>=13.0 (uvloop optional)
```

**Server:** `asyncio` + `websockets`, optional uvloop. 30 FPS tick rate.
**Deployment:** Push to `master` -> GitHub Actions (`.github/workflows/deploy-orb-arena.yml`) syncs to the DigitalOcean droplet and runs `rebuild-game` (Docker rebuild + restart). Manual override: `push-orb-arena` skill. nginx/swag reverse proxy, SSL at proxy, `/` -> :8080, `/ws` -> :8765.

## Game Classes (server.py)

- **GameState** — shared multiplayer arena
- **ChallengeGame(GameState)** — "Missile Magnet": survive homing-missile turrets (8 positions, 4 start active, +1 per 30s, fire interval 4.0s -> 1.5s)
- **RallyRunGame(GameState)** — "Nitro Orb": 3-lap time trial on a mine-lined track (waypoint centreline, checkpoint orbs, fixed r=20/speed 16.1)
- **BossHuntGame(GameState)** — "Hunter Seeker": flee a giant boss orb (r=200, speed ramps 4->11 over 120s, periodic shooting phases, anti-camping precision strike)

Challenge instances are per-player and run their own tick loop (`run_challenge_loop` / `run_rally_loop` / `run_boss_loop`); the shared arena uses `broadcast_state`.

## Entities (dataclasses)

**Player:** id, name, x, y, radius, score, alive, active_powerup, powerup_until, cooldowns, mines/missiles ammo, trail/wormhole held flags, speed_override (challenges). Methods: `to_dict()`, `get_speed()`, `has_shield()`, `has_protection()`

**Orbs:** EnergyOrb (r=8, +2 radius/+10 score), SpikeOrb (r=12, damage), GoldenOrb (r=12, +10), PowerUpOrb (r=14, random buff), MinePickup (r=18, rare)

**Combat:** Projectile, HomingMissile, WormholePortal, Mine, MissileTurret, Wall (destructible, hp=3), BossOrb

**Disasters:** Meteor (x, y, r, impact_time), BlackHole (x, y, current_r, max_r)

## WebSocket Protocol

**Client -> Server:** `join` (name, mode: player|spectate|challenge + challenge name), `move` (x, y), `boost`, `shoot` (x, y, wormhole flag), `place_mine`, `respawn`, `ping` (t, numeric only — echoed as `_pong_t` in `you`), `test_disasters` (no-op unless server started with `ALLOW_DISASTER_TEST=1`; client hotkey 4+T)

**Server -> Client:**
- `welcome` - Once on join. player_id, walls, world bounds, mode/challenge extras
- `state` - Every tick (30 FPS). All entities, kill_feed, leaderboard, disaster, `you` (per-client, spliced into a shared cached JSON string)
- `challenge_result` - Final state when a challenge run ends (rank, top_scores)

## HTTP API (port 8080)

`/` serves index.html only. JSON endpoints: `/api/challenge/scores`, `/api/rally/scores`, `/api/boss/scores`, `/api/alltime/scores` (top 10 each), `/api/status` (player count). Leaderboards persist to `/data/scores.json` (Docker volume), personal-best-only, top 10.

## Game Loop

**Main (30 FPS):** `game.tick()` -> `build_shared_state()` (cached) -> splice `you` per-client -> broadcast

**Tick order:** move_players -> orb_collisions (spatial grid broadphase, cell=200px) -> player_collisions (1.2x consume ratio) -> projectiles/missiles/wormholes/mines/trails -> critical_mass (r>=100) -> powerups -> disaster_manager

## Constants

**World:** 5000x5000, 625 energy/90 spike/30 golden/5 powerup orbs, 20 walls, 50 max connections
**Player:** r 20->150 (min 10), speed 14 (radius-scaled), shrink 0.02/tick, consume 1.2x, 3s spawn protection
**Combat:** Projectile (speed 25, dmg 10, cost 5, cd 0.5s, life 2s, min r 25 to shoot), Boost (2.5x speed, 0.25s, cd 3s, cost 3), Critical mass r>=100 (30s timer), Mine (max 3 held, blast r=80, dmg 25, proximity 60)
**Powerups (30s respawn):** shield (5s, 1 hit), rapid_fire (5s, free shots, longer projectile life), magnet (8s, 400px), phantom (5s, wall phase), speed_force (7s), trail (8s Tron light-trail, 1.7x speed), homing_missiles (3 shots, dmg 20), wormhole (held; fires a teleport portal, dmg 15 to enemies entering)
**Abuse guards:** rate limit 120 msgs/s per client, 1KB max message, name sanitization, `safe_float` on coords, `ALLOWED_ORIGINS` env var restricts WS origins

## Disasters

First disaster ~90-120s after lobby fills (30s settle + 60-90s). Recurring every ~2-2.5min. Requires 2+ players, 5s warning. Active disasters keep ticking if players drop below minimum.

**black_hole (30s):** grows to r=350, pulls 2000px (mass-scaled, boost resists), scatters 30 orbs on collapse
**meteor_shower (20s):** 5 meteors/0.15s, AoE dmg 30 (r=120), walls shelter
**fog_of_war (15s):** 300px visibility (client-side)
**feeding_frenzy (10s):** +1500 energy orbs (temp)
**supernova (~14s):** 10 pulses (1.5s interval), r=2200, 15-20% mass loss scaled by proximity
**earthquake (3s):** Walls interpolate to new positions, trapped orbs relocated

## Rendering

**Pipeline:** Clear -> transform (zoom + shake) -> grid/boundary/walls/orbs/particles/projectiles -> disasters -> players (size-sorted, cached per state) -> kill effects -> HUD -> minimap

**Interpolation:** Player positions lerp between 30Hz server states (`interpMap`/`renderT`, adaptive interval, snaps on >150px jumps like teleports/respawns). Camera follows the interpolated position.

**Zoom:** Dynamic r 30-120 = zoom 1.0-0.55; dramatic pull-back during boss precision strikes

## Input

**Desktop:** Mouse (zoom-adjusted coords), click to shoot, space to boost
**Mobile:** Touch joystick (3x sensitivity, relative to player), double-tap boost, dedicated buttons (bottom-left)

## Adding Features

New mechanics typically touch: constants -> entity dataclass -> tick pipeline -> state serialization -> WebSocket messages (if interactive) -> client state parsing -> rendering (z-order) -> HUD (if player-facing) -> mobile controls
