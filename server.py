"""
Orb Arena - Multiplayer WebSocket Game Server
A competitive arena game where players control orbs, collect energy, and consume smaller players.
"""

import asyncio
import json
import os
import random
import math
import time

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("Using uvloop (faster async)")
except ImportError:
    pass  # Falls back to default asyncio loop

import websockets
from websockets.exceptions import ConnectionClosed
from dataclasses import dataclass
from typing import Dict, Set, Optional
import colorsys
import socket
import http.server
import threading
import os
import re

# Game configuration
WORLD_WIDTH = 5000
WORLD_HEIGHT = 5000
INITIAL_RADIUS = 20
MAX_RADIUS = 150
MIN_RADIUS = 10
BASE_SPEED = 14
SPEED_SCALING = 0.2  # Higher = more speed difference between small and large
ENERGY_ORB_COUNT = 625
ENERGY_ORB_VALUE = 2
ENERGY_ORB_RADIUS = 8
SPIKE_ORB_COUNT = 90  # Evil spike orbs
SPIKE_ORB_RADIUS = 12
GOLDEN_ORB_COUNT = 30  # Rare golden orbs
GOLDEN_ORB_VALUE = 10  # 5x energy orb value
GOLDEN_ORB_RADIUS = 12
TICK_RATE = 1 / 30  # 30 FPS (reduced from 60 for memory efficiency)
SHRINK_RATE = 0.02  # Slowly shrink over time
CONSUME_RATIO = 1.2  # Must be 20% larger to consume another player

# Boost/Dash configuration
BOOST_SPEED_MULTIPLIER = 2.5
BOOST_DURATION = 0.25  # seconds
BOOST_COOLDOWN = 3.0  # seconds
BOOST_MASS_COST = 3  # radius cost to boost

# Projectile/Shooting configuration
PROJECTILE_SPEED = 25
PROJECTILE_RADIUS = 5
PROJECTILE_LIFETIME = 2.0  # seconds
PROJECTILE_RAPID_FIRE_LIFETIME = 3.2  # seconds (40% of map at speed 25)
PROJECTILE_DAMAGE = 10  # radius removed from target
PROJECTILE_COST = 5  # radius cost to shooter
PROJECTILE_COOLDOWN = 0.5  # seconds between shots
PROJECTILE_MIN_RADIUS = 25  # must be this big to shoot

# Critical mass configuration
CRITICAL_MASS_THRESHOLD = 100  # radius threshold to start timer
CRITICAL_MASS_TIMER = 30.0  # seconds before explosion

# Power-up configuration
POWERUP_COUNT = 5  # max on map at once
POWERUP_RADIUS = 14
POWERUP_RESPAWN_DELAY = 30.0  # seconds before replacement spawns
POWERUP_TYPES = ["shield", "rapid_fire", "magnet", "phantom", "speed_force", "homing_missiles", "trail", "wormhole"]
POWERUP_DURATIONS = {"shield": 5.0, "rapid_fire": 5.0, "magnet": 8.0, "phantom": 5.0, "speed_force": 7.0, "trail": 8.0}
HOMING_MISSILES_AMMO = 3  # discrete shots granted on pickup

# Wormhole power-up configuration
WORMHOLE_SPEED = 12           # portal travel speed (px/tick)
WORMHOLE_TRAVEL_DIST = 250    # px the portal travels before stopping dead
WORMHOLE_LIFETIME = 6.0       # seconds before portal closes on its own
WORMHOLE_DAMAGE = 15          # radius damage dealt to enemy who enters portal
WORMHOLE_RADIUS = 22          # collision/visual radius
WORMHOLE_MIN_EXIT_DIST = 600  # minimum px between entry and exit point
MAGNET_RANGE = 400  # radius for magnet pull
MAGNET_STRENGTH = 22  # speed orbs move toward player (must outpace base speed of 14)

# Trail (Tron) power-up configuration
TRAIL_SEGMENT_LIFETIME = 5.0   # seconds a placed segment persists
TRAIL_SEGMENT_RADIUS = 8       # collision/render radius (same as energy orb)
TRAIL_SEGMENT_INTERVAL = 0.1   # seconds between segment placements (3 ticks at 30 FPS)
TRAIL_DAMAGE = 10              # radius damage on contact (same as projectile)
TRAIL_SPEED_MULTIPLIER = 1.7   # speed boost while trail is actively laying segments

# Mine configuration
MINE_PICKUP_COUNT = 1  # only 1 on map at a time (super rare)
MINE_PICKUP_RESPAWN_DELAY = 90.0  # 90s respawn (3x longer than power-ups)
MINE_MAX_COUNT = 3  # max mines per player
MINE_ARM_DELAY = 0.5
MINE_BLAST_RADIUS = 80
MINE_DAMAGE = 25
MINE_PROXIMITY_TRIGGER = 60

# Nitro Orb (Rally Run) challenge configuration
RALLY_TRACK_HALF_WIDTH = 175    # px from centreline to barrier mine row
RALLY_MINE_SPACING = 140        # px between adjacent barrier mines along edge
RALLY_PLAYER_RADIUS = 20        # fixed orb radius throughout the run
RALLY_PLAYER_SPEED = 16.1       # BASE_SPEED * (INITIAL_RADIUS / 10) ** SPEED_SCALING
BARRIER_MINE_REARM_DELAY = 1.5  # seconds before a triggered barrier mine rearms
RALLY_CHECKPOINT_SPACING = 700  # px between sequential checkpoint orbs
RALLY_MAX_LAPS = 3              # laps per run (death ends early)
RALLY_TRACK_WAYPOINTS = [
    (700,  900),    # 0 - Start / Finish
    (4300, 900),    # 1 - Turn 1 entry (end of main straight)
    (4600, 1500),   # 2 - Turn 1 apex (sweeping right)
    (4500, 2200),   # 3 - Sector 2 entry
    (4100, 2700),   # 4 - Hairpin apex (tightest corner)
    (3200, 2400),   # 5 - Hairpin exit
    (3200, 3800),   # 6 - Back straight south
    (1600, 4200),   # 7 - South corner
    (700,  3600),   # 8 - Final sector entry
    (700,  900),    # 9 - Back to Start / Finish (closed loop)
]
RALLY_ESCALATION_CORNERS = [1, 4, 7]   # waypoint indices of tightest corners


def _compute_rally_layout():
    """Pre-compute barrier mine positions and checkpoint orb centreline positions."""
    barriers = []
    # Segments stored for second-pass checkpoint placement: (x0, y0, ux, uy, seg_len)
    segments = []

    n = len(RALLY_TRACK_WAYPOINTS) - 1
    for i in range(n):
        x0, y0 = RALLY_TRACK_WAYPOINTS[i]
        x1, y1 = RALLY_TRACK_WAYPOINTS[i + 1]
        dx, dy = x1 - x0, y1 - y0
        seg_len = math.sqrt(dx * dx + dy * dy)
        if seg_len < 1:
            continue
        ux, uy = dx / seg_len, dy / seg_len
        nx, ny = -uy, ux  # left-hand normal

        # Barrier mines: start half a spacing in to avoid corner pile-ups
        t = RALLY_MINE_SPACING / 2
        while t < seg_len:
            cx, cy = x0 + ux * t, y0 + uy * t
            barriers.append((cx + nx * RALLY_TRACK_HALF_WIDTH, cy + ny * RALLY_TRACK_HALF_WIDTH))
            barriers.append((cx - nx * RALLY_TRACK_HALF_WIDTH, cy - ny * RALLY_TRACK_HALF_WIDTH))
            t += RALLY_MINE_SPACING

        segments.append((x0, y0, ux, uy, seg_len))

    # Post-filter: remove barrier mines that landed inside the track corridor.
    # At corners the normal-direction offset for the inside of a bend can land
    # much closer to an adjacent segment's centreline than RALLY_TRACK_HALF_WIDTH.
    _MIN_MINE_CENTRELINE_DIST = RALLY_TRACK_HALF_WIDTH - 40  # px

    def _min_dist_to_centreline(px: float, py: float) -> float:
        min_d = float('inf')
        for sx0, sy0, sux, suy, slen in segments:
            ddx, ddy = px - sx0, py - sy0
            proj = max(0.0, min(slen, ddx * sux + ddy * suy))
            rx, ry = px - (sx0 + sux * proj), py - (sy0 + suy * proj)
            d = math.sqrt(rx * rx + ry * ry)
            if d < min_d:
                min_d = d
        return min_d

    barriers = [
        (mx, my) for mx, my in barriers
        if _min_dist_to_centreline(mx, my) >= _MIN_MINE_CENTRELINE_DIST
    ]

    # Second pass: place checkpoint orbs on centreline, sliding clear of barrier mines
    _CHECKPOINT_MIN_MINE_DIST = 100  # px - minimum clearance from any barrier mine
    _CHECKPOINT_SLIDE_STEP = 35      # px - nudge along segment when too close
    _CHECKPOINT_MAX_SLIDES = 4       # attempts before accepting the position anyway

    checkpoints = []
    cp_dist = 0.0
    for x0, y0, ux, uy, seg_len in segments:
        offset = RALLY_CHECKPOINT_SPACING - (cp_dist % RALLY_CHECKPOINT_SPACING)
        t = offset
        while t < seg_len:
            cx, cy = x0 + ux * t, y0 + uy * t
            # Slide forward along centreline if too close to any barrier mine
            for _ in range(_CHECKPOINT_MAX_SLIDES):
                if all(
                    (cx - bx) ** 2 + (cy - by) ** 2 >= _CHECKPOINT_MIN_MINE_DIST ** 2
                    for bx, by in barriers
                ):
                    break
                cx += ux * _CHECKPOINT_SLIDE_STEP
                cy += uy * _CHECKPOINT_SLIDE_STEP
            checkpoints.append((cx, cy))
            t += RALLY_CHECKPOINT_SPACING
        cp_dist += seg_len

    # Remove any checkpoint that lands too close to the start/finish line to
    # avoid spawning an orb that looks like it's on the line but can't be collected
    # before the lap completes.
    sx, sy = RALLY_TRACK_WAYPOINTS[0]
    _FINISH_LINE_EXCLUSION = 500  # px radius around start/finish to keep clear
    checkpoints = [
        (cx, cy) for cx, cy in checkpoints
        if (cx - sx) ** 2 + (cy - sy) ** 2 >= _FINISH_LINE_EXCLUSION ** 2
    ]

    return barriers, checkpoints


RALLY_BARRIER_POSITIONS, RALLY_CHECKPOINT_POSITIONS = _compute_rally_layout()

# Hunter Seeker challenge configuration
BOSS_RADIUS = 200.0
BOSS_SPEED_BASE = 4.0
BOSS_SPEED_MAX = 11.0
BOSS_SPEED_RAMP_DURATION = 120.0       # seconds to ramp from base to max speed
BOSS_WEAKEN_DURATION = 4.0             # seconds boss is slowed after being hit
BOSS_WEAKEN_SPEED_MULT = 0.45          # speed multiplier when weakened
BOSS_WALL_REPULSION_RANGE = 140        # px from wall edge to start repulsion force
BOSS_SHOOT_PHASE_INTERVAL = 90.0       # seconds between shooting phases starting
BOSS_SHOOT_PHASE_DURATION = 30.0       # seconds each shooting phase lasts
BOSS_SHOOT_COOLDOWN = 60.0             # seconds cooldown after shooting phase ends
BOSS_SHOOT_FIRE_INTERVAL = 2.5         # seconds between shots during shooting phase
BOSS_SHOT_SPEED = 18.0
BOSS_SHOT_DAMAGE = 15
BOSS_SHOT_RADIUS = 8
BOSS_SHOT_LIFETIME = 4.0
BOSS_HUNT_POWERUP_TYPES = ["shield", "rapid_fire", "speed_force", "phantom", "homing_missiles"]

# Corner-buster precision strike configuration
CAMP_TRIGGER_TIME = 10.0        # seconds boss cannot close distance before strike initiates
CAMP_CLOSE_THRESHOLD = 80.0     # boss must reduce distance by this much to reset timer
CAMP_PLAYER_MOVE_THRESHOLD = 300.0  # player moving this far from camp origin resets timer
STRIKE_PHASE_DURATION = 3.0     # seconds each alert phase lasts
STRIKE_COOLDOWN = 25.0          # seconds before another strike can trigger after one ends
STRIKE_BARRAGE_SHOTS = 15
STRIKE_BARRAGE_INTERVAL = 0.2   # seconds between barrage impacts
STRIKE_SCATTER = 50             # px radius scatter around locked target
STRIKE_SHOT_SPEED = 30.0
STRIKE_SHOT_RADIUS = 10
STRIKE_SHOT_DAMAGE = 22
STRIKE_SHOT_LIFETIME = 4.0


def _dist_to_track(px: float, py: float) -> float:
    """Minimum distance from a point to the nearest track segment centreline."""
    min_dist = float('inf')
    n = len(RALLY_TRACK_WAYPOINTS) - 1
    for i in range(n):
        x0, y0 = RALLY_TRACK_WAYPOINTS[i]
        x1, y1 = RALLY_TRACK_WAYPOINTS[i + 1]
        dx, dy = x1 - x0, y1 - y0
        seg_sq = dx * dx + dy * dy
        if seg_sq < 1:
            continue
        t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / seg_sq))
        cx, cy = x0 + t * dx, y0 + t * dy
        dist = math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
        if dist < min_dist:
            min_dist = dist
    return min_dist


# Homing missile configuration
HOMING_MISSILE_SPEED = 20
HOMING_MISSILE_INITIAL_SPEED_RATIO = 0.45  # starts at 45% of max speed
HOMING_MISSILE_RAMP_TIME = 1.2  # seconds to reach full speed
HOMING_MISSILE_DAMAGE = 20
HOMING_MISSILE_LIFETIME = 5.0
HOMING_TRACKING_STRENGTH = 0.15
HOMING_REACQUIRE_RANGE = 400  # proximity range for continuous target re-acquisition

# Respawn invincibility
RESPAWN_INVINCIBILITY = 3.0  # seconds

# Kill feed
KILL_FEED_MAX = 5  # max messages to show
KILL_FEED_DURATION = 5.0  # seconds before message expires

# Walls/Obstacles
WALL_COUNT = 20

# ── Natural Disaster Configuration ──
DISASTER_FIRST_MIN = 60.0      # first disaster: min delay after settle
DISASTER_FIRST_MAX = 90.0      # first disaster: max delay after settle
DISASTER_MIN_INTERVAL = 120.0  # ~2 minutes between subsequent disasters
DISASTER_MAX_INTERVAL = 150.0  # ~2 minutes + 10-30s jitter
DISASTER_WARNING_TIME = 5.0    # seconds of warning before disaster hits
DISASTER_MIN_PLAYERS = 2       # need at least 2 players to trigger
DISASTER_SETTLE_TIME = 30.0    # 30s grace period after lobby first fills

# Black Hole
BLACK_HOLE_DURATION = 30.0
BLACK_HOLE_MAX_RADIUS = 350    # visual/kill radius at full size
BLACK_HOLE_PULL_RANGE = 2000   # gravitational pull range (40% of map)
BLACK_HOLE_PULL_STRENGTH = 45  # base pull speed (scaled by distance)
BLACK_HOLE_MASS_FACTOR = 0.7   # smaller players pulled harder (inverse mass)

# Meteor Shower
METEOR_SHOWER_DURATION = 20.0
METEOR_INTERVAL = 0.15         # seconds between meteor strikes
METEOR_DAMAGE = 30             # radius removed on hit
METEOR_BLAST_RADIUS = 120      # area of effect per meteor
METEOR_COUNT_PER_WAVE = 5      # meteors per interval tick

# Fog of War
FOG_DURATION = 15.0
FOG_VISIBILITY_RADIUS = 300    # pixels around player

# Feeding Frenzy
FRENZY_DURATION = 10.0
FRENZY_ORB_COUNT = 1500        # orbs spawned at start

# Supernova
SUPERNOVA_RADIUS = 2200        # blast radius from center (~44% of map width)
SUPERNOVA_PULSE_COUNT = 10     # number of ripple pulses
SUPERNOVA_PULSE_INTERVAL = 1.5 # seconds between each pulse
SUPERNOVA_PULSE_EXPAND_TIME = 1.2  # seconds for each ring to expand
SUPERNOVA_MASS_LOSS_MIN = 0.15 # 15% mass loss per pulse at edge
SUPERNOVA_MASS_LOSS_MAX = 0.20 # 20% mass loss per pulse at edge (up to 2x at epicentre)

# Earthquake
EARTHQUAKE_DURATION = 3.0      # wall transition time

# Derived / internal constants
WALL_COLLISION_ITERATIONS = 3          # stability passes for wall push-out
MOVE_THRESHOLD_SQ = 25                 # 5^2 - minimum distance before moving
KILL_BASE_SCORE = 100                  # base score for consuming a player
KILL_SCORE_RATIO = 0.1                 # fraction of victim's score awarded as bonus
BLACK_HOLE_INITIAL_RADIUS = 5.0        # starting radius before growth
BLACK_HOLE_KILL_RADIUS_FACTOR = 0.6    # fraction of current_radius that kills
BLACK_HOLE_ORB_PULL_STRENGTH = 15      # orb-specific pull strength
BLACK_HOLE_EXIT_ORB_COUNT = 30         # orbs scattered on collapse
METEOR_MARKER_DURATION = 0.5           # seconds to keep impact marker visible


@dataclass
class BaseOrb:
    """Base class for all orb types with shared serialization."""
    id: str
    x: float
    y: float
    radius: float = 0
    color: str = ""

    def to_dict(self):
        return {"id": self.id, "x": round(self.x, 1), "y": round(self.y, 1), "radius": self.radius, "color": self.color}


@dataclass
class EnergyOrb(BaseOrb):
    radius: float = ENERGY_ORB_RADIUS
    color: str = "#00ff88"


