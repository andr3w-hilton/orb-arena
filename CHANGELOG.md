# Orb Arena - Changelog

## v1.1.0 - Trail Blazer

### New Power-up: Tron Trail
- Pick up a **Trail** orb to leave a glowing hazard trail behind you as you move
- Each segment persists for 5 seconds before fading - use it to wall off escape routes, funnel enemies into a corner, or punish anyone trying to tail you
- Enemies that run through your trail take 10 damage per segment hit - same as a direct projectile
- Trail segments don't hurt you, so weave freely through your own path
- Active for 8 seconds per pickup

### Disasters Arrive Faster
- The first disaster now hits 60-90s after the arena fills (down from 2-3 minutes) - no more long safe openers
- Subsequent disasters follow every 2-2.5 minutes (was 3 minutes) - the pressure stays on
- Settle grace period after the lobby fills is now 30s instead of 60s

### Start Screen
- Live player indicator now shows on the start screen - a pulsing green dot and count let you know if a game is already running before you jump in
- Quick start guide cards are now collapsible - tap any section header to hide it and reduce clutter
- Hall of Fame is visible before you even join, so you can scope out the competition

---

## v1.0.0 - First Full Release

### Persistent Scores
- Challenge leaderboards (Missile Magnet, Nitro Orb) now persist across server restarts via a Docker volume
- All-time multiplayer Hall of Fame - top 10 peak scores recorded on disconnect, one entry per player (personal best only)
- Hall of Fame card displayed on the start screen, fetched on page load with gold accent styling
- `load_scores()` / `save_scores()` written atomically on every score change; survives rebuilds indefinitely

### Audio
- Full sound system implemented

---

## v0.6.0 - Nitro Orb Challenge

### New Challenge: Nitro Orb
- New solo challenge selectable from the Challenges screen alongside Missile Magnet; cyan colour scheme
- F1-style closed circuit defined by 9 waypoints across the 5000x5000 world
- Pre-placed barrier mines line both sides of the track (~190 total) - armed from the start, never removed; touching one detonates it (instant death) and it rearms after 1.5s
- Sequential golden gate orbs placed every ~700px along the centreline - collect them in order to complete a lap
- 3 laps per run; crashing ends the run early as a DNF
- Score = total 3-lap time - only posted to the board if all 3 laps are completed, giving full incentive to race every lap
- Leaderboard tracks best total time; lowest wins
- Escalation: tight corners narrow each lap with additional mines placed progressively closer to centre (capped at 100px from centreline)
- No shrink, no growth, no disasters, no powerups - pure driving
- Player fixed at radius 20 with speed of a radius-10 orb (~16 units/tick)
- Boost is unlimited - no cooldown, no mass cost; timing it well through corners is the skill expression
- Decorative game elements scattered in the infield and outfield (60 energy orbs, 20 spike orbs, 6 obstacle walls, up to 5 inactive turret emplacements) to make the challenge feel part of the same game world

### Client Changes
- Challenge select screen cards are now horizontal (side by side) with wrap on small screens
- Nitro Orb card uses electric cyan (`#00c8ff`) to distinguish it from Missile Magnet orange
- Subtle tarmac fill and dashed centreline rendered in world space along waypoints
- Chequered start/finish line drawn perpendicular to the first track segment at the S/F waypoint
- Checkpoint arrow points toward the next gate orb when more than 80px away
- Nitro Orb HUD: current lap time, lap counter, running total time, gate progress
- Challenge result shows total time and rank on completion, or "DNF - crashed on lap X" on death
- Inactive decorative turret emplacements rendered in the infield and map corners

### Architecture
- `RallyRunGame(GameState)` - isolated per-player instance; overrides `_collect_golden_orbs`, `_collect_energy_orbs`, `_collect_spike_orbs`, `_update_mines`, `activate_boost`, `tick`
- `_compute_rally_layout()` - module-level precompute of barrier mine positions and checkpoint orb positions from waypoints
- `_dist_to_track(px, py)` - module-level point-to-segment distance guard used when placing decorative elements
- `run_rally_loop()` - dedicated async tick loop; only calls `record_rally_score()` on clean 3-lap completion
- `Player.speed_override` field - bypasses radius-based speed scaling for challenge modes

## v0.5.1 - Destructible Walls

