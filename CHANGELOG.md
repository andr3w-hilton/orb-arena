# Orb Arena - Changelog

## v0.3.1 — Disaster Buffs & UI Fixes

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