@dataclass
class SpikeOrb(BaseOrb):
    radius: float = SPIKE_ORB_RADIUS
    color: str = "#ff2266"


@dataclass
class GoldenOrb(BaseOrb):
    radius: float = GOLDEN_ORB_RADIUS
    color: str = "#ffd700"


@dataclass
class PowerUpOrb(BaseOrb):
    radius: float = POWERUP_RADIUS
    color: str = "#dd44ff"


@dataclass
class Projectile:
    id: str
    owner_id: str
    x: float
    y: float
    dx: float  # normalized direction
    dy: float
    radius: float = PROJECTILE_RADIUS
    color: str = "#ffffff"
    created_at: float = 0.0
    lifetime: float = PROJECTILE_LIFETIME

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "radius": self.radius,
            "color": self.color
        }


@dataclass
class HomingMissile(Projectile):
    target_id: str = ""
    tracking_strength: float = 0.08
    speed: float = 14

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "dx": round(self.dx, 3),
            "dy": round(self.dy, 3),
            "radius": self.radius,
            "color": self.color,
            "homing": True
        }


@dataclass
class WormholePortal:
    id: str
    owner_id: str
    x: float
    y: float
    dx: float           # normalized travel direction
    dy: float
    travel_remaining: float = WORMHOLE_TRAVEL_DIST
    traveling: bool = True
    created_at: float = 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "traveling": self.traveling
        }


@dataclass
class Mine:
    id: str
    owner_id: str
    x: float
    y: float
    radius: float = 20
    color: str = "#ff6600"
    armed_at: float = 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "radius": self.radius,
            "color": self.color,
            "armed": time.time() >= self.armed_at
        }


@dataclass
class MinePickup(BaseOrb):
    radius: float = 18
    color: str = "#ff3300"


@dataclass
class MissileTurret:
    id: str
    x: float
    y: float
    active: bool = False
    last_fired: float = 0.0

    def to_dict(self):
        return {"id": self.id, "x": self.x, "y": self.y, "active": self.active}


@dataclass
class Wall:
    id: str
    x: float
    y: float
    width: float
    height: float
    color: str = "#334455"
    hp: int = 3
    max_hp: int = 3

    def to_dict(self):
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "color": self.color,
            "hp": self.hp,
            "max_hp": self.max_hp,
        }


@dataclass
class Meteor:
    x: float
    y: float
    radius: float = METEOR_BLAST_RADIUS
    impact_time: float = 0.0  # when it lands

    def to_dict(self):
        return {"x": round(self.x, 1), "y": round(self.y, 1), "radius": self.radius}


@dataclass
class BlackHole:
    x: float
    y: float
    current_radius: float = 5.0
    max_radius: float = BLACK_HOLE_MAX_RADIUS

    def to_dict(self):
        return {"x": round(self.x, 1), "y": round(self.y, 1), "radius": round(self.current_radius, 1)}


@dataclass
class BossOrb:
    id: str
    x: float
    y: float
    radius: float = BOSS_RADIUS
    weakened_until: float = 0.0
    shielded: bool = False

    def to_dict(self, current_time: float):
        return {
            "id": self.id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "radius": self.radius,
            "weakened": current_time < self.weakened_until,
            "weakened_remaining": round(max(0.0, self.weakened_until - current_time), 1),
            "shielded": self.shielded,
        }


@dataclass
class Player:
    id: str
    name: str
    x: float
    y: float
    radius: float
    color: str
    target_x: float
    target_y: float
    score: int = 0
    peak_score: int = 0
    alive: bool = True
    # Boost tracking
    boost_cooldown_until: float = 0
    boost_active_until: float = 0
    # Invincibility tracking
    invincible_until: float = 0
    # Shooting tracking
    shoot_cooldown_until: float = 0
    # Critical mass tracking
    critical_mass_start: float = 0  # timestamp when threshold crossed, 0 = inactive
    # Power-up tracking
    active_powerup: str = ""
    powerup_until: float = 0
    # Mine tracking
    mines_remaining: int = 0  # how many mines can still be placed
    mines_placed: int = 0  # how many currently on map
    # Homing missile ammo
    homing_missiles_remaining: int = 0
    # Trail power-up tracking
    trail_held: bool = False  # held but not yet activated
    wormhole_held: bool = False  # held but not yet fired
    # Hall of fame: only tracks score earned while 2+ players are present
    played_with_others: bool = False
    peak_score_with_others: int = 0
    trail_last_segment_time: float = 0.0
    # Challenge mode: fixed speed override (bypasses radius-based scaling)
    speed_override: Optional[float] = None

    def to_dict(self, current_time: float):
        critical_mass_active = self.critical_mass_start > 0
        critical_mass_remaining = 0
        if critical_mass_active:
            elapsed = current_time - self.critical_mass_start
            critical_mass_remaining = max(0, CRITICAL_MASS_TIMER - elapsed)
        return {
            "id": self.id,
            "name": self.name,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "radius": round(self.radius, 1),
            "color": self.color,
            "score": self.score,
            "alive": self.alive,
            "is_boosting": current_time < self.boost_active_until,
            "boost_ready": current_time >= self.boost_cooldown_until,
            "is_invincible": current_time < self.invincible_until,
            "shoot_ready": current_time >= self.shoot_cooldown_until,
            "critical_mass_active": critical_mass_active,
            "critical_mass_remaining": round(critical_mass_remaining, 1),
            "active_powerup": self.active_powerup if current_time < self.powerup_until else "",
            "powerup_remaining": round(max(0, self.powerup_until - current_time), 1) if self.active_powerup else 0,
            "mines_remaining": self.mines_remaining,
            "homing_missiles_remaining": self.homing_missiles_remaining,
            "trail_held": self.trail_held,
            "wormhole_held": self.wormhole_held
        }

    def get_speed(self, current_time: float):
        # Larger players move slower, smaller players are much faster
        base = self.speed_override if self.speed_override is not None \
            else BASE_SPEED * (INITIAL_RADIUS / self.radius) ** SPEED_SCALING
        # Apply boost multiplier if active
        if current_time < self.boost_active_until:
            return base * BOOST_SPEED_MULTIPLIER
        # Tron trail grants a speed boost while active - lean into the light-cycle fantasy
        if self.active_powerup == "trail" and current_time < self.powerup_until:
            return base * TRAIL_SPEED_MULTIPLIER
        return base

    def check_invincible(self, current_time: float):
        return current_time < self.invincible_until

    def has_protection(self, current_time: float) -> bool:
        """Check if player is protected by invincibility, shield, or phantom."""
        if current_time < self.invincible_until:
            return True
        return self.active_powerup in ("shield", "phantom") and current_time < self.powerup_until

    def has_shield(self, current_time: float) -> bool:
        """Check if player has an active shield power-up."""
        return self.active_powerup == "shield" and current_time < self.powerup_until


@dataclass
class Spectator:
    id: str
    name: str
    websocket: any


DISASTER_TYPES = ["black_hole", "meteor_shower", "fog_of_war", "feeding_frenzy", "supernova", "earthquake"]