### Challenge: Missile Magnet - Balance Fix
- Walls in challenge mode now have durability: 3 turret missile hits destroy a wall
- Destroyed walls respawn after 10 seconds as a single rectangle at a random map position (L-shaped corner walls do not reform as L-shapes on respawn, adding layout variety)
- Wall health visualised by a coloured border: green (3 hp), amber (2 hp), red (1 hp)
- Player shots now pass through walls in challenge mode - useful for intercepting incoming missiles through cover
- Fixes exploit where players could shelter indefinitely behind corner L-walls
- Credit: destructible wall mechanic concept by **Braeden Lazarus** (play tester)

### TODO
- Seeker missile: every Nth turret shot fires a slower homing missile with a tighter turn radius that can navigate around walls - to be added as a future escalation mechanic

## v0.5.0 - Missile Magnet Solo Challenge

### New Feature: Solo Challenge Mode
- New "Challenges" button on the landing page launches an isolated solo game instance
- Each challenge player gets a completely separate `ChallengeGame` - no multiplayer interference
- Challenge game ticks in its own asyncio task (30 FPS), independent of the main game loop

### Challenge: Missile Magnet
- 8 fixed turrets positioned at map corners and edge midpoints
- 4 turrets active at start; a new turret unlocks every 30 seconds (up to all 8)
- Fire rate escalates over time: starts at one shot per 4s, ramps down to 1.5s minimum
- Turret missiles are red homing missiles with longer lifetime and line-of-sight tracking
- Turrets are indestructible but their missiles can be shot down by the player mid-flight
- Player projectiles vs turret missiles: direct collision destroys both (new projectile-vs-projectile mechanic)
- Walls provide real cover - homing missile lock-on breaks when LOS is blocked
- Score = time survived; game ends on death (no respawn in challenge mode)
- Leaderboard tracks top 10 survival times

### Client Changes
- Challenge HUD (top-right): shows time survived and current wave
- Turrets rendered as directional triangle emplacements with glow effect when active
- Challenge result overlay on death: shows time, rank, and top 5 scores
- Multiplayer leaderboard hidden during challenge (replaced by challenge HUD)
- "Play Again" reloads the page for a clean run

## v0.4.0 - Homing Missiles, Mines & Spectator Mode

### New Power-up: Homing Missiles
- Picked up from power-up orbs, grants 3 missiles per pickup
- Missiles fire in aimed direction then proximity-acquire the nearest enemy within 400px
- Line-of-sight checks - walls block lock-on and break tracking
- Continuously re-acquires targets if current target dies, gains protection, or breaks LOS
- No mass cost to fire (uses ammo instead)
- Deals 20 damage on hit (2x normal projectile damage)
- Acceleration system - missiles launch at 45% speed and ramp to full over 1.2s, giving visible inertia on launch
- Top speed of 20 (vs 14 for normal projectiles), 5s lifetime

### New Feature: Mines
- Super-rare mine pickup orb spawns on map (1 at a time, 90s respawn)
- Collecting a pickup grants 1 mine (max 3 held, max 3 placed)
- Place mines at current position via dedicated input
- Mines arm after 0.5s delay, then trigger on enemy proximity (60px)
- Blast radius of 80px with distance-based damage falloff (25 max) and knockback
- Mines don't trigger on the player who placed them

### New Feature: Spectator Mode
- Players can join as spectators instead of playing
- Spectators receive full game state broadcasts without a "you" field
- Separate connection tracking - spectators don't count as players for game logic

### Server Improvements
- Added error handling around game tick to prevent server crashes
- Added `_line_blocked_by_wall()` using Liang-Barsky algorithm for LOS checks
- Refactored broadcast loop to handle both player and spectator connections
- Added `Spectator` dataclass, `HomingMissile` dataclass, `Mine`/`MinePickup` dataclasses

## v0.3.1 - Disaster Buffs & UI Fixes

### Bug Fixes
- Fixed earthquake not updating wall graphics — walls now visually move with the server-side collision positions during and after an earthquake
- Fixed kill feed rendering behind the minimap after it was moved to top-left in v0.3.0

### UI
- Leaderboard is now collapsible — tap the header to toggle. Starts collapsed on mobile to save screen space

