# Orb Arena

Multiplayer browser game. Players grow orbs by consuming energy, shoot projectiles, survive disasters. Python async WebSocket server + vanilla JS Canvas client.

## Architecture

```
server.py        # Async WebSocket server, all game logic (~1,680 lines)
index.html       # Canvas client, rendering + input (~2,530 lines)
Dockerfile       # Python 3.11-slim, ports 8080 (HTTP) + 8765 (WS)
requirements.txt # websockets>=13.0 (uvloop optional)
```

**Server:** `asyncio` + `websockets`, optional uvloop. 30 FPS tick rate.
**Deployment:** Docker + nginx reverse proxy. SSL at nginx, `/` -> :8080, `/ws` -> :8765.

## Entities (dataclasses)

**Player:** id, name, x, y, radius, score, alive, active_powerup, powerup_until, cooldowns. Methods: `to_dict()`, `get_speed()`, `has_shield()`, `has_protection()`

**Orbs:** EnergyOrb (r=8, +2 score), SpikeOrb (r=12, damage), GoldenOrb (r=12, +10), PowerUpOrb (r=14, random buff)

**Combat:** Projectile (owner_id, x, y, dx, dy, lifetime), Wall (x, y, w, h)

**Disasters:** Meteor (x, y, r, impact_time), BlackHole (x, y, current_r, max_r)

## WebSocket Protocol

**Client -> Server:** `join` (name), `move` (x, y), `boost`, `shoot` (x, y), `respawn`

**Server -> Client:**
- `welcome` - Once on join. Includes player_id, walls, world bounds
- `state` - Every tick (30 FPS). All entities, kill_feed, leaderboard, disaster, `you` (per-client)

## Game Loop

**Main (30 FPS):** `game.tick()` -> `build_shared_state()` (cached) -> splice `you` per-client -> broadcast

**Tick order:** move_players -> orb_collisions -> player_collisions (1.2x consume ratio) -> projectiles -> critical_mass (r>=100) -> powerups -> disaster_manager

## Constants

**World:** 5000x5000, 625 energy/90 spike/30 golden/5 powerup orbs, 20 walls, 50 max players
**Player:** r 20->150 (min 10), speed 14, shrink 0.02/tick, consume 1.2x, 3s spawn protection
**Combat:** Projectile (speed 25, dmg 10, cost 5, cd 0.5s, life 2s), Boost (2.5x speed, 0.25s, cd 3s, cost 3), Critical mass r>=100 (30s timer)
**Powerups (30s respawn):** shield (5s, 1 hit), rapid_fire (5s, free shots), magnet (8s, 300px), phantom (5s, wall phase)

## Disasters

First disaster ~90-120s after lobby fills (30s settle + 60-90s). Recurring every ~2-2.5min (120-150s). Requires 2+ players, 5s warning.

**black_hole (30s):** r=80, pulls 750px, scatters 30 orbs on collapse
**meteor_shower (10s):** 3 meteors/0.15s, AoE dmg 8 (r=40), walls protect
**fog_of_war (15s):** 300px visibility (client-side)
**feeding_frenzy (10s):** +1500 energy orbs (temp)
**supernova (~7.5s):** 5 pulses (1.5s interval), 900px, 8-12% mass loss
**earthquake (3s):** Walls interpolate to new positions

## Rendering

**Pipeline:** Clear -> transform (zoom + shake) -> grid/boundary/walls/orbs/particles/projectiles -> disasters -> players (size-sorted) -> kill effects -> HUD -> minimap

**Zoom:** Dynamic r 30-120 = zoom 1.0-0.55

## Input

**Desktop:** Mouse (zoom-adjusted coords), click to shoot, space to boost
**Mobile:** Touch joystick (3x sensitivity, relative to player), double-tap boost, dedicated buttons (bottom-left)

## Adding Features

New mechanics typically touch: constants -> entity dataclass -> tick pipeline -> state serialization -> WebSocket messages (if interactive) -> client state parsing -> rendering (z-order) -> HUD (if player-facing) -> mobile controls