# ── Challenge Mode Configuration ──
TURRET_POSITIONS = [
    (300, 300), (4700, 300), (300, 4700), (4700, 4700),    # corners (start active)
    (2500, 150), (2500, 4850), (150, 2500), (4850, 2500),  # edge midpoints (unlock over time)
]
TURRET_INITIAL_ACTIVE = 4
TURRET_FIRE_INTERVAL_START = 4.0   # seconds between shots at the start
TURRET_FIRE_INTERVAL_MIN = 1.5     # fastest possible fire rate
TURRET_FIRE_INTERVAL_REDUCTION = 0.3  # interval reduction per 30s elapsed
TURRET_ACTIVATE_INTERVAL = 30.0    # new turret unlocks every N seconds
TURRET_MISSILE_COLOR = "#ff3300"
TURRET_MISSILE_LIFETIME = 8.0      # longer than normal - player is far away
TURRET_MISSILE_SPEED = 18
TURRET_MISSILE_TRACKING = 0.12


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to a finite float, clamped to world bounds."""
    try:
        f = float(value)
        if not math.isfinite(f):
            return default
        # Clamp to reasonable world bounds to prevent absurd values
        return max(-1000, min(max(WORLD_WIDTH, WORLD_HEIGHT) + 1000, f))
    except (TypeError, ValueError):
        return default


def sanitize_name(raw: str) -> str:
    """Sanitize a player name: strip HTML/control chars, collapse whitespace, limit length."""
    # Strip HTML tags
    name = re.sub(r'<[^>]*>', '', raw)
    # Strip control characters and zero-width chars
    name = re.sub(r'[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff]', '', name)
    # Collapse whitespace
    name = ' '.join(name.split())
    # Limit length
    name = name[:15].strip()
    return name if name else "Anonymous"


class DisasterManager:
    """Manages natural disaster scheduling and execution."""

    def __init__(self, game):
        self.game = game
        self.active_disaster: Optional[str] = None
        self.disaster_start: float = 0
        self.disaster_end: float = 0
        self.warning_active: bool = False
        self.warning_type: str = ""
        self.warning_start: float = 0
        # Scheduling — timer is paused until enough players join
        self.next_disaster_time: float = 0  # 0 = not scheduled yet
        self.lobby_ready_since: float = 0   # when player count first hit minimum
        self.timer_paused: bool = True       # paused until lobby is ready
        # Black hole state
        self.black_hole: Optional[BlackHole] = None
        # Meteor shower state
        self.meteors: list = []  # active meteor impact markers
        self.last_meteor_time: float = 0
        # Fog of war state
        self.fog_active: bool = False
        # Feeding frenzy state
        self.frenzy_orb_ids: list = []  # track frenzy orbs for cleanup
        # Supernova state
        self.supernova_x: float = 0
        self.supernova_y: float = 0
        self.supernova_triggered: bool = False
        self.supernova_time: float = 0  # when the first pulse started
        self.supernova_pulses_fired: int = 0  # how many pulses have triggered
        # Earthquake state
        self.earthquake_progress: float = 0  # 0..1
        self.earthquake_old_walls: list = []
        self.earthquake_new_walls: list = []
        # Test cycle state
        self._test_queue: list = []  # remaining disaster types to test
        self._test_running: bool = False  # True while last disaster is still active
        self._test_gap: float = 3.0  # seconds between test disasters
        self._test_next_time: float = 0

    def _player_count(self) -> int:
        return len(self.game.players)

    def start_test_cycle(self, current_time: float):
        """Start a test cycle that runs through all disasters in sequence."""
        # End any active disaster first
        if self.active_disaster:
            self._end_disaster(current_time)
        self.warning_active = False
        self.warning_type = ""
        self._test_queue = list(DISASTER_TYPES)
        self._test_running = True
        self._test_next_time = current_time + 1.0  # 1s before first disaster
        print(f"[TEST] Disaster test cycle started: {self._test_queue}")

    def tick(self, current_time: float):
        """Called every game tick."""
        # ── Test cycle override ──
        if self._test_queue or self._test_running:
            if self.active_disaster:
                if current_time >= self.disaster_end:
                    self._end_disaster(current_time)
                    self._test_next_time = current_time + self._test_gap
                    if not self._test_queue:
                        self._test_running = False
                        print("[TEST] Disaster test cycle complete")
                else:
                    self._tick_disaster(current_time)
                return
            if self.warning_active:
                if current_time - self.warning_start >= DISASTER_WARNING_TIME:
                    self._start_disaster(self.warning_type, current_time)
                    self.warning_active = False
                return
            if self._test_queue and current_time >= self._test_next_time:
                dtype = self._test_queue.pop(0)
                self._test_running = True
                self.warning_type = dtype
                self.warning_active = True
                self.warning_start = current_time
                print(f"[TEST] Next disaster: {dtype} ({len(self._test_queue)} remaining)")
            return

        player_count = self._player_count()

        # ── Lobby readiness / timer management ──
        if player_count < DISASTER_MIN_PLAYERS:
            # Not enough players — pause timer and reset lobby readiness
            if not self.timer_paused:
                self.timer_paused = True
                self.next_disaster_time = 0
                self.lobby_ready_since = 0
            # If a warning was queued but players left, cancel it
            if self.warning_active and not self.active_disaster:
                self.warning_active = False
                self.warning_type = ""
            return

        # Enough players are present
        if self.timer_paused:
            # Lobby just became ready — start settle period
            self.lobby_ready_since = current_time
            self.timer_paused = False
            # Schedule first disaster after settle time + shorter first interval
            self.next_disaster_time = (
                current_time + DISASTER_SETTLE_TIME
                + random.uniform(DISASTER_FIRST_MIN, DISASTER_FIRST_MAX)
            )
            return

        # Still in settle period — don't trigger yet
        if current_time - self.lobby_ready_since < DISASTER_SETTLE_TIME:
            return

        # ── Warning phase ──
        if not self.active_disaster and not self.warning_active:
            if self.next_disaster_time > 0 and current_time >= self.next_disaster_time:
                self.warning_type = random.choice(DISASTER_TYPES)
                self.warning_active = True
                self.warning_start = current_time
            return

        if self.warning_active and not self.active_disaster:
            if current_time - self.warning_start >= DISASTER_WARNING_TIME:
                self._start_disaster(self.warning_type, current_time)
                self.warning_active = False
            return

        # ── Active disaster tick ──
        if self.active_disaster:
            if current_time >= self.disaster_end:
                self._end_disaster(current_time)
            else:
                self._tick_disaster(current_time)

    def _start_disaster(self, dtype: str, current_time: float):
        self.active_disaster = dtype
        self.disaster_start = current_time
        starters = {
            "black_hole": self._start_black_hole,
            "meteor_shower": self._start_meteor_shower,
            "fog_of_war": self._start_fog_of_war,
            "feeding_frenzy": self._start_feeding_frenzy,
            "supernova": self._start_supernova,
            "earthquake": self._start_earthquake,
        }
        starters[dtype](current_time)

    def _start_black_hole(self, current_time: float):
        self.disaster_end = current_time + BLACK_HOLE_DURATION
        x, y = self.game.find_safe_orb_position(BLACK_HOLE_MAX_RADIUS)
        self.black_hole = BlackHole(x=x, y=y)

    def _start_meteor_shower(self, current_time: float):
        self.disaster_end = current_time + METEOR_SHOWER_DURATION
        self.meteors = []
        self.last_meteor_time = current_time

    def _start_fog_of_war(self, current_time: float):
        self.disaster_end = current_time + FOG_DURATION
        self.fog_active = True

    def _start_feeding_frenzy(self, current_time: float):
        self.disaster_end = current_time + FRENZY_DURATION
        self._spawn_frenzy_orbs()

    def _start_supernova(self, current_time: float):
        self.supernova_x = random.uniform(200, WORLD_WIDTH - 200)
        self.supernova_y = random.uniform(200, WORLD_HEIGHT - 200)
        self.supernova_triggered = True
        self.supernova_time = current_time
        self.supernova_pulses_fired = 1
        self._apply_supernova()
        total_duration = (SUPERNOVA_PULSE_COUNT - 1) * SUPERNOVA_PULSE_INTERVAL + SUPERNOVA_PULSE_EXPAND_TIME + 0.5
        self.disaster_end = current_time + total_duration

    def _start_earthquake(self, current_time: float):
        self.disaster_end = current_time + EARTHQUAKE_DURATION
        self.earthquake_progress = 0
        self.earthquake_old_walls = [
            {"id": w.id, "x": w.x, "y": w.y, "width": w.width, "height": w.height}
            for w in self.game.walls.values()
        ]
        self.earthquake_new_walls = self._generate_new_wall_positions()

    def _tick_disaster(self, current_time: float):
        tickers = {
            "black_hole": self._tick_black_hole,
            "meteor_shower": self._tick_meteor_shower,
            "earthquake": self._tick_earthquake,
            "supernova": self._tick_supernova,
        }
        ticker = tickers.get(self.active_disaster)
        if ticker:
            ticker(current_time)

    def _end_disaster(self, current_time: float):
        enders = {
            "black_hole": self._end_black_hole,
            "meteor_shower": self._end_meteor_shower,
            "fog_of_war": self._end_fog_of_war,
            "feeding_frenzy": self._end_feeding_frenzy,
            "supernova": self._end_supernova,
            "earthquake": self._end_earthquake,
        }
        ender = enders.get(self.active_disaster)
        if ender:
            ender()
        self.active_disaster = None
        self.next_disaster_time = current_time + random.uniform(DISASTER_MIN_INTERVAL, DISASTER_MAX_INTERVAL)

    def _end_black_hole(self):
        if self.black_hole:
            for _ in range(BLACK_HOLE_EXIT_ORB_COUNT):
                angle = random.uniform(0, math.pi * 2)
                dist = random.uniform(50, 300)
                ox = max(50, min(WORLD_WIDTH - 50, self.black_hole.x + math.cos(angle) * dist))
                oy = max(50, min(WORLD_HEIGHT - 50, self.black_hole.y + math.sin(angle) * dist))
                self.game.orb_counter += 1
                orb_id = f"orb_{self.game.orb_counter}"
                self.game.energy_orbs[orb_id] = EnergyOrb(id=orb_id, x=ox, y=oy)
            self.game._energy_orbs_cache = None
        self.black_hole = None

    def _end_meteor_shower(self):
        self.meteors = []

    def _end_fog_of_war(self):
        self.fog_active = False

    def _end_feeding_frenzy(self):
        for orb_id in self.frenzy_orb_ids:
            if orb_id in self.game.energy_orbs:
                del self.game.energy_orbs[orb_id]
        self.frenzy_orb_ids = []
        self.game._energy_orbs_cache = None

    def _end_supernova(self):
        self.supernova_triggered = False
        self.supernova_pulses_fired = 0

    def _end_earthquake(self):
        self._finalize_earthquake()
        self.earthquake_progress = 0

    # ── Black Hole ──

    def _tick_black_hole(self, current_time: float):
        bh = self.black_hole
        if not bh:
            return
        elapsed = current_time - self.disaster_start
        progress = min(1.0, elapsed / BLACK_HOLE_DURATION)
        bh.current_radius = BLACK_HOLE_INITIAL_RADIUS + (bh.max_radius - BLACK_HOLE_INITIAL_RADIUS) * progress

        self._apply_black_hole_pull(bh, progress, current_time)
        self._apply_black_hole_orb_pull(bh, progress)

    def _apply_black_hole_pull(self, bh, progress: float, current_time: float):
        """Pull players toward the black hole and kill those that reach the center."""
        for player in self.game.players.values():
            if not player.alive:
                continue
            dx = bh.x - player.x
            dy = bh.y - player.y
            dist_sq = max(1, dx * dx + dy * dy)
            dist = math.sqrt(dist_sq)

            if dist >= BLACK_HOLE_PULL_RANGE:
                continue

            mass_factor = (INITIAL_RADIUS / player.radius) ** BLACK_HOLE_MASS_FACTOR
            proximity_factor = (1.0 - (dist / BLACK_HOLE_PULL_RANGE)) ** 0.5  # sqrt curve — strong pull much further out
            ramp = 0.3 + 0.7 * progress  # starts at 30% strength, not zero
            pull = BLACK_HOLE_PULL_STRENGTH * proximity_factor * mass_factor * ramp

            # Boosting reduces pull to 30% — costs mass but lets you claw out
            if current_time < player.boost_active_until:
                pull *= 0.3

            player.x += (dx / dist) * pull
            player.y += (dy / dist) * pull

            if dist < bh.current_radius * BLACK_HOLE_KILL_RADIUS_FACTOR:
                if not player.check_invincible(current_time) and not player.has_shield(current_time):
                    player.alive = False
                    player.score = 0
                    self.game.add_kill("Black Hole", player.name)

    def _apply_black_hole_orb_pull(self, bh, progress: float):
        """Pull energy orbs toward the black hole and consume those that reach the center."""
        orb_moved = False
        for orb in self.game.energy_orbs.values():
            dx = bh.x - orb.x
            dy = bh.y - orb.y
            dist = math.sqrt(dx * dx + dy * dy)
            if 0 < dist < BLACK_HOLE_PULL_RANGE:
                pull = BLACK_HOLE_ORB_PULL_STRENGTH * (1.0 - dist / BLACK_HOLE_PULL_RANGE) * progress
                orb.x += (dx / dist) * pull
                orb.y += (dy / dist) * pull
                orb_moved = True

        kill_radius_sq = (bh.current_radius * BLACK_HOLE_KILL_RADIUS_FACTOR) ** 2
        orbs_consumed = [oid for oid, orb in self.game.energy_orbs.items()
                         if (orb.x - bh.x)**2 + (orb.y - bh.y)**2 < kill_radius_sq]
        for oid in orbs_consumed:
            del self.game.energy_orbs[oid]

        if orb_moved or orbs_consumed:
            self.game._energy_orbs_cache = None

    # ── Meteor Shower ──

    def _is_sheltered(self, player) -> bool:
        """Check if a player is sheltered by a wall (inside or very close)."""
        for wall in self.game.walls.values():
            if (wall.x <= player.x <= wall.x + wall.width and
                    wall.y <= player.y <= wall.y + wall.height):
                return True
            closest_x = max(wall.x, min(player.x, wall.x + wall.width))
            closest_y = max(wall.y, min(player.y, wall.y + wall.height))
            wall_dist = math.sqrt((player.x - closest_x)**2 + (player.y - closest_y)**2)
            if wall_dist < player.radius * 0.5:
                return True
        return False

    def _tick_meteor_shower(self, current_time: float):
        if current_time - self.last_meteor_time >= METEOR_INTERVAL:
            self.last_meteor_time = current_time
            for _ in range(METEOR_COUNT_PER_WAVE):
                mx = random.uniform(50, WORLD_WIDTH - 50)
                my = random.uniform(50, WORLD_HEIGHT - 50)
                self.meteors.append(Meteor(x=mx, y=my, impact_time=current_time))
                self._apply_meteor_damage(mx, my, current_time)

        self.meteors = [m for m in self.meteors if current_time - m.impact_time < METEOR_MARKER_DURATION]

    def _apply_meteor_damage(self, mx: float, my: float, current_time: float):
        """Damage players in blast radius of a meteor impact."""
        for player in self.game.players.values():
            if not player.alive or player.check_invincible(current_time):
                continue
            if player.has_shield(current_time):
                continue
            if self._is_sheltered(player):
                continue
            dx = player.x - mx
            dy = player.y - my
            if dx * dx + dy * dy < (METEOR_BLAST_RADIUS + player.radius) ** 2:
                player.radius = max(MIN_RADIUS, player.radius - METEOR_DAMAGE)
                if player.radius <= MIN_RADIUS:
                    player.alive = False
                    player.score = 0
                    self.game.add_kill("Meteor", player.name)

    # ── Feeding Frenzy ──

    def _spawn_frenzy_orbs(self):
        self.frenzy_orb_ids = []
        for _ in range(FRENZY_ORB_COUNT):
            self.game.orb_counter += 1
            orb_id = f"frenzy_{self.game.orb_counter}"
            x, y = self.game.find_safe_orb_position(ENERGY_ORB_RADIUS)
            hue = 0.25 + random.random() * 0.15
            r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
            color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
            self.game.energy_orbs[orb_id] = EnergyOrb(id=orb_id, x=x, y=y, color=color)
            self.frenzy_orb_ids.append(orb_id)
        self.game._energy_orbs_cache = None

    # ── Supernova ──

    def _tick_supernova(self, current_time: float):
        """Fire subsequent pulses at intervals."""
        if self.supernova_pulses_fired >= SUPERNOVA_PULSE_COUNT:
            return
        elapsed = current_time - self.supernova_time
        next_pulse_time = self.supernova_pulses_fired * SUPERNOVA_PULSE_INTERVAL
        if elapsed >= next_pulse_time:
            self.supernova_pulses_fired += 1
            self._apply_supernova()

    def _apply_supernova(self):
        base_loss = random.uniform(SUPERNOVA_MASS_LOSS_MIN, SUPERNOVA_MASS_LOSS_MAX)
        for player in self.game.players.values():
            if not player.alive:
                continue
            dx = player.x - self.supernova_x
            dy = player.y - self.supernova_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < SUPERNOVA_RADIUS:
                # Closer to epicentre = up to 2x damage
                proximity = 1.0 + (1.0 - dist / SUPERNOVA_RADIUS)
                loss_pct = base_loss * proximity
                player.radius = player.radius * (1 - loss_pct)
                player.score = max(0, int(player.score * (1 - loss_pct * 0.5)))
                # Kill if radius drops to minimum
                if player.radius <= MIN_RADIUS:
                    player.radius = MIN_RADIUS
                    player.alive = False
                    player.score = 0
                    self.game.add_kill("Supernova", player.name)

    # ── Earthquake ──

    def _generate_new_wall_positions(self) -> list:
        new_walls = []
        for old in self.earthquake_old_walls:
            # Randomize position but keep same dimensions
            new_x = random.uniform(100, WORLD_WIDTH - 100 - old["width"])
            new_y = random.uniform(100, WORLD_HEIGHT - 100 - old["height"])
            new_walls.append({
                "id": old["id"], "x": new_x, "y": new_y,
                "width": old["width"], "height": old["height"]
            })
        return new_walls

    def _tick_earthquake(self, current_time: float):
        elapsed = current_time - self.disaster_start
        self.earthquake_progress = min(1.0, elapsed / EARTHQUAKE_DURATION)
        t = self.earthquake_progress
        # Smooth easing
        t = t * t * (3 - 2 * t)

        for old, new in zip(self.earthquake_old_walls, self.earthquake_new_walls):
            wall = self.game.walls.get(old["id"])
            if wall:
                wall.x = old["x"] + (new["x"] - old["x"]) * t
                wall.y = old["y"] + (new["y"] - old["y"]) * t
        self.game._walls_cache = None
        self.game._walls_dirty = True

    def _finalize_earthquake(self):
        for new in self.earthquake_new_walls:
            wall = self.game.walls.get(new["id"])
            if wall:
                wall.x = new["x"]
                wall.y = new["y"]
        self.game._walls_cache = None
        self.game._walls_dirty = True
        self.game.relocate_trapped_orbs()

    def get_state(self, current_time: float) -> dict:
        """Return disaster state for broadcast to clients."""
        state = {
            "active": self.active_disaster,
            "warning": self.warning_type if self.warning_active else None,
            "warning_remaining": round(max(0, DISASTER_WARNING_TIME - (current_time - self.warning_start)), 1) if self.warning_active else 0,
        }
        if self.active_disaster:
            elapsed = current_time - self.disaster_start
            duration = self.disaster_end - self.disaster_start
            state["remaining"] = round(max(0, duration - elapsed), 1)
            state["progress"] = round(min(1.0, elapsed / duration), 2)

        if self.active_disaster == "black_hole" and self.black_hole:
            state["black_hole"] = self.black_hole.to_dict()
        elif self.active_disaster == "meteor_shower":
            state["meteors"] = [m.to_dict() for m in self.meteors]
        elif self.active_disaster == "fog_of_war":
            state["fog_radius"] = FOG_VISIBILITY_RADIUS
        elif self.active_disaster == "supernova":
            state["supernova"] = {
                "x": round(self.supernova_x, 1),
                "y": round(self.supernova_y, 1),
                "radius": SUPERNOVA_RADIUS,
                "time": round(current_time - self.supernova_time, 2),
                "pulse_count": SUPERNOVA_PULSE_COUNT,
                "pulse_interval": SUPERNOVA_PULSE_INTERVAL,
                "pulse_expand": SUPERNOVA_PULSE_EXPAND_TIME
            }
        elif self.active_disaster == "earthquake":
            state["earthquake_progress"] = round(self.earthquake_progress, 2)

        return state


class GameState:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.spectators: Dict[str, Spectator] = {}
        self.energy_orbs: Dict[str, EnergyOrb] = {}
        self.spike_orbs: Dict[str, SpikeOrb] = {}
        self.golden_orbs: Dict[str, GoldenOrb] = {}
        self.walls: Dict[str, Wall] = {}
        self.projectiles: Dict[str, Projectile] = {}
        self.powerup_orbs: Dict[str, PowerUpOrb] = {}
        self.mine_pickups: Dict[str, MinePickup] = {}
        self.mines: Dict[str, Mine] = {}
        self.wormhole_portals: Dict[str, WormholePortal] = {}
        self.wormhole_counter = 0
        self.trail_segments: list = []
        self.connections: Dict[str, any] = {}
        self.orb_counter = 0
        self.spike_counter = 0
        self.golden_counter = 0
        self.wall_counter = 0
        self.projectile_counter = 0
        self.powerup_counter = 0
        self.powerup_respawn_timers: list = []  # [(respawn_time), ...]
        self.mine_pickup_counter = 0
        self.mine_pickup_respawn_timers: list = []
        self.mine_counter = 0
        # Kill feed
        self.kill_feed: list = []  # [(timestamp, killer_name, victim_name), ...]
        # Leaderboard cache (updated every 1 second instead of every tick)
        self._cached_leaderboard: list = []
        self._leaderboard_update_time: float = 0
        self._leaderboard_cache_duration: float = 1.0  # seconds
        # Orb serialization caches (invalidated on collect/respawn)
        self._energy_orbs_cache: list = None
        self._spike_orbs_cache: list = None
        self._golden_orbs_cache: list = None
        self._powerup_orbs_cache: list = None
        self._mine_pickups_cache: list = None
        self._walls_cache: list = None
        self._walls_dirty: bool = False  # True when walls have moved and clients need an update
        self.spawn_walls()
        self.spawn_energy_orbs(ENERGY_ORB_COUNT)
        self.spawn_spike_orbs(SPIKE_ORB_COUNT)
        self.spawn_golden_orbs(GOLDEN_ORB_COUNT)
        self.spawn_powerup_orbs(POWERUP_COUNT)
        self.spawn_mine_pickups()
        self.disaster_manager = DisasterManager(self)

    def generate_color(self) -> str:
        """Generate a vibrant random color."""
        hue = random.random()
        saturation = 0.7 + random.random() * 0.3
        value = 0.8 + random.random() * 0.2
        r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    def find_safe_orb_position(self, radius: float = 10) -> tuple:
        """Find a random position not inside any wall."""
        for _ in range(50):
            x = random.uniform(50, WORLD_WIDTH - 50)
            y = random.uniform(50, WORLD_HEIGHT - 50)
            inside_wall = False
            for wall in self.walls.values():
                if (wall.x - radius < x < wall.x + wall.width + radius and
                    wall.y - radius < y < wall.y + wall.height + radius):
                    inside_wall = True
                    break
            if not inside_wall:
                return x, y
        return x, y  # fallback to last attempt

    def _is_inside_wall(self, x: float, y: float, radius: float) -> bool:
        """Check if a point with given radius overlaps any wall."""
        for wall in self.walls.values():
            if (wall.x - radius < x < wall.x + wall.width + radius and
                wall.y - radius < y < wall.y + wall.height + radius):
                return True
        return False

    def relocate_trapped_orbs(self):
        """Move any orbs trapped inside walls to safe positions after earthquake."""
        moved = False
        for orb in self.energy_orbs.values():
            if self._is_inside_wall(orb.x, orb.y, orb.radius):
                orb.x, orb.y = self.find_safe_orb_position(orb.radius)
                moved = True
        for orb in self.spike_orbs.values():
            if self._is_inside_wall(orb.x, orb.y, orb.radius):
                orb.x, orb.y = self.find_safe_orb_position(orb.radius)
                moved = True
        for orb in self.golden_orbs.values():
            if self._is_inside_wall(orb.x, orb.y, orb.radius):
                orb.x, orb.y = self.find_safe_orb_position(orb.radius)
                moved = True
        for orb in self.powerup_orbs.values():
            if self._is_inside_wall(orb.x, orb.y, orb.radius):
                orb.x, orb.y = self.find_safe_orb_position(orb.radius)
                moved = True
        if moved:
            self._energy_orbs_cache = None
            self._spike_orbs_cache = None
            self._golden_orbs_cache = None
            self._powerup_orbs_cache = None

    def spawn_energy_orbs(self, count: int):
        """Spawn energy orbs at random positions."""
        for _ in range(count):
            self.orb_counter += 1
            orb_id = f"orb_{self.orb_counter}"
            # Random green-ish color
            hue = 0.25 + random.random() * 0.15  # Green range
            r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
            color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

            x, y = self.find_safe_orb_position(ENERGY_ORB_RADIUS)
            self.energy_orbs[orb_id] = EnergyOrb(
                id=orb_id,
                x=x,
                y=y,
                color=color
            )

    def spawn_spike_orbs(self, count: int):
        """Spawn evil spike orbs at random positions."""
        for _ in range(count):
            self.spike_counter += 1
            orb_id = f"spike_{self.spike_counter}"
            # Random red/pink color
            hue = random.uniform(0.95, 1.0) if random.random() > 0.5 else random.uniform(0.0, 0.05)
            r, g, b = colorsys.hsv_to_rgb(hue, 0.9, 0.9)
            color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

            x, y = self.find_safe_orb_position(SPIKE_ORB_RADIUS)
            self.spike_orbs[orb_id] = SpikeOrb(
                id=orb_id,
                x=x,
                y=y,
                color=color
            )

    def spawn_golden_orbs(self, count: int):
        """Spawn rare golden orbs worth extra points."""
        for _ in range(count):
            self.golden_counter += 1
            orb_id = f"golden_{self.golden_counter}"
            x, y = self.find_safe_orb_position(GOLDEN_ORB_RADIUS)
            self.golden_orbs[orb_id] = GoldenOrb(
                id=orb_id,
                x=x,
                y=y
            )

    def spawn_powerup_orbs(self, count: int):
        """Spawn mystery power-up orbs."""
        for _ in range(count):
            self.powerup_counter += 1
            orb_id = f"powerup_{self.powerup_counter}"
            x, y = self.find_safe_orb_position(POWERUP_RADIUS)
            self.powerup_orbs[orb_id] = PowerUpOrb(
                id=orb_id,
                x=x,
                y=y
            )
        self._powerup_orbs_cache = None

    def spawn_mine_pickups(self):
        """Spawn super rare mine pickup orbs."""
        for _ in range(MINE_PICKUP_COUNT):
            self.mine_pickup_counter += 1
            pickup_id = f"mine_pickup_{self.mine_pickup_counter}"
            x, y = self.find_safe_spawn()
            self.mine_pickups[pickup_id] = MinePickup(
                id=pickup_id,
                x=x,
                y=y
            )
        self._mine_pickups_cache = None

    def spawn_walls(self):
        """Spawn obstacle walls around the map."""
        wall_configs = [
            # Central cross
            {"x": WORLD_WIDTH // 2 - 150, "y": WORLD_HEIGHT // 2 - 25, "width": 300, "height": 50},
            {"x": WORLD_WIDTH // 2 - 25, "y": WORLD_HEIGHT // 2 - 150, "width": 50, "height": 300},
            # Corner L-shapes (4 corners, 2 walls each = 8 walls)
            {"x": 200, "y": 200, "width": 150, "height": 30},
            {"x": 200, "y": 200, "width": 30, "height": 150},
            {"x": WORLD_WIDTH - 350, "y": 200, "width": 150, "height": 30},
            {"x": WORLD_WIDTH - 230, "y": 200, "width": 30, "height": 150},
            {"x": 200, "y": WORLD_HEIGHT - 230, "width": 150, "height": 30},
            {"x": 200, "y": WORLD_HEIGHT - 350, "width": 30, "height": 150},
            {"x": WORLD_WIDTH - 350, "y": WORLD_HEIGHT - 230, "width": 150, "height": 30},
            {"x": WORLD_WIDTH - 230, "y": WORLD_HEIGHT - 350, "width": 30, "height": 150},
        ]
        # Fill remaining wall slots with random walls spread across the map
        remaining = WALL_COUNT - len(wall_configs)
        for _ in range(remaining):
            if random.random() < 0.5:
                w = random.randint(120, 300)
                h = random.randint(25, 50)
            else:
                w = random.randint(25, 50)
                h = random.randint(120, 300)
            x = random.uniform(300, WORLD_WIDTH - 300 - w)
            y = random.uniform(300, WORLD_HEIGHT - 300 - h)
            wall_configs.append({"x": x, "y": y, "width": w, "height": h})

        for i, cfg in enumerate(wall_configs):
            wall_id = f"wall_{i}"
            self.walls[wall_id] = Wall(
                id=wall_id,
                x=cfg["x"],
                y=cfg["y"],
                width=cfg["width"],
                height=cfg["height"]
            )

    def add_kill(self, killer_name: str, victim_name: str):
        """Add a kill to the feed."""
        self.kill_feed.append({
            "time": time.time(),
            "killer": killer_name,
            "victim": victim_name
        })
        # Keep only recent kills
        if len(self.kill_feed) > KILL_FEED_MAX * 2:
            self.kill_feed = self.kill_feed[-KILL_FEED_MAX:]

    def get_kill_feed(self) -> list:
        """Get recent kills for display."""
        current_time = time.time()
        # Filter to recent kills only
        recent = [k for k in self.kill_feed if current_time - k["time"] < KILL_FEED_DURATION]
        return recent[-KILL_FEED_MAX:]

    def activate_boost(self, player_id: str):
        """Activate boost for a player."""
        if player_id not in self.players:
            return
        player = self.players[player_id]
        current_time = time.time()

        # Speed Force: unlimited boost — no cooldown, no mass cost
        if player.active_powerup == "speed_force" and current_time < player.powerup_until:
            player.boost_active_until = current_time + BOOST_DURATION
            return

        # Check cooldown and minimum size
        if current_time < player.boost_cooldown_until:
            return
        if player.radius <= MIN_RADIUS + BOOST_MASS_COST:
            return

        # Activate boost
        player.boost_active_until = current_time + BOOST_DURATION
        player.boost_cooldown_until = current_time + BOOST_COOLDOWN
        player.radius -= BOOST_MASS_COST

        # Deploy trail if held
        if player.trail_held:
            player.trail_held = False
            player.active_powerup = "trail"
            player.powerup_until = current_time + POWERUP_DURATIONS["trail"]

    def shoot(self, player_id: str, target_x: float, target_y: float):
        """Fire a projectile from a player toward a target position."""
        if player_id not in self.players:
            return
        player = self.players[player_id]
        current_time = time.time()

        if not player.alive:
            return

        has_rapid_fire = player.active_powerup == "rapid_fire" and current_time < player.powerup_until
        has_homing = player.homing_missiles_remaining > 0
        has_wormhole = player.wormhole_held

        # Wormhole bypasses the size check (no mass cost, no projectile)
        if not has_wormhole and player.radius < PROJECTILE_MIN_RADIUS:
            return

        if not has_rapid_fire and not has_wormhole and current_time < player.shoot_cooldown_until:
            return

        # Calculate direction
        dx = target_x - player.x
        dy = target_y - player.y
        distance = math.sqrt(dx * dx + dy * dy)
        if distance < 1:
            return

        # Normalize direction
        ndx = dx / distance
        ndy = dy / distance

        # Wormhole: fire portal, no mass cost, no cooldown consumed
        if has_wormhole:
            player.wormhole_held = False
            self.wormhole_counter += 1
            portal_id = f"wormhole_{self.wormhole_counter}"
            self.wormhole_portals[portal_id] = WormholePortal(
                id=portal_id,
                owner_id=player_id,
                x=player.x + ndx * (player.radius + WORMHOLE_RADIUS + 2),
                y=player.y + ndy * (player.radius + WORMHOLE_RADIUS + 2),
                dx=ndx,
                dy=ndy,
                travel_remaining=WORMHOLE_TRAVEL_DIST,
                traveling=True,
                created_at=current_time
            )
            return

        # Cost mass (free with rapid fire/homing)
        if has_homing:
            # Homing missiles: no mass cost, normal cooldown, consume ammo
            player.shoot_cooldown_until = current_time + PROJECTILE_COOLDOWN
            player.homing_missiles_remaining -= 1
        elif not has_rapid_fire:
            player.radius -= PROJECTILE_COST
            player.shoot_cooldown_until = current_time + PROJECTILE_COOLDOWN

        # Spawn projectile at player's edge
        self.projectile_counter += 1
        proj_id = f"proj_{self.projectile_counter}"

        if has_homing:
            # Fire in aimed direction - missile will proximity-acquire targets in flight
            self.projectiles[proj_id] = HomingMissile(
                id=proj_id,
                owner_id=player_id,
                x=player.x + ndx * (player.radius + 10),
                y=player.y + ndy * (player.radius + 10),
                dx=ndx,
                dy=ndy,
                color="#ffaa00",
                created_at=current_time,
                lifetime=HOMING_MISSILE_LIFETIME,
                radius=8,
                target_id="",
                speed=HOMING_MISSILE_SPEED,
                tracking_strength=HOMING_TRACKING_STRENGTH
            )
        else:
            # Normal projectile
            self.projectiles[proj_id] = Projectile(
                id=proj_id,
                owner_id=player_id,
                x=player.x + ndx * (player.radius + PROJECTILE_RADIUS + 2),
                y=player.y + ndy * (player.radius + PROJECTILE_RADIUS + 2),
                dx=ndx,
                dy=ndy,
                color=player.color,
                created_at=current_time,
                lifetime=PROJECTILE_RAPID_FIRE_LIFETIME if has_rapid_fire else PROJECTILE_LIFETIME
            )

    def place_mine(self, player_id: str):
        """Place a mine at the player's current position."""
        if player_id not in self.players:
            return
        player = self.players[player_id]

        if not player.alive or player.mines_remaining <= 0:
            return
        if player.mines_placed >= MINE_MAX_COUNT:
            return

        self.mine_counter += 1
        mine_id = f"mine_{self.mine_counter}"
        self.mines[mine_id] = Mine(
            id=mine_id,
            owner_id=player_id,
            x=player.x,
            y=player.y,
            armed_at=time.time() + MINE_ARM_DELAY,
            color=player.color
        )
        player.mines_remaining -= 1
        player.mines_placed += 1

    def add_player(self, player_id: str, name: str, websocket) -> Player:
        """Add a new player to the game."""
        # Spawn at random position away from walls and other players
        x, y = self.find_safe_spawn()

        player = Player(
            id=player_id,
            name=sanitize_name(name),
            x=x,
            y=y,
            radius=INITIAL_RADIUS,
            color=self.generate_color(),
            target_x=x,
            target_y=y,
            invincible_until=time.time() + RESPAWN_INVINCIBILITY
        )
        self.players[player_id] = player
        self.connections[player_id] = websocket
        # Mark hall of fame eligibility: once 2+ players are present, flag all of them
        if len(self.players) >= 2:
            for p in self.players.values():
                p.played_with_others = True
        return player

    def find_safe_spawn(self) -> tuple:
        """Find a spawn point not inside a wall."""
        for _ in range(50):  # Max attempts
            x = random.uniform(100, WORLD_WIDTH - 100)
            y = random.uniform(100, WORLD_HEIGHT - 100)
            # Check if inside any wall
            safe = True
            for wall in self.walls.values():
                if (wall.x - 50 < x < wall.x + wall.width + 50 and
                    wall.y - 50 < y < wall.y + wall.height + 50):
                    safe = False
                    break
            if safe:
                return x, y
        # Fallback
        return WORLD_WIDTH // 2, WORLD_HEIGHT // 2

    def remove_player(self, player_id: str):
        """Remove a player from the game."""
        if player_id in self.players:
            player = self.players[player_id]
            if player.peak_score_with_others > 0:
                record_alltime_score(player.name, player.peak_score_with_others)
            del self.players[player_id]
        if player_id in self.connections:
            del self.connections[player_id]

    def add_spectator(self, spectator_id: str, name: str, websocket) -> Spectator:
        """Add a new spectator to the game."""
        spectator = Spectator(
            id=spectator_id,
            name=sanitize_name(name),
            websocket=websocket
        )
        self.spectators[spectator_id] = spectator
        self.connections[spectator_id] = websocket
        return spectator

    def remove_spectator(self, spectator_id: str):
        """Remove a spectator from the game."""
        if spectator_id in self.spectators:
            del self.spectators[spectator_id]
        if spectator_id in self.connections:
            del self.connections[spectator_id]

    def update_player_target(self, player_id: str, target_x: float, target_y: float):
        """Update where a player is moving towards."""
        if player_id in self.players:
            self.players[player_id].target_x = target_x
            self.players[player_id].target_y = target_y

    def respawn_player(self, player_id: str):
        """Respawn a dead player."""
        if player_id in self.players:
            player = self.players[player_id]
            x, y = self.find_safe_spawn()
            player.x = x
            player.y = y
            player.radius = INITIAL_RADIUS
            player.target_x = player.x
            player.target_y = player.y
            player.alive = True
            player.invincible_until = time.time() + RESPAWN_INVINCIBILITY
            player.boost_cooldown_until = 0
            player.boost_active_until = 0
            player.shoot_cooldown_until = 0
            player.critical_mass_start = 0
            player.active_powerup = ""
            player.powerup_until = 0
            player.trail_held = False
            player.wormhole_held = False

    def _move_players(self, current_time: float):
        """Move players towards targets, handle bounds and wall collisions, apply shrink."""
        for player in self.players.values():
            if not player.alive:
                continue

            prev_x, prev_y = player.x, player.y

            dx = player.target_x - player.x
            dy = player.target_y - player.y
            dist_sq = dx * dx + dy * dy

            if dist_sq > MOVE_THRESHOLD_SQ:
                distance = math.sqrt(dist_sq)
                speed = player.get_speed(current_time)
                player.x += (dx / distance) * speed
                player.y += (dy / distance) * speed

            # Keep player in bounds
            player.x = max(player.radius, min(WORLD_WIDTH - player.radius, player.x))
            player.y = max(player.radius, min(WORLD_HEIGHT - player.radius, player.y))

            # Wall collisions - push player out of walls (phantom passes through)
            self._resolve_wall_collisions(player, prev_x, prev_y, current_time)

            # Slowly shrink (but not below minimum)
            if player.radius > MIN_RADIUS + 5:
                player.radius = max(MIN_RADIUS, player.radius - SHRINK_RATE)

    def _resolve_wall_collisions(self, player, prev_x: float, prev_y: float, current_time: float):
        """Push a player out of any overlapping walls."""
        is_phantom = player.active_powerup == "phantom" and current_time < player.powerup_until
        wall_iters = 0 if is_phantom else WALL_COLLISION_ITERATIONS
        for _iteration in range(wall_iters):
            for wall in self.walls.values():
                closest_x = max(wall.x, min(player.x, wall.x + wall.width))
                closest_y = max(wall.y, min(player.y, wall.y + wall.height))
                dist_x = player.x - closest_x
                dist_y = player.y - closest_y
                dist = math.sqrt(dist_x * dist_x + dist_y * dist_y)

                if dist < player.radius:
                    if dist > 0:
                        overlap = player.radius - dist + 1
                        player.x += (dist_x / dist) * overlap
                        player.y += (dist_y / dist) * overlap
                    else:
                        self._push_player_from_wall(player, wall, prev_x, prev_y)

    def _push_player_from_wall(self, player, wall, prev_x: float, prev_y: float):
        """Push a player whose center is inside a wall back to safety."""
        push_dx = prev_x - player.x
        push_dy = prev_y - player.y
        push_dist = math.sqrt(push_dx * push_dx + push_dy * push_dy)
        if push_dist > 0:
            player.x = prev_x
            player.y = prev_y
        else:
            # Fallback: push to nearest edge
            push_left = player.x - wall.x
            push_right = (wall.x + wall.width) - player.x
            push_up = player.y - wall.y
            push_down = (wall.y + wall.height) - player.y
            min_push = min(push_left, push_right, push_up, push_down)
            if min_push == push_left:
                player.x = wall.x - player.radius - 1
            elif min_push == push_right:
                player.x = wall.x + wall.width + player.radius + 1
            elif min_push == push_up:
                player.y = wall.y - player.radius - 1
            else:
                player.y = wall.y + wall.height + player.radius + 1

    def _check_orb_collisions(self, current_time: float):
        """Handle all orb pickup collisions (energy, spike, golden, power-up) and respawns."""
        self._collect_energy_orbs()
        self._collect_spike_orbs(current_time)
        self._collect_golden_orbs()
        self._collect_powerup_orbs(current_time)
        self._process_powerup_respawns(current_time)

    def _collect_energy_orbs(self):
        orbs_to_remove = []
        for orb_id, orb in self.energy_orbs.items():
            for player in self.players.values():
                if not player.alive:
                    continue
                dx = player.x - orb.x
                dy = player.y - orb.y
                combined = player.radius + orb.radius
                if dx * dx + dy * dy < combined * combined:
                    player.radius = min(MAX_RADIUS, player.radius + ENERGY_ORB_VALUE)
                    player.score += 10
                    orbs_to_remove.append(orb_id)
                    break
        if orbs_to_remove:
            for orb_id in orbs_to_remove:
                del self.energy_orbs[orb_id]
            self.spawn_energy_orbs(len(orbs_to_remove))
            self._energy_orbs_cache = None

    def _collect_spike_orbs(self, current_time: float):
        spikes_to_remove = []
        for orb_id, orb in self.spike_orbs.items():
            for player in self.players.values():
                if not player.alive:
                    continue
                if player.has_protection(current_time):
                    continue
                dx = player.x - orb.x
                dy = player.y - orb.y
                combined = player.radius + orb.radius
                if dx * dx + dy * dy < combined * combined:
                    player.radius = max(MIN_RADIUS, player.radius * 0.75)
                    spikes_to_remove.append(orb_id)
                    break
        if spikes_to_remove:
            for orb_id in spikes_to_remove:
                del self.spike_orbs[orb_id]
            self.spawn_spike_orbs(len(spikes_to_remove))
            self._spike_orbs_cache = None

    def _collect_golden_orbs(self):
        golden_to_remove = []
        for orb_id, orb in self.golden_orbs.items():
            for player in self.players.values():
                if not player.alive:
                    continue
                dx = player.x - orb.x
                dy = player.y - orb.y
                combined = player.radius + orb.radius
                if dx * dx + dy * dy < combined * combined:
                    player.radius = min(MAX_RADIUS, player.radius + GOLDEN_ORB_VALUE)
                    player.score += 50
                    golden_to_remove.append(orb_id)
                    break
        if golden_to_remove:
            for orb_id in golden_to_remove:
                del self.golden_orbs[orb_id]
            self.spawn_golden_orbs(len(golden_to_remove))
            self._golden_orbs_cache = None

    def _collect_powerup_orbs(self, current_time: float):
        powerups_to_remove = []
        for orb_id, orb in self.powerup_orbs.items():
            for player in self.players.values():
                if not player.alive:
                    continue
                dx = player.x - orb.x
                dy = player.y - orb.y
                combined = player.radius + orb.radius
                if dx * dx + dy * dy < combined * combined:
                    powerup_type = random.choice(POWERUP_TYPES)
                    if powerup_type == "homing_missiles":
                        player.homing_missiles_remaining = HOMING_MISSILES_AMMO
                    elif powerup_type == "trail":
                        # Swap: drop wormhole if held, take trail
                        player.wormhole_held = False
                        player.trail_held = True
                    elif powerup_type == "wormhole":
                        # Swap: drop trail if held, take wormhole
                        player.trail_held = False
                        player.wormhole_held = True
                    else:
                        player.active_powerup = powerup_type
                        player.powerup_until = current_time + POWERUP_DURATIONS[powerup_type]
                    powerups_to_remove.append(orb_id)
                    break
        if powerups_to_remove:
            for orb_id in powerups_to_remove:
                del self.powerup_orbs[orb_id]
            self._powerup_orbs_cache = None
            for _ in powerups_to_remove:
                self.powerup_respawn_timers.append(current_time + POWERUP_RESPAWN_DELAY)

    def _process_powerup_respawns(self, current_time: float):
        if self.powerup_respawn_timers:
            respawns = [t for t in self.powerup_respawn_timers if current_time >= t]
            if respawns:
                self.powerup_respawn_timers = [t for t in self.powerup_respawn_timers if current_time < t]
                self.spawn_powerup_orbs(len(respawns))

    def _collect_mine_pickups(self, current_time: float):
        """Collect mine pickup orbs (super rare)."""
        pickups_to_remove = []
        for pickup_id, pickup in self.mine_pickups.items():
            for player in self.players.values():
                if not player.alive:
                    continue
                dx = player.x - pickup.x
                dy = player.y - pickup.y
                combined = player.radius + pickup.radius
                if dx * dx + dy * dy < combined * combined:
                    if player.mines_remaining >= MINE_MAX_COUNT:
                        continue  # already full, skip pickup
                    player.mines_remaining = min(player.mines_remaining + 1, MINE_MAX_COUNT)
                    pickups_to_remove.append(pickup_id)
                    break
        if pickups_to_remove:
            for pickup_id in pickups_to_remove:
                del self.mine_pickups[pickup_id]
            self._mine_pickups_cache = None
            for _ in pickups_to_remove:
                self.mine_pickup_respawn_timers.append(current_time + MINE_PICKUP_RESPAWN_DELAY)

    def _process_mine_pickup_respawns(self, current_time: float):
        """Respawn mine pickups after delay."""
        if self.mine_pickup_respawn_timers:
            respawns = [t for t in self.mine_pickup_respawn_timers if current_time >= t]
            if respawns:
                self.mine_pickup_respawn_timers = [t for t in self.mine_pickup_respawn_timers if current_time < t]
                self.spawn_mine_pickups()

    def _consume_player(self, consumer, victim):
        """One player consumes another."""
        consumer.radius = min(MAX_RADIUS, consumer.radius + victim.radius * 0.5)
        consumer.score += KILL_BASE_SCORE + int(victim.score * KILL_SCORE_RATIO)
        victim.alive = False
        victim.score = 0
        self.add_kill(consumer.name, victim.name)

    def _check_player_collisions(self, current_time: float):
        """Handle player vs player consume and bounce collisions."""
        players_list = list(self.players.values())
        for i, player1 in enumerate(players_list):
            if not player1.alive:
                continue
            for player2 in players_list[i+1:]:
                if not player2.alive:
                    continue

                if player1.has_protection(current_time) or player2.has_protection(current_time):
                    continue

                dx = player1.x - player2.x
                dy = player1.y - player2.y
                combined = player1.radius + player2.radius
                dist_sq = dx * dx + dy * dy

                if dist_sq < combined * combined:
                    distance = math.sqrt(dist_sq)
                    if player1.radius > player2.radius * CONSUME_RATIO:
                        self._consume_player(player1, player2)
                    elif player2.radius > player1.radius * CONSUME_RATIO:
                        self._consume_player(player2, player1)
                    elif distance > 0:
                        overlap = (player1.radius + player2.radius - distance) / 2
                        player1.x += (dx / distance) * overlap
                        player1.y += (dy / distance) * overlap
                        player2.x -= (dx / distance) * overlap
                        player2.y -= (dy / distance) * overlap

    def _update_projectiles(self, current_time: float):
        """Move projectiles and handle wall/player hit detection."""
        projectiles_to_remove = []
        for proj_id, proj in self.projectiles.items():
            # Homing tracking - continuous proximity-based re-acquisition
            if isinstance(proj, HomingMissile):
                # Check if current target is still valid
                target = self.players.get(proj.target_id) if proj.target_id else None
                if target and (not target.alive or target.has_protection(current_time)):
                    target = None
                    proj.target_id = ""

                # Re-acquire nearest enemy if no valid target
                if not target:
                    nearest = None
                    min_dist_sq = HOMING_REACQUIRE_RANGE * HOMING_REACQUIRE_RANGE
                    for p in self.players.values():
                        if not p.alive or p.id == proj.owner_id or p.has_protection(current_time):
                            continue
                        pdx = p.x - proj.x
                        pdy = p.y - proj.y
                        d_sq = pdx * pdx + pdy * pdy
                        if d_sq < min_dist_sq:
                            # Check line-of-sight (walls block lock-on)
                            if not self._line_blocked_by_wall(proj.x, proj.y, p.x, p.y):
                                min_dist_sq = d_sq
                                nearest = p
                    if nearest:
                        proj.target_id = nearest.id
                        target = nearest

                # Steer toward target
                if target:
                    # Check line-of-sight is still clear
                    if self._line_blocked_by_wall(proj.x, proj.y, target.x, target.y):
                        proj.target_id = ""
                    else:
                        dx = target.x - proj.x
                        dy = target.y - proj.y
                        dist = math.sqrt(dx * dx + dy * dy)
                        if dist > 1:
                            target_dx = dx / dist
                            target_dy = dy / dist
                            proj.dx += (target_dx - proj.dx) * proj.tracking_strength
                            proj.dy += (target_dy - proj.dy) * proj.tracking_strength
                            mag = math.sqrt(proj.dx * proj.dx + proj.dy * proj.dy)
                            if mag > 0:
                                proj.dx /= mag
                                proj.dy /= mag

            # Move projectile (homing uses acceleration ramp)
            if isinstance(proj, HomingMissile):
                age = current_time - proj.created_at
                ramp = min(1.0, HOMING_MISSILE_INITIAL_SPEED_RATIO + (1.0 - HOMING_MISSILE_INITIAL_SPEED_RATIO) * (age / HOMING_MISSILE_RAMP_TIME))
                speed = proj.speed * ramp
            else:
                speed = PROJECTILE_SPEED
            proj.x += proj.dx * speed
            proj.y += proj.dy * speed

            if current_time - proj.created_at > proj.lifetime:
                projectiles_to_remove.append(proj_id)
                continue
            if proj.x < 0 or proj.x > WORLD_WIDTH or proj.y < 0 or proj.y > WORLD_HEIGHT:
                projectiles_to_remove.append(proj_id)
                continue

            if self._projectile_hit_wall(proj):
                projectiles_to_remove.append(proj_id)
                continue

            if self._projectile_hit_player(proj, current_time):
                projectiles_to_remove.append(proj_id)

        for proj_id in projectiles_to_remove:
            if proj_id in self.projectiles:
                del self.projectiles[proj_id]

    def _line_blocked_by_wall(self, x1: float, y1: float, x2: float, y2: float) -> bool:
        """Check if a line segment from (x1,y1) to (x2,y2) intersects any wall (Liang-Barsky)."""
        dx = x2 - x1
        dy = y2 - y1
        for wall in self.walls.values():
            p = [-dx, dx, -dy, dy]
            q = [x1 - wall.x, wall.x + wall.width - x1, y1 - wall.y, wall.y + wall.height - y1]
            t_min, t_max = 0.0, 1.0
            valid = True
            for i in range(4):
                if p[i] == 0:
                    if q[i] < 0:
                        valid = False
                        break
                else:
                    t = q[i] / p[i]
                    if p[i] < 0:
                        t_min = max(t_min, t)
                    else:
                        t_max = min(t_max, t)
                    if t_min > t_max:
                        valid = False
                        break
            if valid:
                return True
        return False

    def _projectile_hit_wall(self, proj) -> bool:
        for wall in self.walls.values():
            closest_x = max(wall.x, min(proj.x, wall.x + wall.width))
            closest_y = max(wall.y, min(proj.y, wall.y + wall.height))
            dist_x = proj.x - closest_x
            dist_y = proj.y - closest_y
            dist = math.sqrt(dist_x * dist_x + dist_y * dist_y)
            if dist < proj.radius:
                return True
        return False

    def _projectile_hit_player(self, proj, current_time: float) -> bool:
        for player in self.players.values():
            if not player.alive or player.id == proj.owner_id or player.has_protection(current_time):
                continue
            dx = player.x - proj.x
            dy = player.y - proj.y
            combined = player.radius + proj.radius
            if dx * dx + dy * dy < combined * combined:
                damage = HOMING_MISSILE_DAMAGE if isinstance(proj, HomingMissile) else PROJECTILE_DAMAGE
                player.radius = max(MIN_RADIUS, player.radius - damage)
                if player.radius <= MIN_RADIUS:
                    shooter = self.players.get(proj.owner_id)
                    if shooter and shooter.alive and shooter.radius > player.radius * CONSUME_RATIO:
                        player.alive = False
                        shooter.score += KILL_BASE_SCORE + int(player.score * KILL_SCORE_RATIO)
                        player.score = 0
                        self.add_kill(shooter.name, player.name)
                return True
        return False

    def _update_mines(self, current_time: float):
        """Update mine state and check for proximity triggers."""
        mines_to_remove = []
        for mine_id, mine in self.mines.items():
            if current_time < mine.armed_at:
                continue

            for player in self.players.values():
                if not player.alive or player.id == mine.owner_id:
                    continue
                dx = player.x - mine.x
                dy = player.y - mine.y
                dist_sq = dx * dx + dy * dy

                if dist_sq < MINE_PROXIMITY_TRIGGER * MINE_PROXIMITY_TRIGGER:
                    self._detonate_mine(mine, current_time)
                    mines_to_remove.append(mine_id)
                    break

        for mine_id in mines_to_remove:
            owner_id = self.mines[mine_id].owner_id
            del self.mines[mine_id]
            if owner_id in self.players:
                self.players[owner_id].mines_placed -= 1

    def _detonate_mine(self, mine: Mine, current_time: float):
        """Detonate a mine, damaging nearby players."""
        for player in self.players.values():
            if not player.alive or player.has_protection(current_time):
                continue
            dx = player.x - mine.x
            dy = player.y - mine.y
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < MINE_BLAST_RADIUS:
                damage_factor = 1.0 - (dist / MINE_BLAST_RADIUS) * 0.5
                player.radius = max(MIN_RADIUS, player.radius - MINE_DAMAGE * damage_factor)

                if dist > 0:
                    knockback = 40 * damage_factor
                    player.x += (dx / dist) * knockback
                    player.y += (dy / dist) * knockback

                if player.radius <= MIN_RADIUS:
                    player.alive = False
                    player.score = 0
                    owner = self.players.get(mine.owner_id)
                    if owner:
                        self.add_kill(owner.name, player.name)

    def _update_critical_mass(self, current_time: float):
        """Handle critical mass timer and explosion."""
        for player in self.players.values():
            if not player.alive:
                continue
            if player.radius >= CRITICAL_MASS_THRESHOLD:
                if player.critical_mass_start == 0:
                    player.critical_mass_start = current_time
                elif current_time - player.critical_mass_start >= CRITICAL_MASS_TIMER:
                    player.radius = INITIAL_RADIUS
                    player.score = max(0, player.score // 2)
                    player.critical_mass_start = 0
                    self.add_kill(player.name, f"{player.name} (exploded)")
            else:
                player.critical_mass_start = 0

    def _update_powerups(self, current_time: float):
        """Handle power-up expiry and magnet pull effect."""
        for player in self.players.values():
            if player.active_powerup and current_time >= player.powerup_until:
                player.active_powerup = ""
                player.powerup_until = 0

        magnet_energy_moved = False
        magnet_golden_moved = False
        for player in self.players.values():
            if not player.alive or player.active_powerup != "magnet" or current_time >= player.powerup_until:
                continue
            range_sq = MAGNET_RANGE * MAGNET_RANGE
            for orb in self.energy_orbs.values():
                dx = player.x - orb.x
                dy = player.y - orb.y
                dist_sq = dx * dx + dy * dy
                if dist_sq < range_sq and dist_sq > 1:
                    dist = math.sqrt(dist_sq)
                    orb.x += (dx / dist) * MAGNET_STRENGTH
                    orb.y += (dy / dist) * MAGNET_STRENGTH
                    magnet_energy_moved = True
            for orb in self.golden_orbs.values():
                dx = player.x - orb.x
                dy = player.y - orb.y
                dist_sq = dx * dx + dy * dy
                if dist_sq < range_sq and dist_sq > 1:
                    dist = math.sqrt(dist_sq)
                    orb.x += (dx / dist) * MAGNET_STRENGTH
                    orb.y += (dy / dist) * MAGNET_STRENGTH
                    magnet_golden_moved = True
        if magnet_energy_moved:
            self._energy_orbs_cache = None
        if magnet_golden_moved:
            self._golden_orbs_cache = None

    def _update_trail_segments(self, current_time: float):
        """Place new trail segments for active trail players, expire old ones, check collisions."""
        # Place new segments for players with active trail power-up
        for player in self.players.values():
            if not player.alive:
                continue
            if player.active_powerup != "trail" or current_time >= player.powerup_until:
                continue
            if current_time - player.trail_last_segment_time >= TRAIL_SEGMENT_INTERVAL:
                self.trail_segments.append({
                    "x": player.x,
                    "y": player.y,
                    "owner_id": player.id,
                    "color": player.color,
                    "expires_at": current_time + TRAIL_SEGMENT_LIFETIME,
                })
                player.trail_last_segment_time = current_time

        # Expire old segments and check collisions
        segments_to_remove = []
        for i, seg in enumerate(self.trail_segments):
            if current_time >= seg["expires_at"]:
                segments_to_remove.append(i)
                continue
            for player in self.players.values():
                if not player.alive or player.id == seg["owner_id"] or player.has_protection(current_time):
                    continue
                dx = player.x - seg["x"]
                dy = player.y - seg["y"]
                combined = player.radius + TRAIL_SEGMENT_RADIUS
                if dx * dx + dy * dy < combined * combined:
                    player.radius = max(MIN_RADIUS, player.radius - TRAIL_DAMAGE)
                    if player.radius <= MIN_RADIUS:
                        player.alive = False
                        player.score = 0
                        owner = self.players.get(seg["owner_id"])
                        if owner:
                            self.add_kill(owner.name, player.name)
                    segments_to_remove.append(i)
                    break

        for i in reversed(sorted(set(segments_to_remove))):
            self.trail_segments.pop(i)

    def _update_wormhole_portals(self, current_time: float):
        """Move traveling portals, check player collisions (owner teleports, enemy takes damage)."""
        portals_to_remove = []
        for portal_id, portal in self.wormhole_portals.items():
            # Move if still traveling
            if portal.traveling:
                step = min(WORMHOLE_SPEED, portal.travel_remaining)
                portal.x += portal.dx * step
                portal.y += portal.dy * step
                portal.travel_remaining -= step
                if portal.travel_remaining <= 0:
                    portal.traveling = False

            # Expire by lifetime
            if current_time - portal.created_at > WORMHOLE_LIFETIME:
                portals_to_remove.append(portal_id)
                continue

            # Check collisions with players
            hit = False
            for player in self.players.values():
                if not player.alive:
                    continue
                dx = player.x - portal.x
                dy = player.y - portal.y
                combined = player.radius + WORMHOLE_RADIUS
                if dx * dx + dy * dy >= combined * combined:
                    continue

                if player.id == portal.owner_id:
                    # Owner enters - teleport to random exit location
                    for _ in range(100):
                        ex = random.uniform(50, WORLD_WIDTH - 50)
                        ey = random.uniform(50, WORLD_HEIGHT - 50)
                        dist_sq = (ex - portal.x) ** 2 + (ey - portal.y) ** 2
                        if dist_sq >= WORMHOLE_MIN_EXIT_DIST ** 2:
                            # Check not inside a wall
                            inside_wall = False
                            for wall in self.walls.values():
                                if (wall.x <= ex <= wall.x + wall.width and
                                        wall.y <= ey <= wall.y + wall.height):
                                    inside_wall = True
                                    break
                            if not inside_wall:
                                player.x = ex
                                player.y = ey
                                player.invincible_until = current_time + 1.0  # brief post-exit grace
                                break
                    hit = True
                else:
                    # Enemy enters - take damage, portal closes
                    if not player.has_protection(current_time):
                        owner = self.players.get(portal.owner_id)
                        player.radius = max(MIN_RADIUS, player.radius - WORMHOLE_DAMAGE)
                        if player.radius <= MIN_RADIUS:
                            player.alive = False
                            player.score = 0
                            if owner:
                                self.add_kill(owner.name, player.name)
                    hit = True

                if hit:
                    portals_to_remove.append(portal_id)
                    break

        for portal_id in portals_to_remove:
            if portal_id in self.wormhole_portals:
                del self.wormhole_portals[portal_id]

    def tick(self):
        """Update game state for one tick."""
        current_time = time.time()
        self._move_players(current_time)
        self._check_orb_collisions(current_time)
        self._collect_mine_pickups(current_time)
        self._process_mine_pickup_respawns(current_time)
        self._check_player_collisions(current_time)
        self._update_projectiles(current_time)
        self._update_mines(current_time)
        self._update_critical_mass(current_time)
        self._update_powerups(current_time)
        self._update_trail_segments(current_time)
        self._update_wormhole_portals(current_time)
        self.disaster_manager.tick(current_time)
        for player in self.players.values():
            if player.score > player.peak_score:
                player.peak_score = player.score
            if player.played_with_others and player.score > player.peak_score_with_others:
                player.peak_score_with_others = player.score

    def get_static_data(self) -> dict:
        """Get static data that only needs to be sent once (on welcome)."""
        if self._walls_cache is None:
            self._walls_cache = [w.to_dict() for w in self.walls.values()]
        return {
            "walls": self._walls_cache,
            "world": {"width": WORLD_WIDTH, "height": WORLD_HEIGHT}
        }

    def build_shared_state(self, current_time: float) -> dict:
        """Build the shared portion of game state (called once per tick)."""
        # Use cached orb lists when available
        if self._energy_orbs_cache is None:
            self._energy_orbs_cache = [o.to_dict() for o in self.energy_orbs.values()]
        if self._spike_orbs_cache is None:
            self._spike_orbs_cache = [o.to_dict() for o in self.spike_orbs.values()]
        if self._golden_orbs_cache is None:
            self._golden_orbs_cache = [o.to_dict() for o in self.golden_orbs.values()]
        if self._powerup_orbs_cache is None:
            self._powerup_orbs_cache = [o.to_dict() for o in self.powerup_orbs.values()]
        if self._mine_pickups_cache is None:
            self._mine_pickups_cache = [o.to_dict() for o in self.mine_pickups.values()]

        state = {
            "type": "state",
            "players": [p.to_dict(current_time) for p in self.players.values()],
            "energy_orbs": self._energy_orbs_cache,
            "spike_orbs": self._spike_orbs_cache,
            "golden_orbs": self._golden_orbs_cache,
            "powerup_orbs": self._powerup_orbs_cache,
            "mine_pickups": self._mine_pickups_cache,
            "mines": [m.to_dict() for m in self.mines.values()],
            "projectiles": [p.to_dict() for p in self.projectiles.values()],
            "wormhole_portals": [p.to_dict() for p in self.wormhole_portals.values()],
            "trail_segments": [{"x": round(s["x"], 1), "y": round(s["y"], 1), "color": s["color"],
                                 "ttl": round(s["expires_at"] - current_time, 2)} for s in self.trail_segments],
            "kill_feed": self.get_kill_feed(),
            "leaderboard": self.get_leaderboard(),
            "disaster": self.disaster_manager.get_state(current_time)
        }

        # Include walls when they've moved (earthquake)
        if self._walls_dirty:
            if self._walls_cache is None:
                self._walls_cache = [w.to_dict() for w in self.walls.values()]
            state["walls"] = self._walls_cache
            # Clear dirty flag once cache is built (will be set again next tick if still moving)
            self._walls_dirty = False

        return state

    def get_leaderboard(self) -> list:
        """Get top 10 players by score (cached for performance)."""
        current_time = time.time()
        if current_time - self._leaderboard_update_time >= self._leaderboard_cache_duration:
            sorted_players = sorted(
                [p for p in self.players.values() if p.alive],
                key=lambda p: p.score,
                reverse=True
            )[:10]
            self._cached_leaderboard = [{"name": p.name, "score": p.score} for p in sorted_players]
            self._leaderboard_update_time = current_time
        return self._cached_leaderboard


class ChallengeGame(GameState):
    """Isolated single-player challenge game instance."""

    def __init__(self, player_id: str):
        super().__init__()
        self.player_id = player_id
        self.challenge_start_time = time.time()
        self.turrets = [
            MissileTurret(
                id=f"turret_{i}",
                x=float(x),
                y=float(y),
                active=(i < TURRET_INITIAL_ACTIVE),
                # Stagger first shots so all turrets don't fire simultaneously
                last_fired=self.challenge_start_time - random.uniform(0.0, 2.0),
            )
            for i, (x, y) in enumerate(TURRET_POSITIONS)
        ]
        self._current_fire_interval = TURRET_FIRE_INTERVAL_START
        self._wall_respawns: list = []   # list of (respawn_time, width, height)
        self._wall_respawn_counter: int = 0

    def get_elapsed(self) -> float:
        return time.time() - self.challenge_start_time

    def get_wave(self) -> int:
        return 1 + int(self.get_elapsed() / TURRET_ACTIVATE_INTERVAL)

    def tick(self):
        super().tick()
        current_time = time.time()
        elapsed = self.get_elapsed()
        self._update_turret_difficulty(elapsed)
        self._fire_turret_missiles(current_time)
        self._check_projectile_collisions()
        self._update_wall_respawns(current_time)

    def _update_turret_difficulty(self, elapsed: float):
        turrets_active = min(len(self.turrets), TURRET_INITIAL_ACTIVE + int(elapsed / TURRET_ACTIVATE_INTERVAL))
        for i, turret in enumerate(self.turrets):
            turret.active = i < turrets_active
        reduction = min(
            TURRET_FIRE_INTERVAL_START - TURRET_FIRE_INTERVAL_MIN,
            (elapsed / TURRET_ACTIVATE_INTERVAL) * TURRET_FIRE_INTERVAL_REDUCTION
        )
        self._current_fire_interval = TURRET_FIRE_INTERVAL_START - reduction

    def _fire_turret_missiles(self, current_time: float):
        player = self.players.get(self.player_id)
        if not player or not player.alive:
            return
        for turret in self.turrets:
            if not turret.active:
                continue
            if current_time - turret.last_fired >= self._current_fire_interval:
                turret.last_fired = current_time
                self._spawn_turret_missile(turret, player, current_time)

    def _spawn_turret_missile(self, turret: MissileTurret, player: Player, current_time: float):
        dx = player.x - turret.x
        dy = player.y - turret.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1:
            return
        ndx, ndy = dx / dist, dy / dist
        self.projectile_counter += 1
        proj_id = f"tmissile_{self.projectile_counter}"
        self.projectiles[proj_id] = HomingMissile(
            id=proj_id,
            owner_id=turret.id,
            x=turret.x + ndx * 30,
            y=turret.y + ndy * 30,
            dx=ndx,
            dy=ndy,
            color=TURRET_MISSILE_COLOR,
            created_at=current_time,
            lifetime=TURRET_MISSILE_LIFETIME,
            radius=8,
            target_id=player.id,
            speed=TURRET_MISSILE_SPEED,
            tracking_strength=TURRET_MISSILE_TRACKING,
        )

    def _check_projectile_collisions(self):
        """Player-fired projectiles can destroy incoming turret missiles."""
        player_projs = {pid: p for pid, p in self.projectiles.items()
                        if p.owner_id == self.player_id}
        turret_missiles = {pid: p for pid, p in self.projectiles.items()
                           if p.owner_id.startswith("turret_")}
        to_remove = set()
        for ppid, pp in player_projs.items():
            if ppid in to_remove:
                continue
            for tmid, tm in turret_missiles.items():
                if tmid in to_remove:
                    continue
                dx = pp.x - tm.x
                dy = pp.y - tm.y
                combined = pp.radius + tm.radius
                if dx * dx + dy * dy < combined * combined:
                    to_remove.add(ppid)
                    to_remove.add(tmid)
                    break
        for proj_id in to_remove:
            if proj_id in self.projectiles:
                del self.projectiles[proj_id]

    def _projectile_hit_wall(self, proj) -> bool:
        """Override: turret missiles damage walls (3 hits to destroy). Player shots pass through walls."""
        if not proj.owner_id.startswith("turret_"):
            return False
        for wall_id, wall in list(self.walls.items()):
            closest_x = max(wall.x, min(proj.x, wall.x + wall.width))
            closest_y = max(wall.y, min(proj.y, wall.y + wall.height))
            dist_x = proj.x - closest_x
            dist_y = proj.y - closest_y
            if math.sqrt(dist_x * dist_x + dist_y * dist_y) < proj.radius:
                wall.hp -= 1
                if wall.hp <= 0:
                    del self.walls[wall_id]
                    self._wall_respawns.append((time.time() + 10.0, wall.width, wall.height))
                self._walls_cache = None
                self._walls_dirty = True
                return True
        return False

    def _update_wall_respawns(self, current_time: float):
        """Respawn destroyed walls as single rectangles at random positions."""
        remaining = []
        spawned = False
        for respawn_time, width, height in self._wall_respawns:
            if current_time >= respawn_time:
                x = random.uniform(200, WORLD_WIDTH - 200 - width)
                y = random.uniform(200, WORLD_HEIGHT - 200 - height)
                self._wall_respawn_counter += 1
                wall_id = f"wall_r{self._wall_respawn_counter}"
                self.walls[wall_id] = Wall(id=wall_id, x=x, y=y, width=width, height=height, hp=3, max_hp=3)
                spawned = True
            else:
                remaining.append((respawn_time, width, height))
        self._wall_respawns = remaining
        if spawned:
            self._walls_cache = None
            self._walls_dirty = True

    def _projectile_hit_player(self, proj, current_time: float) -> bool:
        """Override: turret missiles kill the player when they drop to MIN_RADIUS."""
        for player in self.players.values():
            if not player.alive or player.id == proj.owner_id or player.has_protection(current_time):
                continue
            dx = player.x - proj.x
            dy = player.y - proj.y
            combined = player.radius + proj.radius
            if dx * dx + dy * dy < combined * combined:
                damage = HOMING_MISSILE_DAMAGE if isinstance(proj, HomingMissile) else PROJECTILE_DAMAGE
                player.radius = max(MIN_RADIUS, player.radius - damage)
                if player.radius <= MIN_RADIUS:
                    if proj.owner_id.startswith("turret_"):
                        player.alive = False
                        player.score = 0
                        self.add_kill("Turret", player.name)
                    else:
                        shooter = self.players.get(proj.owner_id)
                        if shooter and shooter.alive and shooter.radius > player.radius * CONSUME_RATIO:
                            player.alive = False
                            shooter.score += KILL_BASE_SCORE + int(player.score * KILL_SCORE_RATIO)
                            player.score = 0
                            self.add_kill(shooter.name, player.name)
                return True
        return False


class RallyRunGame(GameState):
    """Isolated single-player Nitro Orb rally challenge."""

    def __init__(self, player_id: str):
        super().__init__()
        self.player_id = player_id
        self.challenge_start_time = time.time()
        # Lap tracking
        self.lap_count = 0
        self.lap_start_time: Optional[float] = None   # resets each lap for HUD display
        self.run_start_time: Optional[float] = None   # set on first gate, never reset
        self.final_time: Optional[float] = None       # set only when all laps complete
        self.checkpoint_index = 0
        self.total_checkpoints = len(RALLY_CHECKPOINT_POSITIONS)
        self._escalation_mine_counter = 0
        self.decorative_turrets: list = []
        self.countdown_end = time.time() + 3.0
        # Clear normal world populated by parent __init__
        self.energy_orbs.clear()
        self.spike_orbs.clear()
        self.golden_orbs.clear()
        self.powerup_orbs.clear()
        self.mine_pickups.clear()
        self.walls.clear()
        self._energy_orbs_cache = []
        self._spike_orbs_cache = []
        self._powerup_orbs_cache = []
        self._mine_pickups_cache = []
        self._walls_cache = []
        self._walls_dirty = False
        # Build track
        self._spawn_barrier_mines()
        self._spawn_checkpoint_orbs()
        self._spawn_decorative_elements()

    def _spawn_barrier_mines(self):
        for i, (x, y) in enumerate(RALLY_BARRIER_POSITIONS):
            mine_id = f"barrier_{i}"
            self.mines[mine_id] = Mine(
                id=mine_id, owner_id="barrier",
                x=x, y=y, armed_at=0.0, color="#cc2200", radius=15,
            )

    def _spawn_checkpoint_orbs(self):
        i = self.checkpoint_index
        if i >= self.total_checkpoints:
            return
        x, y = RALLY_CHECKPOINT_POSITIONS[i]
        orb_id = f"checkpoint_{i}"
        self.golden_counter += 1
        self.golden_orbs[orb_id] = GoldenOrb(id=orb_id, x=x, y=y)
        self._golden_orbs_cache = None

    def _find_off_track_pos(self, margin: float = 80) -> Optional[tuple]:
        """Find a random world position safely outside the track barriers."""
        min_clear = RALLY_TRACK_HALF_WIDTH + margin
        for _ in range(40):
            x = random.uniform(150, WORLD_WIDTH - 150)
            y = random.uniform(150, WORLD_HEIGHT - 150)
            if _dist_to_track(x, y) > min_clear:
                return (x, y)
        return None

    def _spawn_decorative_elements(self):
        """Scatter game elements in non-track areas for visual richness."""
        # Energy orbs
        for _ in range(60):
            pos = self._find_off_track_pos(margin=60)
            if pos:
                self.orb_counter += 1
                oid = f"orb_{self.orb_counter}"
                self.energy_orbs[oid] = EnergyOrb(id=oid, x=pos[0], y=pos[1])
        self._energy_orbs_cache = None

        # Spike orbs
        for _ in range(20):
            pos = self._find_off_track_pos(margin=60)
            if pos:
                self.spike_counter += 1
                sid = f"spike_{self.spike_counter}"
                self.spike_orbs[sid] = SpikeOrb(id=sid, x=pos[0], y=pos[1])
        self._spike_orbs_cache = None

        # Obstacle walls (infield / outfield)
        wall_specs = [(200, 40), (40, 200), (160, 30), (30, 160), (120, 120), (240, 30)]
        for w, h in wall_specs:
            pos = self._find_off_track_pos(margin=max(w, h) + 80)
            if pos:
                self.wall_counter += 1
                wid = f"wall_d{self.wall_counter}"
                self.walls[wid] = Wall(
                    id=wid, x=pos[0] - w / 2, y=pos[1] - h / 2,
                    width=w, height=h, hp=3, max_hp=3,
                )
        self._walls_cache = None
        self._walls_dirty = True

        # Decorative (inactive) turret emplacements
        turret_candidates = [
            (2100, 1600),   # upper infield
            (2600, 2900),   # centre infield
            (1300, 2700),   # left infield
            (300,  300),    # far top-left corner
            (4750, 4750),   # far bottom-right corner
        ]
        for i, (tx, ty) in enumerate(turret_candidates):
            if _dist_to_track(tx, ty) > RALLY_TRACK_HALF_WIDTH + 150:
                self.decorative_turrets.append(
                    MissileTurret(id=f"deco_{i}", x=float(tx), y=float(ty), active=False)
                )

    def _collect_energy_orbs(self):
        """Override: decorative only - no collection or respawn."""
        pass

    def _collect_spike_orbs(self, current_time: float):
        """Override: decorative only - no damage or respawn."""
        pass

    def activate_boost(self, player_id: str):
        """Override: no cooldown, no mass cost - boost any time."""
        player = self.players.get(player_id)
        if not player or not player.alive:
            return
        player.boost_active_until = time.time() + BOOST_DURATION
        player.boost_cooldown_until = 0  # immediately available again

    def add_rally_player(self, player_id: str, name: str, websocket) -> "Player":
        player = self.add_player(player_id, name, websocket)
        player.radius = RALLY_PLAYER_RADIUS
        player.speed_override = RALLY_PLAYER_SPEED
        sx, sy = RALLY_TRACK_WAYPOINTS[0]
        player.x, player.y = float(sx), float(sy)
        player.target_x, player.target_y = float(sx), float(sy)
        return player

    def tick(self):
        player = self.players.get(self.player_id)
        if player and time.time() < self.countdown_end:
            sx, sy = RALLY_TRACK_WAYPOINTS[0]
            player.target_x = float(sx)
            player.target_y = float(sy)
        super().tick()
        player = self.players.get(self.player_id)
        if player and player.alive:
            player.radius = RALLY_PLAYER_RADIUS  # lock size: no shrink, no growth
            self._check_checkpoints(player)

    def _check_checkpoints(self, player):
        orb_id = f"checkpoint_{self.checkpoint_index}"
        orb = self.golden_orbs.get(orb_id)
        if not orb:
            return
        dx, dy = player.x - orb.x, player.y - orb.y
        collect_sq = (player.radius + orb.radius + 10) ** 2
        if dx * dx + dy * dy < collect_sq:
            del self.golden_orbs[orb_id]
            self._golden_orbs_cache = None
            self.checkpoint_index += 1
            # Start timers on first gate of the very first lap
            if self.checkpoint_index == 1 and self.run_start_time is None:
                now = time.time()
                self.run_start_time = now
                self.lap_start_time = now
            if self.checkpoint_index >= self.total_checkpoints:
                self._complete_lap()
            else:
                self._spawn_checkpoint_orbs()

    def _complete_lap(self):
        now = time.time()
        self.lap_count += 1
        if self.lap_count >= RALLY_MAX_LAPS:
            # All laps done - capture exact finish time, don't reset for another lap
            if self.run_start_time is not None:
                self.final_time = round(now - self.run_start_time, 2)
            return
        self.lap_start_time = now
        self.checkpoint_index = 0
        self._spawn_checkpoint_orbs()
        if self.lap_count <= 5:
            self._add_escalation_mines()

    def _add_escalation_mines(self):
        """Progressively narrow tight corners after each lap."""
        inner_dist = max(100, RALLY_TRACK_HALF_WIDTH - self.lap_count * 15)
        for corner_idx in RALLY_ESCALATION_CORNERS:
            x, y = RALLY_TRACK_WAYPOINTS[corner_idx]
            prev_x, prev_y = RALLY_TRACK_WAYPOINTS[corner_idx - 1]
            dx, dy = x - prev_x, y - prev_y
            seg_len = math.sqrt(dx * dx + dy * dy)
            if seg_len < 1:
                continue
            ux, uy = dx / seg_len, dy / seg_len
            nx, ny = -uy, ux
            for k in range(3):
                t = seg_len - RALLY_MINE_SPACING * (k + 0.5)
                if t < 0:
                    continue
                mx, my = prev_x + ux * t, prev_y + uy * t
                for side in [1, -1]:
                    self._escalation_mine_counter += 1
                    mine_id = f"esc_{self._escalation_mine_counter}"
                    self.mines[mine_id] = Mine(
                        id=mine_id, owner_id="barrier",
                        x=mx + nx * inner_dist * side,
                        y=my + ny * inner_dist * side,
                        armed_at=0.0, color="#990000", radius=15,
                    )

    def _collect_golden_orbs(self):
        """Override: checkpoint orbs give no mass/score - handled by _check_checkpoints."""
        pass

    def _update_trail_segments(self, current_time: float):
        """Override: visual-only trail always active for the rally player - no collision damage."""
        player = self.players.get(self.player_id)
        if player and player.alive:
            if current_time - player.trail_last_segment_time >= TRAIL_SEGMENT_INTERVAL:
                self.trail_segments.append({
                    "x": player.x,
                    "y": player.y,
                    "owner_id": player.id,
                    "color": player.color,
                    "expires_at": current_time + TRAIL_SEGMENT_LIFETIME,
                })
                player.trail_last_segment_time = current_time
        self.trail_segments = [s for s in self.trail_segments if current_time < s["expires_at"]]

    def _update_mines(self, current_time: float):
        """Override: barrier mines rearm after triggering instead of being removed."""
        for mine in self.mines.values():
            if current_time < mine.armed_at:
                continue
            player = self.players.get(self.player_id)
            if not player or not player.alive:
                continue
            dx, dy = player.x - mine.x, player.y - mine.y
            if dx * dx + dy * dy < MINE_PROXIMITY_TRIGGER * MINE_PROXIMITY_TRIGGER:
                self._detonate_mine(mine, current_time)
                mine.armed_at = current_time + BARRIER_MINE_REARM_DELAY

    def get_rally_state(self) -> dict:
        now = time.time()
        lap_time = round(now - self.lap_start_time, 1) if self.lap_start_time is not None else None
        total_time = round(now - self.run_start_time, 1) if self.run_start_time is not None else None
        return {
            "type": "rally_run",
            "lap": min(self.lap_count + 1, RALLY_MAX_LAPS),
            "max_laps": RALLY_MAX_LAPS,
            "lap_time": lap_time,
            "total_time": total_time,
            "checkpoint": self.checkpoint_index,
            "total_checkpoints": self.total_checkpoints,
            "countdown": round(max(0.0, self.countdown_end - now), 2),
        }

    def is_run_complete(self) -> bool:
        return self.lap_count >= RALLY_MAX_LAPS


class BossHuntGame(GameState):
    """Isolated single-player Hunter Seeker challenge."""

    def __init__(self, player_id: str):
        super().__init__()
        self.player_id = player_id
        self.challenge_start_time = time.time()
        # Spawn boss in a random corner, away from where player starts
        corners = [(400.0, 400.0), (4600.0, 400.0), (400.0, 4600.0), (4600.0, 4600.0)]
        bx, by = random.choice(corners)
        self.boss = BossOrb(id="boss", x=bx, y=by)
        # Shooting phase state
        self._shooting_phase = False
        self._next_phase_change = self.challenge_start_time + BOSS_SHOOT_PHASE_INTERVAL
        self._boss_shoot_cooldown_until = 0.0
        # Precision strike (corner-buster) state
        self._camp_best_dist = float('inf')
        self._camp_start_time = self.challenge_start_time
        self._camp_player_pos = None  # player position when camp timer last reset (set on first tick)
        self._strike_phase = None   # None | "targeting" | "cleared_hot" | "danger_close" | "barrage"
        self._strike_phase_until = 0.0
        self._strike_origin = (0.0, 0.0)
        self._strike_next_shot = 0.0
        self._strike_shots_fired = 0
        self._strike_cooldown_until = 0.0

    def get_elapsed(self) -> float:
        return time.time() - self.challenge_start_time

    # --- Disable mine mechanic for this mode ---

    def spawn_mine_pickups(self):
        pass

    def _collect_mine_pickups(self, current_time: float):
        pass

    def _process_mine_pickup_respawns(self, current_time: float):
        pass

    def _update_mines(self, current_time: float):
        pass

    # --- Restrict powerup pool to relevant types ---

    def _collect_powerup_orbs(self, current_time: float):
        powerups_to_remove = []
        for orb_id, orb in self.powerup_orbs.items():
            player = self.players.get(self.player_id)
            if not player or not player.alive:
                continue
            dx = player.x - orb.x
            dy = player.y - orb.y
            combined = player.radius + orb.radius
            if dx * dx + dy * dy < combined * combined:
                powerup_type = random.choice(BOSS_HUNT_POWERUP_TYPES)
                if powerup_type == "homing_missiles":
                    player.homing_missiles_remaining = HOMING_MISSILES_AMMO
                else:
                    player.active_powerup = powerup_type
                    player.powerup_until = current_time + POWERUP_DURATIONS.get(powerup_type, 5.0)
                powerups_to_remove.append(orb_id)
                break
        if powerups_to_remove:
            for orb_id in powerups_to_remove:
                del self.powerup_orbs[orb_id]
            self._powerup_orbs_cache = None
            for _ in powerups_to_remove:
                self.powerup_respawn_timers.append(current_time + POWERUP_RESPAWN_DELAY)

    # --- Boss shot hit detection: kill player at MIN_RADIUS ---

    def _projectile_hit_player(self, proj, current_time: float) -> bool:
        player = self.players.get(self.player_id)
        if not player or not player.alive or player.has_protection(current_time):
            return False
        if player.id == proj.owner_id:
            return False
        dx = player.x - proj.x
        dy = player.y - proj.y
        combined = player.radius + proj.radius
        if dx * dx + dy * dy < combined * combined:
            damage = HOMING_MISSILE_DAMAGE if isinstance(proj, HomingMissile) else PROJECTILE_DAMAGE
            player.radius = max(MIN_RADIUS, player.radius - damage)
            if player.radius <= MIN_RADIUS and proj.owner_id in ("boss", "strike"):
                player.alive = False
                self.add_kill("Hunter Seeker", player.name)
            return True
        return False

    # --- Boss AI ---

    def _move_boss(self, current_time: float):
        """Move boss toward player with wall repulsion for smooth flow."""
        player = self.players.get(self.player_id)
        if not player or not player.alive:
            return

        elapsed = self.get_elapsed()
        ramp = min(elapsed / BOSS_SPEED_RAMP_DURATION, 1.0)
        speed = BOSS_SPEED_BASE + (BOSS_SPEED_MAX - BOSS_SPEED_BASE) * ramp
        if current_time < self.boss.weakened_until:
            speed *= BOSS_WEAKEN_SPEED_MULT

        # Primary force: toward player
        dx = player.x - self.boss.x
        dy = player.y - self.boss.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1:
            return
        fx = dx / dist
        fy = dy / dist

        # Wall repulsion: push boss away from wall surfaces
        for wall in self.walls.values():
            cx = max(wall.x, min(self.boss.x, wall.x + wall.width))
            cy = max(wall.y, min(self.boss.y, wall.y + wall.height))
            wdx = self.boss.x - cx
            wdy = self.boss.y - cy
            wdist = math.sqrt(wdx * wdx + wdy * wdy)
            if 0 < wdist < BOSS_WALL_REPULSION_RANGE:
                strength = (1.0 - wdist / BOSS_WALL_REPULSION_RANGE) * 2.5
                fx += (wdx / wdist) * strength
                fy += (wdy / wdist) * strength

        # Normalize combined force
        mag = math.sqrt(fx * fx + fy * fy)
        if mag > 0:
            fx /= mag
            fy /= mag

        self.boss.x = max(self.boss.radius, min(WORLD_WIDTH - self.boss.radius,
                                                 self.boss.x + fx * speed))
        self.boss.y = max(self.boss.radius, min(WORLD_HEIGHT - self.boss.radius,
                                                 self.boss.y + fy * speed))

        # Hard wall collision: push boss out of any wall it has entered
        for wall in self.walls.values():
            cx = max(wall.x, min(self.boss.x, wall.x + wall.width))
            cy = max(wall.y, min(self.boss.y, wall.y + wall.height))
            wdx = self.boss.x - cx
            wdy = self.boss.y - cy
            wdist = math.sqrt(wdx * wdx + wdy * wdy)
            if wdist < self.boss.radius:
                if wdist < 0.001:
                    # Boss centre is exactly on the wall edge - push upward as a safe default
                    wdx, wdy, wdist = 0.0, -1.0, 1.0
                overlap = self.boss.radius - wdist
                self.boss.x += (wdx / wdist) * overlap
                self.boss.y += (wdy / wdist) * overlap

    def _check_boss_collision(self, current_time: float):
        """Boss contact-kills the player (boss is always large enough to consume)."""
        player = self.players.get(self.player_id)
        if not player or not player.alive or player.has_protection(current_time):
            return
        dx = player.x - self.boss.x
        dy = player.y - self.boss.y
        combined = player.radius + self.boss.radius
        if dx * dx + dy * dy < combined * combined:
            player.alive = False
            self.add_kill("Hunter Seeker", player.name)

    def _check_player_shots_hit_boss(self, current_time: float):
        """Player projectiles weaken the boss (slow it temporarily)."""
        if self.boss.shielded:
            return  # Boss shield is up - shots bounce off
        projs_to_remove = []
        for proj_id, proj in self.projectiles.items():
            if proj.owner_id != self.player_id:
                continue
            dx = proj.x - self.boss.x
            dy = proj.y - self.boss.y
            combined = proj.radius + self.boss.radius
            if dx * dx + dy * dy < combined * combined:
                self.boss.weakened_until = max(
                    self.boss.weakened_until, current_time + BOSS_WEAKEN_DURATION
                )
                projs_to_remove.append(proj_id)
        for proj_id in projs_to_remove:
            if proj_id in self.projectiles:
                del self.projectiles[proj_id]

    def _update_shooting_phase(self, current_time: float):
        """Manage the boss shooting phase state machine and fire shots."""
        # Phase transitions
        if current_time >= self._next_phase_change:
            if not self._shooting_phase:
                self._shooting_phase = True
                self._next_phase_change = current_time + BOSS_SHOOT_PHASE_DURATION
            else:
                self._shooting_phase = False
                self._next_phase_change = current_time + BOSS_SHOOT_COOLDOWN

        if not self._shooting_phase:
            return

        player = self.players.get(self.player_id)
        if not player or not player.alive:
            return
        if current_time < self._boss_shoot_cooldown_until:
            return

        # Fire a shot at the player
        dx = player.x - self.boss.x
        dy = player.y - self.boss.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1:
            return
        ndx, ndy = dx / dist, dy / dist

        self.projectile_counter += 1
        proj_id = f"bossshot_{self.projectile_counter}"
        self.projectiles[proj_id] = Projectile(
            id=proj_id,
            owner_id="boss",
            x=self.boss.x + ndx * (self.boss.radius + 12),
            y=self.boss.y + ndy * (self.boss.radius + 12),
            dx=ndx,
            dy=ndy,
            color="#ff2200",
            created_at=current_time,
            lifetime=BOSS_SHOT_LIFETIME,
            radius=BOSS_SHOT_RADIUS,
        )
        self._boss_shoot_cooldown_until = current_time + BOSS_SHOOT_FIRE_INTERVAL

    def _fire_strike_shot(self, current_time: float):
        """Fire a single barrage round at the locked strike origin with scatter."""
        tx = self._strike_origin[0] + random.uniform(-STRIKE_SCATTER, STRIKE_SCATTER)
        ty = self._strike_origin[1] + random.uniform(-STRIKE_SCATTER, STRIKE_SCATTER)
        angle = random.uniform(0, 2 * math.pi)
        spawn_dist = random.uniform(1500, 2200)
        sx = max(50.0, min(float(WORLD_WIDTH - 50), tx + math.cos(angle) * spawn_dist))
        sy = max(50.0, min(float(WORLD_HEIGHT - 50), ty + math.sin(angle) * spawn_dist))
        dx, dy = tx - sx, ty - sy
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1:
            return
        ndx, ndy = dx / dist, dy / dist
        self.projectile_counter += 1
        self.projectiles[f"strike_{self.projectile_counter}"] = Projectile(
            id=f"strike_{self.projectile_counter}",
            owner_id="strike",
            x=sx, y=sy, dx=ndx, dy=ndy,
            color="#ff8800",
            created_at=current_time,
            lifetime=STRIKE_SHOT_LIFETIME,
            radius=STRIKE_SHOT_RADIUS,
        )

    def _update_precision_strike(self, current_time: float):
        """Track corner camping and run the 3-phase precision strike sequence."""
        player = self.players.get(self.player_id)
        if not player or not player.alive:
            self._strike_phase = None
            self.boss.shielded = False
            return

        current_dist = math.sqrt((self.boss.x - player.x) ** 2 + (self.boss.y - player.y) ** 2)

        # Advance active strike sequence
        if self._strike_phase is not None:
            if self._strike_phase == "targeting" and current_time >= self._strike_phase_until:
                self._strike_phase = "cleared_hot"
                self._strike_phase_until = current_time + STRIKE_PHASE_DURATION

            elif self._strike_phase == "cleared_hot" and current_time >= self._strike_phase_until:
                self._strike_phase = "danger_close"
                self._strike_phase_until = current_time + STRIKE_PHASE_DURATION
                self.boss.shielded = True

            elif self._strike_phase == "danger_close" and current_time >= self._strike_phase_until:
                self._strike_phase = "barrage"
                self._strike_phase_until = current_time + STRIKE_BARRAGE_SHOTS * STRIKE_BARRAGE_INTERVAL + 0.5
                self._strike_next_shot = current_time
                self._strike_shots_fired = 0

            elif self._strike_phase == "barrage":
                if self._strike_shots_fired < STRIKE_BARRAGE_SHOTS and current_time >= self._strike_next_shot:
                    self._fire_strike_shot(current_time)
                    self._strike_shots_fired += 1
                    self._strike_next_shot = current_time + STRIKE_BARRAGE_INTERVAL
                if current_time >= self._strike_phase_until:
                    self._strike_phase = None
                    self.boss.shielded = False
                    self._strike_cooldown_until = current_time + STRIKE_COOLDOWN
                    self._camp_best_dist = current_dist
                    self._camp_start_time = current_time
                    self._camp_player_pos = (player.x, player.y)
            return

        # Not in a strike - track whether boss is making progress toward player
        if self._camp_player_pos is None:
            self._camp_player_pos = (player.x, player.y)
        player_moved = math.sqrt(
            (player.x - self._camp_player_pos[0]) ** 2 +
            (player.y - self._camp_player_pos[1]) ** 2
        ) > CAMP_PLAYER_MOVE_THRESHOLD

        if current_dist < self._camp_best_dist - CAMP_CLOSE_THRESHOLD or player_moved:
            # Boss closed in, or player is actively roaming - not camping
            self._camp_best_dist = current_dist
            self._camp_start_time = current_time
            self._camp_player_pos = (player.x, player.y)
        elif (current_time - self._camp_start_time >= CAMP_TRIGGER_TIME
              and current_time >= self._strike_cooldown_until):
            # Boss has been blocked and player hasn't moved - initiate strike
            self._strike_origin = (player.x, player.y)
            self._strike_phase = "targeting"
            self._strike_phase_until = current_time + STRIKE_PHASE_DURATION
            self._camp_best_dist = current_dist
            self._camp_start_time = current_time
            self._camp_player_pos = (player.x, player.y)

    def tick(self):
        super().tick()
        current_time = time.time()
        self._move_boss(current_time)
        self._check_boss_collision(current_time)
        self._check_player_shots_hit_boss(current_time)
        self._update_shooting_phase(current_time)
        self._update_precision_strike(current_time)

    def build_shared_state(self, current_time: float) -> dict:
        state = super().build_shared_state(current_time)
        state["boss"] = self.boss.to_dict(current_time)
        return state

    def get_boss_hunt_state(self) -> dict:
        now = time.time()
        return {
            "type": "hunter_seeker",
            "time_survived": round(self.get_elapsed(), 1),
            "boss_weakened": now < self.boss.weakened_until,
            "boss_weakened_remaining": round(max(0.0, self.boss.weakened_until - now), 1),
            "shooting_phase": self._shooting_phase,
            "next_phase_in": round(max(0.0, self._next_phase_change - now), 1),
            "strike_phase": self._strike_phase,
            "strike_target": [round(self._strike_origin[0], 1), round(self._strike_origin[1], 1)]
                              if self._strike_phase else None,
        }


# Global game state
game = GameState()

SCORES_PATH = "/data/scores.json"

# Persistent leaderboards (loaded from SCORES_PATH on startup)
missile_magnet_scores: list = []
rally_run_scores: list = []
all_time_scores: list = []
boss_hunt_scores: list = []


def load_scores():
    global missile_magnet_scores, rally_run_scores, all_time_scores, boss_hunt_scores
    try:
        if os.path.exists(SCORES_PATH):
            with open(SCORES_PATH, "r") as f:
                data = json.load(f)
            missile_magnet_scores = data.get("missile_magnet", [])[:10]
            rally_run_scores = data.get("rally_run", [])[:10]
            all_time_scores = data.get("all_time", [])[:10]
            boss_hunt_scores = data.get("boss_hunt", [])[:10]
            print(f"Scores loaded from {SCORES_PATH}")
        else:
            print(f"No scores file at {SCORES_PATH} - starting fresh")
    except Exception as e:
        print(f"Could not load scores: {e}")


def save_scores():
    try:
        os.makedirs(os.path.dirname(SCORES_PATH), exist_ok=True)
        with open(SCORES_PATH, "w") as f:
            json.dump({
                "missile_magnet": missile_magnet_scores,
                "rally_run": rally_run_scores,
                "all_time": all_time_scores,
                "boss_hunt": boss_hunt_scores,
            }, f, indent=2)
    except Exception as e:
        print(f"Could not save scores: {e}")


def record_challenge_score(name: str, time_survived: float) -> int:
    """Record survival time, personal best only, keep top 10 sorted, return 1-indexed rank."""
    global missile_magnet_scores
    existing = next((s for s in missile_magnet_scores if s["name"] == name), None)
    if existing and existing["time"] >= time_survived:
        return next((i + 1 for i, s in enumerate(missile_magnet_scores) if s["name"] == name), len(missile_magnet_scores))
    missile_magnet_scores = [s for s in missile_magnet_scores if s["name"] != name]
    entry = {"name": name, "time": time_survived}
    missile_magnet_scores.append(entry)
    missile_magnet_scores.sort(key=lambda s: s["time"], reverse=True)
    missile_magnet_scores = missile_magnet_scores[:10]
    save_scores()
    for i, s in enumerate(missile_magnet_scores):
        if s is entry:
            return i + 1
    return len(missile_magnet_scores)


def record_rally_score(name: str, best_lap: float) -> int:
    """Record best lap time, personal best only, keep top 10 ascending, return 1-indexed rank."""
    global rally_run_scores
    existing = next((s for s in rally_run_scores if s["name"] == name), None)
    if existing and existing["time"] <= best_lap:
        return next((i + 1 for i, s in enumerate(rally_run_scores) if s["name"] == name), len(rally_run_scores))
    rally_run_scores = [s for s in rally_run_scores if s["name"] != name]
    entry = {"name": name, "time": best_lap}
    rally_run_scores.append(entry)
    rally_run_scores.sort(key=lambda s: s["time"])  # lowest lap time = best
    rally_run_scores = rally_run_scores[:10]
    save_scores()
    for i, s in enumerate(rally_run_scores):
        if s is entry:
            return i + 1
    return len(rally_run_scores)


def record_boss_hunt_score(name: str, time_survived: float) -> int:
    """Record survival time for Hunter Seeker. Personal best only, top 10 descending, return 1-indexed rank."""
    global boss_hunt_scores
    existing = next((s for s in boss_hunt_scores if s["name"] == name), None)
    if existing and existing["time"] >= time_survived:
        return next((i + 1 for i, s in enumerate(boss_hunt_scores) if s["name"] == name), len(boss_hunt_scores))
    boss_hunt_scores = [s for s in boss_hunt_scores if s["name"] != name]
    entry = {"name": name, "time": time_survived}
    boss_hunt_scores.append(entry)
    boss_hunt_scores.sort(key=lambda s: s["time"], reverse=True)
    boss_hunt_scores = boss_hunt_scores[:10]
    save_scores()
    for i, s in enumerate(boss_hunt_scores):
        if s is entry:
            return i + 1
    return len(boss_hunt_scores)


def record_alltime_score(name: str, score: int):
    """Record a multiplayer peak score, keep top 10 descending. Only updates if new score beats personal best."""
    global all_time_scores
    existing = next((s for s in all_time_scores if s["name"] == name), None)
    if existing and existing["score"] >= score:
        return
    all_time_scores = [s for s in all_time_scores if s["name"] != name]
    all_time_scores.append({"name": name, "score": score})
    all_time_scores.sort(key=lambda s: s["score"], reverse=True)
    all_time_scores = all_time_scores[:10]
    save_scores()


# Load persisted scores on startup
load_scores()

SEND_TIMEOUT = 0.5  # seconds - drop slow clients to prevent buffer buildup

# Rate limiting / connection cap
MAX_CONNECTIONS = 50
RATE_LIMIT_WINDOW = 1.0   # seconds
RATE_LIMIT_MAX_MSGS = 120  # max messages per window (30fps move + up to 60 shoots during rapid_fire)
active_connections = 0


async def broadcast_state():
    """Broadcast game state to all connected players."""
    while True:
        try:
            game.tick()
        except Exception as e:
            print(f"Error in game tick: {e}")
        current_time = time.time()

        # Build shared state once and serialize to JSON once
        shared_state = game.build_shared_state(current_time)
        # Serialize without 'you' - we'll splice it in per player
        shared_json = json.dumps(shared_state)
        # Remove trailing '}' so we can append ',"you":...}'
        shared_json_prefix = shared_json[:-1] + ',"you":'

        # Send state to each player and spectator
        disconnected = []
        for client_id, websocket in list(game.connections.items()):
            try:
                # Check if this is a spectator or player
                if client_id in game.spectators:
                    # Spectators get state without "you" field
                    message = shared_json
                else:
                    # Players get state with their "you" field
                    player = game.players.get(client_id)
                    if not player:
                        continue
                    you_json = json.dumps(player.to_dict(current_time))
                    message = shared_json_prefix + you_json + '}'

                await asyncio.wait_for(
                    websocket.send(message),
                    timeout=SEND_TIMEOUT
                )
            except asyncio.TimeoutError:
                print(f"Client {client_id} send timeout - dropping connection")
                disconnected.append(client_id)
            except ConnectionClosed:
                disconnected.append(client_id)
            except Exception as e:
                print(f"Error sending to {client_id}: {e}")
                disconnected.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            if client_id in game.spectators:
                game.remove_spectator(client_id)
                print(f"Spectator {client_id} disconnected")
            else:
                game.remove_player(client_id)
                print(f"Player {client_id} disconnected")

        await asyncio.sleep(TICK_RATE)


async def run_challenge_loop(player_id: str, challenge_game: ChallengeGame, websocket):
    """Tick a solo challenge game and send state to the player each frame."""
    try:
        while True:
            try:
                challenge_game.tick()
            except Exception as e:
                print(f"Challenge tick error: {e}")

            current_time = time.time()
            player = challenge_game.players.get(player_id)
            if not player:
                break

            elapsed = challenge_game.get_elapsed()
            shared_state = challenge_game.build_shared_state(current_time)
            shared_state["challenge"] = {
                "time_survived": round(elapsed, 1),
                "wave": challenge_game.get_wave(),
                "active_turrets": [t.id for t in challenge_game.turrets if t.active],
                "fire_interval": round(challenge_game._current_fire_interval, 2),
            }

            if not player.alive:
                time_survived = round(elapsed, 1)
                rank = record_challenge_score(player.name, time_survived)
                shared_state["type"] = "challenge_result"
                shared_state["challenge"]["rank"] = rank
                shared_state["challenge"]["total"] = len(missile_magnet_scores)
                shared_state["challenge"]["top_scores"] = missile_magnet_scores[:5]
                try:
                    await asyncio.wait_for(websocket.send(json.dumps(shared_state)), timeout=SEND_TIMEOUT)
                except Exception:
                    pass
                break

            you_json = json.dumps(player.to_dict(current_time))
            shared_json = json.dumps(shared_state)
            message = shared_json[:-1] + ',"you":' + you_json + '}'
            try:
                await asyncio.wait_for(websocket.send(message), timeout=SEND_TIMEOUT)
            except (asyncio.TimeoutError, ConnectionClosed):
                break
            except Exception as e:
                print(f"Challenge send error: {e}")
                break

            await asyncio.sleep(TICK_RATE)
    except asyncio.CancelledError:
        pass


async def run_rally_loop(player_id: str, rally_game: RallyRunGame, websocket):
    """Tick a solo Nitro Orb rally game and send state to the player each frame."""
    try:
        while True:
            try:
                rally_game.tick()
            except Exception as e:
                print(f"Rally tick error: {e}")

            current_time = time.time()
            player = rally_game.players.get(player_id)
            if not player:
                break

            shared_state = rally_game.build_shared_state(current_time)
            shared_state["challenge"] = rally_game.get_rally_state()

            run_over = not player.alive or rally_game.is_run_complete()
            if run_over:
                rank = None
                # Only post a score if all 3 laps were completed - DNF gets nothing
                if rally_game.is_run_complete() and rally_game.final_time is not None:
                    rank = record_rally_score(player.name, rally_game.final_time)
                shared_state["type"] = "challenge_result"
                shared_state["challenge"]["rank"] = rank
                shared_state["challenge"]["total"] = len(rally_run_scores)
                shared_state["challenge"]["top_scores"] = rally_run_scores[:5]
                shared_state["challenge"]["laps_completed"] = rally_game.lap_count
                shared_state["challenge"]["final_time"] = rally_game.final_time
                shared_state["challenge"]["is_complete"] = rally_game.is_run_complete()
                try:
                    await asyncio.wait_for(websocket.send(json.dumps(shared_state)), timeout=SEND_TIMEOUT)
                except Exception:
                    pass
                break

            you_json = json.dumps(player.to_dict(current_time))
            shared_json = json.dumps(shared_state)
            message = shared_json[:-1] + ',"you":' + you_json + '}'
            try:
                await asyncio.wait_for(websocket.send(message), timeout=SEND_TIMEOUT)
            except (asyncio.TimeoutError, ConnectionClosed):
                break
            except Exception as e:
                print(f"Rally send error: {e}")
                break

            await asyncio.sleep(TICK_RATE)
    except asyncio.CancelledError:
        pass


async def run_boss_loop(player_id: str, boss_game: BossHuntGame, websocket):
    """Tick a solo Hunter Seeker game and send state to the player each frame."""
    try:
        while True:
            try:
                boss_game.tick()
            except Exception as e:
                print(f"Boss hunt tick error: {e}")

            current_time = time.time()
            player = boss_game.players.get(player_id)
            if not player:
                break

            shared_state = boss_game.build_shared_state(current_time)
            shared_state["challenge"] = boss_game.get_boss_hunt_state()

            if not player.alive:
                time_survived = round(boss_game.get_elapsed(), 1)
                rank = record_boss_hunt_score(player.name, time_survived)
                shared_state["type"] = "challenge_result"
                shared_state["challenge"]["rank"] = rank
                shared_state["challenge"]["total"] = len(boss_hunt_scores)
                shared_state["challenge"]["top_scores"] = boss_hunt_scores[:5]
                try:
                    await asyncio.wait_for(websocket.send(json.dumps(shared_state)), timeout=SEND_TIMEOUT)
                except Exception:
                    pass
                break

            you_json = json.dumps(player.to_dict(current_time))
            shared_json = json.dumps(shared_state)
            message = shared_json[:-1] + ',"you":' + you_json + '}'
            try:
                await asyncio.wait_for(websocket.send(message), timeout=SEND_TIMEOUT)
            except (asyncio.TimeoutError, ConnectionClosed):
                break
            except Exception as e:
                print(f"Boss hunt send error: {e}")
                break

            await asyncio.sleep(TICK_RATE)
    except asyncio.CancelledError:
        pass


async def handle_client(websocket):
    """Handle a single client connection."""
    global active_connections
    player_id = None

    # Enforce connection cap
    if active_connections >= MAX_CONNECTIONS:
        await websocket.close(1013, "Server full")
        return

    active_connections += 1
    # Rate limiting state for this client
    msg_count = 0
    window_start = time.time()

    try:
        # Wait for join message
        message = await websocket.recv()
        data = json.loads(message)

        if data.get("type") == "join":
            player_id = f"player_{id(websocket)}"
            name = sanitize_name(str(data.get("name", "Anonymous")))
            mode = data.get("mode", "player")  # "player" or "spectate"

            if mode == "spectate":
                # Send welcome message before adding to connections
                # (avoids race with broadcast loop sending state concurrently)
                welcome_data = {
                    "type": "welcome",
                    "player_id": player_id,
                    "mode": "spectate"
                }
                welcome_data.update(game.get_static_data())
                await websocket.send(json.dumps(welcome_data))

                # Now add to game so broadcast loop can send state
                spectator = game.add_spectator(player_id, name, websocket)
                print(f"Spectator {name} ({player_id}) joined!")
            elif mode == "challenge":
                # Solo challenge mode - isolated game instance per player
                challenge_name = data.get("challenge", "missile_magnet")

                if challenge_name == "rally_run":
                    challenge_game = RallyRunGame(player_id)
                    player = challenge_game.add_rally_player(player_id, name, websocket)
                    welcome_data = {
                        "type": "welcome",
                        "player_id": player_id,
                        "mode": "challenge",
                        "challenge": "rally_run",
                        "player": player.to_dict(time.time()),
                        "track_waypoints": list(RALLY_TRACK_WAYPOINTS),
                        "total_checkpoints": challenge_game.total_checkpoints,
                        "turrets": [t.to_dict() for t in challenge_game.decorative_turrets],
                    }
                    welcome_data.update(challenge_game.get_static_data())
                    await websocket.send(json.dumps(welcome_data))
                    print(f"Challenge player {name} ({player_id}) started Nitro Orb!")
                    tick_task = asyncio.create_task(run_rally_loop(player_id, challenge_game, websocket))
                elif challenge_name == "boss_hunt":
                    challenge_game = BossHuntGame(player_id)
                    player = challenge_game.add_player(player_id, name, websocket)
                    welcome_data = {
                        "type": "welcome",
                        "player_id": player_id,
                        "mode": "challenge",
                        "challenge": "boss_hunt",
                        "player": player.to_dict(time.time()),
                        "boss": challenge_game.boss.to_dict(time.time()),
                        "top_scores": boss_hunt_scores[:5],
                    }
                    welcome_data.update(challenge_game.get_static_data())
                    await websocket.send(json.dumps(welcome_data))
                    print(f"Challenge player {name} ({player_id}) started Hunter Seeker!")
                    tick_task = asyncio.create_task(run_boss_loop(player_id, challenge_game, websocket))
                else:
                    challenge_game = ChallengeGame(player_id)
                    player = challenge_game.add_player(player_id, name, websocket)
                    welcome_data = {
                        "type": "welcome",
                        "player_id": player_id,
                        "mode": "challenge",
                        "challenge": challenge_name,
                        "player": player.to_dict(time.time()),
                        "turrets": [t.to_dict() for t in challenge_game.turrets],
                    }
                    welcome_data.update(challenge_game.get_static_data())
                    await websocket.send(json.dumps(welcome_data))
                    print(f"Challenge player {name} ({player_id}) started {challenge_name}!")
                    tick_task = asyncio.create_task(run_challenge_loop(player_id, challenge_game, websocket))
                try:
                    async for message in websocket:
                        now = time.time()
                        if now - window_start >= RATE_LIMIT_WINDOW:
                            msg_count = 0
                            window_start = now
                        msg_count += 1
                        if msg_count > RATE_LIMIT_MAX_MSGS:
                            continue
                        try:
                            data = json.loads(message)
                            msg_type = data.get("type")
                            if msg_type == "move":
                                challenge_game.update_player_target(
                                    player_id,
                                    safe_float(data.get("x", 0)),
                                    safe_float(data.get("y", 0))
                                )
                            elif msg_type == "boost":
                                challenge_game.activate_boost(player_id)
                            elif msg_type == "shoot":
                                challenge_game.shoot(
                                    player_id,
                                    safe_float(data.get("x", 0)),
                                    safe_float(data.get("y", 0))
                                )
                            elif msg_type == "place_mine":
                                challenge_game.place_mine(player_id)
                        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
                            pass
                finally:
                    tick_task.cancel()

            else:
                # Add as player
                player = game.add_player(player_id, name, websocket)

                # Send welcome message with static data
                welcome_data = {
                    "type": "welcome",
                    "player_id": player_id,
                    "player": player.to_dict(time.time())
                }
                welcome_data.update(game.get_static_data())
                await websocket.send(json.dumps(welcome_data))

                print(f"Player {name} ({player_id}) joined!")

            # Handle messages from this client (multiplayer only - challenge has its own loop above)
            if mode not in ("challenge",):
                async for message in websocket:
                    # Rate limiting
                    now = time.time()
                    if now - window_start >= RATE_LIMIT_WINDOW:
                        msg_count = 0
                        window_start = now
                    msg_count += 1
                    if msg_count > RATE_LIMIT_MAX_MSGS:
                        continue  # Silently drop excess messages

                    try:
                        data = json.loads(message)
                        msg_type = data.get("type")

                        if msg_type == "move":
                            game.update_player_target(
                                player_id,
                                safe_float(data.get("x", 0)),
                                safe_float(data.get("y", 0))
                            )

                        elif msg_type == "boost":
                            game.activate_boost(player_id)

                        elif msg_type == "shoot":
                            game.shoot(
                                player_id,
                                safe_float(data.get("x", 0)),
                                safe_float(data.get("y", 0))
                            )

                        elif msg_type == "place_mine":
                            game.place_mine(player_id)

                        elif msg_type == "respawn":
                            game.respawn_player(player_id)

                        elif msg_type == "test_disasters":
                            game.disaster_manager.start_test_cycle(time.time())

                    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
                        pass  # Silently drop malformed messages

    except ConnectionClosed:
        pass
    finally:
        active_connections -= 1
        if player_id:
            # Remove player or spectator (challenge players are not in game.players)
            if player_id in game.spectators:
                game.remove_spectator(player_id)
                print(f"Spectator {player_id} left")
            elif player_id in game.players:
                game.remove_player(player_id)
                print(f"Player {player_id} left")


def get_local_ip():
    """Get the local IP address for LAN play."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


ALLOWED_HTTP_FILES = {"/", "/index.html"}


class SafeHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that only serves the game client file."""

    def do_GET(self):
        # Normalize path and only allow index.html (plus API endpoints)
        path = self.path.split("?")[0].split("#")[0]  # strip query/fragment
        if path == "/api/challenge/scores":
            self._serve_challenge_scores()
            return
        if path == "/api/rally/scores":
            self._serve_rally_scores()
            return
        if path == "/api/alltime/scores":
            self._serve_alltime_scores()
            return
        if path == "/api/boss/scores":
            self._serve_boss_scores()
            return
        if path == "/api/status":
            self._serve_status()
            return
        if path not in ALLOWED_HTTP_FILES:
            self.send_error(404, "Not Found")
            return
        # Always serve index.html
        self.path = "/index.html"
        super().do_GET()

    def _serve_challenge_scores(self):
        data = json.dumps(missile_magnet_scores[:10]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_rally_scores(self):
        data = json.dumps(rally_run_scores[:10]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_boss_scores(self):
        data = json.dumps(boss_hunt_scores[:10]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_alltime_scores(self):
        data = json.dumps(all_time_scores[:10]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_status(self):
        data = json.dumps({"players": len(game.players)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):
        path = self.path.split("?")[0].split("#")[0]
        if path not in ALLOWED_HTTP_FILES:
            self.send_error(404, "Not Found")
            return
        self.path = "/index.html"
        super().do_HEAD()

    def log_message(self, format, *args):
        pass  # Suppress routine request logs

    def log_error(self, format, *args):
        # Keep error logging for visibility into abuse attempts
        print(f"[HTTP] {self.client_address[0]} - {format % args}")


def start_http_server(port=8080):
    """Start a threaded HTTP server to serve the game files."""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Use ThreadingHTTPServer to handle multiple connections
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", port), SafeHTTPHandler)
    httpd.serve_forever()


async def main():
    """Start the game server."""
    local_ip = get_local_ip()

    # Start HTTP server in a background thread
    http_thread = threading.Thread(target=start_http_server, args=(8080,), daemon=True)
    http_thread.start()

    print("=" * 50)
    print("  ORB ARENA - Multiplayer Game Server")
    print("=" * 50)
    print(f"  World Size: {WORLD_WIDTH}x{WORLD_HEIGHT}")
    print(f"  Tick Rate: {int(1/TICK_RATE)} FPS")
    print("=" * 50)
    print(f"\n  PLAY THE GAME:")
    print(f"    Local:  http://localhost:8080")
    print(f"    LAN:    http://{local_ip}:8080")
    print("=" * 50)
    print(f"\n  Share this URL with friends: http://{local_ip}:8080")
    print("\n  Press Ctrl+C to stop the server\n")

    # Start the game loop
    asyncio.create_task(broadcast_state())

    # Allowed origins for WebSocket connections (prevents cross-site hijacking)
    # None = allow all origins (for LAN play without domain setup)
    # Set ALLOWED_ORIGINS env var to restrict in production, e.g. "https://game.yourdomain.com"
    allowed_origins_env = os.environ.get("ALLOWED_ORIGINS")
    if allowed_origins_env:
        ws_origins = [o.strip() for o in allowed_origins_env.split(",")]
        print(f"  WebSocket origins restricted to: {ws_origins}")
    else:
        ws_origins = None  # Allow all for LAN play
        print("  WebSocket origins: unrestricted (set ALLOWED_ORIGINS to restrict)")

    # Start WebSocket server (0.0.0.0 allows LAN connections)
    # Enable permessage-deflate compression to reduce bandwidth
    async with websockets.serve(
        handle_client, "0.0.0.0", 8765,
        compression="deflate",
        origins=ws_origins,
        max_size=1024,  # Max message size: 1KB (game messages are tiny)
    ):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