### Disaster Balance
- **Supernova:** blast radius 900 → 2200 (+144%, covers ~44% of map width). Mass loss per pulse 8-12% → 10-15% (+25%). Cumulative loss now 41-56% (was 34-47%)
- **Meteor Shower:** duration 10s → 20s. Blast radius 40 → 120 (+200%, 9x area). Damage per hit 8 → 30 (+275%). Meteors per wave 3 → 5. Total meteors ~667 (was ~200). Overall lethality ~56x previous
- **Black Hole:** max radius 80 → 200 (+150%). Pull range 750 → 1500 (+100%, covers 30% of map). Pull strength 18 → 30 (+67%). Kill zone factor 0.5 → 0.6. Orb pull strength 8 → 15 (+88%)
- Disaster spawn interval reduced from ~5 min to ~3 min. Settle time reduced from 2 min to 1 min

## v0.3.0 — Mobile HUD Overhaul & Code Quality

### Mobile UI
- Moved minimap to top-left corner underneath the score
- Repositioned shoot and boost buttons to left side, stacked vertically
- Removed connection status indicator (unnecessary clutter)
- Moved power-up notification below the minimap with consistent spacing
- Moved critical mass warning to bottom-center, aligned with boost button

### Balance
- Reduced speed scaling penalty for large players (0.3 → 0.2) so max-size players feel less sluggish on the larger map

### Code Quality — Server
- Broke down `GameState.tick()` (315 lines) into 6 focused methods plus helpers
- Refactored `DisasterManager` to use dispatch dicts instead of if/elif chains
- Extracted `_is_sheltered()`, `_apply_meteor_damage()`, `_apply_black_hole_pull()`, `_apply_black_hole_orb_pull()`
- Added `Player.has_protection()` and `Player.has_shield()` to eliminate repeated powerup checks
- Extracted `_consume_player()` helper for shared kill/score logic
- Created `BaseOrb` parent class to deduplicate 4 identical `to_dict()` methods
- Replaced 10+ magic numbers with named constants
- Fixed unnecessary `math.sqrt()` in black hole orb consumption (now compares squared distances)

### Code Quality — Client
- Extracted `drawInvincibilityEffect()`, `drawCriticalMassEffect()`, `drawPowerupEffect()`, `drawBoostTrail()` from `drawPlayer()` (200 → ~40 lines)
- Extracted `handleStateUpdate()` from `handleMessage()`
- Extracted `renderDisasterEffects()` from `render()`
- Added `isOffScreen()` utility replacing 7 duplicate boundary checks
- Added `isMobile()` helper replacing 3 repeated device checks
- Added `drawHudBar()` shared renderer, simplifying `drawBoostIndicator()` from 72 to 15 lines
- Removed dead code: unused `serverInput`, overwritten `fillStyle` manipulation
- Added `PROJECTILE_MIN_RADIUS` constant replacing magic number

## v0.2.0 — Playtesting Tweaks & Map Expansion

### Balance Changes
- Black Hole duration increased from 15s to 30s
- Spike orb damage reduced from 50% mass + 50% score to 25% mass only (score unaffected)
- Disaster spawn interval reduced from 10-15 min to ~5 min with 10-30s random jitter
- Rapid fire projectile range extended to 40% of map (3.2s lifetime vs 2.0s normal)

### Supernova Rework
- Now pulses 5 expanding shockwave rings instead of a single blast
- Pulses spaced 1.5s apart, each dealing 8-12% mass loss
- Color shifts from orange through red to pink across pulses
- Pulsing core glow at epicenter while active

### Fog of War Fix
- Fixed bug where fog made entire screen dark instead of reducing visibility
- Replaced broken `destination-out` compositing with `evenodd` path cutout
- Soft gradient edge around visibility circle for smooth falloff

### Dynamic Zoom
- Camera zooms out as player grows (radius 30-120 maps to 1.0x-0.55x zoom)
- Smooth lerp transitions between zoom levels
- Enabled on both mobile and desktop
- All coordinate conversions, culling, overlays, and minimap updated for zoom

### Map Expansion (2.5x)
- World size increased from 2000x2000 to 5000x5000
- Energy orbs: 100 → 625
- Spike orbs: 15 → 90
- Golden orbs: 5 → 30
- Power-ups: 2 → 5
- Walls: 8 → 20 (10 structured + 10 procedurally generated)
- Black hole pull range: 500 → 750
- Supernova blast radius: 600 → 900
- Frenzy orbs: 250 → 1500

### Minimap
- Simplified to only show other players and power-ups
- Removed walls, energy orbs, golden orbs, spike orbs, and projectiles

### UI
- Quick start guide: added missing Supernova and Earthquake to disaster card
- Quick start guide: removed "& walls" from spike avoidance tip
- Fixed mobile start screen clipping on iPhone (scroll support + safe area padding)
